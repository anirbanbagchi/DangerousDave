#!/usr/bin/env python3
"""
PATH Inspector (macOS/Linux)
- Grouped output by category (tree)
- Detect missing/broken directories
- Rich-table UI (uses 'rich' if available, otherwise fallback text)
- Highlight duplicates & ordering issues (duplicates + shadowed paths)
- Interactive broken-path fixer (--fix) with logging of actions

Usage:
  python3 paths.py
Optional:
  python3 paths.py --json   # prints JSON summary at end
  python3 paths.py --fix    # interactive broken-path fixer (logs actions)
  # After the report prints, you will be prompted to enter fix mode if broken entries exist.

Logs:
  Creates path_fix_log_<datetimestamp>.log next to this script.
"""

import os
import sys
import json
import logging
import datetime
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple, Optional


# ---- Classification rules ----------------------------------------------------

# Categorization is heuristic-based. We classify by strongest match first.
# Each rule is (category, match_function, reason_label)

SYSTEM_PREFIXES = (
    "/System",
    "/bin",
    "/sbin",
    "/usr/bin",
    "/usr/sbin",
    "/usr/libexec",
)

BREW_PREFIXES = (
    "/opt/homebrew",   # Apple Silicon default
    "/usr/local",      # Intel default (and legacy)
)

DEV_PREFIXES = (
    "/Applications/Xcode.app",
    "/Library/Developer",
    "/Developer",
)

HOME = str(Path.home())

# A few well-known toolchain markers to make categories more useful.
KEYWORD_BUCKETS: Dict[str, List[str]] = {
    "Python": ["pyenv", "conda", "anaconda", "miniconda", "venv", "virtualenv", "pipx", "python"],
    "Node.js": ["nvm", "node", "npm", "yarn", "pnpm"],
    "Java": ["java", "jdk", "jre", "maven", "gradle"],
    "Go": ["/go", "gobin", "golang"],
    "Rust": ["cargo", ".cargo", "rustup"],
    "Ruby": ["rbenv", "rvm", "ruby", "bundler"],
    "Android": ["android", "sdk"],
    "Dotfiles / User Local": [HOME, "~", ".local", ".dotfiles"],
    "Cloud / DevOps": ["aws", "gcloud", "google-cloud-sdk", "azure", "az", "kubectl", "helm", "terraform"],
    "Databricks": ["databricks"],
    "Databases": ["postgres", "mysql", "mariadb", "mongo", "redis"],
}

CATEGORY_PRIORITY = [
    "System",
    "Apple / Xcode / Developer",
    "Homebrew",
    "Python",
    "Node.js",
    "Java",
    "Go",
    "Rust",
    "Ruby",
    "Android",
    "Cloud / DevOps",
    "Databricks",
    "Databases",
    "Dotfiles / User Local",
    "Other / Unknown",
]


def _contains_any(haystack_lower: str, needles: List[str]) -> Optional[str]:
    for n in needles:
        if n.lower() in haystack_lower:
            return n
    return None


def classify(path: str) -> Tuple[str, str]:
    """Return (category, reason)."""
    p = path
    pl = p.lower()

    # Strong prefix rules
    if p.startswith(SYSTEM_PREFIXES):
        return "System", "system prefix"

    if p.startswith(DEV_PREFIXES):
        return "Apple / Xcode / Developer", "developer tools prefix"

    if p.startswith(BREW_PREFIXES):
        # Distinguish some common brew shapes
        if "/Cellar/" in p or "/cellar/" in pl:
            return "Homebrew", "brew cellar"
        return "Homebrew", "brew prefix"

    # Keyword buckets
    for cat, needles in KEYWORD_BUCKETS.items():
        hit = _contains_any(pl, needles)
        if hit:
            return cat, f"matched '{hit}'"

    # A couple of regex niceties
    if re.search(r"/versions/node/v\d+", pl):
        return "Node.js", "node versioned path"

    if re.search(r"/python\d+(\.\d+)?/", pl):
        return "Python", "python versioned path"

    return "Other / Unknown", "no match"


# ---- Analysis ----------------------------------------------------------------

@dataclass
class Entry:
    index: int
    raw: str
    expanded: str
    normalized: str
    exists: bool
    is_dir: bool
    category: str
    reason: str
    duplicate_of: Optional[int]  # first index that had the same normalized path
    shadowed_by: Optional[int]   # earlier index that "contains" this dir (heuristic)


