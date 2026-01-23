"""
Python Package Manager (PakMan)
--------------------------------
Author :  Anirban Bagchi
"""

#!/usr/bin/env python3
import sys
import json
import subprocess
import argparse
import os

# ANSI Colors
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BLUE = "\033[94m"
BOLD = "\033[1m"
RESET = "\033[0m"


def format_text(text: str, color: str = RESET, bold: bool = False) -> str:
    """Format text with ANSI colors."""
    code = color
    if bold:
        code += BOLD
    return f"{code}{text}{RESET}"


def run_command(cmd: list[str], stream: bool = False, check: bool = True, dry_run: bool = False, capture: bool = True) -> subprocess.CompletedProcess:
    """Run a command with optional streaming definition."""
    cmd_str = ' '.join(cmd)
    
    if dry_run:
        print(f"{format_text('[DRY-RUN]', YELLOW)} Would execute: {cmd_str}")
        return subprocess.CompletedProcess(cmd, 0, stdout="{}", stderr="")

    try:
        if stream:
            print(f"{format_text('Running:', BLUE)} {cmd_str}")
            return subprocess.run(cmd, text=True, check=check)
        
        # When not streaming, we usually want to capture output
        return subprocess.run(cmd, text=True, capture_output=capture, check=check)

    except subprocess.CalledProcessError as e:
        if not dry_run:
            print(f"\n{format_text('❌ Command failed:', RED, bold=True)} {cmd_str}")
            if e.stderr:
                print(f"Error: {e.stderr.strip()}")
        if check:
            sys.exit(e.returncode)
        return e
    except FileNotFoundError:
        print(f"\n{format_text('❌ Error:', RED)} Command not found: {cmd[0]}")
        sys.exit(1)


def check_venv():
    """Warn user if not in a virtual environment."""
    in_venv = sys.prefix != sys.base_prefix
    if not in_venv:
        print(format_text("\n⚠️  WARNING: You are NOT running in a virtual environment.", YELLOW))
        print(format_text("   Installing/Upgrading global packages can break system tools.", YELLOW))
        print(f"   Interpreter: {sys.executable}\n")


def get_outdated_packages() -> list[dict]:
    """Return a list of outdated packages."""
    print("🔍 Checking for outdated packages...")
    cmd = [sys.executable, '-m', 'pip', 'list', '--outdated', '--format=json']
    
    # We never dry-run the check, we always need the info
    result = run_command(cmd, dry_run=False)
    
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        print(format_text("❌ Error: Could not parse pip output.", RED))
        return []


def main():
    parser = argparse.ArgumentParser(description="PakMan: A robust Python package updater.")
    parser.add_argument("-y", "--yes", action="store_true", help="Auto-approve upgrades")
    parser.add_argument("--check-only", action="store_true", help="List outdated packages and exit")
    parser.add_argument("--dry-run", action="store_true", help="Simulate commands")
    parser.add_argument("--exclude", nargs="+", default=[], help="Packages to exclude from upgrade")
    
    args = parser.parse_args()

    print(format_text("\n📦 --- PakMan: Python Package Manager ---", BLUE, bold=True))
    
    check_venv()

    outdated = get_outdated_packages()
    
    # Filter exclusions
    if args.exclude:
        original_count = len(outdated)
        outdated = [p for p in outdated if p['name'] not in args.exclude]
        excluded_count = original_count - len(outdated)
        if excluded_count > 0:
            print(f"{format_text('ℹ️  Excluded', BLUE)} {excluded_count} package(s) requested by user.")

    if not outdated:
        print(format_text("\n✅ All packages are up to date!", GREEN))
        return

    # Print Summary
    print(f"\n{format_text('📦 Outdated Packages:', YELLOW, bold=True)}")
    print(f"{'Package':<25} {'Current':<15} {'Latest':<15}")
    print("-" * 55)
    
    for pkg in outdated:
        print(f"{pkg['name']:<25} {pkg['version']:<15} {pkg['latest_version']:<15}")
    print("-" * 55)

    if args.check_only:
        return

    # Confirmation
    if not args.yes:
        if args.dry_run:
            print(f"\n{format_text('[DRY-RUN]', YELLOW)} Skipping confirmation.")
        else:
            choice = input(f"\n{format_text('❓ Upgrade all displayed packages? (y/N): ', BLUE)}").strip().lower()
            if choice not in ('y', 'yes'):
                print(format_text("\n⏭️  Upgrade canceled.", YELLOW))
                return

    # Batch Upgrade
    packages_to_upgrade = [pkg['name'] for pkg in outdated]
    if packages_to_upgrade:
        print(f"\n{format_text('⬆️  Upgrading packages...', BLUE)}")
        
        # Construct one big command for efficiency
        cmd = [sys.executable, '-m', 'pip', 'install', '--upgrade'] + packages_to_upgrade
        
        run_command(cmd, stream=True, dry_run=args.dry_run)
        
        print(f"\n{format_text('✅ Done.', GREEN, bold=True)}")


if __name__ == "__main__":
    main()