#!/usr/bin/env python3
"""
HistClean — inspect, audit and clear shell history, carefully.
--------------------------------------------------------------
Author :  Anirban Bagchi

Finds the history files your shells and REPLs actually use, shows you what is
in them, flags entries that look like leaked credentials, and removes entries
either wholesale or one pattern at a time — taking a compressed 0600 backup
before it changes anything.

Python 3.10+, standard library only.
"""

from __future__ import annotations

import argparse
import datetime
import fnmatch
import gzip
import json
import logging
import logging.handlers
import os
import re
import shutil
import signal
import stat
import sys
import threading
import time
import unicodedata
from collections import Counter
from pathlib import Path

VERSION = "2.0.0"

HOME = Path.home()
LOG_PATH = HOME / ".histclean.log"
BACKUP_DIR = HOME / ".histclean_backups"
CONFIG_PATH = HOME / ".histcleanrc.json"

MAX_BACKUPS = 10            # per history file
LOG_MAX_BYTES = 1024 * 1024
LOG_BACKUPS = 2
SHRED_PASSES = 1            # overwrite passes before truncation

# Exit codes for scripting/cron use
EXIT_OK = 0          # success, nothing to do or everything applied
EXIT_FATAL = 1       # unrecoverable error (bad arguments, nothing to act on)
EXIT_FAILURES = 2    # run completed but one or more files failed
EXIT_FOUND = 3       # --scan found something (mirrors grep's "matched")
EXIT_INTERRUPT = 130 # Ctrl-C / SIGTERM

# History files are private by definition; anything looser is worth reporting.
SAFE_MODE = 0o600
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
    "logo": "\U0001f9f9", "down": "⬇", "up": "⬆", "broom": "\U0001f9f9",
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


# --------------------------------------------------------------------------
# History files: discovery, parsing, rewriting
# --------------------------------------------------------------------------

class Entry:
    """One history event, keeping the exact bytes it came from.

    `raw` is what gets written back, so rewriting a file after dropping some
    entries leaves every surviving entry byte-identical to what the shell
    wrote — no reformatting, no lost escapes, no mangled non-UTF-8.
    """

    __slots__ = ("command", "when", "raw", "lineno")

    def __init__(self, command: str, when: int | None, raw: str, lineno: int):
        self.command = command
        self.when = when
        self.raw = raw
        self.lineno = lineno

    @property
    def stamp(self) -> str:
        if self.when is None:
            return ""
        try:
            return datetime.datetime.fromtimestamp(self.when).strftime("%Y-%m-%d %H:%M")
        except (OverflowError, OSError, ValueError):
            return ""


# zsh EXTENDED_HISTORY: ": <start>:<elapsed>;<command>", command may continue
# onto following lines when it ends with a backslash.
ZSH_META = re.compile(r"^: (\d+):(\d+);(.*)$", re.DOTALL)
# bash with HISTTIMEFORMAT writes a "#<epoch>" line before each command.
BASH_STAMP = re.compile(r"^#(\d{9,})$")
# fish history is a YAML-ish record list.
FISH_CMD = re.compile(r"^- cmd: (.*)$")
FISH_WHEN = re.compile(r"^\s+when: (\d+)\s*$")


def _read_text(path: Path) -> str:
    """Read a history file without losing bytes that are not valid UTF-8.

    zsh metafies high bytes and plenty of history files contain stray encodings;
    surrogateescape round-trips them exactly on the way back out.
    """
    return path.read_bytes().decode("utf-8", errors="surrogateescape")


def _write_text(path: Path, text: str) -> None:
    path.write_bytes(text.encode("utf-8", errors="surrogateescape"))


def parse_zsh(text: str) -> list[Entry]:
    entries: list[Entry] = []
    lines = text.splitlines(keepends=True)
    i = 0
    while i < len(lines):
        start = i
        block = lines[i]
        # A trailing backslash continues the command onto the next line.
        while block.rstrip("\n").endswith("\\") and i + 1 < len(lines):
            i += 1
            block += lines[i]
        i += 1
        body = block.rstrip("\n")
        match = ZSH_META.match(body)
        if match:
            when = int(match.group(1))
            command = match.group(3)
        else:
            when, command = None, body
        if not command.strip() and not body.strip():
            continue
        entries.append(Entry(command, when, block, start + 1))
    return entries


def parse_plain(text: str) -> list[Entry]:
    """bash and the REPL histories: one command per line, optional #epoch lines."""
    entries: list[Entry] = []
    pending_when: int | None = None
    pending_raw = ""
    for lineno, line in enumerate(text.splitlines(keepends=True), 1):
        body = line.rstrip("\n")
        match = BASH_STAMP.match(body)
        if match:
            pending_when = int(match.group(1))
            pending_raw = line
            continue
        if not body.strip():
            pending_when, pending_raw = None, ""
            continue
        entries.append(Entry(body, pending_when, pending_raw + line, lineno))
        pending_when, pending_raw = None, ""
    return entries


def parse_fish(text: str) -> list[Entry]:
    entries: list[Entry] = []
    lines = text.splitlines(keepends=True)
    i = 0
    while i < len(lines):
        match = FISH_CMD.match(lines[i].rstrip("\n"))
        if not match:
            i += 1
            continue
        start, block, when = i, lines[i], None
        i += 1
        # Consume the indented continuation lines belonging to this record.
        while i < len(lines) and (lines[i].startswith(" ") or lines[i].startswith("\t")):
            stamp = FISH_WHEN.match(lines[i].rstrip("\n"))
            if stamp:
                when = int(stamp.group(1))
            block += lines[i]
            i += 1
        entries.append(Entry(match.group(1), when, block, start + 1))
    return entries


PARSERS = {"zsh": parse_zsh, "plain": parse_plain, "fish": parse_fish}


