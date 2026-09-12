#!/usr/bin/env python3
"""
BrewMaster — a graphical, fast, careful Homebrew upgrader.
--------------------------------------------------------
Author :  Anirban Bagchi

Python 3.10+, standard library only.
"""

from __future__ import annotations

import argparse
import datetime
import fcntl
import fnmatch
import json
import logging
import logging.handlers
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import threading
import time
import unicodedata
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path

VERSION = "3.0.0"

HOME = Path.home()
LOG_PATH = HOME / ".brewmaster.log"
HISTORY_PATH = HOME / ".brewmaster_history.jsonl"
LOCK_PATH = HOME / ".brewmaster.lock"
CONFIG_PATH = HOME / ".brewmasterrc.json"

MAX_BACKUPS = 5
MAX_HISTORY = 500           # history records retained in the JSONL file
LOG_MAX_BYTES = 2 * 1024 * 1024
LOG_BACKUPS = 3

# Package names may come from third-party taps; reject anything outside
# brew's own naming alphabet before passing it to a subprocess.
VALID_PKG = re.compile(r"^[A-Za-z0-9@._+/-]+$")

# Standard install locations (Apple Silicon, Intel). Anything else is
# worth a warning — a brew earlier in PATH is a classic hijack vector.
KNOWN_BREW_PATHS = ("/opt/homebrew/bin/brew", "/usr/local/bin/brew")

# Exit codes for scripting/cron use
EXIT_OK = 0          # success, nothing to do or all upgrades succeeded
EXIT_FATAL = 1       # unrecoverable error (no brew, command not found, ...)
EXIT_FAILURES = 2    # run completed but one or more packages failed
EXIT_OUTDATED = 3    # --check-only found outdated packages (mirrors brew outdated)
EXIT_INTERRUPT = 130 # Ctrl-C / SIGTERM

# Synthetic exit codes used only in audit lines and error paths.
RC_NOT_FOUND = 127
RC_TIMEOUT = 124


# --------------------------------------------------------------------------
# Logging
# --------------------------------------------------------------------------

class _SecureRotatingFileHandler(logging.handlers.RotatingFileHandler):
    """Rotating handler that keeps every file it opens at mode 0600."""

    def _open(self):
        stream = super()._open()
        try:
            os.chmod(self.baseFilename, 0o600)
        except OSError:
            pass
        return stream


_logger = logging.getLogger("brewmaster")
_logger.setLevel(logging.DEBUG)
_logger.propagate = False
_log_enabled = False