def normalize_dir(p: str) -> str:
    # Expand ~ and env vars; normalize path; keep as string
    expanded = str(Path(os.path.expandvars(p)).expanduser())
    # Resolve symlinks only if it exists; otherwise just normalize
    try:
        if Path(expanded).exists():
            return str(Path(expanded).resolve())
    except Exception:
        pass
    return os.path.normpath(expanded)


def compute_shadowing(entries: List[Entry]) -> List[Entry]:
    """
    Heuristic shadowing:
      If an earlier path is an ancestor of a later path, the later is redundant-ish.
      Example: /usr/local/bin shadows /usr/local/bin/something (not typical in PATH, but happens)
    """
    normalized_list = [e.normalized for e in entries]
    for i, e in enumerate(entries):
        for j in range(i):
            a = normalized_list[j]
            b = e.normalized
            # If b is within a (a is prefix dir of b)
            if b != a and b.startswith(a.rstrip(os.sep) + os.sep):
                e.shadowed_by = entries[j].index
                break
    return entries


def analyze_path() -> Tuple[str, List[Entry], Dict[str, List[Entry]]]:
    raw_path = os.environ.get("PATH", "")
    parts = raw_path.split(os.pathsep) if raw_path else []

    seen: Dict[str, int] = {}  # normalized -> first index
    entries: List[Entry] = []

    for idx, raw in enumerate(parts, start=1):
        expanded = str(Path(os.path.expandvars(raw)).expanduser())
        normalized = normalize_dir(raw)
        p = Path(expanded)

        exists = p.exists()
        is_dir = p.is_dir() if exists else False
        category, reason = classify(normalized)

        duplicate_of = None
        if normalized in seen:
            duplicate_of = seen[normalized]
        else:
            seen[normalized] = idx

        entries.append(
            Entry(
                index=idx,
                raw=raw,
                expanded=expanded,
                normalized=normalized,
                exists=exists,
                is_dir=is_dir,
                category=category,
                reason=reason,
                duplicate_of=duplicate_of,
                shadowed_by=None,
            )
        )

    entries = compute_shadowing(entries)

    grouped: Dict[str, List[Entry]] = {}
    for e in entries:
        grouped.setdefault(e.category, []).append(e)

    return raw_path, entries, grouped


# ---- UI (Rich if available, fallback otherwise) ------------------------------

def try_import_rich():
    try:
        from rich.console import Console
        from rich.table import Table
        from rich.tree import Tree
        from rich.text import Text
        return Console, Table, Tree, Text
    except Exception:
        return None, None, None, None


def status_badges(e: Entry) -> List[str]:
    badges = []
    if not e.exists or not e.is_dir:
        badges.append("BROKEN")
    if e.duplicate_of is not None:
        badges.append(f"DUP({e.duplicate_of:02d})")
    if e.shadowed_by is not None:
        badges.append(f"SHADOW({e.shadowed_by:02d})")
    return badges


def print_rich(raw_path: str, entries: List[Entry], grouped: Dict[str, List[Entry]]):
    Console, Table, Tree, Text = try_import_rich()
    console = Console()

    console.print("\n[bold]🔍 PATH Inspector[/bold]")
    console.print(f"[dim]Entries:[/dim] {len(entries)}\n")

    # Summary counts
    broken = [e for e in entries if (not e.exists or not e.is_dir)]
    dups = [e for e in entries if e.duplicate_of is not None]
    shadowed = [e for e in entries if e.shadowed_by is not None]

    summary = Table(title="Summary", show_header=False)
    summary.add_column("k", style="bold")
    summary.add_column("v")
    summary.add_row("Total entries", str(len(entries)))
    summary.add_row("Broken / missing dirs", str(len(broken)))
    summary.add_row("Duplicates", str(len(dups)))
    summary.add_row("Shadowed (heuristic)", str(len(shadowed)))
    console.print(summary)
    console.print()

    # Detailed table (ordered)
    table = Table(title="Ordered PATH Entries", show_lines=False)
    table.add_column("#", justify="right")
    table.add_column("Path")
    table.add_column("Category")
    table.add_column("Reason")
    table.add_column("Flags")

    for e in entries:
        flags = " ".join(status_badges(e))
        path_text = Text(e.normalized)
        if not e.exists or not e.is_dir:
            path_text.stylize("red")
        elif e.duplicate_of is not None:
            path_text.stylize("yellow")
        elif e.shadowed_by is not None:
            path_text.stylize("magenta")

        table.add_row(f"{e.index:02d}", path_text, e.category, e.reason, flags)

    console.print(table)
    console.print()

    # Grouped tree by category
    tree = Tree("Grouped by category")
    for cat in sorted(grouped.keys()):
        node = tree.add(f"[bold]{cat}[/bold] ({len(grouped[cat])})")
        for e in grouped[cat]:
            flags = " ".join(status_badges(e))
            label = Text(f"{e.index:02d}. {e.normalized}")
            if flags:
                label.append(f"  [{flags}]")
            if not e.exists or not e.is_dir:
                label.stylize("red")
            elif e.duplicate_of is not None:
                label.stylize("yellow")
            elif e.shadowed_by is not None:
                label.stylize("magenta")
            node.add(label)

    console.print(tree)
    console.print()

    # Raw PATH (so you can copy)
    console.print("[bold]Raw PATH:[/bold]")
    console.print(raw_path)
    console.print()



