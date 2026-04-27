#!/usr/bin/env python3
"""
Python Package Manager (PakMan)
--------------------------------
Author :  Anirban Bagchi
"""

import sys
import json
import subprocess
import argparse
import time
import datetime
import logging
from pathlib import Path

# ANSI Colors
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BLUE = "\033[94m"
BOLD = "\033[1m"
RESET = "\033[0m"

LOG_PATH = Path.home() / ".pakman.log"

_file_handler = logging.FileHandler(LOG_PATH)
_file_handler.setFormatter(logging.Formatter("[%(asctime)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
_logger = logging.getLogger("pakman")
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


def run_command(cmd: list[str], stream: bool = False, check: bool = True, dry_run: bool = False, capture: bool = True) -> subprocess.CompletedProcess:
    """Run a command with optional streaming."""
    cmd_str = ' '.join(cmd)

    if dry_run:
        print(f"{format_text('[DRY-RUN]', YELLOW)} Would execute: {cmd_str}")
        return subprocess.CompletedProcess(cmd, 0, stdout="[]", stderr="")

    try:
        if stream:
            print(f"{format_text('Running:', BLUE)} {cmd_str}")
            return subprocess.run(cmd, text=True, check=check)

        return subprocess.run(cmd, text=True, capture_output=capture, check=check)

    except subprocess.CalledProcessError as e:
        print(f"\n{format_text('❌ Command failed:', RED, bold=True)} {cmd_str}")
        if e.stderr:
            print(f"Error: {e.stderr.strip()}")
        if check:
            sys.exit(e.returncode)
        return e
    except FileNotFoundError:
        print(f"\n{format_text('❌ Error:', RED)} Command not found: {cmd[0]}")
        sys.exit(1)


def run_package_upgrade(pkg: str, dry_run: bool, pre: bool, max_retries: int) -> tuple[str, bool, str]:
    """Upgrade a single package with retries. Returns (name, success, error_message)."""
    cmd = [sys.executable, "-m", "pip", "install", "--upgrade"]
    if pre:
        cmd.append("--pre")
    cmd.append(pkg)
    cmd_str = ' '.join(cmd)

    if dry_run:
        print(f"{format_text('[DRY-RUN]', YELLOW)} Would execute: {cmd_str}")
        return (pkg, True, "")

    p = None
    for attempt in range(1, max_retries + 1):
        suffix = f" (attempt {attempt}/{max_retries})" if attempt > 1 else ""
        print(f"{format_text('Running:', BLUE)} {cmd_str}{suffix}")
        p = subprocess.run(cmd, text=True, capture_output=True)
        if p.returncode == 0:
            return (pkg, True, "")
        if attempt < max_retries:
            print(format_text("  ⚠️  Retrying...", YELLOW))

    error = (p.stderr.strip() or p.stdout.strip()) if p else "no attempts made"
    return (pkg, False, error)


def check_venv():
    """Warn user if not in a virtual environment."""
    if sys.prefix == sys.base_prefix:
        print(format_text("\n⚠️  WARNING: You are NOT running in a virtual environment.", YELLOW))
        print(format_text("   Installing/Upgrading global packages can break system tools.", YELLOW))
        print(f"   Interpreter: {sys.executable}\n")


def upgrade_pip(dry_run: bool):
    """Upgrade pip itself before upgrading packages."""
    print(f"\n{format_text('⬆️  Upgrading pip...', BLUE)}")
    cmd = [sys.executable, "-m", "pip", "install", "--upgrade", "pip"]
    run_command(cmd, stream=True, dry_run=dry_run)


def get_outdated_packages() -> list[dict]:
    """Return a list of outdated packages from pip."""
    print("🔍 Checking for outdated packages...")
    result = run_command(
        [sys.executable, "-m", "pip", "list", "--outdated", "--format=json"],
        dry_run=False
    )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        print(format_text("❌ Error: Could not parse pip output.", RED))
        return []


def export_freeze(path: str, dry_run: bool):
    """Run pip freeze and write to a file."""
    if dry_run:
        print(f"{format_text('[DRY-RUN]', YELLOW)} Would export: pip freeze > {path}")
        return
    print(f"\n{format_text('💾 Exporting freeze to:', BLUE)} {path}")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "freeze"],
        text=True, capture_output=True
    )
    if result.returncode != 0:
        print(format_text(f"  ⚠️  Export failed: {result.stderr.strip() or 'unknown error'}", RED))
        return
    Path(path).write_text(result.stdout)
    print(format_text(f"   Saved to {path}", GREEN))
    log(f"Freeze exported to {path}")


def send_notification(title: str, message: str):
    """Send a macOS notification via osascript."""
    title_safe = title.replace("\\", "\\\\").replace('"', '\\"')
    message_safe = message.replace("\\", "\\\\").replace('"', '\\"')
    script = f'display notification "{message_safe}" with title "{title_safe}"'
    subprocess.run(["osascript", "-e", script], capture_output=True)


def print_outdated_table(outdated: list[dict]):
    """Print the outdated packages table with dynamic column widths."""
    w_name = max(len("Package"), max(len(p["name"]) for p in outdated))
    w_ver  = max(len("Current"), max(len(p["version"]) for p in outdated))
    w_lat  = max(len("Latest"),  max(len(p["latest_version"]) for p in outdated))
    w_type = max(len("Type"),    max(len(p.get("latest_filetype", "")) for p in outdated))
    sep = "-" * (w_name + w_ver + w_lat + w_type + 6)

    print(f"\n{format_text('📦 Outdated Packages:', YELLOW, bold=True)}")
    print(f"{'Package':<{w_name}}  {'Current':<{w_ver}}  {'Latest':<{w_lat}}  {'Type':<{w_type}}")
    print(sep)
    for pkg in outdated:
        latest_type = pkg.get("latest_filetype", "")
        print(f"{pkg['name']:<{w_name}}  {pkg['version']:<{w_ver}}  {pkg['latest_version']:<{w_lat}}  {latest_type:<{w_type}}")
    print(sep)
    print(f"  {format_text(str(len(outdated)), YELLOW)} package(s) outdated\n")


