#!/usr/bin/env python3
"""
PakMan — a graphical, fast, careful Python package updater.
----------------------------------------------------------
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
import sysconfig
import tempfile
import threading
import time
import unicodedata
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path

VERSION = "3.0.0"

HOME = Path.home()
LOG_PATH = HOME / ".pakman.log"
HISTORY_PATH = HOME / ".pakman_history.jsonl"
LOCK_PATH = HOME / ".pakman.lock"
CONFIG_PATH = HOME / ".pakmanrc.json"
ROLLBACK_GLOB = ".pakman_rollback_*.txt"

MAX_ROLLBACKS = 5
MAX_HISTORY = 500           # history records retained in the JSONL file
LOG_MAX_BYTES = 2 * 1024 * 1024
LOG_BACKUPS = 3

# PEP 508 project name rules — reject anything else before it reaches pip.
VALID_PKG = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?$")

# Exit codes for scripting/cron use
EXIT_OK = 0          # success, nothing to do or all upgrades succeeded
EXIT_FATAL = 1       # unrecoverable error
EXIT_FAILURES = 2    # run completed but one or more packages failed
EXIT_OUTDATED = 3    # --check-only found outdated packages
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


_logger = logging.getLogger("pakman")
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
    "logo": "\U0001f4e6", "down": "⬇", "up": "⬆", "broom": "\U0001f9f9",
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
    "logo": "", "down": "", "up": "", "broom": "",
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
        logo = self.g["logo"]
        head = f"{logo}  {title}" if logo else title
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


def pip_env() -> dict[str, str]:
    """Environment for every pip/uv call made during a run."""
    env = dict(os.environ)
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    # pip must never stop to ask a question: there is nothing on stdin to
    # answer with, and a prompt would hang until the timeout fired.
    env["PIP_NO_INPUT"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    return env


class Ctx:
    """Everything the worker functions need: UI, parsed args, interpreter, env."""

    def __init__(self, ui: UI, args: argparse.Namespace, env: dict[str, str],
                 uv: str | None):
        self.ui = ui
        self.args = args
        self.env = env
        self.uv = uv
        self.python = sys.executable
        # uv is used for the outdated check whenever it is present; it drives
        # the installs only when --uv asks for it.
        self.use_uv_install = bool(uv and getattr(args, "uv", False))

    def pip_cmd(self, *parts: str) -> list[str]:
        return [self.python, "-m", "pip", *parts]

    def uv_cmd(self, *parts: str) -> list[str]:
        assert self.uv is not None
        return [self.uv, "pip", *parts, "--python", self.python]


def run(ctx: Ctx, cmd: list[str], *, timeout: float | None = None,
        stream: bool = False, dry: bool = False) -> Res:
    """Run a command, audit it, and return its result. Never exits the process.

    stdin is /dev/null throughout: a build backend or index that decides to
    ask a question fails fast instead of hanging until the timeout.
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


# --------------------------------------------------------------------------
# Interpreter environment checks
# --------------------------------------------------------------------------

def in_virtualenv() -> bool:
    return sys.prefix != sys.base_prefix


def externally_managed() -> Path | None:
    """Return the PEP 668 EXTERNALLY-MANAGED marker path, if this interpreter
    has one. Homebrew and system Pythons ship it, and pip refuses to install
    into them without --break-system-packages."""
    try:
        stdlib = sysconfig.get_path("stdlib")
    except (KeyError, OSError):
        return None
    if not stdlib:
        return None
    marker = Path(stdlib) / "EXTERNALLY-MANAGED"
    return marker if marker.exists() else None


def check_environment(ui: UI, require_venv: bool) -> bool:
    """Report on the interpreter being modified. Returns False to refuse the run."""
    if in_virtualenv():
        return True
    if require_venv:
        ui.error("Not in a virtual environment and --require-venv is set. "
                 "Refusing to touch global packages.")
        log("Refused: --require-venv outside a virtualenv.")
        return False
    ui.warn("Not running in a virtual environment.")
    ui.note("upgrading global packages can break system tools")
    ui.note(f"interpreter: {sys.executable}")
    marker = externally_managed()
    if marker is not None:
        ui.warn("This interpreter is marked externally managed (PEP 668).")
        ui.note(f"marker: {marker}")
        ui.note("pip will refuse to install here without --break-system-packages;"
                " a virtualenv is the right fix")
        log(f"WARNING: externally managed interpreter, marker at {marker}")
    return True


def find_uv(disabled: bool) -> str | None:
    if disabled:
        return None
    found = shutil.which("uv")
    return str(Path(found).resolve()) if found else None


# --------------------------------------------------------------------------
# Single-instance lock
# --------------------------------------------------------------------------

@contextmanager
def single_instance(ui: UI, enabled: bool):
    """Refuse to run two upgrades at once. Two pip processes writing the same
    site-packages is the classic way to end up with a half-installed
    distribution and no way to tell which run did it."""
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
        ui.error(f"Another PakMan run holds {LOCK_PATH}. Use --no-lock to override.")
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
    "exclude": list, "only": list, "pre": bool, "only_binary": bool,
    "require_venv": bool, "audit": bool, "no_uv": bool, "uv": bool,
    "no_rollback": bool, "no_batch": bool, "notify": bool, "jobs": int,
    "retries": int, "timeout": int, "log_json": bool, "color": str,
    "ascii": bool, "export": str,
}