class HistoryFile:
    """A history file on disk, plus everything we know about it."""

    def __init__(self, label: str, path: Path, fmt: str, kind: str, source: str = ""):
        self.label = label
        self.path = path
        self.fmt = fmt
        self.kind = kind          # "shell" or "tool"
        self.source = source      # how the path was determined
        self._entries: list[Entry] | None = None
        self.error = ""

    @property
    def exists(self) -> bool:
        return self.path.is_file()

    @property
    def size(self) -> int:
        try:
            return self.path.stat().st_size
        except OSError:
            return 0

    @property
    def mode(self) -> int:
        try:
            return stat.S_IMODE(self.path.stat().st_mode)
        except OSError:
            return 0

    @property
    def insecure(self) -> bool:
        """True when anyone but the owner can read the file."""
        return bool(self.exists and self.mode & 0o077)

    @property
    def modified(self) -> str:
        try:
            return datetime.datetime.fromtimestamp(
                self.path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        except OSError:
            return ""

    def entries(self) -> list[Entry]:
        if self._entries is None:
            if not self.exists:
                self._entries = []
            else:
                try:
                    self._entries = PARSERS[self.fmt](_read_text(self.path))
                except OSError as exc:
                    self.error = str(exc)
                    self._entries = []
        return self._entries

    def invalidate(self) -> None:
        self._entries = None

    def rewrite(self, keep: list[Entry]) -> None:
        """Write back only `keep`, preserving each entry's original bytes."""
        _write_text(self.path, "".join(e.raw for e in keep))
        os.chmod(self.path, SAFE_MODE)
        self.invalidate()


def _env_path(*names: str) -> tuple[Path | None, str]:
    for name in names:
        value = os.environ.get(name)
        if value:
            return Path(value).expanduser(), f"${name}"
    return None, ""


def discover(include_tools: bool) -> list[HistoryFile]:
    """Find the history files this machine actually uses.

    $HISTFILE and $ZDOTDIR are honoured before the conventional paths, because
    a tool that clears ~/.zsh_history while the shell writes somewhere else is
    worse than useless — it reports success having deleted nothing.
    """
    found: list[HistoryFile] = []
    shell = Path(os.environ.get("SHELL", "")).name

    histfile, hist_src = _env_path("HISTFILE")

    # zsh
    zdotdir = os.environ.get("ZDOTDIR")
    if histfile is not None and shell == "zsh":
        zsh_path, zsh_src = histfile, hist_src
    elif zdotdir:
        zsh_path, zsh_src = Path(zdotdir).expanduser() / ".zsh_history", "$ZDOTDIR"
    else:
        zsh_path, zsh_src = HOME / ".zsh_history", "default"
    found.append(HistoryFile("zsh", zsh_path, "zsh", "shell", zsh_src))

    # bash
    if histfile is not None and shell == "bash":
        bash_path, bash_src = histfile, hist_src
    else:
        bash_path, bash_src = HOME / ".bash_history", "default"
    found.append(HistoryFile("bash", bash_path, "plain", "shell", bash_src))

    # fish
    data_home = os.environ.get("XDG_DATA_HOME")
    fish_root = Path(data_home).expanduser() if data_home else HOME / ".local" / "share"
    found.append(HistoryFile("fish", fish_root / "fish" / "fish_history",
                             "fish", "shell", "XDG data dir"))

    if include_tools:
        for label, rel in (
            ("python", ".python_history"),
            ("node", ".node_repl_history"),
            ("sqlite", ".sqlite_history"),
            ("psql", ".psql_history"),
            ("mysql", ".mysql_history"),
            ("redis", ".rediscli_history"),
            ("irb", ".irb_history"),
            ("less", ".lesshst"),
        ):
            found.append(HistoryFile(label, HOME / rel, "plain", "tool", "default"))

    return found


def select_files(files: list[HistoryFile], wanted: list[str],
                 existing_only: bool = True) -> list[HistoryFile]:
    """Filter by label. 'all' (or nothing) means every discovered file."""
    if wanted and "all" not in wanted:
        lowered = {w.lower() for w in wanted}
        files = [f for f in files if f.label.lower() in lowered]
    return [f for f in files if f.exists] if existing_only else files


# --------------------------------------------------------------------------
# Credential scanning
# --------------------------------------------------------------------------

class Rule:
    """One secret-shaped pattern. `group` names the part that is the secret."""

    __slots__ = ("name", "regex", "group", "hint")

    def __init__(self, name: str, pattern: str, group: int = 0, hint: str = "",
                 flags: int = re.IGNORECASE):
        self.name = name
        self.regex = re.compile(pattern, flags)
        self.group = group
        self.hint = hint


RULES: list[Rule] = [
    Rule("aws-access-key", r"\b(AKIA|ASIA)[0-9A-Z]{16}\b", 0,
         "rotate in IAM", flags=0),
    Rule("aws-secret-key", r"(?<![A-Za-z0-9])aws_secret_access_key\s*[=:]\s*['\"]?([A-Za-z0-9/+=]{30,})", 1,
         "rotate in IAM"),
    Rule("github-token", r"\bgh[pousr]_[A-Za-z0-9]{30,}\b", 0,
         "revoke at github.com/settings/tokens", flags=0),
    Rule("slack-token", r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b", 0, "revoke in Slack"),
    Rule("anthropic-key", r"\bsk-ant-[A-Za-z0-9_-]{20,}\b", 0, "revoke in the console", flags=0),
    Rule("openai-key", r"\bsk-(?!ant-)[A-Za-z0-9_-]{20,}\b", 0, "revoke in the console", flags=0),
    Rule("google-api-key", r"\bAIza[0-9A-Za-z_-]{35}\b", 0, "revoke in GCP", flags=0),
    Rule("jwt", r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}", 0,
         "may embed claims", flags=0),
    Rule("private-key", r"BEGIN\s+(?:RSA|DSA|EC|OPENSSH|PGP)?\s*PRIVATE KEY", 0,
         "the key material itself may be in scrollback"),
    Rule("url-credentials", r"\b[a-z][a-z0-9+.-]*://[^\s/:@]+:([^\s/@]+)@", 1,
         "password embedded in a URL"),
    # (?<![A-Za-z0-9]) rather than \b: an underscore is a word character, so
    # \b never fires inside AWS_SECRET_ACCESS_KEY or DB_PASSWORD.
    Rule("assigned-secret",
         r"(?<![A-Za-z0-9])(?:password|passwd|pwd|secret|token|api[_-]?key|apikey|access[_-]?key|auth[_-]?token|client[_-]?secret|passphrase)\s*[=:]\s*['\"]?([^\s'\"]{6,})", 1,
         "assignment on the command line"),
    Rule("curl-basic-auth", r"\bcurl\b[^\n]*?\s-{1,2}u(?:ser)?[= ]['\"]?([^\s'\"]+:[^\s'\"]+)", 1,
         "credentials passed to curl"),
    Rule("auth-header", r"Authorization:\s*(?:Bearer|Basic|Token)\s+([A-Za-z0-9._~+/=-]{12,})", 1,
         "bearer token in a header"),
    Rule("mysql-password", r"\bmysql\b[^\n]*?\s-p(\S+)", 1, "password on the mysql command line"),
    Rule("pgpassword", r"\bPGPASSWORD\s*=\s*['\"]?([^\s'\"]+)", 1, "postgres password in the environment"),
    Rule("ssh-passphrase", r"\bssh-keygen\b[^\n]*?\s-N\s+['\"]?([^\s'\"]{1,})", 1, "key passphrase"),
    Rule("base64-blob", r"\b(?:echo|printf)\s+['\"]?([A-Za-z0-9+/]{60,}={0,2})['\"]?\s*\|\s*base64\s+-{1,2}d", 1,
         "encoded payload, not encrypted"),
]


class Finding:
    __slots__ = ("file", "entry", "rule", "secret")

    def __init__(self, file: "HistoryFile", entry: Entry, rule: Rule, secret: str):
        self.file = file
        self.entry = entry
        self.rule = rule
        self.secret = secret


def entry_secrets(command: str) -> list[str]:
    """Every secret-shaped substring in a command, honouring each rule's group."""
    found: list[str] = []
    for rule in RULES:
        for match in rule.regex.finditer(command):
            try:
                found.append(match.group(rule.group) or match.group(0))
            except (IndexError, re.error):
                found.append(match.group(0))
    return found


def flatten(command: str) -> str:
    """Collapse a multi-line history entry onto one line for display.

    A zsh continuation entry contains real newlines; printed straight into a
    table cell they break every border below them.
    """
    parts = [p.strip() for p in command.splitlines()]
    joined = " ".join(p for p in parts if p)
    return joined.replace("\t", " ")


def mask(secret: str) -> str:
    """Show just enough to recognise the value without reprinting it."""
    if len(secret) <= 4:
        return "*" * len(secret)
    keep = 2 if len(secret) < 12 else 4
    return f"{secret[:keep]}{'*' * 6}{secret[-2:]} ({len(secret)} chars)"


def redact_command(command: str, secrets: list[str], reveal: bool) -> str:
    if reveal:
        return command
    out = command
    for secret in sorted(set(secrets), key=len, reverse=True):
        if secret:
            out = out.replace(secret, mask(secret))
    return out


def scan_entries(hist: "HistoryFile", entries: list[Entry]) -> list[Finding]:
    findings: list[Finding] = []
    for entry in entries:
        for rule in RULES:
            for match in rule.regex.finditer(entry.command):
                try:
                    secret = match.group(rule.group) or match.group(0)
                except (IndexError, re.error):
                    secret = match.group(0)
                findings.append(Finding(hist, entry, rule, secret))
    return dedupe_findings(findings)


def display_command(command: str, reveal: bool) -> str:
    """One-line, secret-masked rendering of a command, for any table or preview."""
    return redact_command(flatten(command), entry_secrets(command), reveal)


def dedupe_findings(findings: list[Finding]) -> list[Finding]:
    """One finding per (entry, value). RULES are ordered specific-first, so the
    first rule to match is the one worth naming."""
    seen: set[tuple[int, str]] = set()
    unique: list[Finding] = []
    for finding in findings:
        key = (id(finding.entry), finding.secret)
        if key in seen:
            continue
        seen.add(key)
        unique.append(finding)
    return unique


def secret_entry_ids(findings: list[Finding]) -> set[int]:
    return {id(f.entry) for f in findings}


# --------------------------------------------------------------------------
# Backups
# --------------------------------------------------------------------------

def ensure_backup_dir() -> bool:
    try:
        BACKUP_DIR.mkdir(mode=0o700, exist_ok=True)
        os.chmod(BACKUP_DIR, 0o700)
        return True
    except OSError as exc:
        log(f"Backup directory unavailable: {exc}")
        return False


def backup_path_for(label: str) -> Path:
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    return BACKUP_DIR / f"{label}_{stamp}.gz"


def list_backups(label: str | None = None) -> list[Path]:
    if not BACKUP_DIR.is_dir():
        return []
    pattern = f"{label}_*.gz" if label else "*.gz"
    return sorted(BACKUP_DIR.glob(pattern), reverse=True)


def prune_backups(ui: UI, label: str, keep: int = MAX_BACKUPS) -> None:
    for old in list_backups(label)[keep:]:
        try:
            old.unlink()
        except OSError as exc:
            ui.warn(f"Could not prune {old.name}: {exc}")
            continue
        log(f"Pruned old backup: {old}")


def backup_file(ui: UI, hist: HistoryFile, dry_run: bool) -> Path | None:
    """Compress the current file into the backup directory before touching it."""
    if dry_run:
        ui.note(f"[dry-run] would back up {hist.label} first")
        return None
    if not ensure_backup_dir():
        ui.warn(f"Could not create {BACKUP_DIR}; refusing to change {hist.label} "
                f"without a backup (use --no-backup to override).")
        return None
    dest = backup_path_for(hist.label)
    try:
        raw = hist.path.read_bytes()
        with gzip.open(dest, "wb") as fh:
            fh.write(raw)
        os.chmod(dest, SAFE_MODE)
    except OSError as exc:
        ui.warn(f"Backup of {hist.label} failed: {exc}")
        log(f"Backup failed for {hist.path}: {exc}")
        return None
    log(f"Backed up {hist.path} -> {dest} ({len(raw)} bytes)")
    prune_backups(ui, hist.label)
    return dest


def restore_backup(ui: UI, archive: Path, target: HistoryFile, dry_run: bool) -> bool:
    if dry_run:
        ui.note(f"[dry-run] would restore {archive.name} -> {target.path}")
        return True
    try:
        with gzip.open(archive, "rb") as fh:
            data = fh.read()
    except (OSError, gzip.BadGzipFile) as exc:
        ui.error(f"Could not read {archive.name}: {exc}")
        return False
    # The file being replaced is itself worth keeping.
    if target.exists:
        backup_file(ui, target, dry_run=False)
    try:
        target.path.write_bytes(data)
        os.chmod(target.path, SAFE_MODE)
    except OSError as exc:
        ui.error(f"Could not write {target.path}: {exc}")
        return False
    target.invalidate()
    log(f"Restored {archive} -> {target.path} ({len(data)} bytes)")
    return True


# --------------------------------------------------------------------------
# Destructive primitives
# --------------------------------------------------------------------------

def shred_file(path: Path, passes: int = SHRED_PASSES) -> bool:
    """Overwrite the file's bytes in place before truncating it.

    On a copy-on-write filesystem (APFS) or an SSD with wear levelling this
    does NOT guarantee the old blocks are gone — callers must say so rather
    than promise an erase they cannot deliver.
    """
    try:
        size = path.stat().st_size
        if size:
            with open(path, "r+b") as fh:
                for _ in range(max(1, passes)):
                    fh.seek(0)
                    fh.write(os.urandom(size))
                    fh.flush()
                    os.fsync(fh.fileno())
        return True
    except OSError as exc:
        log(f"Shred failed for {path}: {exc}")
        return False


def truncate_file(path: Path) -> None:
    with open(path, "wb"):
        pass
    os.chmod(path, SAFE_MODE)


# --------------------------------------------------------------------------
# Matching helpers
# --------------------------------------------------------------------------

def build_matcher(patterns: list[str], use_regex: bool):
    """Return a predicate over command text.

    Substring (case-insensitive) by default, because the common need is
    "forget everything that mentions this token"; --regex switches to a
    proper pattern match.
    """
    if use_regex:
        compiled = [re.compile(p, re.IGNORECASE) for p in patterns]
        return lambda cmd: any(c.search(cmd) for c in compiled)
    lowered = [p.lower() for p in patterns]
    def match(cmd: str) -> bool:
        low = cmd.lower()
        return any(p in low or fnmatch.fnmatch(low, p) for p in lowered)
    return match


def top_commands(entries: list[Entry], limit: int = 10) -> list[tuple[str, int]]:
    """Most-used command words (the first token, minus common wrappers)."""
    counter: Counter[str] = Counter()
    skip = {"sudo", "command", "time", "nohup", "env", "exec", "nice", "doas"}
    for entry in entries:
        for token in entry.command.strip().split():
            word = token.strip()
            if not word or word.startswith("-"):
                continue
            if word in skip:
                continue
            counter[word] += 1
            break
    return counter.most_common(limit)


def date_span(entries: list[Entry]) -> tuple[str, str]:
    stamps = [e.when for e in entries if e.when]
    if not stamps:
        return "", ""
    fmt = "%Y-%m-%d"
    try:
        return (datetime.datetime.fromtimestamp(min(stamps)).strftime(fmt),
                datetime.datetime.fromtimestamp(max(stamps)).strftime(fmt))
    except (OverflowError, OSError, ValueError):
        return "", ""


# --------------------------------------------------------------------------
# Shell state guidance
# --------------------------------------------------------------------------

def running_shell_warning(ui: UI, labels: list[str]) -> None:
    """A cleared file is refilled by any shell still holding it in memory.

    This is the failure everyone hits: clear the file, close the terminal, and
    the history is back, because the exiting shell wrote its in-memory copy
    over the top.
    """
    shell = Path(os.environ.get("SHELL", "")).name
    touched = {l for l in labels if l in ("zsh", "bash", "fish")}
    if not touched:
        return
    ui.blank()
    ui.warn("Shells already running still hold their history in memory.")
    ui.note("any open session will write its copy back over the file when it exits")
    if "zsh" in touched:
        ui.note("zsh — drop the in-memory list in each open session:  HISTSIZE=0; HISTSIZE=10000")
    if "bash" in touched:
        ui.note("bash — drop the in-memory list in each open session:  history -c")
    if "fish" in touched:
        ui.note("fish — drop the in-memory list in each open session:  history clear")
    ui.note(f"surest route: close every other terminal first (current shell: {shell or 'unknown'})")


# --------------------------------------------------------------------------
# Context and shared plumbing
# --------------------------------------------------------------------------

class Ctx:
    def __init__(self, ui: UI, args: argparse.Namespace):
        self.ui = ui
        self.args = args
        self.failures: list[str] = []
        self.changed: list[str] = []


def confirm(ui: UI, question: str, strict: bool = False) -> bool:
    """Ask before destroying something. `strict` demands the whole word 'yes'."""
    suffix = "(type 'yes'): " if strict else "(y/N): "
    try:
        answer = input(ui.c(f"{question} {suffix}", CYAN, BOLD)).strip().lower()
    except EOFError:
        return False
    return answer == "yes" if strict else answer in ("y", "yes")


def preview_entries(ui: UI, entries: list[Entry], limit: int, reveal: bool) -> None:
    shown = entries[:limit]
    for entry in shown:
        text = display_command(entry.command, reveal)
        stamp = ui.c(entry.stamp or "—", GREY)
        ui.out(f"    {stamp}  {clip(text, max(20, ui.width - 24))}")
    if len(entries) > limit:
        ui.note(f"...and {len(entries) - limit} more")


def apply_removal(ctx: Ctx, hist: HistoryFile, keep: list[Entry],
                  dropped: list[Entry], verb: str) -> bool:
    """Preview, confirm, back up, then rewrite a history file."""
    ui, args = ctx.ui, ctx.args
    if not dropped:
        ui.note(f"{hist.label}: nothing to {verb}")
        return False

    ui.out(f"  {ui.c(hist.label, BOLD)}: {ui.c(str(len(dropped)), YELLOW)} of "
           f"{len(keep) + len(dropped)} entries would be removed")
    preview_entries(ui, dropped, args.limit, args.show_secrets)

    if not args.yes and not args.dry_run:
        if not confirm(ui, f"  Remove {len(dropped)} entr"
                           f"{'y' if len(dropped) == 1 else 'ies'} from {hist.label}?"):
            ui.note(f"{hist.label}: skipped")
            return False

    if args.dry_run:
        ui.note(f"[dry-run] {hist.label}: would keep {len(keep)}, remove {len(dropped)}")
        return False

    if not args.no_backup:
        if backup_file(ui, hist, dry_run=False) is None and not args.yes:
            ui.warn(f"{hist.label}: no backup taken — skipping (use --no-backup to proceed anyway)")
            ctx.failures.append(hist.label)
            return False
    try:
        hist.rewrite(keep)
    except OSError as exc:
        ui.error(f"{hist.label}: could not rewrite {hist.path}: {exc}")
        log(f"FAILED rewrite {hist.path}: {exc}")
        ctx.failures.append(hist.label)
        return False

    ui.ok(f"{hist.label}: removed {len(dropped)}, kept {len(keep)}")
    log(f"{verb}: {hist.path} removed {len(dropped)} kept {len(keep)}")
    ctx.changed.append(hist.label)
    return True


# --------------------------------------------------------------------------
# Read-only actions
# --------------------------------------------------------------------------

def act_list(ctx: Ctx, files: list[HistoryFile]) -> int:
    ui = ctx.ui
    rows = []
    for hist in files:
        if hist.exists:
            entries = hist.entries()
            perm = (ui.c(f"{hist.mode:04o}", RED) if hist.insecure
                    else ui.c(f"{hist.mode:04o}", GREY))
            rows.append([
                ui.c(hist.label, BOLD),
                str(len(entries)),
                human_size(hist.size),
                perm,
                hist.modified,
                ui.c(str(hist.path), GREY),
            ])
        else:
            rows.append([ui.c(hist.label, GREY), ui.c("—", GREY), ui.c("—", GREY),
                         ui.c("—", GREY), ui.c("not present", GREY),
                         ui.c(str(hist.path), GREY)])
    ui.blank()
    ui.step("search", f"{sum(1 for f in files if f.exists)} history file(s) found", BLUE)
    ui.table(["Shell/Tool", "Entries", "Size", "Mode", "Modified", "Path"],
             rows, aligns="<>><<<")
    insecure = [f for f in files if f.insecure]
    if insecure:
        ui.warn(f"{len(insecure)} file(s) readable by other users — fix with --fix-perms")
    return EXIT_OK


def act_show(ctx: Ctx, files: list[HistoryFile]) -> int:
    ui, args = ctx.ui, ctx.args
    for hist in files:
        entries = hist.entries()
        if not entries:
            ui.note(f"{hist.label}: empty")
            continue
        recent = entries[-args.limit:]
        ui.blank()
        ui.step("note", f"{hist.label}: last {len(recent)} of {len(entries)} entries", BLUE)
        rows = []
        for entry in recent:
            flagged = bool(entry_secrets(entry.command))
            rows.append([ui.c(entry.stamp or "—", GREY),
                         ui.c(display_command(entry.command, args.show_secrets),
                              YELLOW if flagged else "")])
        ui.table(["When", "Command"], rows)
    return EXIT_OK


def act_stats(ctx: Ctx, files: list[HistoryFile]) -> int:
    ui = ctx.ui
    for hist in files:
        entries = hist.entries()
        if not entries:
            ui.note(f"{hist.label}: empty")
            continue
        first, last = date_span(entries)
        unique = len({e.command for e in entries})
        findings = scan_entries(hist, entries)
        lines = [
            f"{ui.c(pad('Entries', 14), GREY)}{len(entries)}",
            f"{ui.c(pad('Unique', 14), GREY)}{unique} "
            f"{ui.c(f'({100 * unique // max(1, len(entries))}%)', GREY)}",
            f"{ui.c(pad('Size', 14), GREY)}{human_size(hist.size)}",
        ]
        if first:
            lines.append(f"{ui.c(pad('Span', 14), GREY)}{first} to {last}")
        if findings:
            lines.append(f"{ui.c(pad('Secrets', 14), GREY)}"
                         f"{ui.c(str(len(findings)), RED)}")
        ui.blank()
        ui.panel(f"{hist.label}  {hist.path}", lines, color=BLUE)
        top = top_commands(entries)
        if top:
            width = max(count for _, count in top)
            rows = [[ui.c(name, BOLD), str(count),
                     ui.c(ui.g["full"] * max(1, round(20 * count / width)), CYAN)]
                    for name, count in top]
            ui.table(["Command", "Uses", ""], rows, aligns="<><")
    return EXIT_OK


def act_scan(ctx: Ctx, files: list[HistoryFile]) -> int:
    ui, args = ctx.ui, ctx.args
    total: list[Finding] = []
    for hist in files:
        with ui.status(f"Scanning {hist.label}") as st:
            findings = scan_entries(hist, hist.entries())
            st.done(f"Scanned {hist.label}: {len(hist.entries())} entries, "
                    f"{len(findings)} hit(s)",
                    glyph="warn" if findings else "ok",
                    color=YELLOW if findings else GREEN)
        total.extend(findings)
        if not findings:
            ui.ok(f"{hist.label}: nothing that looks like a credential")
            continue
        ui.blank()
        ui.step("warn", f"{hist.label}: {len(findings)} possible credential(s)", YELLOW)
        rows = []
        for finding in findings[:args.limit]:
            rows.append([
                ui.c(finding.rule.name, RED),
                ui.c(finding.entry.stamp or "—", GREY),
                (finding.secret if args.show_secrets else mask(finding.secret)),
                display_command(finding.entry.command, args.show_secrets),
            ])
        ui.table(["Rule", "When", "Value", "Command"], rows)
        if len(findings) > args.limit:
            ui.note(f"...and {len(findings) - args.limit} more (raise --limit to see them)")
    if total:
        ui.blank()
        ui.warn(f"{len(total)} possible credential(s) across "
                f"{len({id(f.file) for f in total})} file(s).")
        ui.note("values are masked; --show-secrets reveals them")
        ui.note("remove the entries with --redact-secrets, then rotate anything real")
        log(f"Scan found {len(total)} candidate secret(s)")
        return EXIT_FOUND
    ui.blank()
    ui.ok("No credential-shaped entries found.")
    return EXIT_OK


def act_backups(ctx: Ctx) -> int:
    ui = ctx.ui
    archives = list_backups()
    if not archives:
        ui.note(f"no backups in {BACKUP_DIR}")
        return EXIT_OK
    rows = []
    for archive in archives:
        try:
            info = archive.stat()
        except OSError:
            continue
        label = archive.name.split("_")[0]
        rows.append([
            ui.c(label, BOLD),
            datetime.datetime.fromtimestamp(info.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            human_size(info.st_size),
            ui.c(archive.name, GREY),
        ])
    ui.blank()
    ui.step("disk", f"{len(rows)} backup(s) in {BACKUP_DIR}", BLUE)
    ui.table(["For", "Taken", "Size", "Archive"], rows, aligns="<<><")
    ui.note("restore one with: --restore <archive>")
    return EXIT_OK


# --------------------------------------------------------------------------
# Mutating actions
# --------------------------------------------------------------------------

def act_fix_perms(ctx: Ctx, files: list[HistoryFile]) -> int:
    ui, args = ctx.ui, ctx.args
    targets = [f for f in files if f.insecure]
    if not targets:
        ui.ok("All history files are already owner-only (0600).")
        return EXIT_OK
    for hist in targets:
        if args.dry_run:
            ui.note(f"[dry-run] would chmod 0600 {hist.path} (currently {hist.mode:04o})")
            continue
        try:
            os.chmod(hist.path, SAFE_MODE)
        except OSError as exc:
            ui.error(f"{hist.label}: {exc}")
            ctx.failures.append(hist.label)
            continue
        ui.ok(f"{hist.label}: {hist.path} is now 0600")
        log(f"Tightened permissions on {hist.path}")
        ctx.changed.append(hist.label)
    return EXIT_OK


def act_dedupe(ctx: Ctx, files: list[HistoryFile]) -> int:
    for hist in files:
        entries = hist.entries()
        seen: set[str] = set()
        keep_rev: list[Entry] = []
        dropped: list[Entry] = []
        # Walk backwards so the most recent occurrence — and its timestamp —
        # is the one that survives.
        for entry in reversed(entries):
            key = entry.command.strip()
            if key and key in seen:
                dropped.append(entry)
            else:
                seen.add(key)
                keep_rev.append(entry)
        apply_removal(ctx, hist, list(reversed(keep_rev)), dropped, "dedupe")
    return EXIT_OK


def act_redact(ctx: Ctx, files: list[HistoryFile], patterns: list[str]) -> int:
    try:
        matches = build_matcher(patterns, ctx.args.regex)
    except re.error as exc:
        ctx.ui.error(f"Invalid --regex pattern: {exc}")
        return EXIT_FATAL
    for hist in files:
        keep, dropped = [], []
        for entry in hist.entries():
            (dropped if matches(entry.command) else keep).append(entry)
        apply_removal(ctx, hist, keep, dropped, "redact")
    return EXIT_OK


def act_redact_secrets(ctx: Ctx, files: list[HistoryFile]) -> int:
    for hist in files:
        entries = hist.entries()
        flagged = secret_entry_ids(scan_entries(hist, entries))
        keep = [e for e in entries if id(e) not in flagged]
        dropped = [e for e in entries if id(e) in flagged]
        apply_removal(ctx, hist, keep, dropped, "redact")
    if ctx.changed:
        ctx.ui.blank()
        ctx.ui.warn("Removing the entry does not un-leak the secret — rotate it.")
    return EXIT_OK


def act_clear(ctx: Ctx, files: list[HistoryFile]) -> int:
    ui, args = ctx.ui, ctx.args
    for hist in files:
        count = len(hist.entries())
        if not hist.size:
            ui.note(f"{hist.label}: already empty")
            continue
        ui.out(f"  {ui.c(hist.label, BOLD)}: {ui.c(str(count), YELLOW)} entries, "
               f"{human_size(hist.size)} — {ui.c(str(hist.path), GREY)}")
        if args.dry_run:
            ui.note(f"[dry-run] would clear {hist.path}")
            continue
        if not args.yes and not confirm(
                ui, f"  PERMANENTLY clear {hist.label}?", strict=True):
            ui.note(f"{hist.label}: skipped")
            continue
        if not args.no_backup and backup_file(ui, hist, dry_run=False) is None and not args.yes:
            ui.warn(f"{hist.label}: no backup taken — skipping (use --no-backup to proceed anyway)")
            ctx.failures.append(hist.label)
            continue
        if args.shred and not shred_file(hist.path):
            ui.warn(f"{hist.label}: overwrite pass failed; clearing anyway")
        try:
            truncate_file(hist.path)
        except OSError as exc:
            ui.error(f"{hist.label}: could not clear {hist.path}: {exc}")
            log(f"FAILED clear {hist.path}: {exc}")
            ctx.failures.append(hist.label)
            continue
        hist.invalidate()
        ui.ok(f"{hist.label}: cleared {count} entries")
        log(f"Cleared {hist.path} ({count} entries)")
        ctx.changed.append(hist.label)
    if args.shred and ctx.changed:
        ui.note("overwriting does not guarantee erasure on APFS or any SSD: "
                "copy-on-write and wear levelling keep old blocks around")
    return EXIT_OK


def act_restore(ctx: Ctx, files: list[HistoryFile], choice: str | None) -> int:
    ui, args = ctx.ui, ctx.args
    archives = list_backups()
    if not archives:
        ui.error(f"No backups in {BACKUP_DIR}.")
        return EXIT_FATAL

    if choice:
        candidate = Path(choice)
        if not candidate.is_file():
            candidate = BACKUP_DIR / choice
        if not candidate.is_file():
            ui.error(f"No such backup: {choice}")
            return EXIT_FATAL
        archive = candidate
    else:
        act_backups(ctx)
        try:
            raw = input(ui.c("Archive to restore (name, or blank to cancel): ",
                             CYAN, BOLD)).strip()
        except EOFError:
            raw = ""
        if not raw:
            ui.note("restore cancelled")
            return EXIT_OK
        archive = BACKUP_DIR / raw
        if not archive.is_file():
            ui.error(f"No such backup: {raw}")
            return EXIT_FATAL

    label = archive.name.split("_")[0]
    target = next((f for f in files if f.label == label), None)
    if target is None:
        ui.error(f"Backup is for {label!r}, which is not among the selected files.")
        return EXIT_FATAL

    ui.out(f"  restore {ui.c(archive.name, BOLD)} {ui.g['arrow']} "
           f"{ui.c(str(target.path), GREY)}")
    if not args.yes and not args.dry_run and not confirm(
            ui, f"  Overwrite {target.label} history with this backup?"):
        ui.note("restore cancelled")
        return EXIT_OK
    if not restore_backup(ui, archive, target, args.dry_run):
        ctx.failures.append(label)
        return EXIT_FAILURES
    if not args.dry_run:
        ui.ok(f"{label}: restored from {archive.name}")
        ctx.changed.append(label)
    return EXIT_OK


# --------------------------------------------------------------------------
# Machine-readable report
# --------------------------------------------------------------------------

def json_report(files: list[HistoryFile], reveal: bool) -> dict:
    payload = {
        "version": VERSION,
        "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
        "files": [],
    }
    for hist in files:
        entries = hist.entries()
        first, last = date_span(entries)
        findings = scan_entries(hist, entries)
        payload["files"].append({
            "label": hist.label,
            "path": str(hist.path),
            "kind": hist.kind,
            "source": hist.source,
            "exists": hist.exists,
            "entries": len(entries),
            "unique": len({e.command for e in entries}),
            "bytes": hist.size,
            "mode": f"{hist.mode:04o}",
            "world_readable": hist.insecure,
            "first": first,
            "last": last,
            "findings": [
                {
                    "rule": f.rule.name,
                    "when": f.entry.stamp,
                    "value": f.secret if reveal else mask(f.secret),
                    "note": f.rule.hint,
                }
                for f in findings
            ],
        })
    return payload


# --------------------------------------------------------------------------
# Interactive menu
# --------------------------------------------------------------------------

MENU = [
    ("1", "List history files"),
    ("2", "Show recent entries"),
    ("3", "Statistics"),
    ("4", "Scan for credentials"),
    ("5", "Remove entries matching a pattern"),
    ("6", "Remove entries flagged as credentials"),
    ("7", "Remove duplicate entries"),
    ("8", "Clear a history file"),
    ("9", "Backups and restore"),
    ("10", "Fix file permissions (0600)"),
    ("s", "Change which files are selected"),
    ("q", "Quit"),
]


def choose_files(ui: UI, all_files: list[HistoryFile]) -> list[HistoryFile]:
    present = [f for f in all_files if f.exists]
    if not present:
        return []
    ui.blank()
    for i, hist in enumerate(present, 1):
        ui.out(f"  {ui.c(f'{i:>2}', GREY)}. {ui.c(hist.label, BOLD)}  "
               f"{ui.c(str(hist.path), GREY)}")
    try:
        raw = input(ui.c("Select (e.g. 1,3 | all): ", CYAN, BOLD)).strip().lower()
    except EOFError:
        return present
    if raw in ("", "all", "a"):
        return present
    picked = []
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit() and 1 <= int(part) <= len(present):
            picked.append(present[int(part) - 1])
        else:
            match = next((f for f in present if f.label == part), None)
            if match:
                picked.append(match)
    if not picked:
        ui.warn("nothing matched; keeping the current selection")
        return present
    return picked


def menu(ctx: Ctx, all_files: list[HistoryFile], selected: list[HistoryFile]) -> int:
    ui = ctx.ui
    worst = EXIT_OK
    while True:
        ui.blank()
        labels = ", ".join(f.label for f in selected) or "none"
        ui.rule(f"selected: {labels}")
        for key, text in MENU:
            ui.out(f"  {ui.c(f'{key:>2}', CYAN)}. {text}")
        try:
            choice = input(ui.c("\nChoice: ", CYAN, BOLD)).strip().lower()
        except EOFError:
            return worst

        if choice in ("q", "0", "quit", "exit"):
            return worst
        if choice == "s":
            selected = choose_files(ui, all_files)
            continue
        if not selected and choice not in ("9",):
            ui.warn("no files selected — press s to choose")
            continue

        if choice == "1":
            act_list(ctx, all_files)
        elif choice == "2":
            act_show(ctx, selected)
        elif choice == "3":
            act_stats(ctx, selected)
        elif choice == "4":
            worst = max(worst, act_scan(ctx, selected))
        elif choice == "5":
            try:
                pattern = input(ui.c("Pattern to remove (substring): ", CYAN, BOLD)).strip()
            except EOFError:
                continue
            if pattern:
                act_redact(ctx, selected, [pattern])
        elif choice == "6":
            act_redact_secrets(ctx, selected)
            running_shell_warning(ui, [f.label for f in selected])
        elif choice == "7":
            act_dedupe(ctx, selected)
        elif choice == "8":
            act_clear(ctx, selected)
            running_shell_warning(ui, [f.label for f in selected])
        elif choice == "9":
            act_restore(ctx, all_files, None)
        elif choice == "10":
            act_fix_perms(ctx, all_files)
        else:
            ui.warn("invalid choice")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="clear_terminal_history.py",
        description="HistClean: inspect, audit and clear shell history, carefully.",
        epilog="With no action flag, an interactive menu is shown.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"HistClean {VERSION}")

    act = parser.add_argument_group("actions")
    act.add_argument("--list", action="store_true",
                     help="List the history files found, with sizes and permissions")
    act.add_argument("--show", action="store_true",
                     help="Show the most recent entries (see --limit)")
    act.add_argument("--stats", action="store_true",
                     help="Entry counts, date span and most-used commands")
    act.add_argument("--scan", action="store_true",
                     help="Report entries that look like leaked credentials (exit 3 if any)")
    act.add_argument("--dedupe", action="store_true",
                     help="Remove duplicate commands, keeping the most recent")
    act.add_argument("--redact", nargs="+", metavar="PATTERN",
                     help="Remove entries containing these substrings (or regexes with --regex)")
    act.add_argument("--redact-secrets", action="store_true",
                     help="Remove every entry --scan would flag")
    act.add_argument("--clear", action="store_true",
                     help="Empty the selected history files")
    act.add_argument("--fix-perms", action="store_true",
                     help="Set 0600 on any history file others can read")
    act.add_argument("--backups", action="store_true",
                     help="List the backups taken before previous changes")
    act.add_argument("--restore", nargs="?", const="", metavar="ARCHIVE",
                     help="Restore a backup (prompts when no archive is named)")

    tgt = parser.add_argument_group("targets")
    tgt.add_argument("--files", nargs="+", default=[], metavar="LABEL",
                     help="Which histories to act on: zsh, bash, fish, python, ... or all")
    tgt.add_argument("--tools", action="store_true",
                     help="Also consider REPL and client histories (python, psql, mysql, ...)")

    saf = parser.add_argument_group("safety")
    saf.add_argument("-y", "--yes", action="store_true",
                     help="Do not prompt for confirmation")
    saf.add_argument("--dry-run", action="store_true",
                     help="Report what would change without writing anything")
    saf.add_argument("--no-backup", action="store_true",
                     help="Do not take a backup before changing a file")
    saf.add_argument("--shred", action="store_true",
                     help="Overwrite the bytes before clearing (see the caveat in --help output)")

    out = parser.add_argument_group("output")
    out.add_argument("--limit", type=int, default=20, metavar="N",
                     help="How many entries or findings to display")
    out.add_argument("--regex", action="store_true",
                     help="Treat --redact patterns as regular expressions")
    out.add_argument("--show-secrets", action="store_true",
                     help="Print matched credentials in full instead of masking them")
    out.add_argument("--color", choices=("auto", "always", "never"), default="auto",
                     help="Colorise output")
    out.add_argument("--ascii", action="store_true",
                     help="ASCII-only output (no box drawing or emoji)")
    out.add_argument("-q", "--quiet", action="store_true",
                     help="Print only warnings and errors")
    out.add_argument("--json", action="store_true",
                     help="Emit a machine-readable report to stdout (UI goes to stderr)")

    return parser


def make_ui(args: argparse.Namespace) -> UI:
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


def _raise_interrupt(signum, frame) -> None:
    raise KeyboardInterrupt


MUTATING = ("dedupe", "redact", "redact_secrets", "clear", "fix_perms", "restore")
# Of those, the ones that change what the file *contains* — only these can be
# undone by a shell writing its in-memory history back over the top.
CONTENT_CHANGING = ("dedupe", "redact", "redact_secrets", "clear", "restore")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    ui = make_ui(args)

    if args.limit < 1:
        parser.error("--limit must be at least 1")
    if args.regex and not args.redact:
        parser.error("--regex only applies to --redact")
    if args.shred and not args.clear:
        parser.error("--shred only applies to --clear")

    if not setup_logging():
        ui.warn(f"Could not open {LOG_PATH}; continuing without a log file.")

    signal.signal(signal.SIGTERM, _raise_interrupt)
    log(f"--- HistClean {VERSION} run started: {' '.join(sys.argv[1:])} ---")

    actions = [name for name in
               ("list", "show", "stats", "scan", "dedupe", "redact", "redact_secrets",
                "clear", "fix_perms", "backups", "restore")
               if getattr(args, name, None)]
    # --json is itself a report, so it must not fall through to the menu and
    # then be refused for want of a terminal.
    interactive = not actions and not args.json

    mutating = [a for a in actions if a in MUTATING]
    if mutating and not args.yes and not args.dry_run and not sys.stdin.isatty():
        ui.error(f"{mutating[0]} would change files, but this is a non-interactive "
                 f"session and -y/--yes was not given.")
        return EXIT_FATAL
    if interactive and not sys.stdin.isatty():
        ui.error("No action flag and no terminal to show the menu on. Try --list.")
        return EXIT_FATAL

    sep = " · " if ui.uni else " | "
    ui.banner(f"HistClean {VERSION}",
              sep.join([f"{HOME}", "dry-run" if args.dry_run else "live",
                        f"backups: {BACKUP_DIR.name}"]))

    # Discovery is just path checks, so always look everywhere; what differs
    # is what gets *selected*. Read-only actions default to every history that
    # exists — a scanner that silently skips ~/.psql_history is worse than
    # useless — while anything that deletes defaults to the shells alone.
    all_files = discover(include_tools=True)
    existing = [f for f in all_files if f.exists]
    destructive = [a for a in actions if a in ("dedupe", "redact", "redact_secrets", "clear")]

    if args.files:
        selected = select_files(all_files, args.files, existing_only=True)
    elif args.tools or not destructive:
        selected = existing
    else:
        selected = [f for f in existing if f.kind == "shell"]
        skipped = [f.label for f in existing if f.kind != "shell"]
        if skipped:
            ui.note(f"not touching tool histories ({', '.join(skipped)}) — "
                    f"add --tools or --files to include them")

    # Absent tool paths are noise unless they were asked for.
    listable = all_files if (args.tools or args.files) else [
        f for f in all_files if f.kind == "shell" or f.exists]

    unknown = [w for w in args.files
               if w.lower() != "all" and w.lower() not in {f.label for f in all_files}]
    if unknown:
        ui.error(f"Unknown history label(s): {', '.join(unknown)}")
        ui.note(f"known: {', '.join(f.label for f in all_files)}")
        return EXIT_FATAL

    if args.json:
        json.dump(json_report(selected or existing, args.show_secrets),
                  sys.stdout, indent=2)
        sys.stdout.write("\n")
        sys.stdout.flush()
        if not actions:
            return EXIT_OK

    ctx = Ctx(ui, args)
    worst = EXIT_OK

    if interactive:
        if not selected:
            ui.warn("No history files found.")
            act_list(ctx, listable)
            return EXIT_OK
        return menu(ctx, listable, selected)

    needs_files = [a for a in actions if a not in ("backups",)]
    if needs_files and not selected and "restore" not in actions:
        ui.warn("None of the selected history files exist.")
        act_list(ctx, listable)
        return EXIT_OK

    for action in actions:
        if action == "list":
            worst = max(worst, act_list(ctx, listable))
        elif action == "show":
            worst = max(worst, act_show(ctx, selected))
        elif action == "stats":
            worst = max(worst, act_stats(ctx, selected))
        elif action == "scan":
            worst = max(worst, act_scan(ctx, selected))
        elif action == "dedupe":
            worst = max(worst, act_dedupe(ctx, selected))
        elif action == "redact":
            worst = max(worst, act_redact(ctx, selected, args.redact))
        elif action == "redact_secrets":
            worst = max(worst, act_redact_secrets(ctx, selected))
        elif action == "clear":
            worst = max(worst, act_clear(ctx, selected))
        elif action == "fix_perms":
            worst = max(worst, act_fix_perms(ctx, existing))
        elif action == "backups":
            worst = max(worst, act_backups(ctx))
        elif action == "restore":
            worst = max(worst, act_restore(ctx, all_files, args.restore or None))

    if ctx.changed and any(a in CONTENT_CHANGING for a in actions):
        running_shell_warning(ui, ctx.changed)

    if ctx.failures:
        ui.blank()
        ui.warn(f"{len(ctx.failures)} file(s) could not be changed: "
                f"{', '.join(sorted(set(ctx.failures)))}")
        return EXIT_FAILURES

    log(f"Run complete: changed {ctx.changed or 'nothing'}, exit {worst}")
    return worst


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.stderr.write("\nInterrupted.\n")
        log("Run interrupted by user.")
        sys.exit(EXIT_INTERRUPT)
    except BrokenPipeError:
        os._exit(EXIT_OK)