def setup_logging() -> bool:
    """Attach the rotating 0600 file handler. Returns False if the log is unusable."""
    global _log_enabled
    try:
        LOG_PATH.touch(mode=0o600, exist_ok=True)
        os.chmod(LOG_PATH, 0o600)
        handler = _SecureRotatingFileHandler(
            LOG_PATH, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUPS
        )
    except OSError:
        _logger.addHandler(logging.NullHandler())
        return False
    handler.setFormatter(
        logging.Formatter("[%(asctime)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    )
    _logger.addHandler(handler)
    _log_enabled = True
    return True


def log(message: str) -> None:
    _logger.info(message)


def audit(cmd: list[str], rc: int, note: str = "") -> None:
    """One AUDIT line per subprocess call: exact command, exit code, duration."""
    suffix = f" {note}" if note else ""
    log(f"AUDIT: {shlex.join(cmd)} -> exit {rc}{suffix}")


# --------------------------------------------------------------------------
# Terminal presentation
# --------------------------------------------------------------------------

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
MAGENTA = "\033[95m"
CYAN = "\033[96m"
GREY = "\033[90m"

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

GLYPHS_UNICODE = {
    "tl": "╭", "tr": "╮", "bl": "╰", "br": "╯",
    "h": "─", "v": "│", "lt": "├", "rt": "┤",
    "tt": "┬", "bt": "┴", "x": "┼",
    "bullet": "•", "arrow": "→",
    "ok": "✔", "fail": "✖", "warn": "⚠", "skip": "↷",
    "pin": "\U0001f4cc", "full": "█", "half": "▒", "empty": "░",
    "beer": "\U0001f37a", "down": "⬇", "up": "⬆", "broom": "\U0001f9f9",
    "clock": "⏱", "note": "\U0001f4dd", "disk": "\U0001f4be", "search": "\U0001f50d",
    "sync": "\U0001f504", "stop": "⏹",
}

GLYPHS_ASCII = {
    "tl": "+", "tr": "+", "bl": "+", "br": "+",
    "h": "-", "v": "|", "lt": "+", "rt": "+",
    "tt": "+", "bt": "+", "x": "+",
    "bullet": "*", "arrow": "->",
    "ok": "OK", "fail": "XX", "warn": "!!", "skip": ">>",
    "pin": "[pin]", "full": "#", "half": "=", "empty": ".",
    "beer": "", "down": "", "up": "", "broom": "",
    "clock": "", "note": "", "disk": "", "search": "", "sync": "", "stop": "",
}

SPINNER_UNICODE = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
SPINNER_ASCII = "|/-\\"


def char_width(ch: str) -> int:
    """Terminal columns one character occupies.

    Emoji and CJK are double-width, and combining marks, variation selectors
    and joiners take no space of their own. Counting them all as one column
    is what pushes a box border out of true.
    """
    if unicodedata.combining(ch):
        return 0
    if unicodedata.category(ch) in ("Mn", "Me", "Cf"):
        return 0
    if unicodedata.east_asian_width(ch) in ("W", "F"):
        return 2
    return 1


def vislen(text: str) -> int:
    """Terminal columns a string occupies, ignoring ANSI escape sequences."""
    return sum(char_width(ch) for ch in ANSI_RE.sub("", text))


_ELLIPSIS = "…"


def clip(text: str, width: int) -> str:
    """Truncate to at most `width` terminal columns, ANSI-aware.

    Never splits a double-width character: if only one column is left, the
    character is dropped rather than half-drawn. Callers that need the result
    to fill the width exactly pad it afterwards.
    """
    if width <= 0:
        return ""
    if vislen(text) <= width:
        return text
    tail = _ELLIPSIS if width > vislen(_ELLIPSIS) else ""
    budget = width - vislen(tail)
    out, seen, i, styled = [], 0, 0, False
    while i < len(text):
        m = ANSI_RE.match(text, i)
        if m:
            out.append(m.group())
            styled = True
            i = m.end()
            continue
        step = char_width(text[i])
        if seen + step > budget:
            break
        out.append(text[i])
        seen += step
        i += 1
    out.append(tail)
    # Only re-emit a reset if we actually cut through styled text.
    if styled:
        out.append(RESET)
    return "".join(out)


def pad(text: str, width: int, align: str = "<") -> str:
    """Pad to `width` visible columns (ANSI-aware)."""
    gap = max(0, width - vislen(text))
    if align == ">":
        return " " * gap + text
    if align == "^":
        left = gap // 2
        return " " * left + text + " " * (gap - left)
    return text + " " * gap


def human_size(n: float) -> str:
    for unit in ("B", "KB", "MB"):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def human_time(secs: float) -> str:
    if secs < 10:
        return f"{secs:.1f}s"
    secs = int(secs)
    if secs < 60:
        return f"{secs}s"
    if secs < 3600:
        return f"{secs // 60}m {secs % 60:02d}s"
    return f"{secs // 3600}h {(secs % 3600) // 60:02d}m"


def _want_color(mode: str, stream) -> bool:
    if mode == "never":
        return False
    if mode == "always":
        return True
    if os.environ.get("NO_COLOR") is not None:
        return False
    if os.environ.get("TERM", "") in ("", "dumb"):
        return False
    try:
        return stream.isatty()
    except (AttributeError, ValueError):
        return False


def _want_unicode(force_ascii: bool, stream) -> bool:
    if force_ascii:
        return False
    enc = (getattr(stream, "encoding", "") or "").lower()
    return "utf" in enc


class UI:
    """Terminal presentation: colors, boxes, tables, and a live bottom line.

    Everything degrades on its own: no TTY, NO_COLOR, TERM=dumb or a
    non-UTF-8 stream all fall back to plain ASCII without losing content.
    """

    def __init__(self, stream=None, color: str = "auto", force_ascii: bool = False,
                 quiet: bool = False):
        self.stream = stream or sys.stdout
        self.quiet = quiet
        try:
            self.tty = self.stream.isatty()
        except (AttributeError, ValueError):
            self.tty = False
        self.color = _want_color(color, self.stream)
        self.uni = _want_unicode(force_ascii, self.stream)
        global _ELLIPSIS
        _ELLIPSIS = "…" if self.uni else "..."
        self.g = GLYPHS_UNICODE if self.uni else GLYPHS_ASCII
        self.spinner = SPINNER_UNICODE if self.uni else SPINNER_ASCII
        self.lock = threading.RLock()
        self.live: LiveLine | None = None

    # -- primitives --------------------------------------------------------

    @property
    def width(self) -> int:
        if not self.tty:
            return 100
        return max(46, min(120, shutil.get_terminal_size((100, 24)).columns))

    def c(self, text: str, *codes: str) -> str:
        active = [code for code in codes if code]
        if not self.color or not active:
            return text
        return "".join(active) + text + RESET

    def _raw(self, text: str) -> None:
        """Write through, stepping around the live line if one is active."""
        with self.lock:
            live = self.live
            if live is not None:
                live.clear()
            self.stream.write(text)
            if live is not None:
                live.draw()
            self.stream.flush()

    def out(self, text: str = "") -> None:
        if self.quiet:
            return
        self._raw(clip(text, self.width) + "\n")

    def blank(self) -> None:
        self.out("")

    # -- semantic lines ----------------------------------------------------

    def step(self, glyph: str, text: str, color: str = BLUE) -> None:
        mark = self.g.get(glyph, "")
        prefix = f"{mark} " if mark else ""
        self.out(self.c(f"{prefix}{text}", color, BOLD))

    def note(self, text: str) -> None:
        self.out(f"  {self.c(text, GREY)}")

    def ok(self, text: str) -> None:
        self.out(f"  {self.c(self.g['ok'], GREEN)} {text}")

    def warn(self, text: str) -> None:
        self.out(f"  {self.c(self.g['warn'], YELLOW)} {self.c(text, YELLOW)}")

    def error(self, text: str) -> None:
        # Errors are worth seeing even under --quiet.
        line = f"  {self.c(self.g['fail'], RED)} {self.c(text, RED)}"
        self._raw(clip(line, self.width) + "\n")

    # -- boxes -------------------------------------------------------------

    def _box(self, lines: list[str], width: int, color: str = "") -> None:
        g = self.g
        top = self.c(g["tl"] + g["h"] * (width + 2) + g["tr"], color)
        bot = self.c(g["bl"] + g["h"] * (width + 2) + g["br"], color)
        bar = self.c(g["v"], color)
        self.out(top)
        for line in lines:
            self.out(f"{bar} {pad(line, width)} {bar}")
        self.out(bot)

    def banner(self, title: str, subtitle: str = "") -> None:
        if self.quiet:
            return
        beer = self.g["beer"]
        head = f"{beer}  {title}" if beer else title
        lines = [self.c(head, CYAN, BOLD)]
        if subtitle:
            lines.append(self.c(subtitle, GREY))
        width = min(self.width - 4, max(vislen(x) for x in lines))
        width = max(width, 34)
        self._box([clip(x, width) for x in lines], width, CYAN)

    def panel(self, title: str, lines: list[str], color: str = BLUE) -> None:
        if self.quiet:
            return
        body = [self.c(title, color, BOLD)] + lines
        width = min(self.width - 4, max(vislen(x) for x in body))
        width = max(width, 34)
        self._box([clip(x, width) for x in body], width, color)

    def rule(self, title: str = "", color: str = GREY) -> None:
        if self.quiet:
            return
        g = self.g["h"]
        if not title:
            self.out(self.c(g * (self.width - 2), color))
            return
        label = f" {title} "
        fill = max(3, self.width - 2 - len(label) - 2)
        self.out(self.c(g * 2 + label + g * fill, color))

    # -- tables ------------------------------------------------------------

    def table(self, headers: list[str], rows: list[list[str]],
              aligns: str | None = None) -> None:
        """Render an ANSI-aware, width-aware box table."""
        if self.quiet or not rows:
            return
        ncols = len(headers)
        aligns = aligns or "<" * ncols
        widths = [vislen(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row[:ncols]):
                widths[i] = max(widths[i], vislen(cell))

        # Shrink the widest column until the table fits the terminal.
        overhead = 3 * ncols + 1
        budget = self.width - overhead
        while sum(widths) > budget:
            widest = max(range(ncols), key=lambda i: widths[i])
            if widths[widest] <= 6:
                break
            widths[widest] -= 1

        g = self.g
        def line(left, mid, right):
            return self.c(left + mid.join(g["h"] * (w + 2) for w in widths) + right, GREY)

        bar = self.c(g["v"], GREY)
        self.out(line(g["tl"], g["tt"], g["tr"]))
        head = bar + bar.join(
            f" {pad(self.c(h, BOLD), w, a)} " for h, w, a in zip(headers, widths, aligns)
        ) + bar
        self.out(head)
        self.out(line(g["lt"], g["x"], g["rt"]))
        for row in rows:
            cells = list(row[:ncols]) + [""] * (ncols - len(row))
            self.out(bar + bar.join(
                f" {pad(clip(cell, w), w, a)} " for cell, w, a in zip(cells, widths, aligns)
            ) + bar)
        self.out(line(g["bl"], g["bt"], g["br"]))

    # -- live line factories ----------------------------------------------

    def status(self, text: str, live: bool = True) -> "Status":
        return Status(self, text, live=live)

    def progress(self, total: int, title: str, live: bool = True) -> "Bar":
        return Bar(self, total, title, live=live)


class LiveLine:
    """A single self-refreshing terminal line anchored to the bottom."""

    interval = 0.12

    def __init__(self, ui: UI, live: bool = True):
        self.ui = ui
        # `live` is cleared when raw subprocess output is being streamed —
        # a repainting bottom line and streamed output would fight over stdout.
        self.enabled = live and ui.tty and not ui.quiet
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._frame = 0
        self.started = time.monotonic()

    def render(self) -> str:  # pragma: no cover - overridden
        raise NotImplementedError

    def spin(self) -> str:
        frames = self.ui.spinner
        return frames[self._frame % len(frames)]

    def clear(self) -> None:
        self.ui.stream.write("\r\033[2K")

    def draw(self) -> None:
        self.ui.stream.write("\r\033[2K" + clip(self.render(), self.ui.width - 1))

    def _loop(self) -> None:
        while not self._stop.wait(self.interval):
            with self.ui.lock:
                if self.ui.live is self:
                    self._frame += 1
                    self.draw()
                    self.ui.stream.flush()

    def __enter__(self):
        if self.enabled:
            with self.ui.lock:
                self.ui.live = self
                self.draw()
                self.ui.stream.flush()
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()
        return self

    def __exit__(self, *exc) -> bool:
        if self.enabled:
            self._stop.set()
            if self._thread is not None:
                self._thread.join(timeout=1.0)
            with self.ui.lock:
                self.ui.live = None
                self.clear()
                self.ui.stream.flush()
        return False


class Status(LiveLine):
    """Indeterminate spinner for a single long-running step."""

    def __init__(self, ui: UI, text: str, live: bool = True):
        super().__init__(ui, live=live)
        self.text = text

    def update(self, text: str) -> None:
        self.text = text
        if self.enabled:
            with self.ui.lock:
                self.draw()
                self.ui.stream.flush()

    def render(self) -> str:
        elapsed = time.monotonic() - self.started
        tail = self.ui.c(f" {elapsed:4.1f}s", GREY) if elapsed >= 1 else ""
        return f"  {self.ui.c(self.spin(), CYAN)} {self.text}{tail}"

    def done(self, text: str, glyph: str = "ok", color: str = GREEN) -> None:
        """Retire the spinner and leave a permanent result line in its place."""
        with self.ui.lock:
            if self.ui.live is self:
                self.clear()
                self.ui.live = None
                self.ui.stream.flush()
        mark = self.ui.c(self.ui.g[glyph], color)
        elapsed = time.monotonic() - self.started
        self.ui.out(f"  {mark} {text} {self.ui.c(f'({elapsed:.1f}s)', GREY)}")


class Bar(LiveLine):
    """Determinate progress bar with a spinner, counts, and elapsed time."""

    def __init__(self, ui: UI, total: int, title: str, live: bool = True):
        super().__init__(ui, live=live)
        self.total = max(1, total)
        self.title = title
        self.done_count = 0
        self.current = ""

    def set_current(self, name: str) -> None:
        self.current = name
        if self.enabled:
            with self.ui.lock:
                self.draw()
                self.ui.stream.flush()

    def advance(self, line: str = "") -> None:
        """Record one completed item and print its result line above the bar."""
        self.done_count += 1
        if line:
            self.ui.out(line)
        elif self.enabled:
            with self.ui.lock:
                self.draw()
                self.ui.stream.flush()

    def render(self) -> str:
        frac = min(1.0, self.done_count / self.total)
        counts = f"{self.done_count}/{self.total}"
        elapsed = human_time(time.monotonic() - self.started)
        head = f"  {self.ui.c(self.spin(), CYAN)} "
        tail = f" {self.ui.c(counts, BOLD)} {self.ui.c(elapsed, GREY)}"
        room = self.ui.width - 1 - vislen(head) - vislen(tail) - vislen(self.current) - 4
        barw = max(8, min(28, room))
        filled = int(barw * frac)
        bar = (self.ui.c(self.ui.g["full"] * filled, GREEN)
               + self.ui.c(self.ui.g["empty"] * (barw - filled), GREY))
        name = self.ui.c(self.current, CYAN) if self.current else ""
        return f"{head}{bar}{tail}  {name}"


# --------------------------------------------------------------------------
# Subprocess layer
# --------------------------------------------------------------------------

class Res:
    """Result of one subprocess call. Never raises; callers inspect `.ok`."""

    __slots__ = ("rc", "out", "err", "secs")

    def __init__(self, rc: int, out: str = "", err: str = "", secs: float = 0.0):
        self.rc = rc
        self.out = out
        self.err = err
        self.secs = secs

    @property
    def ok(self) -> bool:
        return self.rc == 0

    @property
    def message(self) -> str:
        return (self.err or self.out or "").strip() or f"exit {self.rc}"


class Ctx:
    """Everything the worker functions need: UI, parsed args, brew path, env."""

    def __init__(self, ui: UI, args: argparse.Namespace, brew: str, env: dict[str, str]):
        self.ui = ui
        self.args = args
        self.brew = brew
        self.env = env

    def brew_cmd(self, *parts: str) -> list[str]:
        return [self.brew, *parts]


def run(ctx: Ctx, cmd: list[str], *, timeout: float | None = None,
        stream: bool = False, dry: bool = False) -> Res:
    """Run a command, audit it, and return its result. Never exits the process.

    Package upgrades and queries get DEVNULL on stdin so a stray sudo or
    confirmation prompt fails fast instead of hanging until the timeout.
    """
    cmd_str = shlex.join(cmd)

    if dry and ctx.args.dry_run:
        ctx.ui.note(f"[dry-run] {cmd_str}")
        log(f"AUDIT: {cmd_str} -> exit 0 (dry-run, not executed)")
        return Res(0)

    kwargs: dict = {"text": True, "env": ctx.env, "stdin": subprocess.DEVNULL}
    if not stream:
        kwargs["capture_output"] = True

    started = time.monotonic()
    try:
        p = subprocess.run(cmd, timeout=timeout, **kwargs)
    except FileNotFoundError:
        audit(cmd, RC_NOT_FOUND, "(executable not found)")
        return Res(RC_NOT_FOUND, "", f"executable not found: {cmd[0]}")
    except PermissionError as exc:
        audit(cmd, RC_NOT_FOUND, "(permission denied)")
        return Res(RC_NOT_FOUND, "", f"permission denied: {exc}")
    except subprocess.TimeoutExpired as exc:
        secs = time.monotonic() - started
        audit(cmd, RC_TIMEOUT, f"(timed out after {timeout}s)")
        partial = exc.stdout if isinstance(exc.stdout, str) else ""
        return Res(RC_TIMEOUT, partial, f"timed out after {timeout}s", secs)

    secs = time.monotonic() - started
    audit(cmd, p.returncode, f"({secs:.1f}s)")
    return Res(p.returncode, p.stdout or "", p.stderr or "", secs)


def brew_env() -> dict[str, str]:
    """Environment for every brew call made during a run.

    Auto-update and per-install cleanup are disabled because BrewMaster does
    both itself, once, instead of once per package — the single largest
    speedup available on a multi-package run.
    """
    env = dict(os.environ)
    env["HOMEBREW_NO_AUTO_UPDATE"] = "1"
    env["HOMEBREW_NO_INSTALL_CLEANUP"] = "1"
    env["HOMEBREW_NO_ENV_HINTS"] = "1"
    return env


def resolve_brew(ui: UI) -> tuple[str, str]:
    """Resolve brew to an absolute path. Returns (path, warning) so the caller
    can print the warning after the banner."""
    found = shutil.which("brew")
    if not found:
        ui.error("'brew' not found. Install Homebrew first: https://brew.sh/")
        sys.exit(EXIT_FATAL)
    brew = str(Path(found).resolve())
    if brew not in KNOWN_BREW_PATHS:
        log(f"WARNING: unusual brew location: {brew}")
        return brew, f"Unusual brew location: {brew}"
    return brew, ""


# --------------------------------------------------------------------------
# Single-instance lock
# --------------------------------------------------------------------------

@contextmanager
def single_instance(ui: UI, enabled: bool):
    """Refuse to run two upgrades at once — overlapping cron runs fight over
    Homebrew's own locks and produce confusing partial failures."""
    if not enabled:
        yield True
        return
    try:
        handle = open(LOCK_PATH, "w")
        os.chmod(LOCK_PATH, 0o600)
    except OSError as exc:
        # Not being able to create the lock file at all is a different problem
        # from another run holding it — do not refuse the run over it.
        ui.warn(f"Could not open {LOCK_PATH} ({exc}); continuing without the instance lock.")
        log(f"Instance lock unavailable: {exc}")
        yield True
        return
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        ui.error(f"Another BrewMaster run holds {LOCK_PATH}. Use --no-lock to override.")
        log("Refused to start: lock already held.")
        yield False
        return
    try:
        handle.write(f"{os.getpid()}\n")
        handle.flush()
        yield True
    finally:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        handle.close()


# --------------------------------------------------------------------------
# Config file
# --------------------------------------------------------------------------

CONFIG_SCHEMA: dict[str, type] = {
    "skip": list, "only": list, "greedy": bool, "notify": bool, "backup": bool,
    "jobs": int, "retries": int, "timeout": int, "log_json": bool,
    "no_cleanup": bool, "no_prefetch": bool, "color": str, "ascii": bool,
}


def load_config(ui: UI) -> dict:
    """Read ~/.brewmasterrc.json. Unknown or mistyped keys warn and are ignored."""
    if not CONFIG_PATH.exists():
        return {}
    try:
        raw = json.loads(CONFIG_PATH.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        ui.warn(f"Ignoring unreadable config {CONFIG_PATH}: {exc}")
        return {}
    if not isinstance(raw, dict):
        ui.warn(f"Ignoring config {CONFIG_PATH}: expected a JSON object.")
        return {}
    clean: dict = {}
    for key, value in raw.items():
        want = CONFIG_SCHEMA.get(key)
        if want is None:
            ui.warn(f"Ignoring unknown config key: {key!r}")
        elif not isinstance(value, want) or isinstance(value, bool) != (want is bool):
            ui.warn(f"Ignoring config key {key!r}: expected {want.__name__}")
        elif want is list and not all(isinstance(v, str) for v in value):
            ui.warn(f"Ignoring config key {key!r}: expected a list of strings")
        else:
            clean[key] = value
    if clean:
        log(f"Loaded config from {CONFIG_PATH}: {sorted(clean)}")
    return clean


# --------------------------------------------------------------------------
# Brew queries
# --------------------------------------------------------------------------

def brew_update_is_fresh(ctx: Ctx, max_age_secs: int = 3600) -> bool:
    """Return True if brew update ran within the last max_age_secs."""
    res = run(ctx, ctx.brew_cmd("--repository"), timeout=30)
    if not res.ok or not res.out.strip():
        return False
    fetch_head = Path(res.out.strip()) / ".git" / "FETCH_HEAD"
    try:
        return (time.time() - fetch_head.stat().st_mtime) < max_age_secs
    except OSError:
        return False


def get_pinned(ctx: Ctx) -> set[str]:
    res = run(ctx, ctx.brew_cmd("list", "--pinned"), timeout=60)
    if not res.ok:
        return set()
    return {line.strip() for line in res.out.splitlines() if line.strip()}


def get_outdated(ctx: Ctx, greedy: bool) -> tuple[list[dict], list[dict], str]:
    """Outdated formulae and casks from one brew call. Third item is an error, if any."""
    cmd = ctx.brew_cmd("outdated", "--json=v2")
    if greedy:
        cmd.append("--greedy")
    res = run(ctx, cmd, timeout=300)
    if not res.out.strip():
        return [], [], "" if res.ok else res.message
    try:
        data = json.loads(res.out)
    except json.JSONDecodeError as exc:
        return [], [], f"could not parse brew outdated JSON: {exc}"
    if not isinstance(data, dict):
        return [], [], "unexpected brew outdated payload"
    formulae = [p for p in data.get("formulae", []) if isinstance(p, dict)]
    casks = [p for p in data.get("casks", []) if isinstance(p, dict)]
    return formulae, casks, ""


def installed_version(pkg: dict) -> str:
    versions = pkg.get("installed_versions") or []
    if versions:
        return ", ".join(str(v) for v in versions)
    return str(pkg.get("installed_version") or "?")


def available_version(pkg: dict) -> str:
    return str(pkg.get("current_version") or "?")


def cached_sizes(ctx: Ctx, formulae: list[str], casks: list[str]) -> dict[str, int]:
    """Map package name -> cached download size, via batched `brew --cache` calls."""
    sizes: dict[str, int] = {}
    for flag, names in (("--formula", formulae), ("--cask", casks)):
        if not names:
            continue
        res = run(ctx, ctx.brew_cmd("--cache", flag, *names), timeout=120)
        if not res.ok:
            continue
        paths = [line.strip() for line in res.out.splitlines() if line.strip()]
        if len(paths) != len(names):
            # Layout we do not recognise; skip per-package attribution rather
            # than mislabelling sizes.
            continue
        for name, path in zip(names, paths):
            try:
                sizes[name] = Path(path).stat().st_size
            except OSError:
                sizes[name] = 0
    return sizes


def free_disk_bytes(ctx: Ctx) -> int:
    res = run(ctx, ctx.brew_cmd("--prefix"), timeout=30)
    target = Path(res.out.strip()) if res.ok and res.out.strip() else HOME
    try:
        return shutil.disk_usage(target).free
    except OSError:
        return -1


FREED_RE = re.compile(r"freed approximately\s+([\d.]+\s*[KMGT]?B)", re.IGNORECASE)


def send_notification(title: str, message: str) -> None:
    """Send a macOS notification via osascript, escaping both fields."""
    if sys.platform != "darwin":
        return

    def esc(text: str) -> str:
        return text.replace("\\", "\\\\").replace('"', '\\"')

    script = f'display notification "{esc(message)}" with title "{esc(title)}"'
    cmd = ["osascript", "-e", script]
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=15, stdin=subprocess.DEVNULL)
        audit(cmd, p.returncode)
    except (OSError, subprocess.SubprocessError):
        audit(cmd, RC_NOT_FOUND, "(notification failed)")


# --------------------------------------------------------------------------
# Backups
# --------------------------------------------------------------------------

def prune_backups(ctx: Ctx, keep: int = MAX_BACKUPS) -> None:
    """Delete all but the newest `keep` backup Brewfiles created by this tool."""
    backups = sorted(HOME.glob(".brewmaster_backup_*.Brewfile"))
    for old in backups[:-keep]:
        try:
            old.unlink()
        except OSError as exc:
            ctx.ui.warn(f"Could not prune {old.name}: {exc}")
            continue
        ctx.ui.note(f"pruned old backup: {old.name}")
        log(f"Pruned old backup: {old}")


def backup_bundle(ctx: Ctx) -> None:
    """Snapshot the current Homebrew state via brew bundle dump."""
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = HOME / f".brewmaster_backup_{stamp}.Brewfile"
    if ctx.args.dry_run:
        ctx.ui.note(f"[dry-run] would back up bundle to {backup_path}")
        return
    with ctx.ui.status(f"Backing up bundle to {backup_path.name}") as st:
        res = run(ctx, ctx.brew_cmd("bundle", "dump", "--file=/dev/stdout"), timeout=300)
        if not res.ok:
            st.done(f"Backup failed: {res.message}", glyph="fail", color=RED)
            log(f"Backup failed: {res.message}")
            return
        try:
            backup_path.write_text(res.out)
            os.chmod(backup_path, 0o600)
        except OSError as exc:
            st.done(f"Backup could not be written: {exc}", glyph="fail", color=RED)
            log(f"Backup write failed: {exc}")
            return
        lines = sum(1 for line in res.out.splitlines() if line.strip())
        st.done(f"Backed up {lines} entries to {backup_path.name}")
    log(f"Backup saved to {backup_path}")
    prune_backups(ctx)


# --------------------------------------------------------------------------
# Filtering and selection
# --------------------------------------------------------------------------

class Entry:
    """One outdated package selected for upgrade."""

    __slots__ = ("kind", "name", "installed", "available", "size")

    def __init__(self, kind: str, pkg: dict):
        self.kind = kind
        self.name = str(pkg.get("name", ""))
        self.installed = installed_version(pkg)
        self.available = available_version(pkg)
        self.size = 0

    @property
    def is_cask(self) -> bool:
        return self.kind == "cask"


def filter_packages(pkgs: list[dict], skip: list[str], only: list[str],
                    pinned: set[str]) -> tuple[list[dict], list[str], list[str], list[str]]:
    """Split into (kept, skipped_by_skip, skipped_by_only, skipped_pinned).

    Both --skip and --only accept fnmatch globs; --skip wins on a conflict.
    """
    kept, by_skip, by_only, by_pin = [], [], [], []
    for pkg in pkgs:
        name = str(pkg.get("name", ""))
        if name in pinned:
            by_pin.append(name)
        elif any(fnmatch.fnmatch(name, pat) for pat in skip):
            by_skip.append(name)
        elif only and not any(fnmatch.fnmatch(name, pat) for pat in only):
            by_only.append(name)
        else:
            kept.append(pkg)
    return kept, by_skip, by_only, by_pin


def parse_selection(text: str, count: int) -> list[int] | None:
    """Parse '1,3,5-7' into zero-based indices. Returns None on invalid input."""
    indices: set[int] = set()
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo, _, hi = part.partition("-")
            lo, hi = lo.strip(), hi.strip()
            if not (lo.isdigit() and hi.isdigit()):
                return None
            lo_i, hi_i = int(lo), int(hi)
            if lo_i < 1 or hi_i > count or lo_i > hi_i:
                return None
            indices.update(range(lo_i - 1, hi_i))
        elif part.isdigit():
            i = int(part)
            if i < 1 or i > count:
                return None
            indices.add(i - 1)
        else:
            return None
    return sorted(indices)


def select_packages(ui: UI, entries: list[Entry]) -> list[Entry]:
    """Interactive per-package selection against the numbered table above."""
    prompt = ui.c("Selection (e.g. 1,3,5-7 | all | none): ", CYAN, BOLD)
    while True:
        try:
            raw = input(prompt).strip().lower()
        except EOFError:
            return []
        if raw in ("all", "a", ""):
            return entries
        if raw in ("none", "n", "q"):
            return []
        idxs = parse_selection(raw, len(entries))
        if idxs is not None:
            return [entries[i] for i in idxs]
        ui.warn("Invalid selection, try again.")


def confirm(ui: UI, question: str) -> bool:
    try:
        return input(ui.c(question, CYAN, BOLD)).strip().lower() in ("y", "yes")
    except EOFError:
        return False


# --------------------------------------------------------------------------
# Prefetch pipeline
# --------------------------------------------------------------------------

class Prefetcher:
    """Downloads bottles and casks on a thread pool while upgrades run.

    Submissions are made in upgrade order, and the upgrade loop waits only on
    the future for the package it is about to install — so the download of
    package N+1 overlaps the installation of package N instead of the whole
    batch having to finish first.
    """

    def __init__(self, ctx: Ctx, jobs: int, timeout: float):
        self.ctx = ctx
        self.timeout = timeout
        self.pool = ThreadPoolExecutor(max_workers=max(1, jobs),
                                       thread_name_prefix="bm-fetch")
        self.futures: dict[str, Future] = {}

    def submit(self, entries: list[Entry]) -> None:
        for entry in entries:
            self.futures[entry.name] = self.pool.submit(self._fetch, entry)

    def _fetch(self, entry: Entry) -> Res:
        flag = "--cask" if entry.is_cask else "--formula"
        return run(self.ctx, self.ctx.brew_cmd("fetch", flag, entry.name),
                   timeout=self.timeout)

    def wait(self, entry: Entry) -> None:
        """Block until this package's download finishes; failures are non-fatal
        because `brew upgrade` will simply fetch it again itself."""
        future = self.futures.get(entry.name)
        if future is None:
            return
        try:
            future.result(timeout=self.timeout)
        except Exception as exc:  # noqa: BLE001 - a failed prefetch is advisory
            log(f"Prefetch failed for {entry.name}: {exc}")

    def cancel(self) -> None:
        for future in self.futures.values():
            future.cancel()

    def shutdown(self) -> None:
        self.pool.shutdown(wait=False, cancel_futures=True)


# --------------------------------------------------------------------------
# Upgrading
# --------------------------------------------------------------------------

# Errors that will fail identically on every retry — retrying them only burns
# time and clutters the log.
PERMANENT_ERRORS = (
    "no available formula", "no casks found", "no available cask",
    "is not installed", "does not exist", "no such keg",
    "requires a password", "sudo: a terminal is required",
    "not supported on", "requires macos",
)


def is_permanent(error: str) -> bool:
    low = error.lower()
    return any(marker in low for marker in PERMANENT_ERRORS)


def upgrade_one(ctx: Ctx, entry: Entry, retries: int, timeout: float) -> tuple[bool, str]:
    """Upgrade a single package with bounded retries and backoff."""
    cmd = ctx.brew_cmd("upgrade", "--cask") if entry.is_cask else ctx.brew_cmd("upgrade")
    if entry.is_cask and ctx.args.greedy:
        cmd.append("--greedy")
    cmd.append(entry.name)

    if ctx.args.dry_run:
        ctx.ui.note(f"[dry-run] {shlex.join(cmd)}")
        log(f"AUDIT: {shlex.join(cmd)} -> exit 0 (dry-run, not executed)")
        return True, ""

    error = ""
    for attempt in range(1, retries + 1):
        res = run(ctx, cmd, timeout=timeout, stream=ctx.args.verbose)
        if res.ok:
            return True, ""
        error = res.message
        if is_permanent(error):
            log(f"Not retrying {entry.name}: permanent error")
            break
        if attempt < retries:
            delay = min(8.0, 2.0 ** (attempt - 1))
            log(f"Retrying {entry.name} in {delay:.0f}s (attempt {attempt + 1}/{retries})")
            time.sleep(delay)

    return False, error or "unknown error"


# --------------------------------------------------------------------------
# History
# --------------------------------------------------------------------------

def write_history(record: dict) -> None:
    """Append one JSON record per run, trimming the file to MAX_HISTORY records."""
    try:
        HISTORY_PATH.touch(mode=0o600, exist_ok=True)
        os.chmod(HISTORY_PATH, 0o600)
        with open(HISTORY_PATH, "a") as fh:
            fh.write(json.dumps(record) + "\n")
        lines = HISTORY_PATH.read_text().splitlines()
        if len(lines) > MAX_HISTORY:
            HISTORY_PATH.write_text("\n".join(lines[-MAX_HISTORY:]) + "\n")
    except OSError as exc:
        log(f"Could not write history: {exc}")


def read_history(limit: int) -> list[dict]:
    if not HISTORY_PATH.exists():
        return []
    records: list[dict] = []
    try:
        for line in HISTORY_PATH.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                records.append(item)
    except OSError:
        return []
    return records[-limit:]


def show_history(ui: UI, limit: int) -> int:
    records = read_history(limit)
    if not records:
        ui.step("note", "No run history yet — add --log-json to record runs.", YELLOW)
        return EXIT_OK
    rows = []
    for rec in records:
        code = int(rec.get("exit_code", 0) or 0)
        color = GREEN if code == EXIT_OK else (YELLOW if code == EXIT_FAILURES else RED)
        rows.append([
            str(rec.get("timestamp", "?"))[:19].replace("T", " "),
            ui.c(str(len(rec.get("upgraded", []) or [])), GREEN),
            ui.c(str(len(rec.get("failures", []) or [])), RED if rec.get("failures") else GREY),
            human_time(float(rec.get("elapsed_secs", 0) or 0)),
            ui.c(str(code), color),
        ])
    ui.blank()
    ui.step("note", f"Last {len(rows)} run(s) — {HISTORY_PATH}", BLUE)
    ui.table(["When", "Upgraded", "Failed", "Elapsed", "Exit"], rows, aligns="<>>><")
    return EXIT_OK


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="brewmaster.py",
        description="BrewMaster: a graphical, fast, careful Homebrew upgrader.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"BrewMaster {VERSION}")

    sel = parser.add_argument_group("selection")
    sel.add_argument("-y", "--yes", action="store_true", help="Auto-approve all upgrades")
    sel.add_argument("-i", "--interactive", action="store_true",
                     help="Pick packages to upgrade from a numbered list")
    sel.add_argument("--skip", nargs="+", metavar="PKG", default=[],
                     help="Skip packages; glob patterns supported (e.g. --skip node 'python@*')")
    sel.add_argument("--only", nargs="+", metavar="PKG", default=[],
                     help="Upgrade only packages matching these names/globs")
    sel.add_argument("--formula-only", action="store_true",
                     help="Only upgrade formulae, skip casks")
    sel.add_argument("--cask-only", action="store_true",
                     help="Only upgrade casks, skip formulae")
    sel.add_argument("--greedy", action="store_true", default=True,
                     help="Use --greedy for casks")
    sel.add_argument("--no-greedy", dest="greedy", action="store_false",
                     help="Disable --greedy for casks")

    beh = parser.add_argument_group("behaviour")
    beh.add_argument("--check-only", dest="check_only", action="store_true",
                     help="Only report outdated packages, don't upgrade (exit 3 if any found)")
    beh.add_argument("--dry-run", action="store_true",
                     help="Simulate commands without running them")
    beh.add_argument("--backup", action="store_true",
                     help=f"Backup Homebrew bundle before upgrading (keeps last {MAX_BACKUPS})")
    beh.add_argument("--no-update", action="store_true", help="Skip brew update entirely")
    beh.add_argument("--force-update", action="store_true",
                     help="Run brew update even if it ran within the last hour")
    beh.add_argument("--no-cleanup", action="store_true",
                     help="Skip the brew cleanup step at the end of the run")
    beh.add_argument("--no-lock", action="store_true",
                     help="Allow concurrent BrewMaster runs (skips the instance lock)")
    beh.add_argument("--no-config", action="store_true",
                     help=f"Ignore {CONFIG_PATH}")
    beh.add_argument("--notify", action="store_true",
                     help="Send a macOS notification when done")

    perf = parser.add_argument_group("performance")
    perf.add_argument("--jobs", type=int, default=6, metavar="N",
                      help="Parallel download workers (1-16)")
    perf.add_argument("--no-prefetch", action="store_true",
                      help="Do not pre-download in parallel; let each upgrade fetch itself")
    perf.add_argument("--sizes", action="store_true",
                      help="Prefetch downloads and show per-package sizes before confirming "
                           "(downloads before you confirm)")
    perf.add_argument("--retries", type=int, default=2, metavar="N",
                      help="Attempts per package before it is marked failed (min: 1)")
    perf.add_argument("--timeout", type=int, default=600, metavar="SECS",
                      help="Timeout per package upgrade")

    out = parser.add_argument_group("output")
    out.add_argument("--color", choices=("auto", "always", "never"), default="auto",
                     help="Colorise output")
    out.add_argument("--ascii", action="store_true",
                     help="ASCII-only output (no box drawing or emoji)")
    out.add_argument("-q", "--quiet", action="store_true",
                     help="Print only warnings and errors")
    out.add_argument("-v", "--verbose", action="store_true",
                     help="Stream raw brew output instead of progress indicators")
    out.add_argument("--json", action="store_true",
                     help="Print a machine-readable run summary to stdout (UI goes to stderr)")
    out.add_argument("--log-json", action="store_true",
                     help=f"Append a structured JSON record per run to {HISTORY_PATH}")
    out.add_argument("--history", nargs="?", type=int, const=15, metavar="N",
                     help="Show the last N recorded runs and exit")

    return parser


def _raise_interrupt(signum, frame) -> None:
    """Turn SIGTERM into the same KeyboardInterrupt path Ctrl-C already takes."""
    raise KeyboardInterrupt


def make_ui(args: argparse.Namespace) -> UI:
    # A terminal with a non-UTF-8 encoding should lose a glyph, not the run.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError, OSError):
            pass
    return UI(
        stream=sys.stderr if args.json else sys.stdout,
        color=args.color,
        force_ascii=args.ascii,
        quiet=args.quiet,
    )


def validate(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.formula_only and args.cask_only:
        parser.error("--formula-only and --cask-only are mutually exclusive")
    if args.interactive and args.yes:
        parser.error("--interactive and --yes are mutually exclusive")
    if args.interactive and args.quiet:
        parser.error("--interactive and --quiet are mutually exclusive")
    if args.retries < 1:
        parser.error("--retries must be at least 1")
    if args.timeout < 1:
        parser.error("--timeout must be at least 1")
    if not 1 <= args.jobs <= 16:
        parser.error("--jobs must be between 1 and 16")
    if args.history is not None and args.history < 1:
        parser.error("--history must be at least 1")


# --------------------------------------------------------------------------
# Reporting helpers
# --------------------------------------------------------------------------

def kind_tag(ui: UI, kind: str) -> str:
    return ui.c(kind, CYAN if kind == "formula" else MAGENTA)


def outdated_table(ui: UI, entries: list[Entry], show_sizes: bool) -> None:
    headers = ["#", "Kind", "Package", "Installed", "Available"]
    aligns = "><<<<"
    if show_sizes:
        headers.append("Download")
        aligns += ">"
    rows = []
    for i, e in enumerate(entries, 1):
        row = [
            ui.c(str(i), GREY),
            kind_tag(ui, e.kind),
            ui.c(e.name, BOLD),
            ui.c(e.installed, YELLOW),
            ui.c(e.available, GREEN),
        ]
        if show_sizes:
            row.append(human_size(e.size) if e.size else ui.c("cached", GREY))
        rows.append(row)
    ui.table(headers, rows, aligns=aligns)


def summary_panel(ui: UI, upgraded: list[str], failures: list[tuple[str, str, str]],
                  skipped: int, elapsed: float, downloaded: int, freed: str,
                  interrupted: bool) -> None:
    if interrupted:
        title, color = "Interrupted", YELLOW
    elif failures:
        title, color = "Completed with failures", YELLOW
    else:
        title, color = "Done", GREEN

    def row(label: str, value: str, value_color: str = "") -> str:
        return f"{ui.c(pad(label, 12), GREY)}{ui.c(value, value_color)}"

    lines = [
        row("Upgraded", str(len(upgraded)), GREEN if upgraded else ""),
        row("Failed", str(len(failures)), RED if failures else ""),
    ]
    if skipped:
        lines.append(row("Skipped", str(skipped), YELLOW))
    if downloaded:
        lines.append(row("Downloaded", human_size(downloaded)))
    if freed:
        lines.append(row("Freed", freed))
    lines.append(row("Elapsed", human_time(elapsed)))
    if _log_enabled:
        lines.append(row("Log", str(LOG_PATH)))
    ui.blank()
    ui.panel(title, lines, color=color)


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    ui = make_ui(args)

    log_ok = setup_logging()

    if not args.no_config:
        config = load_config(ui)
        if config:
            parser.set_defaults(**config)
            args = parser.parse_args(argv)
            ui = make_ui(args)

    validate(parser, args)

    if not log_ok:
        ui.warn(f"Could not open {LOG_PATH}; continuing without a log file.")

    if args.history is not None:
        return show_history(ui, args.history)

    # Fail fast in cron/launchd instead of hanging on input()
    needs_tty = args.interactive or not (args.yes or args.dry_run or args.check_only)
    if needs_tty and not sys.stdin.isatty():
        ui.error("Non-interactive session and no -y/--yes flag; refusing to prompt.")
        return EXIT_FATAL

    # SIGTERM (launchd stopping the job) takes the same clean path as Ctrl-C.
    signal.signal(signal.SIGTERM, _raise_interrupt)

    start = time.monotonic()
    log(f"--- BrewMaster {VERSION} run started: {shlex.join(sys.argv[1:])} ---")

    brew, brew_warning = resolve_brew(ui)
    ctx = Ctx(ui, args, brew, brew_env())

    sep = " · " if ui.uni else " | "
    mode = "greedy" if args.greedy else "no-greedy"
    if args.dry_run:
        mode += f"{sep}dry-run"
    ui.banner(f"BrewMaster {VERSION}",
              sep.join([brew, mode, f"{args.jobs} download jobs"]))
    if brew_warning:
        ui.warn(brew_warning)
        ui.note("Expected /opt/homebrew/bin/brew or /usr/local/bin/brew — verify your PATH.")

    with single_instance(ui, enabled=not args.no_lock and not args.dry_run) as acquired:
        if not acquired:
            return EXIT_FATAL
        return run_upgrade(ctx, start)


def run_upgrade(ctx: Ctx, start: float) -> int:
    ui, args = ctx.ui, ctx.args
    live = not args.verbose

    if args.backup:
        backup_bundle(ctx)

    # -- refresh metadata --------------------------------------------------
    if args.no_update:
        ui.note("skipping brew update (--no-update)")
    elif not args.force_update and brew_update_is_fresh(ctx):
        ui.note("brew update ran within the last hour — skipping (--force-update to force)")
    else:
        with ui.status("Updating Homebrew metadata (brew update)", live=live) as st:
            res = run(ctx, ctx.brew_cmd("update"), timeout=900,
                      stream=args.verbose, dry=True)
            if res.ok:
                changed = sum(1 for line in res.out.splitlines() if line.startswith("=="))
                st.done("Homebrew metadata updated"
                        + (f" ({changed} section(s) changed)" if changed else ""))
            else:
                st.done(f"brew update failed: {res.message} — continuing with cached data",
                        glyph="warn", color=YELLOW)
                log(f"brew update failed (non-fatal): {res.message}")

    # -- what is outdated --------------------------------------------------
    with ui.status("Checking for outdated packages", live=live) as st:
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="bm-query") as pool:
            fut_outdated = pool.submit(get_outdated, ctx, args.greedy)
            fut_pinned = pool.submit(get_pinned, ctx)
            formulae_raw, casks_raw, query_error = fut_outdated.result()
            pinned = fut_pinned.result()
        if query_error:
            st.done(f"Could not read outdated packages: {query_error}", glyph="fail", color=RED)
            log(f"FATAL: {query_error}")
            return EXIT_FATAL
        st.done(f"Found {len(formulae_raw)} formula(e) and {len(casks_raw)} cask(s) outdated")

    if args.formula_only:
        casks_raw = []
    if args.cask_only:
        formulae_raw = []

    formulae, skip_f, only_f, pin_f = filter_packages(formulae_raw, args.skip, args.only, pinned)
    casks, skip_c, only_c, pin_c = filter_packages(casks_raw, args.skip, args.only, pinned)

    for name in pin_f + pin_c:
        ui.out(f"  {ui.c(ui.g['pin'], YELLOW)} pinned, skipping: {name}")
    for name in skip_f + skip_c:
        ui.out(f"  {ui.c(ui.g['skip'], YELLOW)} --skip: {name}")
    for name in only_f + only_c:
        ui.out(f"  {ui.c(ui.g['skip'], GREY)} not matched by --only: {name}")

    skipped_total = len(pin_f + pin_c + skip_f + skip_c + only_f + only_c)
    entries = [Entry("formula", p) for p in formulae] + [Entry("cask", p) for p in casks]

    if not entries:
        elapsed = time.monotonic() - start
        ui.blank()
        ui.panel("Everything is up to date", [
            f"{ui.c(pad('Skipped', 12), GREY)}{skipped_total}",
            f"{ui.c(pad('Elapsed', 12), GREY)}{human_time(elapsed)}",
        ], color=GREEN)
        log("Everything up to date. Run complete.")
        if args.notify:
            send_notification("BrewMaster", "Everything is up to date!")
        record = build_record([], [], skipped_total, elapsed, 0, "", False, EXIT_OK)
        finish_reporting(ctx, record)
        return EXIT_OK

    # -- reject suspicious names before anything reaches a subprocess ------
    failures: list[tuple[str, str, str]] = []
    valid: list[Entry] = []
    for entry in entries:
        if VALID_PKG.match(entry.name):
            valid.append(entry)
        else:
            failures.append((entry.kind, entry.name, "invalid package name — skipped"))
            ui.error(f"Skipping invalid package name: {entry.name!r}")
            log(f"SKIPPED invalid package name: {entry.name!r}")
    entries = valid
    if not entries:
        return EXIT_FAILURES

    prefetcher: Prefetcher | None = None
    downloaded = 0

    # --sizes downloads up front so the table can show real byte counts.
    if args.sizes and not args.dry_run and not args.no_prefetch:
        prefetch_all(ctx, entries)
        sizes = cached_sizes(ctx,
                             [e.name for e in entries if not e.is_cask],
                             [e.name for e in entries if e.is_cask])
        for entry in entries:
            entry.size = sizes.get(entry.name, 0)
        downloaded = sum(e.size for e in entries)

    ui.blank()
    ui.step("search", f"{len(entries)} package(s) to upgrade", BLUE)
    outdated_table(ui, entries, show_sizes=bool(downloaded))
    if downloaded:
        ui.note(f"total download size: {human_size(downloaded)}")

    if args.check_only:
        elapsed = time.monotonic() - start
        ui.note(f"check-only: nothing was upgraded ({human_time(elapsed)})")
        log(f"Check-only run: {len(entries)} package(s) outdated.")
        return EXIT_OUTDATED

    # -- consent -----------------------------------------------------------
    if args.interactive:
        entries = select_packages(ui, entries)
        if not entries:
            ui.note("nothing selected — upgrade canceled")
            return EXIT_OK
    elif not args.yes:
        if args.dry_run:
            ui.note("[dry-run] skipping confirmation prompt")
        elif not confirm(ui, f"\n{ui.g['bullet']} Upgrade these {len(entries)} package(s)? (y/N): "):
            ui.note("upgrade canceled")
            return EXIT_OK

    if not check_disk_space(ctx, downloaded):
        return EXIT_FATAL

    # -- upgrade -----------------------------------------------------------
    if not args.no_prefetch and not args.sizes and not args.dry_run:
        prefetcher = Prefetcher(ctx, args.jobs, args.timeout)
        prefetcher.submit(entries)

    upgraded: list[str] = []
    interrupted = False
    failures_before_loop = len(failures)

    ui.blank()
    ui.step("up", f"Upgrading {len(entries)} package(s)", BLUE)
    bar = ui.progress(len(entries), "upgrading", live=live)
    try:
        with bar:
            for entry in entries:
                bar.set_current(entry.name)
                if prefetcher is not None:
                    prefetcher.wait(entry)
                t0 = time.monotonic()
                success, error = upgrade_one(ctx, entry, args.retries, args.timeout)
                took = time.monotonic() - t0
                if success:
                    upgraded.append(entry.name)
                    log(f"Upgraded {entry.kind}: {entry.name} "
                        f"{entry.installed} -> {entry.available}")
                    bar.advance(
                        f"  {ui.c(ui.g['ok'], GREEN)} {ui.c(pad(entry.name, 24), BOLD)}"
                        f" {ui.c(entry.installed, GREY)} {ui.g['arrow']} "
                        f"{ui.c(entry.available, GREEN)} {ui.c(f'({took:.1f}s)', GREY)}"
                    )
                else:
                    failures.append((entry.kind, entry.name, error))
                    log(f"FAILED {entry.kind}: {entry.name} — {error}")
                    bar.advance(
                        f"  {ui.c(ui.g['fail'], RED)} {ui.c(pad(entry.name, 24), BOLD)}"
                        f" {ui.c(clip(error.splitlines()[0] if error else 'unknown error', 60), RED)}"
                    )
    except KeyboardInterrupt:
        interrupted = True
        attempted = len(upgraded) + (len(failures) - failures_before_loop)
        remaining = max(0, len(entries) - attempted)
        ui.blank()
        ui.warn(f"Interrupted — {len(upgraded)} upgraded, {len(failures)} failed, "
                f"{remaining} not attempted.")
        log(f"Run interrupted: {len(upgraded)} upgraded, {len(failures)} failed, "
            f"{remaining} not attempted.")
    finally:
        if prefetcher is not None:
            prefetcher.cancel()
            prefetcher.shutdown()

    # -- cleanup -----------------------------------------------------------
    freed = ""
    if interrupted:
        ui.note("skipping cleanup after interrupt")
    elif args.no_cleanup:
        ui.note("skipping cleanup (--no-cleanup)")
    else:
        with ui.status("Cleaning up old versions (brew cleanup)", live=live) as st:
            res = run(ctx, ctx.brew_cmd("cleanup"), timeout=900,
                      stream=args.verbose, dry=True)
            if res.ok:
                match = FREED_RE.search(res.out)
                freed = match.group(1).strip() if match else ""
                st.done("Cleanup complete" + (f" — freed {freed}" if freed else ""))
            else:
                st.done(f"Cleanup failed: {res.message}", glyph="warn", color=YELLOW)
                log(f"Cleanup failed (non-fatal): {res.message}")

    elapsed = time.monotonic() - start

    if failures:
        if ui.quiet:
            # --quiet still owes the caller its warnings and errors.
            for kind, name, error in failures:
                ui.error(f"[{kind}] {name}: {(error or 'unknown error').splitlines()[0]}")
        else:
            ui.blank()
            ui.step("warn", "Failures", YELLOW)
            ui.table(
                ["Kind", "Package", "Error"],
                [[kind_tag(ui, k), ui.c(n, BOLD), (e or "unknown error").splitlines()[0]]
                 for k, n, e in failures],
            )

    if interrupted:
        exit_code = EXIT_INTERRUPT
    elif failures:
        exit_code = EXIT_FAILURES
    else:
        exit_code = EXIT_OK

    summary_panel(ui, upgraded, failures, skipped_total, elapsed, downloaded, freed, interrupted)

    if args.notify:
        if failures:
            send_notification("BrewMaster", f"Done with {len(failures)} failure(s). Check the log.")
        elif interrupted:
            send_notification("BrewMaster", "Run interrupted.")
        else:
            send_notification("BrewMaster", f"{len(upgraded)} package(s) upgraded successfully!")

    log(f"Run complete: {len(upgraded)} upgraded, {len(failures)} failed, "
        f"elapsed {elapsed:.1f}s, exit {exit_code}")

    record = build_record(upgraded, failures, skipped_total, elapsed, downloaded,
                          freed, interrupted, exit_code)
    finish_reporting(ctx, record)
    return exit_code


def prefetch_all(ctx: Ctx, entries: list[Entry]) -> None:
    """Download everything up front, with a progress bar (used by --sizes)."""
    ui, args = ctx.ui, ctx.args
    ui.blank()
    ui.step("down", f"Prefetching {len(entries)} download(s)", BLUE)
    fetcher = Prefetcher(ctx, args.jobs, args.timeout)
    fetcher.submit(entries)
    bar = ui.progress(len(entries), "downloading", live=not args.verbose)
    try:
        with bar:
            for entry in entries:
                bar.set_current(entry.name)
                fetcher.wait(entry)
                bar.advance()
            done = time.monotonic() - bar.started
        ui.ok(f"Prefetched {len(entries)} download(s) in {human_time(done)}")
    finally:
        fetcher.shutdown()


def check_disk_space(ctx: Ctx, needed: int) -> bool:
    """Refuse to start an upgrade that cannot possibly fit on disk."""
    if ctx.args.dry_run:
        return True
    free = free_disk_bytes(ctx)
    if free < 0:
        return True
    if needed and free < needed:
        ctx.ui.error(f"Only {human_size(free)} free but {human_size(needed)} of downloads "
                     f"are queued — free some space first.")
        log(f"Aborted: insufficient disk space ({free} free, {needed} needed)")
        return False
    threshold = max(needed * 3, 2 * 1024 ** 3)
    if free < threshold:
        ctx.ui.warn(f"Low disk space: {human_size(free)} free. Upgrades may fail part-way.")
    return True


def build_record(upgraded: list[str], failures: list[tuple[str, str, str]], skipped: int,
                 elapsed: float, downloaded: int, freed: str, interrupted: bool,
                 exit_code: int) -> dict:
    return {
        "version": VERSION,
        "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
        "upgraded": upgraded,
        "failures": [{"kind": k, "name": n, "error": e} for k, n, e in failures],
        "skipped": skipped,
        "elapsed_secs": round(elapsed, 1),
        "downloaded_bytes": downloaded,
        "freed": freed,
        "interrupted": interrupted,
        "exit_code": exit_code,
    }


def finish_reporting(ctx: Ctx, record: dict) -> None:
    if ctx.args.log_json and not ctx.args.dry_run:
        write_history(record)
    if ctx.args.json:
        json.dump(record, sys.stdout, indent=2)
        sys.stdout.write("\n")
        sys.stdout.flush()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.stderr.write("\nInterrupted.\n")
        log("Run interrupted by user.")
        sys.exit(EXIT_INTERRUPT)
    except BrokenPipeError:
        os._exit(EXIT_OK)