def load_config(ui: UI) -> dict:
    """Read ~/.pakmanrc.json. Unknown or mistyped keys warn and are ignored."""
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
# Package model and queries
# --------------------------------------------------------------------------

class Pkg:
    """One outdated distribution, tolerant of whatever shape pip or uv returns."""

    __slots__ = ("name", "version", "latest", "filetype")

    def __init__(self, raw: dict):
        self.name = str(raw.get("name", "")).strip()
        self.version = str(raw.get("version", "") or "?").strip()
        self.latest = str(raw.get("latest_version", "") or "?").strip()
        self.filetype = str(raw.get("latest_filetype", "") or "").strip()

    @property
    def is_sdist(self) -> bool:
        return self.filetype == "sdist"

    @property
    def spec(self) -> str:
        return f"{self.name}=={self.latest}" if self.latest != "?" else self.name


def parse_outdated(payload: str) -> tuple[list[Pkg], str]:
    """Parse a pip/uv `list --outdated --format=json` payload."""
    if not payload.strip():
        return [], ""
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        return [], f"could not parse outdated JSON: {exc}"
    if not isinstance(data, list):
        return [], "unexpected outdated payload (expected a JSON list)"
    pkgs = [Pkg(item) for item in data if isinstance(item, dict)]
    return [p for p in pkgs if p.name], ""


def get_outdated(ctx: Ctx) -> tuple[list[Pkg], str, str]:
    """Outdated packages. Returns (packages, source, error)."""
    if ctx.uv:
        res = run(ctx, ctx.uv_cmd("list", "--outdated", "--format=json"), timeout=300)
        if res.ok:
            pkgs, err = parse_outdated(res.out)
            if not err:
                return pkgs, "uv", ""
        log(f"uv outdated check failed ({res.message}); falling back to pip")

    res = run(ctx, ctx.pip_cmd("list", "--outdated", "--format=json"), timeout=600)
    if not res.ok:
        return [], "pip", res.message
    pkgs, err = parse_outdated(res.out)
    return pkgs, "pip", err


def pip_check(ctx: Ctx) -> list[str]:
    """Dependency conflicts reported by `pip check`, one per line."""
    res = run(ctx, ctx.pip_cmd("check"), timeout=300)
    if res.ok:
        return []
    return sorted(line.strip() for line in res.out.splitlines() if line.strip())


# --------------------------------------------------------------------------
# Rollback snapshots
# --------------------------------------------------------------------------

def prune_rollbacks(ctx: Ctx, keep: int = MAX_ROLLBACKS) -> None:
    """Delete all but the newest `keep` rollback files created by this tool."""
    for old in sorted(HOME.glob(ROLLBACK_GLOB))[:-keep]:
        try:
            old.unlink()
        except OSError as exc:
            ctx.ui.warn(f"Could not prune {old.name}: {exc}")
            continue
        ctx.ui.note(f"pruned old rollback: {old.name}")
        log(f"Pruned old rollback: {old}")


def write_rollback(ctx: Ctx, pkgs: list[Pkg]) -> Path | None:
    """Snapshot current versions so the run can be undone with pip install -r."""
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = HOME / f".pakman_rollback_{stamp}.txt"
    if ctx.args.dry_run:
        ctx.ui.note(f"[dry-run] would write rollback file {path}")
        return None
    pinned = [f"{p.name}=={p.version}" for p in pkgs if p.version != "?"]
    if not pinned:
        ctx.ui.warn("No pinnable versions to record; skipping rollback file.")
        return None
    try:
        path.write_text("\n".join(pinned) + "\n")
        path.chmod(0o600)
    except OSError as exc:
        ctx.ui.warn(f"Could not write rollback file: {exc}")
        log(f"Rollback write failed: {exc}")
        return None
    ctx.ui.ok(f"Rollback snapshot: {path.name} ({len(pinned)} pins)")
    ctx.ui.note(f"undo this run with: pip install -r {path}")
    log(f"Rollback file written: {path}")
    prune_rollbacks(ctx)
    return path


def show_rollbacks(ui: UI) -> int:
    files = sorted(HOME.glob(ROLLBACK_GLOB), reverse=True)
    if not files:
        ui.step("note", "No rollback snapshots on disk.", YELLOW)
        return EXIT_OK
    rows = []
    for path in files:
        try:
            stat = path.stat()
            pins = sum(1 for line in path.read_text().splitlines() if line.strip())
        except OSError:
            continue
        when = datetime.datetime.fromtimestamp(stat.st_mtime)
        rows.append([
            when.strftime("%Y-%m-%d %H:%M:%S"),
            ui.c(str(pins), BOLD),
            ui.c(str(path), GREY),
        ])
    ui.blank()
    ui.step("note", f"{len(rows)} rollback snapshot(s)", BLUE)
    ui.table(["When", "Pins", "File"], rows, aligns="<><")
    ui.note("restore one with: pip install -r <file>")
    return EXIT_OK


# --------------------------------------------------------------------------
# Post-upgrade checks
# --------------------------------------------------------------------------