# ---- Fallback color helpers (for fallback mode) ----

def supports_color() -> bool:
    return sys.stdout.isatty() and os.environ.get("NO_COLOR") is None

def c(text: str, color_code: str) -> str:
    if not supports_color():
        return text
    return f"\033[{color_code}m{text}\033[0m"

def colorize_path(e: Entry, s: str) -> str:
    # red for broken, yellow for dup, magenta for shadow
    if not e.exists or not e.is_dir:
        return c(s, "31")
    if e.duplicate_of is not None:
        return c(s, "33")
    if e.shadowed_by is not None:
        return c(s, "35")
    return s

def print_fallback(raw_path: str, entries: List[Entry], grouped: Dict[str, List[Entry]]):
    print("\n🔍 PATH Inspector")
    print(f"Entries: {len(entries)}\n")

    broken = [e for e in entries if (not e.exists or not e.is_dir)]
    dups = [e for e in entries if e.duplicate_of is not None]
    shadowed = [e for e in entries if e.shadowed_by is not None]

    print("Summary")
    print("------")
    print(f"Total entries         : {len(entries)}")
    print(f"Broken / missing dirs : {len(broken)}")
    print(f"Duplicates            : {len(dups)}")
    print(f"Shadowed (heuristic)  : {len(shadowed)}\n")

    print("Ordered PATH Entries")
    print("-------------------")
    for e in entries:
        flags = " ".join(status_badges(e))
        print(f"{e.index:02d}. {colorize_path(e, e.normalized)}")
        print(f"    Category: {e.category}")
        print(f"    Reason  : {e.reason}")
        if flags:
            print(f"    Flags   : {flags}")
        print()

    print("Grouped by category")
    print("-------------------")
    for cat in sorted(grouped.keys()):
        print(f"{cat} ({len(grouped[cat])})")
        for e in grouped[cat]:
            flags = " ".join(status_badges(e))
            suffix = f" [{flags}]" if flags else ""
            print(f"  - {e.index:02d}. {colorize_path(e, e.normalized)}{suffix}")
        print()

    print("Raw PATH")
    print("--------")
    print(raw_path)
    print()


# ---- Interactive Fix & Logging ----------------------------------------------

def setup_logger() -> logging.Logger:
    """Create a timestamped log file in the same directory as this script."""
    script_dir = Path(__file__).resolve().parent
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = script_dir / f"path_fix_log_{ts}.log"

    logger = logging.getLogger("path_inspector")
    logger.setLevel(logging.INFO)

    # Avoid duplicate handlers if main() is called more than once
    if not any(isinstance(h, logging.FileHandler) and getattr(h, "baseFilename", "") == str(log_path) for h in logger.handlers):
        fh = logging.FileHandler(log_path, encoding="utf-8")
        fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
        fh.setFormatter(fmt)
        logger.addHandler(fh)

    # Also log to stderr only if user is in interactive fix mode (added later)
    logger._path_log_file = str(log_path)  # type: ignore[attr-defined]
    return logger


def _safe_expand_and_normalize(p: str) -> str:
    return normalize_dir(p)


