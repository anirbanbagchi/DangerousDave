class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    BLUE = "\033[34m"
    CYAN = "\033[36m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    GRAY = "\033[90m"
#!/usr/bin/env python3

import subprocess
import shutil
import re
import os
from pathlib import Path

ALIAS_OUTPUT_RE = re.compile(r"^(?:alias\s+)?([A-Za-z0-9_:+-]+)=")  # bash prints 'alias name=...', zsh often prints 'name=...'

HOME = Path.home()

# Common startup files (user + system). We'll also follow simple `source` / `.` includes.
ZSH_START_FILES = [
    HOME / ".zshrc",
    HOME / ".zprofile",
    HOME / ".zshenv",
    HOME / ".zlogin",
    Path("/etc/zshrc"),
    Path("/etc/zprofile"),
    Path("/etc/zshenv"),
    Path("/etc/zlogin"),
]

BASH_START_FILES = [
    HOME / ".bashrc",
    HOME / ".bash_profile",
    HOME / ".bash_login",
    HOME / ".profile",
    Path("/etc/bashrc"),
    Path("/etc/profile"),
]

# Also scan common Oh My Zsh/custom locations (best-effort).
OH_MY_ZSH_FILES_GLOBS = [
    HOME / ".oh-my-zsh" / "custom" / "**" / "*.zsh",
    HOME / ".oh-my-zsh" / "custom" / "**" / "*.plugin.zsh",
    HOME / ".oh-my-zsh" / "plugins" / "**" / "*.plugin.zsh",
]

SOURCE_RE = re.compile(r'^\s*(?:source|\.)\s+(.+?)\s*(?:#.*)?$')
ALIAS_DEF_RE = re.compile(r"^\s*alias\s+([A-Za-z0-9_:+-]+)\s*=")  # alias name=...

def get_aliases(shell_name):
    """
    Get aliases from a given shell by invoking its alias command.
    """
    shell_path = shutil.which(shell_name)
    if not shell_path:
        return None

    try:
        # Run interactive shell so aliases are loaded
        result = subprocess.run(
            [shell_path, "-i", "-c", "alias"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True
        )
        aliases = {}
        for raw_line in result.stdout.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            m = ALIAS_OUTPUT_RE.match(line)
            if m:
                name = m.group(1)
                # Normalize display so zsh and bash look the same.
                # bash: "alias ll='ls -lah'"  |  zsh: "ll='ls -lah'"
                if not line.startswith("alias "):
                    line = f"alias {line}"
                aliases[name] = line
        return aliases if aliases else None
    except Exception as e:
        return None


def print_aliases(shell_name, aliases):
    title = f"{shell_name.upper()} ALIASES"
    print(f"\n{C.BOLD}{C.BLUE}⎇  {title}{C.RESET}")
    print(f"{C.GRAY}{'-' * (len(title) + 3)}{C.RESET}")

    def_index = _build_definition_index(shell_name)

    # Column widths (ASCII-only for stable alignment)
    ICON_W = 5
    NAME_W = 18
    SRC_W = 46

    # Use terminal width when available
    try:
        term_w = shutil.get_terminal_size((120, 24)).columns
    except Exception:
        term_w = 120

    sep = "  "
    # Layout: ICON  ALIAS  DEF  SOURCE
    def_w = max(40, term_w - ICON_W - NAME_W - SRC_W - len(sep) * 3)

    header = (
        f"{C.BOLD}"
        f"{'STAT'.ljust(ICON_W)}{sep}"
        f"{'ALIAS'.ljust(NAME_W)}{sep}"
        f"{'DEFINITION'.ljust(def_w)}{sep}"
        f"SOURCE{C.RESET}"
    )
    print(header)
    print(f"{C.GRAY}{'-' * min(term_w, ICON_W + NAME_W + def_w + SRC_W + len(sep) * 3)}{C.RESET}")
    print(f"{C.GRAY}Legend:{C.RESET} {C.GREEN}✔{C.RESET} source found  {C.RED}✖{C.RESET} source not found")

    def wrap(text: str, width: int) -> list[str]:
        if width <= 0:
            return [text]
        words = text.split(' ')
        lines: list[str] = []
        cur = ""
        for w in words:
            if not cur:
                cur = w
            elif len(cur) + 1 + len(w) <= width:
                cur += " " + w
            else:
                lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines if lines else [text]

    for name in sorted(aliases.keys()):
        full_def = aliases[name].replace('alias ', '', 1)
        def_lines = wrap(full_def, def_w)

        locations = def_index.get(name, [])
        src_lines = [f"{p}:{ln}" for (p, ln, _) in locations] if locations else ["<not found>"]

        # Fixed-width, non-emoji symbols (render as single-cell in Terminal/iTerm2)
        # ✔ = found, ✖ = not found
        icon = "✔" if locations else "✖"
        icon_color = C.GREEN if locations else C.RED

        # First printed row
        src0 = src_lines[0]
        if len(src0) > SRC_W:
            src0 = "..." + src0[-(SRC_W - 3):]

        src_color = C.GREEN if locations else C.YELLOW

        print(
            f"{icon_color}{(icon + ' ').ljust(ICON_W)}{C.RESET}{sep}"
            f"{C.CYAN}{name.ljust(NAME_W)}{C.RESET}{sep}"
            f"{def_lines[0].ljust(def_w)}{sep}"
            f"{src_color}{src0}{C.RESET}"
        )

        # Remaining wrapped definition lines
        for extra_def in def_lines[1:]:
            print(
                f"{'':<{ICON_W}}{sep}"
                f"{'':<{NAME_W}}{sep}"
                f"{extra_def.ljust(def_w)}{sep}"
                f"{'':<{SRC_W}}"
            )

        # Additional source locations
        for extra_src in src_lines[1:]:
            src = extra_src
            if len(src) > SRC_W:
                src = "..." + src[-(SRC_W - 3):]
            print(
                f"{'':<{ICON_W}}{sep}"
                f"{'':<{NAME_W}}{sep}"
                f"{'':<{def_w}}{sep}"
                f"{C.GREEN}{src}{C.RESET}"
            )

        print(f"{C.GRAY}{'·' * term_w}{C.RESET}")


def main():
    found_any = False

    for shell in ["zsh", "bash"]:
        aliases = get_aliases(shell)
        if aliases:
            found_any = True
            print_aliases(shell, aliases)

    if not found_any:
        print(f"{C.RED}No user-defined aliases found.{C.RESET}")


def _read_text_safely(path: Path) -> str | None:
    try:
        if not path.exists() or not path.is_file():
            return None
        return path.read_text(errors="ignore")
    except Exception:
        return None


def _expand_path(raw: str, base_dir: Path) -> Path | None:
    raw = raw.strip().strip('"').strip("'")
    if not raw:
        return None
    expanded = os.path.expandvars(os.path.expanduser(raw))
    p = Path(expanded)
    if not p.is_absolute():
        p = (base_dir / p).resolve()
    return p


def _discover_sourced_files(start_files: list[Path], max_depth: int = 4) -> list[Path]:
    """Follow simple `source` / `.` includes from start files (depth-limited)."""
    seen: set[Path] = set()
    queue: list[tuple[Path, int]] = []

    for f in start_files:
        if f.exists():
            queue.append((f.resolve(), 0))

    while queue:
        current, depth = queue.pop(0)
        if current in seen:
            continue
        seen.add(current)

        if depth >= max_depth:
            continue

        content = _read_text_safely(current)
        if not content:
            continue

        base_dir = current.parent
        for line in content.splitlines():
            m = SOURCE_RE.match(line)
            if not m:
                continue
            target_raw = m.group(1)
            target = _expand_path(target_raw, base_dir)
            if not target:
                continue
            if target.exists() and target.is_file():
                queue.append((target.resolve(), depth + 1))

    return sorted(seen)


def _expand_globs(glob_paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for gp in glob_paths:
        # Path.glob supports ** patterns when used with a relative pattern; here gp already contains **,
        # so we glob from its anchor.
        anchor = gp
        # Find the first parent without glob chars to use as a base.
        while any(ch in str(anchor.name) for ch in ['*', '?', '[']):
            anchor = anchor.parent
        pattern = str(gp.relative_to(anchor))
        if anchor.exists():
            files.extend([p for p in anchor.glob(pattern) if p.is_file()])
    return sorted(set([p.resolve() for p in files]))


def _index_alias_definitions(files: list[Path]) -> dict[str, list[tuple[Path, int, str]]]:
    """alias_name -> [(file, line_no, line_text), ...]"""
    found: dict[str, list[tuple[Path, int, str]]] = {}
    for f in files:
        content = _read_text_safely(f)
        if not content:
            continue
        for i, line in enumerate(content.splitlines(), start=1):
            m = ALIAS_DEF_RE.match(line)
            if not m:
                continue
            name = m.group(1)
            found.setdefault(name, []).append((f, i, line.strip()))
    return found


def _build_definition_index(shell_name: str) -> dict[str, list[tuple[Path, int, str]]]:
    if shell_name == "zsh":
        base_files = _discover_sourced_files(ZSH_START_FILES, max_depth=5)
        extra = _expand_globs(OH_MY_ZSH_FILES_GLOBS)
        scanned = sorted(set([p.resolve() for p in (base_files + extra) if p.exists()]))
    else:
        scanned = _discover_sourced_files(BASH_START_FILES, max_depth=5)
    return _index_alias_definitions(scanned)


if __name__ == "__main__":
    main()