def run_audit(ctx: Ctx) -> tuple[bool, list[str]]:
    """Scan the environment for known vulnerabilities via pip-audit, if present.

    Returns (ran, findings)."""
    if ctx.args.dry_run:
        ctx.ui.note("[dry-run] would run pip-audit")
        return False, []
    probe = run(ctx, ctx.pip_cmd("show", "pip-audit"), timeout=60)
    if not probe.ok:
        ctx.ui.warn("pip-audit not installed — skipping. Install with: pip install pip-audit")
        return False, []
    with ctx.ui.status("Auditing for known vulnerabilities (pip-audit)",
                       live=not ctx.args.verbose) as st:
        res = run(ctx, [ctx.python, "-m", "pip_audit"], timeout=900)
        if res.ok:
            st.done("No known vulnerabilities found")
            return True, []
        findings = [line for line in (res.out or res.err).splitlines() if line.strip()]
        st.done(f"pip-audit reported {len(findings)} line(s) of findings",
                glyph="warn", color=YELLOW)
    for line in findings:
        ctx.ui.out(f"    {ctx.ui.c(line, YELLOW)}")
    log("pip-audit findings:\n" + "\n".join(findings))
    return True, findings


def export_freeze(ctx: Ctx, path: str) -> None:
    """Run pip freeze and write the result to a file."""
    if ctx.args.dry_run:
        ctx.ui.note(f"[dry-run] would export pip freeze to {path}")
        return
    with ctx.ui.status(f"Exporting pip freeze to {path}",
                       live=not ctx.args.verbose) as st:
        res = run(ctx, ctx.pip_cmd("freeze"), timeout=300)
        if not res.ok:
            st.done(f"Export failed: {res.message}", glyph="fail", color=RED)
            return
        try:
            Path(path).write_text(res.out)
        except OSError as exc:
            st.done(f"Export could not be written: {exc}", glyph="fail", color=RED)
            log(f"Freeze export failed: {exc}")
            return
        lines = sum(1 for line in res.out.splitlines() if line.strip())
        st.done(f"Exported {lines} requirement(s) to {path}")
    log(f"Freeze exported to {path}")


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
# Filtering and selection
# --------------------------------------------------------------------------

def matches_any(name: str, patterns: list[str]) -> bool:
    """Case-insensitive fnmatch against a list of glob patterns."""
    lowered = name.lower()
    return any(fnmatch.fnmatch(lowered, pat.lower()) for pat in patterns)


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


def select_packages(ui: UI, pkgs: list[Pkg]) -> list[Pkg]:
    """Interactive per-package selection against the numbered table above."""
    prompt = ui.c("Selection (e.g. 1,3,5-7 | all | none): ", CYAN, BOLD)
    while True:
        try:
            raw = input(prompt).strip().lower()
        except EOFError:
            return []
        if raw in ("all", "a", ""):
            return pkgs
        if raw in ("none", "n", "q"):
            return []
        idxs = parse_selection(raw, len(pkgs))
        if idxs is not None:
            return [pkgs[i] for i in idxs]
        ui.warn("Invalid selection, try again.")


def confirm(ui: UI, question: str) -> bool:
    try:
        return input(ui.c(question, CYAN, BOLD)).strip().lower() in ("y", "yes")
    except EOFError:
        return False


# --------------------------------------------------------------------------
# Installing
# --------------------------------------------------------------------------

def install_cmd(ctx: Ctx, names: list[str]) -> list[str]:
    """Build the upgrade command for pip, or for uv when --uv is in effect."""
    if ctx.use_uv_install:
        cmd = [ctx.uv, "pip", "install", "--upgrade"]
        if ctx.args.pre:
            cmd.append("--prerelease=allow")
        if ctx.args.only_binary:
            cmd.append("--only-binary=:all:")
        cmd += ["--python", ctx.python]
        return cmd + names
    cmd = ctx.pip_cmd("install", "--upgrade")
    if ctx.args.pre:
        cmd.append("--pre")
    if ctx.args.only_binary:
        cmd.append("--only-binary=:all:")
    return cmd + names


# Errors that will fail identically on every retry — retrying them only burns
# time and clutters the log.
PERMANENT_ERRORS = (
    "no matching distribution found",
    "could not find a version that satisfies",
    "externally-managed-environment",
    "requires a different python",
    "is not a supported wheel on this platform",
    "no such option",
    "invalid requirement",
    "permission denied",
    "read-only file system",
    "could not install packages due to an oserror",
)


def is_permanent(error: str) -> bool:
    low = error.lower()
    return any(marker in low for marker in PERMANENT_ERRORS)