def main():
    parser = argparse.ArgumentParser(description="PakMan: A robust Python package updater.")
    parser.add_argument("-y", "--yes", action="store_true", help="Auto-approve upgrades")
    parser.add_argument("--check-only", action="store_true", help="List outdated packages and exit")
    parser.add_argument("--dry-run", action="store_true", help="Simulate commands without executing")
    parser.add_argument("--exclude", nargs="+", default=[], metavar="PKG", help="Packages to exclude (case-insensitive)")
    parser.add_argument("--only", nargs="+", default=[], metavar="PKG", help="Upgrade only these packages (case-insensitive, must be outdated)")
    parser.add_argument("--upgrade-pip", action="store_true", help="Upgrade pip itself before upgrading packages")
    parser.add_argument("--pre", action="store_true", help="Include pre-release versions when upgrading")
    parser.add_argument("--export", metavar="FILE", help="Run pip freeze after upgrading and save to FILE")
    parser.add_argument("--notify", action="store_true", help="Send a macOS notification when done")
    parser.add_argument("--json", action="store_true", help="Output outdated packages as JSON and exit")
    parser.add_argument("--retries", type=int, default=2, metavar="N", help="Retries per package on failure [Default: 2, min: 1]")

    args = parser.parse_args()

    if args.retries < 1:
        parser.error("--retries must be at least 1")

    if args.only and args.exclude:
        overlap = {p.lower() for p in args.only} & {p.lower() for p in args.exclude}
        if overlap:
            parser.error(f"package(s) appear in both --only and --exclude: {', '.join(sorted(overlap))}")

    start_time = time.time()
    log("--- PakMan run started ---")

    print(format_text("\n📦 --- PakMan: Python Package Manager ---", BLUE, bold=True))

    check_venv()

    if args.upgrade_pip:
        upgrade_pip(args.dry_run)

    outdated = get_outdated_packages()

    # --json: output raw list and exit
    if args.json:
        print(json.dumps(outdated, indent=2))
        return

    # Apply --only filter (case-insensitive intersect with outdated)
    if args.only:
        only_set = {p.lower() for p in args.only}
        outdated = [p for p in outdated if p["name"].lower() in only_set]

    # Apply --exclude filter (case-insensitive)
    if args.exclude:
        exclude_set = {p.lower() for p in args.exclude}
        before = len(outdated)
        outdated = [p for p in outdated if p["name"].lower() not in exclude_set]
        excluded = before - len(outdated)
        if excluded:
            print(f"{format_text('ℹ️  Excluded', BLUE)} {excluded} package(s) via --exclude.")

    if not outdated:
        print(format_text("\n✅ All packages are up to date!", GREEN))
        elapsed = time.time() - start_time
        print(format_text(f"⏱  Completed in {elapsed:.1f}s", BLUE))
        log("Everything up to date. Run complete.")
        if args.notify:
            send_notification("PakMan", "All packages are up to date!")
        return

    print_outdated_table(outdated)

    if args.check_only:
        elapsed = time.time() - start_time
        print(format_text(f"⏱  Completed in {elapsed:.1f}s", BLUE))
        log(f"Check-only run: {len(outdated)} package(s) outdated.")
        return

    # Confirmation
    if not args.yes:
        if args.dry_run:
            print(f"{format_text('[DRY-RUN]', YELLOW)} Skipping confirmation.")
        else:
            choice = input(f"{format_text('❓ Upgrade all displayed packages? (y/N): ', BLUE)}").strip().lower()
            if choice not in ("y", "yes"):
                print(format_text("\n⏭️  Upgrade canceled.", YELLOW))
                return

    # Per-package upgrade with retries
    print(f"\n{format_text('⬆️  Upgrading packages...', BLUE)}")
    failures: list[tuple[str, str]] = []

    for pkg in outdated:
        name = pkg["name"]
        _, success, error = run_package_upgrade(name, args.dry_run, args.pre, args.retries)
        if success:
            log(f"Upgraded: {name} {pkg['version']} -> {pkg['latest_version']}")
        else:
            failures.append((name, error))
            print(format_text(f"  ❌ Failed: {name} — {error}", RED))
            log(f"FAILED: {name} — {error}")

    # Optional freeze export
    if args.export:
        export_freeze(args.export, args.dry_run)

    elapsed = time.time() - start_time

    if failures:
        print(f"\n{format_text('⚠️  Completed with failures:', YELLOW, bold=True)}")
        for name, error in failures:
            print(f"  • {name}: {error or 'unknown error'}")
        log(f"Run complete with {len(failures)} failure(s). Elapsed: {elapsed:.1f}s")
        if args.notify:
            send_notification("PakMan", f"Done with {len(failures)} failure(s). Check log.")
    else:
        print(f"\n{format_text('✅ Done.', GREEN, bold=True)}")
        log(f"Run complete. All upgrades successful. Elapsed: {elapsed:.1f}s")
        if args.notify:
            send_notification("PakMan", "All packages upgraded successfully!")

    print(format_text(f"⏱  Completed in {elapsed:.1f}s", BLUE))
    print(format_text(f"📝 Log: {LOG_PATH}", BLUE))


if __name__ == "__main__":
    main()
