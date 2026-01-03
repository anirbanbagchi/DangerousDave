#!/usr/bin/env python3
import argparse
import subprocess
import sys
import shutil

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
            # Stream output directly to terminal
            print(f"{format_text('Running:', BLUE)} {cmd_str}")
            p = subprocess.run(cmd, text=True)
        else:
            # Capture output
            p = subprocess.run(cmd, text=True, capture_output=True)
            
        if check and p.returncode != 0:
            print(f"\n{format_text('❌ Command failed:', RED, bold=True)} {cmd_str}")
            if not stream:
                # If we didn't stream, show the captured error now
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


def check_brew_installed():
    """Verify Homebrew is installed."""
    if not shutil.which("brew"):
        print(format_text("❌ 'brew' not found. Install Homebrew first: https://brew.sh/", RED))
        sys.exit(1)


def get_outdated(greedy: bool) -> tuple[list[str], list[str]]:
    """Return list of outdated formulae and casks."""
    # Formulae
    print("🔍 Checking outdated formulae...")
    proc_formula = run_command(["brew", "outdated", "--formula"], check=False)
    formulae = [line for line in proc_formula.stdout.splitlines() if line.strip()]

    # Casks
    print("🔍 Checking outdated casks...")
    cask_cmd = ["brew", "outdated", "--cask"]
    if greedy:
        cask_cmd.append("--greedy")
    
    proc_cask = run_command(cask_cmd, check=False)
    casks = [line for line in proc_cask.stdout.splitlines() if line.strip()]
    
    return formulae, casks


def main():
    parser = argparse.ArgumentParser(description="BrewMaster: A better Homebrew upgrader.")
    parser.add_argument("-y", "--yes", action="store_true", help="Auto-approve all upgrades")
    parser.add_argument("--greedy", action="store_true", default=True, help="Use --greedy for casks (check auto-updating apps) [Default: True]")
    parser.add_argument("--no-greedy", dest="greedy", action="store_false", help="Disable --greedy for casks")
    parser.add_argument("--check-only", dest="check_only", action="store_true", help="Only warn about outdated packages, don't upgrade")
    parser.add_argument("--dry-run", action="store_true", help="Simulate commands without running them")
    
    args = parser.parse_args()

    print(format_text("\n🍺 --- BrewMaster ---", BLUE, bold=True))
    
    check_brew_installed()

    # Update metadata
    print(f"\n{format_text('🔄 Updating Homebrew... (brew update)', BLUE)}")
    run_command(["brew", "update"], stream=True, dry_run=args.dry_run)

    # Get outdated
    formulae, casks = get_outdated(args.greedy)
    
    print(f"\n{format_text('📦 Summary:', BLUE, bold=True)}")
    if not formulae and not casks:
        print(format_text("✅ Everything is up to date!", GREEN))
        return

    if formulae:
        print(f"{format_text(str(len(formulae)), YELLOW)} outdated formulae:")
        for f in formulae:
            print(f"  • {f}")
    
    if casks:
        print(f"{format_text(str(len(casks)), YELLOW)} outdated casks{' (greedy)' if args.greedy else ''}:")
        for c in casks:
            print(f"  • {c}")

    if args.check_only:
        return

    # Ask for confirmation unless -y is passed
    if not args.yes:
        if args.dry_run:
            print(f"\n{format_text('[DRY-RUN]', YELLOW)} Skipping confirmation prompt via --dry-run.")
        else:
            choice = input(f"\n{format_text('❓ Upgrade these packages? (y/N): ', BLUE)}").strip().lower()
            if choice not in ("y", "yes"):
                print(format_text("\n⏭️  Upgrade canceled.", YELLOW))
                return

    # Upgrade Formulae
    if formulae:
        print(f"\n{format_text('⬆️  Upgrading formulae...', BLUE)}")
        run_command(["brew", "upgrade"] + [f.split()[0] for f in formulae], stream=True, dry_run=args.dry_run)

    # Upgrade Casks
    if casks:
        print(f"\n{format_text('⬆️  Upgrading casks...', BLUE)}")
        cmd = ["brew", "upgrade", "--cask"]
        if args.greedy:
            cmd.append("--greedy")
        # We upgrade all outdated casks detected
        # Extract package names (brew outdated output is 'name version_installed < ...')
        cask_names = [c.split()[0] for c in casks]
        run_command(cmd + cask_names, stream=True, dry_run=args.dry_run)

    # Cleanup
    print(f"\n{format_text('🧹 Cleaning up...', BLUE)}")
    run_command(["brew", "cleanup"], stream=True, dry_run=args.dry_run)

    print(f"\n{format_text('✅ Done.', GREEN, bold=True)}")


if __name__ == "__main__":
    main()