def first_error_line(text: str) -> str:
    """Pull the most useful single line out of a pip traceback-ish blob."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in reversed(lines):
        if line.lower().startswith("error:"):
            return line
    return lines[-1] if lines else "unknown error"


def batch_upgrade(ctx: Ctx, pkgs: list[Pkg]) -> bool:
    """Try upgrading everything in one resolver run. Returns True on success.

    One resolver run is dramatically faster than N of them and is the only
    way the resolver can satisfy packages that constrain each other — but a
    single failure takes the whole batch down, hence the per-package fallback.
    """
    names = [p.name for p in pkgs]
    cmd = install_cmd(ctx, names)
    if ctx.args.dry_run:
        ctx.ui.note(f"[dry-run] {shlex.join(cmd)}")
        log(f"AUDIT: {shlex.join(cmd)} -> exit 0 (dry-run, not executed)")
        return True

    tool = "uv" if ctx.use_uv_install else "pip"
    with ctx.ui.status(f"Batch upgrade of {len(names)} package(s) in one {tool} "
                       f"resolver run", live=not ctx.args.verbose) as st:
        res = run(ctx, cmd, timeout=ctx.args.timeout * max(1, len(names)),
                  stream=ctx.args.verbose)
        if res.ok:
            st.done(f"Batch upgrade succeeded ({len(names)} package(s))")
            return True
        reason = "timed out" if res.rc == RC_TIMEOUT else first_error_line(res.message)
        st.done(f"Batch upgrade failed ({reason}) — isolating per package",
                glyph="warn", color=YELLOW)
    log(f"Batch upgrade failed: {res.message}")
    return False


def upgrade_one(ctx: Ctx, pkg: Pkg) -> tuple[bool, str]:
    """Upgrade a single package with bounded retries and backoff."""
    cmd = install_cmd(ctx, [pkg.name])
    if ctx.args.dry_run:
        ctx.ui.note(f"[dry-run] {shlex.join(cmd)}")
        log(f"AUDIT: {shlex.join(cmd)} -> exit 0 (dry-run, not executed)")
        return True, ""

    retries = ctx.args.retries
    error = ""
    for attempt in range(1, retries + 1):
        res = run(ctx, cmd, timeout=ctx.args.timeout, stream=ctx.args.verbose)
        if res.ok:
            return True, ""
        error = res.err.strip() or res.out.strip() or f"exit {res.rc}"
        if res.rc == RC_TIMEOUT:
            error = f"timed out after {ctx.args.timeout}s"
        elif is_permanent(error):
            log(f"Not retrying {pkg.name}: permanent error")
            return False, first_error_line(error)
        if attempt < retries:
            delay = min(8.0, 2.0 ** (attempt - 1))
            log(f"Retrying {pkg.name} in {delay:.0f}s (attempt {attempt + 1}/{retries})")
            time.sleep(delay)

    return False, first_error_line(error) if error else "unknown error"


# --------------------------------------------------------------------------
# Wheel prefetch pipeline
# --------------------------------------------------------------------------

class Prefetcher:
    """Warms pip's HTTP cache on a thread pool while installs run.

    Downloads are submitted in install order and the install loop waits only
    on the future for the package it is about to install, so the download of
    package N+1 overlaps the installation of package N.
    """

    def __init__(self, ctx: Ctx, dest: str):
        self.ctx = ctx
        self.dest = dest
        self.timeout = ctx.args.timeout
        self.pool = ThreadPoolExecutor(max_workers=max(1, ctx.args.jobs),
                                       thread_name_prefix="pm-fetch")
        self.futures: dict[str, Future] = {}

    def submit(self, pkgs: list[Pkg]) -> None:
        for pkg in pkgs:
            self.futures[pkg.name] = self.pool.submit(self._fetch, pkg)

    def _fetch(self, pkg: Pkg) -> Res:
        cmd = self.ctx.pip_cmd("download", "--no-deps", "--dest", self.dest)
        if self.ctx.args.pre:
            cmd.append("--pre")
        if self.ctx.args.only_binary:
            cmd.append("--only-binary=:all:")
        return run(self.ctx, cmd + [pkg.spec], timeout=self.timeout)

    def wait(self, pkg: Pkg) -> None:
        """Block until this package's download finishes; a failure is advisory
        because the install step fetches for itself anyway."""
        future = self.futures.get(pkg.name)
        if future is None:
            return
        try:
            future.result(timeout=self.timeout)
        except Exception as exc:  # noqa: BLE001 - a failed prefetch is advisory
            log(f"Prefetch failed for {pkg.name}: {exc}")

    def cancel(self) -> None:
        for future in self.futures.values():
            future.cancel()

    def shutdown(self) -> None:
        self.pool.shutdown(wait=False, cancel_futures=True)


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
        conflicts = rec.get("new_conflicts", rec.get("conflicts", []) or [])
        rows.append([
            str(rec.get("timestamp", "?"))[:19].replace("T", " "),
            ui.c(str(len(rec.get("upgraded", []) or [])), GREEN),
            ui.c(str(len(rec.get("failures", []) or [])), RED if rec.get("failures") else GREY),
            ui.c(str(len(conflicts)), YELLOW if conflicts else GREY),
            human_time(float(rec.get("elapsed_secs", 0) or 0)),
            ui.c(str(code), color),
        ])
    ui.blank()
    ui.step("note", f"Last {len(rows)} run(s) — {HISTORY_PATH}", BLUE)
    ui.table(["When", "Upgraded", "Failed", "Conflicts", "Elapsed", "Exit"],
             rows, aligns="<>>>><")
    return EXIT_OK


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="PakMan.py",
        description="PakMan: a graphical, fast, careful Python package updater.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"PakMan {VERSION}")

    sel = parser.add_argument_group("selection")
    sel.add_argument("-y", "--yes", action="store_true", help="Auto-approve upgrades")
    sel.add_argument("-i", "--interactive", action="store_true",
                     help="Pick packages to upgrade from a numbered list")
    sel.add_argument("--exclude", nargs="+", default=[], metavar="PKG",
                     help="Packages to exclude; glob patterns supported (e.g. --exclude 'boto*')")
    sel.add_argument("--only", nargs="+", default=[], metavar="PKG",
                     help="Upgrade only these packages; glob patterns supported")

    beh = parser.add_argument_group("behaviour")
    beh.add_argument("--check-only", action="store_true",
                     help="List outdated packages and exit (exit 3 if any found)")
    beh.add_argument("--dry-run", action="store_true",
                     help="Simulate commands without executing")
    beh.add_argument("--upgrade-pip", action="store_true",
                     help="Upgrade pip itself before upgrading packages")
    beh.add_argument("--pre", action="store_true",
                     help="Include pre-release versions when upgrading")
    beh.add_argument("--only-binary", action="store_true",
                     help="Refuse source distributions (pass --only-binary=:all:)")
    beh.add_argument("--require-venv", action="store_true",
                     help="Refuse to run outside a virtual environment")
    beh.add_argument("--audit", action="store_true",
                     help="Run pip-audit after upgrading (skipped if not installed)")
    beh.add_argument("--no-rollback", action="store_true",
                     help="Skip writing the rollback snapshot file")
    beh.add_argument("--no-batch", action="store_true",
                     help="Skip the batch upgrade attempt; go straight to per-package")
    beh.add_argument("--no-lock", action="store_true",
                     help="Allow concurrent PakMan runs (skips the instance lock)")
    beh.add_argument("--no-config", action="store_true", help=f"Ignore {CONFIG_PATH}")
    beh.add_argument("--export", metavar="FILE",
                     help="Run pip freeze after upgrading and save to FILE")
    beh.add_argument("--notify", action="store_true",
                     help="Send a macOS notification when done")

    perf = parser.add_argument_group("performance")
    perf.add_argument("--uv", action="store_true",
                      help="Use uv for the installs too, not just the outdated check "
                           "(much faster; requires uv on PATH)")
    perf.add_argument("--no-uv", action="store_true",
                      help="Don't use uv at all, even if installed")
    perf.add_argument("--jobs", type=int, default=6, metavar="N",
                      help="Parallel wheel-prefetch workers (1-16)")
    perf.add_argument("--no-prefetch", action="store_true",
                      help="Do not pre-download wheels in parallel")
    perf.add_argument("--retries", type=int, default=2, metavar="N",
                      help="Attempts per package before it is marked failed (min: 1)")
    perf.add_argument("--timeout", type=int, default=600, metavar="SECS",
                      help="Timeout per package (batch gets timeout x package count)")

    out = parser.add_argument_group("output")
    out.add_argument("--color", choices=("auto", "always", "never"), default="auto",
                     help="Colorise output")
    out.add_argument("--ascii", action="store_true",
                     help="ASCII-only output (no box drawing or emoji)")
    out.add_argument("-q", "--quiet", action="store_true",
                     help="Print only warnings and errors")
    out.add_argument("-v", "--verbose", action="store_true",
                     help="Stream raw pip output instead of progress indicators")
    out.add_argument("--json", action="store_true",
                     help="Output the outdated package list as JSON and exit")
    out.add_argument("--summary-json", action="store_true",
                     help="Print a machine-readable run summary to stdout when the run ends")
    out.add_argument("--log-json", action="store_true",
                     help=f"Append a structured JSON record per run to {HISTORY_PATH}")
    out.add_argument("--history", nargs="?", type=int, const=15, metavar="N",
                     help="Show the last N recorded runs and exit")
    out.add_argument("--rollbacks", action="store_true",
                     help="List the rollback snapshots on disk and exit")

    return parser


def make_ui(args: argparse.Namespace) -> UI:
    # A terminal with a non-UTF-8 encoding should lose a glyph, not the run.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError, OSError):
            pass
    # Machine-readable output owns stdout; the human UI moves to stderr.
    machine = args.json or args.summary_json
    return UI(
        stream=sys.stderr if machine else sys.stdout,
        color=args.color,
        force_ascii=args.ascii,
        quiet=args.quiet,
    )


def validate(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.interactive and args.yes:
        parser.error("--interactive and --yes are mutually exclusive")
    if args.interactive and args.quiet:
        parser.error("--interactive and --quiet are mutually exclusive")
    if args.uv and args.no_uv:
        parser.error("--uv and --no-uv are mutually exclusive")
    if args.retries < 1:
        parser.error("--retries must be at least 1")
    if args.timeout < 1:
        parser.error("--timeout must be at least 1")
    if not 1 <= args.jobs <= 16:
        parser.error("--jobs must be between 1 and 16")
    if args.history is not None and args.history < 1:
        parser.error("--history must be at least 1")
    if args.only and args.exclude:
        overlap = {p.lower() for p in args.only} & {p.lower() for p in args.exclude}
        if overlap:
            parser.error("package(s) appear in both --only and --exclude: "
                         + ", ".join(sorted(overlap)))


def _raise_interrupt(signum, frame) -> None:
    """Turn SIGTERM into the same KeyboardInterrupt path Ctrl-C already takes."""
    raise KeyboardInterrupt


# --------------------------------------------------------------------------
# Reporting helpers
# --------------------------------------------------------------------------

def outdated_table(ui: UI, pkgs: list[Pkg]) -> None:
    rows = []
    for i, p in enumerate(pkgs, 1):
        if p.is_sdist:
            kind = ui.c("sdist", YELLOW)
        elif p.filetype:
            kind = ui.c(p.filetype, GREY)
        else:
            kind = ui.c("?", GREY)
        rows.append([
            ui.c(str(i), GREY),
            ui.c(p.name, BOLD),
            ui.c(p.version, YELLOW),
            ui.c(p.latest, GREEN),
            kind,
        ])
    ui.table(["#", "Package", "Current", "Latest", "Type"], rows, aligns="><<<<")
    sdists = sum(1 for p in pkgs if p.is_sdist)
    if sdists:
        ui.note(f"{sdists} package(s) ship only a source distribution — "
                f"they build on install (--only-binary refuses them)")


def summary_panel(ui: UI, upgraded: list[str], failures: list[tuple[str, str]],
                  excluded: int, new_conflicts: list[str], elapsed: float,
                  rollback: Path | None, tool: str, interrupted: bool) -> None:
    if interrupted:
        title, color = "Interrupted", YELLOW
    elif failures:
        title, color = "Completed with failures", YELLOW
    elif new_conflicts:
        title, color = "Done, with new dependency conflicts", YELLOW
    else:
        title, color = "Done", GREEN

    def row(label: str, value: str, value_color: str = "") -> str:
        return f"{ui.c(pad(label, 14), GREY)}{ui.c(value, value_color)}"

    lines = [
        row("Upgraded", str(len(upgraded)), GREEN if upgraded else ""),
        row("Failed", str(len(failures)), RED if failures else ""),
    ]
    if excluded:
        lines.append(row("Excluded", str(excluded), YELLOW))
    if new_conflicts:
        lines.append(row("New conflicts", str(len(new_conflicts)), YELLOW))
    lines.append(row("Installer", tool))
    if rollback is not None:
        lines.append(row("Rollback", str(rollback)))
    lines.append(row("Elapsed", human_time(elapsed)))
    if _log_enabled:
        lines.append(row("Log", str(LOG_PATH)))
    ui.blank()
    ui.panel(title, lines, color=color)


def build_record(ctx: Ctx, upgraded: list[str], failures: list[tuple[str, str]],
                 excluded: int, all_conflicts: list[str], new_conflicts: list[str],
                 elapsed: float, rollback: Path | None, tool: str,
                 interrupted: bool, exit_code: int) -> dict:
    return {
        "version": VERSION,
        "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
        "python": ctx.python,
        "installer": tool,
        "upgraded": upgraded,
        "failures": [{"name": n, "error": e} for n, e in failures],
        "excluded": excluded,
        "conflicts": all_conflicts,
        "new_conflicts": new_conflicts,
        "rollback": str(rollback) if rollback else "",
        "elapsed_secs": round(elapsed, 1),
        "interrupted": interrupted,
        "exit_code": exit_code,
    }


def finish_reporting(ctx: Ctx, record: dict) -> None:
    if ctx.args.log_json and not ctx.args.dry_run:
        write_history(record)
    if ctx.args.summary_json:
        json.dump(record, sys.stdout, indent=2)
        sys.stdout.write("\n")
        sys.stdout.flush()


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
    if args.rollbacks:
        return show_rollbacks(ui)

    # Fail fast in cron/launchd instead of hanging on input()
    needs_tty = args.interactive or not (
        args.yes or args.dry_run or args.check_only or args.json
    )
    if needs_tty and not sys.stdin.isatty():
        ui.error("Non-interactive session and no -y/--yes flag; refusing to prompt.")
        return EXIT_FATAL

    # SIGTERM (launchd stopping the job) takes the same clean path as Ctrl-C.
    signal.signal(signal.SIGTERM, _raise_interrupt)

    start = time.monotonic()
    log(f"--- PakMan {VERSION} run started: {shlex.join(sys.argv[1:])} ---")

    uv = find_uv(args.no_uv)
    ctx = Ctx(ui, args, pip_env(), uv)

    sep = " · " if ui.uni else " | "
    facts = [
        ctx.python,
        "venv" if in_virtualenv() else "global",
        f"uv+pip" if ctx.use_uv_install else ("uv check" if uv else "pip"),
    ]
    if args.dry_run:
        facts.append("dry-run")
    ui.banner(f"PakMan {VERSION}", sep.join(facts))

    if args.uv and not uv:
        ui.warn("--uv requested but uv is not on PATH; falling back to pip.")

    if not check_environment(ui, args.require_venv):
        return EXIT_FATAL

    with single_instance(ui, enabled=not args.no_lock and not args.dry_run) as acquired:
        if not acquired:
            return EXIT_FATAL
        return run_upgrade(ctx, start)


def run_upgrade(ctx: Ctx, start: float) -> int:
    ui, args = ctx.ui, ctx.args
    live = not args.verbose
    tool = "uv" if ctx.use_uv_install else "pip"

    if args.upgrade_pip:
        with ui.status("Upgrading pip itself", live=live) as st:
            res = run(ctx, ctx.pip_cmd("install", "--upgrade", "pip"),
                      timeout=args.timeout, stream=args.verbose, dry=True)
            if res.ok:
                st.done("pip is up to date")
            else:
                # Not fatal: the packages we were asked to upgrade can still
                # be upgraded by the pip that is already installed.
                st.done(f"Could not upgrade pip: {first_error_line(res.message)}",
                        glyph="warn", color=YELLOW)
                log(f"pip self-upgrade failed (non-fatal): {res.message}")

    # -- outdated list, with a dependency-health baseline taken alongside it --
    baseline: list[str] = []
    with ui.status("Checking for outdated packages", live=live) as st:
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="pm-query") as pool:
            fut_outdated = pool.submit(get_outdated, ctx)
            # A conflict that already existed is not this run's fault; taking
            # the baseline now is free because it overlaps the slow query.
            fut_baseline = pool.submit(pip_check, ctx) if not args.dry_run else None
            outdated, source, error = fut_outdated.result()
            if fut_baseline is not None:
                baseline = fut_baseline.result()
        if error:
            st.done(f"Could not read the outdated list: {error}", glyph="fail", color=RED)
            log(f"FATAL: {error}")
            return EXIT_FATAL
        st.done(f"Found {len(outdated)} outdated package(s) (via {source})")

    if baseline:
        ui.note(f"{len(baseline)} pre-existing dependency conflict(s) — not caused by this run")

    # --json keeps its documented meaning: the outdated list, then exit.
    if args.json:
        json.dump([
            {"name": p.name, "version": p.version,
             "latest_version": p.latest, "latest_filetype": p.filetype}
            for p in outdated
        ], sys.stdout, indent=2)
        sys.stdout.write("\n")
        return EXIT_OK

    excluded = 0
    if args.only:
        before = len(outdated)
        outdated = [p for p in outdated if matches_any(p.name, args.only)]
        excluded += before - len(outdated)
    if args.exclude:
        before = len(outdated)
        outdated = [p for p in outdated if not matches_any(p.name, args.exclude)]
        dropped = before - len(outdated)
        excluded += dropped
        if dropped:
            ui.note(f"excluded {dropped} package(s) via --exclude")

    if not outdated:
        elapsed = time.monotonic() - start
        ui.blank()
        ui.panel("All packages are up to date", [
            f"{ui.c(pad('Excluded', 14), GREY)}{excluded}",
            f"{ui.c(pad('Elapsed', 14), GREY)}{human_time(elapsed)}",
        ], color=GREEN)
        log("Everything up to date. Run complete.")
        if args.notify:
            send_notification("PakMan", "All packages are up to date!")
        record = build_record(ctx, [], [], excluded, baseline, [], elapsed,
                              None, tool, False, EXIT_OK)
        finish_reporting(ctx, record)
        return EXIT_OK

    ui.blank()
    ui.step("search", f"{len(outdated)} outdated package(s)", BLUE)
    outdated_table(ui, outdated)

    if args.check_only:
        elapsed = time.monotonic() - start
        ui.note(f"check-only: nothing was upgraded ({human_time(elapsed)})")
        log(f"Check-only run: {len(outdated)} package(s) outdated.")
        return EXIT_OUTDATED

    # -- consent -----------------------------------------------------------
    if args.interactive:
        outdated = select_packages(ui, outdated)
        if not outdated:
            ui.note("nothing selected — upgrade canceled")
            return EXIT_OK
    elif not args.yes:
        if args.dry_run:
            ui.note("[dry-run] skipping confirmation prompt")
        elif not confirm(ui, f"\n{ui.g['bullet']} Upgrade these "
                             f"{len(outdated)} package(s)? (y/N): "):
            ui.note("upgrade canceled")
            return EXIT_OK

    # -- reject suspicious names before anything reaches a subprocess ------
    failures: list[tuple[str, str]] = []
    valid: list[Pkg] = []
    for pkg in outdated:
        if VALID_PKG.match(pkg.name):
            valid.append(pkg)
        else:
            failures.append((pkg.name, "invalid package name — skipped"))
            ui.error(f"Skipping invalid package name: {pkg.name!r}")
            log(f"SKIPPED invalid package name: {pkg.name!r}")
    if not valid:
        return EXIT_FAILURES

    rollback = None if args.no_rollback else write_rollback(ctx, valid)

    upgraded, interrupted = perform_upgrades(ctx, valid, failures)

    # -- post-upgrade health ----------------------------------------------
    all_conflicts: list[str] = []
    new_conflicts: list[str] = []
    audited: list[str] = []
    if not interrupted and not args.dry_run:
        with ui.status("Verifying dependencies (pip check)", live=live) as st:
            all_conflicts = pip_check(ctx)
            new_conflicts = [line for line in all_conflicts if line not in baseline]
            resolved = [line for line in baseline if line not in all_conflicts]
            if not all_conflicts:
                st.done("No broken dependencies")
            elif not new_conflicts:
                st.done(f"{len(all_conflicts)} pre-existing conflict(s), none new",
                        glyph="warn", color=YELLOW)
            else:
                st.done(f"{len(new_conflicts)} new dependency conflict(s) "
                        f"introduced by this run", glyph="fail", color=RED)
        for line in new_conflicts:
            ui.warn(line)
        if resolved:
            ui.ok(f"{len(resolved)} pre-existing conflict(s) resolved by this run")
        if new_conflicts and rollback is not None:
            ui.note(f"undo with: pip install -r {rollback}")
        for line in new_conflicts:
            log(f"NEW CONFLICT: {line}")

        if args.audit:
            _, audited = run_audit(ctx)
        if args.export:
            export_freeze(ctx, args.export)
    elif not interrupted and args.dry_run:
        ui.note("[dry-run] would verify dependencies with pip check")
        if args.audit:
            run_audit(ctx)
        if args.export:
            export_freeze(ctx, args.export)

    elapsed = time.monotonic() - start

    if failures:
        if ui.quiet:
            # --quiet still owes the caller its warnings and errors.
            for name, error in failures:
                ui.error(f"{name}: {error or 'unknown error'}")
        else:
            ui.blank()
            ui.step("warn", "Failures", YELLOW)
            ui.table(["Package", "Error"],
                     [[ui.c(n, BOLD), e or "unknown error"] for n, e in failures])

    if interrupted:
        exit_code = EXIT_INTERRUPT
    elif failures:
        exit_code = EXIT_FAILURES
    else:
        exit_code = EXIT_OK

    summary_panel(ui, upgraded, failures, excluded, new_conflicts, elapsed,
                  rollback, tool, interrupted)

    if args.notify:
        if failures:
            send_notification("PakMan", f"Done with {len(failures)} failure(s). Check the log.")
        elif interrupted:
            send_notification("PakMan", "Run interrupted.")
        elif new_conflicts:
            send_notification("PakMan", f"{len(upgraded)} upgraded, "
                                        f"{len(new_conflicts)} new conflict(s).")
        else:
            send_notification("PakMan", f"{len(upgraded)} package(s) upgraded successfully!")

    log(f"Run complete: {len(upgraded)} upgraded, {len(failures)} failed, "
        f"{len(new_conflicts)} new conflict(s), elapsed {elapsed:.1f}s, exit {exit_code}")

    record = build_record(ctx, upgraded, failures, excluded, all_conflicts,
                          new_conflicts, elapsed, rollback, tool, interrupted, exit_code)
    if audited:
        record["audit_findings"] = audited
    finish_reporting(ctx, record)
    return exit_code


def perform_upgrades(ctx: Ctx, pkgs: list[Pkg],
                     failures: list[tuple[str, str]]) -> tuple[list[str], bool]:
    """Batch first, then per-package with a pipelined prefetch on fallback."""
    ui, args = ctx.ui, ctx.args
    upgraded: list[str] = []

    ui.blank()
    ui.step("up", f"Upgrading {len(pkgs)} package(s)", BLUE)

    try:
        if not args.no_batch and batch_upgrade(ctx, pkgs):
            for pkg in pkgs:
                log(f"Upgraded (batch): {pkg.name} {pkg.version} -> {pkg.latest}")
            return [p.name for p in pkgs], False
    except KeyboardInterrupt:
        ui.blank()
        ui.warn("Interrupted during the batch upgrade — nothing recorded as upgraded.")
        log("Run interrupted during batch upgrade.")
        return upgraded, True

    # uv resolves and downloads in parallel already; prefetching for it would
    # only warm a cache it does not read.
    prefetch = not args.no_prefetch and not args.dry_run and not ctx.use_uv_install
    tmpdir = tempfile.TemporaryDirectory(prefix="pakman_prefetch_") if prefetch else None
    fetcher = Prefetcher(ctx, tmpdir.name) if tmpdir else None
    if fetcher is not None:
        fetcher.submit(pkgs)

    bar = ui.progress(len(pkgs), "upgrading", live=not args.verbose)
    interrupted = False
    try:
        with bar:
            for pkg in pkgs:
                bar.set_current(pkg.name)
                if fetcher is not None:
                    fetcher.wait(pkg)
                t0 = time.monotonic()
                success, error = upgrade_one(ctx, pkg)
                took = time.monotonic() - t0
                if success:
                    upgraded.append(pkg.name)
                    log(f"Upgraded: {pkg.name} {pkg.version} -> {pkg.latest}")
                    bar.advance(
                        f"  {ui.c(ui.g['ok'], GREEN)} {ui.c(pad(pkg.name, 28), BOLD)}"
                        f" {ui.c(pkg.version, GREY)} {ui.g['arrow']} "
                        f"{ui.c(pkg.latest, GREEN)} {ui.c(f'({took:.1f}s)', GREY)}"
                    )
                else:
                    failures.append((pkg.name, error))
                    log(f"FAILED: {pkg.name} — {error}")
                    bar.advance(
                        f"  {ui.c(ui.g['fail'], RED)} {ui.c(pad(pkg.name, 28), BOLD)}"
                        f" {ui.c(clip(error, 60), RED)}"
                    )
    except KeyboardInterrupt:
        interrupted = True
        remaining = max(0, len(pkgs) - len(upgraded) - len(failures))
        ui.blank()
        ui.warn(f"Interrupted — {len(upgraded)} upgraded, {len(failures)} failed, "
                f"{remaining} not attempted.")
        log(f"Run interrupted: {len(upgraded)} upgraded, {len(failures)} failed, "
            f"{remaining} not attempted.")
    finally:
        if fetcher is not None:
            fetcher.cancel()
            fetcher.shutdown()
        if tmpdir is not None:
            tmpdir.cleanup()

    return upgraded, interrupted


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.stderr.write("\nInterrupted.\n")
        log("Run interrupted by user.")
        sys.exit(EXIT_INTERRUPT)
    except BrokenPipeError:
        os._exit(EXIT_OK)