def suggest_alternatives(broken_path: str, limit: int = 8) -> List[str]:
    """Suggest likely alternatives for a broken PATH entry.

    Heuristics:
      - Walk up until an existing parent is found, then list child dirs similar to the missing component
      - If the broken path ends with 'bin' or 'sbin', look for sibling 'bin' directories under nearby parents
    """
    suggestions: List[str] = []
    norm = _safe_expand_and_normalize(broken_path)
    p = Path(norm)

    # If it's empty, nothing to suggest
    if not str(p).strip():
        return suggestions

    # Find closest existing ancestor
    target_name = p.name
    parent = p.parent

    existing_ancestor: Optional[Path] = None
    cursor = p
    while True:
        if cursor.exists() and cursor.is_dir():
            existing_ancestor = cursor
            break
        if cursor.parent == cursor:
            break
        cursor = cursor.parent

    # If we found an existing ancestor, suggest children that resemble the missing tail
    if existing_ancestor is not None:
        try:
            for child in sorted(existing_ancestor.iterdir()):
                if not child.is_dir():
                    continue
                name = child.name
                if target_name and (name == target_name or name.startswith(target_name) or target_name.startswith(name)):
                    suggestions.append(str(child.resolve()))
                    if len(suggestions) >= limit:
                        return suggestions
        except Exception:
            pass

    # If the missing component is 'bin'/'sbin', look for nearby bin dirs
    if target_name in {"bin", "sbin"}:
        # Try the first existing parent
        cur = parent
        for _ in range(4):
            if cur.exists() and cur.is_dir():
                for candidate in [cur / "bin", cur / "sbin"]:
                    if candidate.exists() and candidate.is_dir():
                        s = str(candidate.resolve())
                        if s not in suggestions:
                            suggestions.append(s)
                            if len(suggestions) >= limit:
                                return suggestions
            if cur.parent == cur:
                break
            cur = cur.parent

    return suggestions[:limit]



def interactive_fix_broken_paths(raw_path: str, entries: List[Entry], logger: logging.Logger) -> Tuple[str, List[Entry]]:
    """Interactive broken PATH fixer with preview and per-entry control.

    Key behavior:
      - Works on the current PATH list (no index drift after removals)
      - Does not automatically persist changes to your shell
      - Does not mutate os.environ globally; uses a temporary PATH for re-analysis
    """

    def rebuild_path(parts: List[str]) -> str:
        cleaned = [p for p in parts if p]
        return os.pathsep.join(cleaned)

    def reanalyze_with(path_value: str) -> Tuple[str, List[Entry]]:
        old = os.environ.get("PATH", "")
        try:
            os.environ["PATH"] = path_value
            new_raw, new_entries, _ = analyze_path()
            return new_raw, new_entries
        finally:
            os.environ["PATH"] = old

    # Start from the *current* PATH parts (cleaned)
    current_parts = [p for p in (raw_path.split(os.pathsep) if raw_path else []) if p]

    # Quick guard
    broken = [e for e in entries if (not e.exists or not e.is_dir)]
    if not broken:
        print("No broken PATH entries detected.")
        return raw_path, entries

    logger.info("Starting interactive fix session")
    logger.info("Original PATH: %s", raw_path)

    print("\n🛠 Interactive PATH Fix Mode")
    print("---------------------------")
    print("Fix broken entries one-by-one. Preview anytime. Nothing is persisted automatically.\n")

    def print_broken_list(cur_entries: List[Entry]) -> None:
        b = [e for e in cur_entries if (not e.exists or not e.is_dir)]
        print("\nBroken PATH entries:")
        for e in b:
            print(f"  #{e.index:02d} {e.normalized}")
        print("\nCommands: [number]=fix entry, a=guided fix all, p=preview, q=quit")

    # Initial analyzed view based on current_parts
    current_raw, current_entries = reanalyze_with(rebuild_path(current_parts))

    while True:
        print_broken_list(current_entries)
        cmd = input("Fix> ").strip().lower()

        if cmd == "q":
            logger.info("Fix session quit by user")
            break

        if cmd == "p":
            proposed = rebuild_path(current_parts)
            print("\nPreview")
            print("-------")
            print("Proposed export line:")
            print("  export PATH=\"" + proposed.replace("\"", "\\\"") + "\"")

            _, preview_entries = reanalyze_with(proposed)
            prev_broken = [e for e in preview_entries if (not e.exists or not e.is_dir)]

            print(f"\nSummary: broken now = {len(prev_broken)}")
            print()
            logger.info("Preview requested")
            continue

        # Determine next target(s)
        if cmd == "a":
            # Guided fix all: repeatedly take the first broken entry in the *current* view
            while True:
                current_raw, current_entries = reanalyze_with(rebuild_path(current_parts))
                b = [e for e in current_entries if (not e.exists or not e.is_dir)]
                if not b:
                    print("\nNo broken entries remain.")
                    break
                target_entry = b[0]
                # Run the per-entry flow by faking a numeric selection
                cmd = str(target_entry.index)
                # fall through to numeric handler
                if not cmd.isdigit():
                    break
                # numeric handler below will run once; then loop repeats
                # We use a local flag to indicate we're in guided mode
                guided_mode = True
                # handle numeric selection
                target_idx = int(cmd)

                e = next((x for x in current_entries if x.index == target_idx), None)
                if e is None:
                    break
                # Apply fix for this entry
                _apply_fix_for_entry(e, current_parts, logger)
                continue

        if not cmd.isdigit():
            print("Enter a number, or a/p/q.")
            continue

        # numeric selection
        target_idx = int(cmd)
        current_raw, current_entries = reanalyze_with(rebuild_path(current_parts))
        e = next((x for x in current_entries if x.index == target_idx), None)
        if e is None:
            print(f"Entry #{target_idx:02d} not found.")
            continue
        if e.exists and e.is_dir:
            print(f"Entry #{target_idx:02d} is not broken.")
            continue

        _apply_fix_for_entry(e, current_parts, logger)
        current_raw, current_entries = reanalyze_with(rebuild_path(current_parts))

    proposed = rebuild_path(current_parts)
    logger.info("Interactive fix session complete")
    logger.info("Proposed PATH: %s", proposed)

    print("\n✅ Fix mode finished.")
    print("Suggested command to apply in your current shell session:")
    print("  export PATH=\"" + proposed.replace("\"", "\\\"") + "\"")
    print("To make it permanent, add that export line to your shell profile (e.g., ~/.zshrc).")
    print(f"\n📝 Log written to: {getattr(logger, '_path_log_file', 'path_fix_log_<timestamp>.log')}")

    new_raw, new_entries = reanalyze_with(proposed)
    return new_raw, new_entries


