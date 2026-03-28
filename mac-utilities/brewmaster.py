#!/usr/bin/env python3
"""
Homebrew Upgrader with Enhanced Features
--------------------------------
Author :  Anirban Bagchi
"""

import argparse
import subprocess
import sys
import shutil
import json
import time
import datetime
import threading
from pathlib import Path

# ANSI Colors
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BLUE = "\033[94m"
BOLD = "\033[1m"
RESET = "\033[0m"

LOG_PATH = Path.home() / ".brewmaster.log"


def format_text(text: str, color: str = RESET, bold: bool = False) -> str:
    """Format text with ANSI colors."""
    code = color
    if bold:
        code += BOLD
    return f"{code}{text}{RESET}"


def log(message: str):
    """Append a timestamped message to the log file."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_PATH, "a") as f:
        f.write(f"[{timestamp}] {message}\n")


def run_command(cmd: list[str], stream: bool = False, check: bool = True, dry_run: bool = False) -> subprocess.CompletedProcess:
    """
    Run a command.

    Args:
        cmd: The command to run.
        stream: If True, print output in real-time. If False, capture it.
        check: If True, exit on failure.
        dry_run: If True, print the command but don't execute (returns dummy process).
    """
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
        sys.exit(1)


def run_package(cmd_prefix: list[str], pkg: str, dry_run: bool, max_retries: int = 2) -> tuple[str, bool, str]:
    """
    Attempt to upgrade a single package, with retries.
    Returns (pkg_name, success, error_message).
    """
    cmd = cmd_prefix + [pkg]
    cmd_str = ' '.join(cmd)

    if dry_run:
        print(f"{format_text('[DRY-RUN]', YELLOW)} Would execute: {cmd_str}")
        return (pkg, True, "")

    p = subprocess.CompletedProcess(cmd, 1)
    for attempt in range(1, max_retries + 1):
        suffix = f" (attempt {attempt}/{max_retries})" if attempt > 1 else ""
        print(f"{format_text('Running:', BLUE)} {cmd_str}{suffix}")
        p = subprocess.run(cmd, text=True, capture_output=True)
        if p.returncode == 0:
            return (pkg, True, "")
        if attempt < max_retries:
            print(format_text("  ⚠️  Retrying...", YELLOW))

    error = p.stderr.strip() or p.stdout.strip()
    return (pkg, False, error)


def check_brew_installed():
    """Verify Homebrew is installed."""
    if not shutil.which("brew"):
        print(format_text("❌ 'brew' not found. Install Homebrew first: https://brew.sh/", RED))
        sys.exit(1)


def get_pinned() -> set[str]:
    """Return set of pinned formula names."""
    p = subprocess.run(["brew", "list", "--pinned"], text=True, capture_output=True)
    return {line.strip() for line in p.stdout.splitlines() if line.strip()}


def get_outdated_json(greedy: bool) -> tuple[list[dict], list[dict]]:
    """
    Fetch outdated formulae and casks in parallel using brew's JSON output.
    Each item is a dict with name, installed_versions, current_version.
    """
    formulae: list[dict] = []
    casks: list[dict] = []

    def fetch_formulae():
        p = subprocess.run(
            ["brew", "outdated", "--formula", "--json=v2"],
            text=True, capture_output=True
        )
        if p.returncode == 0 and p.stdout.strip():
            formulae.extend(json.loads(p.stdout).get("formulae", []))

    def fetch_casks():
        cmd = ["brew", "outdated", "--cask", "--json=v2"]
        if greedy:
            cmd.append("--greedy")
        p = subprocess.run(cmd, text=True, capture_output=True)
        if p.returncode == 0 and p.stdout.strip():
            casks.extend(json.loads(p.stdout).get("casks", []))

    t1 = threading.Thread(target=fetch_formulae)
    t2 = threading.Thread(target=fetch_casks)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    return formulae, casks


def format_package_info(pkg: dict) -> str:
    """Format a package entry as 'name  old → new'."""
    name = pkg.get("name", "?")
    installed = pkg.get("installed_versions", [])
    current = pkg.get("current_version", "?")
    installed_str = ", ".join(installed) if installed else "?"
    return f"{name}  {format_text(installed_str, YELLOW)} → {format_text(current, GREEN)}"


def send_notification(title: str, message: str):
    """Send a macOS notification via osascript."""
    script = f'display notification "{message}" with title "{title}"'
    subprocess.run(["osascript", "-e", script], capture_output=True)


def backup_bundle(dry_run: bool):
    """Snapshot the current Homebrew state via brew bundle dump."""
    backup_path = Path.home() / f".brewmaster_backup_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.Brewfile"
    if dry_run:
        print(f"{format_text('[DRY-RUN]', YELLOW)} Would backup bundle to: {backup_path}")
        return
    print(f"{format_text('💾 Backing up bundle to:', BLUE)} {backup_path}")
    result = subprocess.run(
        ["brew", "bundle", "dump", "--file=/dev/stdout"],
        text=True, capture_output=True
    )
    backup_path.write_text(result.stdout)
    print(format_text(f"   Saved to {backup_path}", GREEN))
    log(f"Backup saved to {backup_path}")


def filter_packages(pkgs: list[dict], skip_set: set[str], pinned_set: set[str]):
    """Split packages into (kept, skipped_by_flag, skipped_pinned)."""
    kept, skipped_skip, skipped_pinned = [], [], []
    for pkg in pkgs:
        name = pkg.get("name", "")
        if name in pinned_set:
            skipped_pinned.append(name)
        elif name in skip_set:
            skipped_skip.append(name)
        else:
            kept.append(pkg)
    return kept, skipped_skip, skipped_pinned


def main():
    parser = argparse.ArgumentParser(description="BrewMaster: A better Homebrew upgrader.")
    parser.add_argument("-y", "--yes", action="store_true", help="Auto-approve all upgrades")
    parser.add_argument("--greedy", action="store_true", default=True, help="Use --greedy for casks [Default: True]")
    parser.add_argument("--no-greedy", dest="greedy", action="store_false", help="Disable --greedy for casks")
    parser.add_argument("--check-only", dest="check_only", action="store_true", help="Only report outdated packages, don't upgrade")
    parser.add_argument("--dry-run", action="store_true", help="Simulate commands without running them")
    parser.add_argument("--skip", nargs="+", metavar="PKG", default=[], help="Skip specific packages (e.g. --skip node python)")
    parser.add_argument("--formula-only", action="store_true", help="Only upgrade formulae, skip casks")
    parser.add_argument("--cask-only", action="store_true", help="Only upgrade casks, skip formulae")
    parser.add_argument("--notify", action="store_true", help="Send a macOS notification when done")
    parser.add_argument("--backup", action="store_true", help="Backup Homebrew bundle before upgrading")
    parser.add_argument("--retries", type=int, default=2, metavar="N", help="Retries per package on failure [Default: 2]")

    args = parser.parse_args()

    start_time = time.time()
    log("--- BrewMaster run started ---")

    print(format_text("\n🍺 --- BrewMaster ---", BLUE, bold=True))

    check_brew_installed()

    if args.backup:
        backup_bundle(args.dry_run)

    # Update Homebrew metadata
    print(f"\n{format_text('🔄 Updating Homebrew... (brew update)', BLUE)}")
    run_command(["brew", "update"], stream=True, dry_run=args.dry_run)

    # Fetch outdated packages in parallel with version info
    print(f"\n{format_text('🔍 Checking outdated packages...', BLUE)}")
    formulae_raw, casks_raw = get_outdated_json(args.greedy)

    # Apply --formula-only / --cask-only filters
    if args.formula_only:
        casks_raw = []
    if args.cask_only:
        formulae_raw = []

    # Skip pinned and --skip packages
    pinned = get_pinned()
    skip_set = set(args.skip)

    formulae, skipped_f_flag, skipped_f_pinned = filter_packages(formulae_raw, skip_set, pinned)
    casks, skipped_c_flag, skipped_c_pinned = filter_packages(casks_raw, skip_set, pinned)

    # Summary
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
        return

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
        return

    # Confirmation prompt
    if not args.yes:
        if args.dry_run:
            print(f"\n{format_text('[DRY-RUN]', YELLOW)} Skipping confirmation prompt.")
        else:
            choice = input(f"\n{format_text('❓ Upgrade these packages? (y/N): ', BLUE)}").strip().lower()
            if choice not in ("y", "yes"):
                print(format_text("\n⏭️  Upgrade canceled.", YELLOW))
                return

    failures: list[tuple[str, str, str]] = []

    # Upgrade formulae one-by-one with retries
    if formulae:
        print(f"\n{format_text('⬆️  Upgrading formulae...', BLUE)}")
        for pkg in formulae:
            name = pkg.get("name", "")
            _, success, error = run_package(["brew", "upgrade"], name, args.dry_run, args.retries)
            if success:
                log(f"Upgraded formula: {name}")
            else:
                failures.append(("formula", name, error))
                print(format_text(f"  ❌ Failed: {name} — {error}", RED))
                log(f"FAILED formula: {name} — {error}")

    # Upgrade casks one-by-one with retries
    if casks:
        print(f"\n{format_text('⬆️  Upgrading casks...', BLUE)}")
        cask_prefix = ["brew", "upgrade", "--cask"]
        if args.greedy:
            cask_prefix.append("--greedy")
        for pkg in casks:
            name = pkg.get("name", "")
            _, success, error = run_package(cask_prefix, name, args.dry_run, args.retries)
            if success:
                log(f"Upgraded cask: {name}")
            else:
                failures.append(("cask", name, error))
                print(format_text(f"  ❌ Failed: {name} — {error}", RED))
                log(f"FAILED cask: {name} — {error}")

    # Cleanup
    print(f"\n{format_text('🧹 Cleaning up...', BLUE)}")
    run_command(["brew", "cleanup"], stream=True, dry_run=args.dry_run)

    elapsed = time.time() - start_time

    if failures:
        print(f"\n{format_text('⚠️  Completed with failures:', YELLOW, bold=True)}")
        for kind, name, error in failures:
            print(f"  • [{kind}] {name}: {error or 'unknown error'}")
        log(f"Run complete with {len(failures)} failure(s). Elapsed: {elapsed:.1f}s")
        if args.notify:
            send_notification("BrewMaster", f"Done with {len(failures)} failure(s). Check log.")
    else:
        print(f"\n{format_text('✅ Done.', GREEN, bold=True)}")
        log(f"Run complete. All upgrades successful. Elapsed: {elapsed:.1f}s")
        if args.notify:
            send_notification("BrewMaster", "All packages upgraded successfully!")

    print(format_text(f"⏱  Completed in {elapsed:.1f}s", BLUE))
    print(format_text(f"📝 Log: {LOG_PATH}", BLUE))


if __name__ == "__main__":
    main()
