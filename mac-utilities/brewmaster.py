#!/usr/bin/env python3
"""
Homebrew Upgrader with Enhanced Features
--------------------------------
Author :  Anirban Bagchi
"""

import argparse
import fnmatch
import json
import re
import shutil
import subprocess
import sys
import time
import datetime
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# ANSI Colors
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BLUE = "\033[94m"
BOLD = "\033[1m"
RESET = "\033[0m"

LOG_PATH = Path.home() / ".brewmaster.log"
HISTORY_PATH = Path.home() / ".brewmaster_history.jsonl"
MAX_BACKUPS = 5

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

BREW = "brew"  # resolved to an absolute path in check_brew_installed()

# Log may contain paths and error output — keep it private to the user.
LOG_PATH.touch(mode=0o600, exist_ok=True)
_file_handler = logging.FileHandler(LOG_PATH)
_file_handler.setFormatter(logging.Formatter("[%(asctime)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
_logger = logging.getLogger("brewmaster")
_logger.addHandler(_file_handler)
_logger.setLevel(logging.DEBUG)


def format_text(text: str, color: str = "", bold: bool = False) -> str:
    code = color
    if bold:
        code += BOLD
    if not code:
        return text
    return f"{code}{text}{RESET}"


def log(message: str):
    _logger.info(message)


def human_size(n: float) -> str:
    for unit in ("B", "KB", "MB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def run_command(cmd: list[str], stream: bool = False, check: bool = True, dry_run: bool = False) -> subprocess.CompletedProcess:
    cmd_str = ' '.join(cmd)

    if dry_run:
        print(f"{format_text('[DRY-RUN]', YELLOW)} Would execute: {cmd_str}")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    try:
        if stream:
            print(f"{format_text('Running:', BLUE)} {cmd_str}")
            p = subprocess.run(cmd, text=True)
        else:
            p = subprocess.run(cmd, text=True, capture_output=True)

        if check and p.returncode != 0:
            print(f"\n{format_text('❌ Command failed:', RED, bold=True)} {cmd_str}")
            if not stream:
                if p.stdout and p.stdout.strip():
                    print(format_text("Stdout:", YELLOW))
                    print(p.stdout.strip())
                if p.stderr and p.stderr.strip():
                    print(format_text("Stderr:", YELLOW))
                    print(p.stderr.strip())
            sys.exit(p.returncode)

        return p

    except FileNotFoundError:
        print(f"\n{format_text('❌ Error:', RED, bold=True)} Executable not found for: {cmd[0]}")
        sys.exit(EXIT_FATAL)


def run_package(cmd_prefix: list[str], pkg: str, dry_run: bool, max_retries: int = 2, timeout: int = 600) -> tuple[str, bool, str]:
    """Attempt to upgrade a single package with retries. Returns (pkg_name, success, error_message)."""
    cmd = cmd_prefix + [pkg]
    cmd_str = ' '.join(cmd)

    if dry_run:
        print(f"{format_text('[DRY-RUN]', YELLOW)} Would execute: {cmd_str}")
        return (pkg, True, "")

    error = ""
    for attempt in range(1, max_retries + 1):
        suffix = f" (attempt {attempt}/{max_retries})" if attempt > 1 else ""
        print(f"{format_text('Running:', BLUE)} {cmd_str}{suffix}")
        try:
            p = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            error = f"timed out after {timeout}s"
            log(f"AUDIT: {cmd_str} -> {error}")
            if attempt < max_retries:
                print(format_text("  ⚠️  Timed out, retrying...", YELLOW))
            continue
        log(f"AUDIT: {cmd_str} -> exit {p.returncode}")
        if p.returncode == 0:
            return (pkg, True, "")
        error = p.stderr.strip() or p.stdout.strip()
        if attempt < max_retries:
            print(format_text("  ⚠️  Retrying...", YELLOW))

    return (pkg, False, error or "no attempts made")


def check_brew_installed():
    """Resolve brew to an absolute path and warn on unusual locations."""
    global BREW
    found = shutil.which("brew")
    if not found:
        print(format_text("❌ 'brew' not found. Install Homebrew first: https://brew.sh/", RED))
        sys.exit(EXIT_FATAL)
    BREW = str(Path(found).resolve())
    if BREW not in KNOWN_BREW_PATHS:
        print(format_text(f"⚠️  Unusual brew location: {BREW}", YELLOW))
        print(format_text("   Expected /opt/homebrew/bin/brew or /usr/local/bin/brew — verify your PATH.", YELLOW))
        log(f"WARNING: unusual brew location: {BREW}")


def brew_update_is_fresh(max_age_secs: int = 3600) -> bool:
    """Return True if brew update ran within the last max_age_secs."""
    p = subprocess.run([BREW, "--repository"], text=True, capture_output=True)
    if p.returncode != 0 or not p.stdout.strip():
        return False
    fetch_head = Path(p.stdout.strip()) / ".git" / "FETCH_HEAD"
    try:
        return (time.time() - fetch_head.stat().st_mtime) < max_age_secs
    except OSError:
        return False


def get_pinned() -> set[str]:
    p = subprocess.run([BREW, "list", "--pinned"], text=True, capture_output=True)
    if p.returncode != 0:
        print(format_text("⚠️  Could not fetch pinned packages; proceeding without pin protection.", YELLOW))
        return set()
    return {line.strip() for line in p.stdout.splitlines() if line.strip()}


def get_outdated_json(greedy: bool) -> tuple[list[dict], list[dict]]:
    """Fetch outdated formulae and casks in a single brew call."""
    cmd = [BREW, "outdated", "--json=v2"]
    if greedy:
        cmd.append("--greedy")
    p = subprocess.run(cmd, text=True, capture_output=True)
    if p.returncode != 0 or not p.stdout.strip():
        return [], []
    data = json.loads(p.stdout)
    return data.get("formulae", []), data.get("casks", [])


def prefetch_packages(formula_names: list[str], cask_names: list[str], dry_run: bool, timeout: int):
    """Download all bottles/casks in parallel so upgrades hit the local cache."""
    total = len(formula_names) + len(cask_names)
    if total == 0:
        return
    if dry_run:
        print(f"{format_text('[DRY-RUN]', YELLOW)} Would prefetch {total} download(s) in parallel.")
        return
    print(f"\n{format_text(f'⬇️  Prefetching {total} download(s) in parallel...', BLUE)}")

    def fetch(fetch_args: list[str]):
        try:
            subprocess.run([BREW, "fetch"] + fetch_args, capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            pass  # the upgrade step will retry the download itself

    with ThreadPoolExecutor(max_workers=4) as ex:
        for name in formula_names:
            ex.submit(fetch, ["--formula", name])
        for name in cask_names:
            ex.submit(fetch, ["--cask", name])


def cached_download_size(formula_names: list[str], cask_names: list[str]) -> int:
    """Sum the on-disk size of prefetched downloads via brew --cache."""
    paths: list[str] = []
    if formula_names:
        p = subprocess.run([BREW, "--cache", "--formula"] + formula_names, text=True, capture_output=True)
        if p.returncode == 0:
            paths += p.stdout.splitlines()
    if cask_names:
        p = subprocess.run([BREW, "--cache", "--cask"] + cask_names, text=True, capture_output=True)
        if p.returncode == 0:
            paths += p.stdout.splitlines()
    total = 0
    for path in paths:
        path = path.strip()
        if path and Path(path).exists():
            total += Path(path).stat().st_size
    return total


def format_package_info(pkg: dict) -> str:
    name = pkg.get("name", "?")
    installed = pkg.get("installed_versions", [])
    current = pkg.get("current_version", "?")
    installed_str = ", ".join(installed) if installed else "?"
    return f"{name}  {format_text(installed_str, YELLOW)} → {format_text(current, GREEN)}"


def send_notification(title: str, message: str):
    """Send a macOS notification via osascript."""
    title_safe = title.replace("\\", "\\\\").replace('"', '\\"')
    message_safe = message.replace("\\", "\\\\").replace('"', '\\"')
    script = f'display notification "{message_safe}" with title "{title_safe}"'
    subprocess.run(["osascript", "-e", script], capture_output=True)


def prune_backups(keep: int = MAX_BACKUPS):
    """Delete all but the newest `keep` backup Brewfiles created by this tool."""
    backups = sorted(Path.home().glob(".brewmaster_backup_*.Brewfile"))
    for old in backups[:-keep]:
        old.unlink()
        print(format_text(f"   🗑  Pruned old backup: {old.name}", YELLOW))
        log(f"Pruned old backup: {old}")


def backup_bundle(dry_run: bool):
    """Snapshot the current Homebrew state via brew bundle dump."""
    backup_path = Path.home() / f".brewmaster_backup_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.Brewfile"
    if dry_run:
        print(f"{format_text('[DRY-RUN]', YELLOW)} Would backup bundle to: {backup_path}")
        return
    print(f"{format_text('💾 Backing up bundle to:', BLUE)} {backup_path}")
    result = subprocess.run(
        [BREW, "bundle", "dump", "--file=/dev/stdout"],
        text=True, capture_output=True
    )
    if result.returncode != 0:
        print(format_text(f"  ⚠️  Backup failed: {result.stderr.strip() or 'unknown error'}", RED))
        return
    backup_path.write_text(result.stdout)
    print(format_text(f"   Saved to {backup_path}", GREEN))
    log(f"Backup saved to {backup_path}")
    prune_backups()


def filter_packages(pkgs: list[dict], skip_patterns: list[str], pinned_set: set[str]):
    """Split packages into (kept, skipped_by_flag, skipped_pinned). Skip patterns support fnmatch globs."""
    kept, skipped_skip, skipped_pinned = [], [], []
    for pkg in pkgs:
        name = pkg.get("name", "")
        if name in pinned_set:
            skipped_pinned.append(name)
        elif any(fnmatch.fnmatch(name, pat) for pat in skip_patterns):
            skipped_skip.append(name)
        else:
            kept.append(pkg)
    return kept, skipped_skip, skipped_pinned


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


def select_packages(entries: list[tuple[str, dict]]) -> list[tuple[str, dict]]:
    """Interactive per-package selection. Returns the chosen subset."""
    print(f"\n{format_text('Select packages to upgrade:', BLUE, bold=True)}")
    for i, (kind, pkg) in enumerate(entries, 1):
        print(f"  {i:>3}. [{kind}] {format_package_info(pkg)}")
    while True:
        raw = input(f"{format_text('Selection (e.g. 1,3,5-7 | all | none): ', BLUE)}").strip().lower()
        if raw in ("all", "a", ""):
            return entries
        if raw in ("none", "n", "q"):
            return []
        idxs = parse_selection(raw, len(entries))
        if idxs is not None:
            return [entries[i] for i in idxs]
        print(format_text("  Invalid selection, try again.", YELLOW))


def write_history(record: dict):
    """Append one structured JSON record per run to the history file."""
    HISTORY_PATH.touch(mode=0o600, exist_ok=True)
    with open(HISTORY_PATH, "a") as f:
        f.write(json.dumps(record) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="BrewMaster: A better Homebrew upgrader.")
    parser.add_argument("-y", "--yes", action="store_true", help="Auto-approve all upgrades")
    parser.add_argument("-i", "--interactive", action="store_true", help="Pick packages to upgrade from a numbered list")
    parser.add_argument("--greedy", action="store_true", default=True, help="Use --greedy for casks [Default: True]")
    parser.add_argument("--no-greedy", dest="greedy", action="store_false", help="Disable --greedy for casks")
    parser.add_argument("--check-only", dest="check_only", action="store_true", help="Only report outdated packages, don't upgrade (exit 3 if any found)")
    parser.add_argument("--dry-run", action="store_true", help="Simulate commands without running them")
    parser.add_argument("--skip", nargs="+", metavar="PKG", default=[], help="Skip packages; glob patterns supported (e.g. --skip node 'python@*')")
    parser.add_argument("--formula-only", action="store_true", help="Only upgrade formulae, skip casks")
    parser.add_argument("--cask-only", action="store_true", help="Only upgrade casks, skip formulae")
    parser.add_argument("--notify", action="store_true", help="Send a macOS notification when done")
    parser.add_argument("--backup", action="store_true", help="Backup Homebrew bundle before upgrading (keeps last %d)" % MAX_BACKUPS)
    parser.add_argument("--no-update", action="store_true", help="Skip brew update entirely")
    parser.add_argument("--force-update", action="store_true", help="Run brew update even if it ran within the last hour")
    parser.add_argument("--sizes", action="store_true", help="Prefetch downloads and show total size before confirming (downloads before you confirm)")
    parser.add_argument("--log-json", action="store_true", help=f"Append a structured JSON record per run to {HISTORY_PATH}")
    parser.add_argument("--retries", type=int, default=2, metavar="N", help="Retries per package on failure [Default: 2, min: 1]")
    parser.add_argument("--timeout", type=int, default=600, metavar="SECS", help="Timeout per package upgrade [Default: 600]")

    args = parser.parse_args()

    if args.formula_only and args.cask_only:
        parser.error("--formula-only and --cask-only are mutually exclusive")
    if args.interactive and args.yes:
        parser.error("--interactive and --yes are mutually exclusive")
    if args.retries < 1:
        parser.error("--retries must be at least 1")
    if args.timeout < 1:
        parser.error("--timeout must be at least 1")

    # Fail fast in cron/launchd instead of hanging on input()
    needs_tty = args.interactive or not (args.yes or args.dry_run or args.check_only)
    if needs_tty and not sys.stdin.isatty():
        print(format_text("❌ Non-interactive session and no -y/--yes flag; refusing to prompt.", RED))
        return EXIT_FATAL

    start_time = time.time()
    log("--- BrewMaster run started ---")

    print(format_text("\n🍺 --- BrewMaster ---", BLUE, bold=True))

    check_brew_installed()

    if args.backup:
        backup_bundle(args.dry_run)

    if args.no_update:
        print(f"\n{format_text('🔄 Skipping brew update (--no-update).', YELLOW)}")
    elif not args.force_update and brew_update_is_fresh():
        print(f"\n{format_text('🔄 brew update ran within the last hour — skipping (use --force-update to force).', YELLOW)}")
    else:
        print(f"\n{format_text('🔄 Updating Homebrew... (brew update)', BLUE)}")
        run_command([BREW, "update"], stream=True, dry_run=args.dry_run)

    print(f"\n{format_text('🔍 Checking outdated packages...', BLUE)}")
    formulae_raw, casks_raw = get_outdated_json(args.greedy)

    if args.formula_only:
        casks_raw = []
    if args.cask_only:
        formulae_raw = []

    pinned = get_pinned()

    formulae, skipped_f_flag, skipped_f_pinned = filter_packages(formulae_raw, args.skip, pinned)
    casks, skipped_c_flag, skipped_c_pinned = filter_packages(casks_raw, args.skip, pinned)

    print(f"\n{format_text('📦 Summary:', BLUE, bold=True)}")

    for name in skipped_f_pinned + skipped_c_pinned:
        print(format_text(f"  📌 Skipping pinned: {name}", YELLOW))
    for name in skipped_f_flag + skipped_c_flag:
        print(format_text(f"  ⏭️  Skipping (--skip): {name}", YELLOW))

    if not formulae and not casks:
        print(format_text("✅ Everything is up to date!", GREEN))
        elapsed = time.time() - start_time
        print(format_text(f"⏱  Completed in {elapsed:.1f}s", BLUE))
        log("Everything up to date. Run complete.")
        if args.notify:
            send_notification("BrewMaster", "Everything is up to date!")
        if args.log_json:
            write_history({
                "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
                "upgraded": [], "failures": [], "elapsed_secs": round(elapsed, 1),
                "interrupted": False, "exit_code": EXIT_OK,
            })
        return EXIT_OK

    if formulae:
        print(f"\n{format_text(str(len(formulae)), YELLOW)} outdated formulae:")
        for pkg in formulae:
            print(f"  • {format_package_info(pkg)}")

    if casks:
        print(f"\n{format_text(str(len(casks)), YELLOW)} outdated casks{' (greedy)' if args.greedy else ''}:")
        for pkg in casks:
            print(f"  • {format_package_info(pkg)}")

    if args.check_only:
        elapsed = time.time() - start_time
        print(format_text(f"\n⏱  Completed in {elapsed:.1f}s", BLUE))
        log(f"Check-only run: {len(formulae)} formulae + {len(casks)} casks outdated.")
        return EXIT_OUTDATED

    entries: list[tuple[str, dict]] = [("formula", p) for p in formulae] + [("cask", p) for p in casks]

    if args.interactive:
        entries = select_packages(entries)
        if not entries:
            print(format_text("\n⏭️  Nothing selected. Upgrade canceled.", YELLOW))
            return EXIT_OK

    # Reject suspicious names before they reach a subprocess
    failures: list[tuple[str, str, str]] = []
    valid_entries: list[tuple[str, dict]] = []
    for kind, pkg in entries:
        name = pkg.get("name", "")
        if VALID_PKG.match(name):
            valid_entries.append((kind, pkg))
        else:
            failures.append((kind, name, "invalid package name — skipped"))
            print(format_text(f"  ❌ Skipping invalid package name: {name!r}", RED))
            log(f"SKIPPED invalid package name: {name!r}")

    formula_names = [p["name"] for kind, p in valid_entries if kind == "formula"]
    cask_names = [p["name"] for kind, p in valid_entries if kind == "cask"]

    # --sizes prefetches before the prompt so we can report real byte counts
    if args.sizes:
        prefetch_packages(formula_names, cask_names, args.dry_run, args.timeout)
        if not args.dry_run:
            size = cached_download_size(formula_names, cask_names)
            print(f"{format_text('⬇️  Total download size:', BLUE)} ~{human_size(size)}")

    # Confirmation (interactive selection already implies consent)
    if not args.yes and not args.interactive:
        if args.dry_run:
            print(f"\n{format_text('[DRY-RUN]', YELLOW)} Skipping confirmation prompt.")
        else:
            choice = input(f"\n{format_text('❓ Upgrade these packages? (y/N): ', BLUE)}").strip().lower()
            if choice not in ("y", "yes"):
                print(format_text("\n⏭️  Upgrade canceled.", YELLOW))
                return EXIT_OK

    if not args.sizes:
        prefetch_packages(formula_names, cask_names, args.dry_run, args.timeout)

    cask_prefix = [BREW, "upgrade", "--cask"]
    if args.greedy:
        cask_prefix.append("--greedy")

    upgraded: list[str] = []
    interrupted = False

    print(f"\n{format_text('⬆️  Upgrading packages...', BLUE)}")
    try:
        for kind, pkg in valid_entries:
            name = pkg["name"]
            prefix = [BREW, "upgrade"] if kind == "formula" else cask_prefix
            _, success, error = run_package(prefix, name, args.dry_run, args.retries, args.timeout)
            if success:
                upgraded.append(name)
                log(f"Upgraded {kind}: {name}")
            else:
                failures.append((kind, name, error))
                print(format_text(f"  ❌ Failed: {name} — {error}", RED))
                log(f"FAILED {kind}: {name} — {error}")
    except KeyboardInterrupt:
        interrupted = True
        remaining = len(valid_entries) - len(upgraded) - len(failures)
        print(format_text(f"\n⏹️  Interrupted — {len(upgraded)} upgraded, {len(failures)} failed, {remaining} not attempted.", YELLOW, bold=True))
        log(f"Run interrupted: {len(upgraded)} upgraded, {len(failures)} failed, {remaining} not attempted.")

    if not interrupted:
        print(f"\n{format_text('🧹 Cleaning up...', BLUE)}")
        run_command([BREW, "cleanup"], stream=True, dry_run=args.dry_run)

    elapsed = time.time() - start_time

    if failures:
        print(f"\n{format_text('⚠️  Completed with failures:', YELLOW, bold=True)}")
        for kind, name, error in failures:
            print(f"  • [{kind}] {name}: {error or 'unknown error'}")
        log(f"Run complete with {len(failures)} failure(s). Elapsed: {elapsed:.1f}s")
        if args.notify:
            send_notification("BrewMaster", f"Done with {len(failures)} failure(s). Check log.")
    elif not interrupted:
        print(f"\n{format_text('✅ Done.', GREEN, bold=True)}")
        log(f"Run complete. All upgrades successful. Elapsed: {elapsed:.1f}s")
        if args.notify:
            send_notification("BrewMaster", "All packages upgraded successfully!")

    print(format_text(f"⏱  Completed in {elapsed:.1f}s", BLUE))
    print(format_text(f"📝 Log: {LOG_PATH}", BLUE))

    if interrupted:
        exit_code = 130
    elif failures:
        exit_code = EXIT_FAILURES
    else:
        exit_code = EXIT_OK

    if args.log_json:
        write_history({
            "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
            "upgraded": upgraded,
            "failures": [{"kind": k, "name": n, "error": e} for k, n, e in failures],
            "elapsed_secs": round(elapsed, 1),
            "interrupted": interrupted,
            "exit_code": exit_code,
        })

    return exit_code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print(format_text("\n⏹️  Interrupted.", YELLOW))
        log("Run interrupted by user.")
        sys.exit(130)