def _apply_fix_for_entry(e: Entry, parts: List[str], logger: logging.Logger) -> None:
    """Apply a chosen fix to the PATH parts list for the given (broken) entry."""
    i0 = e.index - 1
    if i0 < 0 or i0 >= len(parts):
        print("Internal index mismatch; skipping.")
        logger.error("Index mismatch for entry #%02d", e.index)
        return

    print(f"\nFixing entry #{e.index:02d}:")
    print(f"  Current : {e.raw}")
    print(f"  Expanded: {e.expanded}")
    print(f"  Normal  : {e.normalized}")

    alts = suggest_alternatives(e.raw)
    if alts:
        print("  Suggestions:")
        for i, s in enumerate(alts, start=1):
            print(f"    {i}) {s}")

    print("\nActions:")
    print("  1) Keep (do nothing)")
    print("  2) Remove from PATH")
    print("  3) Replace with a directory you type")
    print("  4) Replace with one of the suggestions")
    print("  5) Create the directory (mkdir -p) and keep it")
    print("  b) Back")

    action = input("Action [1-5/b]: ").strip().lower()
    if action == "b":
        return
    if action not in {"1", "2", "3", "4", "5"}:
        print("Invalid action.")
        return

    if action == "1":
        logger.info("#%02d KEEP | %s", e.index, e.normalized)
        return

    if action == "2":
        logger.info("#%02d REMOVE | %s", e.index, e.normalized)
        removed = parts.pop(i0)
        print(f"→ Removed: {removed}\n")
        return

    if action == "3":
        while True:
            typed = input("Replacement directory (or 'b' to back): ").strip()
            if typed.lower() == "b":
                return
            if not typed:
                print("Replacement cannot be empty.")
                continue
            norm = _safe_expand_and_normalize(typed)
            p = Path(norm)
            if p.exists() and p.is_dir():
                logger.info("#%02d REPLACE(manual) | from=%s | to=%s", e.index, e.normalized, norm)
                parts[i0] = typed
                print(f"→ Replaced with: {norm}\n")
                return
            print(f"Does not exist: {norm}")
            yn = input("Create it? [y/N]: ").strip().lower()
            if yn == "y":
                try:
                    p.mkdir(parents=True, exist_ok=True)
                    logger.info("#%02d REPLACE+MKDIR(manual) | from=%s | to=%s", e.index, e.normalized, norm)
                    parts[i0] = typed
                    print(f"→ Created and replaced with: {norm}\n")
                    return
                except Exception as ex:
                    logger.error("#%02d MKDIR FAILED | target=%s | error=%s", e.index, norm, ex)
                    print(f"Failed to create directory: {ex}")

    if action == "4":
        if not alts:
            print("No suggestions available.")
            logger.info("#%02d SUGGESTION_NONE | %s", e.index, e.normalized)
            return
        pick = input(f"Pick [1-{len(alts)}] (or 'b' to back): ").strip().lower()
        if pick == "b":
            return
        if pick.isdigit() and 1 <= int(pick) <= len(alts):
            chosen = alts[int(pick) - 1]
            if Path(chosen).exists() and Path(chosen).is_dir():
                logger.info("#%02d REPLACE(suggested) | from=%s | to=%s", e.index, e.normalized, chosen)
                parts[i0] = chosen
                print(f"→ Replaced with suggestion: {chosen}\n")
            else:
                print("Suggestion is not a valid directory.")
                logger.info("#%02d SUGGESTED_INVALID | chosen=%s", e.index, chosen)
        else:
            print("Invalid selection.")
        return

    if action == "5":
        target = _safe_expand_and_normalize(e.raw)
        p = Path(target)
        try:
            p.mkdir(parents=True, exist_ok=True)
            logger.info("#%02d MKDIR | created=%s", e.index, target)
            parts[i0] = e.raw
            print(f"→ Created directory and kept entry: {target}\n")
        except Exception as ex:
            logger.error("#%02d MKDIR FAILED | target=%s | error=%s", e.index, target, ex)
            print(f"Failed to create directory: {ex}")
        return


# ---- Main --------------------------------------------------------------------


def main():
    want_json = "--json" in sys.argv
    force_fix = "--fix" in sys.argv

    logger = setup_logger()

    raw_path, entries, grouped = analyze_path()

    # Log a quick run header
    logger.info("PATH Inspector run started")
    logger.info("Script: %s", str(Path(__file__).resolve()))
    logger.info("Python: %s", sys.version.replace("\n", " "))
    logger.info("Entries=%d", len(entries))

    broken = [e for e in entries if (not e.exists or not e.is_dir)]
    dups = [e for e in entries if e.duplicate_of is not None]
    shadowed = [e for e in entries if e.shadowed_by is not None]
    logger.info("Broken=%d Duplicates=%d Shadowed=%d", len(broken), len(dups), len(shadowed))

    # 1) ALWAYS display the report first
    Console, *_ = try_import_rich()
    if Console is not None:
        print_rich(raw_path, entries, grouped)
    else:
        print_fallback(raw_path, entries, grouped)
        print("Tip: Install rich for nicer output:  pip3 install rich\n")

    # 2) Offer fix after report
    want_fix = False
    if broken:
        if force_fix:
            want_fix = True
        else:
            resp = input(f"\nFound {len(broken)} broken PATH entr{'y' if len(broken)==1 else 'ies'}. Fix them now (you’ll still need to apply the printed export to persist)? [y/N]: ").strip().lower()
            want_fix = (resp == "y")

    if want_fix:
        # Add a console logger for this mode
        if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
            sh = logging.StreamHandler()
            sh.setLevel(logging.INFO)
            sh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
            logger.addHandler(sh)

        raw_path, entries = interactive_fix_broken_paths(raw_path, entries, logger)
        # Recompute grouping for final display
        old = os.environ.get("PATH", "")
        try:
            os.environ["PATH"] = raw_path
            _, _, grouped = analyze_path()
        finally:
            os.environ["PATH"] = old

        # Display final report after fix
        Console, *_ = try_import_rich()
        if Console is not None:
            print_rich(raw_path, entries, grouped)
        else:
            print_fallback(raw_path, entries, grouped)

    if want_json:
        data = {
            "raw_path": raw_path,
            "entries": [
                {
                    "index": e.index,
                    "raw": e.raw,
                    "expanded": e.expanded,
                    "normalized": e.normalized,
                    "exists": e.exists,
                    "is_dir": e.is_dir,
                    "category": e.category,
                    "reason": e.reason,
                    "duplicate_of": e.duplicate_of,
                    "shadowed_by": e.shadowed_by,
                    "flags": status_badges(e),
                }
                for e in entries
            ],
            "summary": {
                "total_entries": len(entries),
                "broken": [e.index for e in entries if (not e.exists or not e.is_dir)],
                "duplicates": [e.index for e in entries if e.duplicate_of is not None],
                "shadowed": [e.index for e in entries if e.shadowed_by is not None],
                "log_file": getattr(logger, "_path_log_file", None),
            },
        }
        print(json.dumps(data, indent=2))

    logger.info("PATH Inspector run finished")


if __name__ == "__main__":
    main()