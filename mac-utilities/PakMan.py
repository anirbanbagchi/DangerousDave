#!/usr/bin/env python3
"""
Python Package Manager (PakMan)
--------------------------------
Author :  Anirban Bagchi
"""

import argparse
import fnmatch
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import datetime
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# ANSI Colors
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BLUE = "\033[94m"
BOLD = "\033[1m"
RESET = "\033[0m"

LOG_PATH = Path.home() / ".pakman.log"
HISTORY_PATH = Path.home() / ".pakman_history.jsonl"
MAX_ROLLBACKS = 5

# PEP 508 project name rules — reject anything else before it reaches pip.
VALID_PKG = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?$")

# Exit codes for scripting/cron use
EXIT_OK = 0          # success, nothing to do or all upgrades succeeded
EXIT_FATAL = 1       # unrecoverable error
EXIT_FAILURES = 2    # run completed but one or more packages failed
EXIT_OUTDATED = 3    # --check-only found outdated packages

# Every pip invocation skips pip's own "new version available" check.
PIP_ENV = {**os.environ, "PIP_DISABLE_PIP_VERSION_CHECK": "1"}

# Log may contain paths and error output — keep it private to the user.
LOG_PATH.touch(mode=0o600, exist_ok=True)
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


def run_pip(pip_args: list[str], timeout: int | None = None) -> subprocess.CompletedProcess:
    """Run pip for the active interpreter with audit logging. Raises TimeoutExpired."""
    cmd = [sys.executable, "-m", "pip"] + pip_args
    cmd_str = ' '.join(cmd)
    try:
        p = subprocess.run(cmd, text=True, capture_output=True, env=PIP_ENV, timeout=timeout)
    except subprocess.TimeoutExpired:
        log(f"AUDIT: {cmd_str} -> timed out after {timeout}s")
        raise
    log(f"AUDIT: {cmd_str} -> exit {p.returncode}")
    return p


def run_command(cmd: list[str], stream: bool = False, check: bool = True, dry_run: bool = False, env: dict | None = None) -> subprocess.CompletedProcess:
    """Run a command with optional streaming."""
    cmd_str = ' '.join(cmd)

    if dry_run:
        print(f"{format_text('[DRY-RUN]', YELLOW)} Would execute: {cmd_str}")
        return subprocess.CompletedProcess(cmd, 0, stdout="[]", stderr="")

    try:
        if stream:
            print(f"{format_text('Running:', BLUE)} {cmd_str}")
            return subprocess.run(cmd, text=True, check=check, env=env)

        return subprocess.run(cmd, text=True, capture_output=True, check=check, env=env)

    except subprocess.CalledProcessError as e:
        print(f"\n{format_text('❌ Command failed:', RED, bold=True)} {cmd_str}")
        if e.stderr:
            print(f"Error: {e.stderr.strip()}")
        if check:
            sys.exit(e.returncode)
        return e
    except FileNotFoundError:
        print(f"\n{format_text('❌ Error:', RED)} Command not found: {cmd[0]}")
        sys.exit(EXIT_FATAL)


def install_args(names: list[str], pre: bool, only_binary: bool) -> list[str]:
    """Build the pip install argument list shared by batch and per-package paths."""
    args = ["install", "--upgrade"]
    if pre:
        args.append("--pre")
    if only_binary:
        args.append("--only-binary=:all:")
    return args + names


def batch_upgrade(names: list[str], pre: bool, only_binary: bool, dry_run: bool, timeout: int) -> bool:
    """Try upgrading everything in one resolver run. Returns True on success."""
    pip_args = install_args(names, pre, only_binary)
    cmd_str = f"{sys.executable} -m pip {' '.join(pip_args)}"

    if dry_run:
        print(f"{format_text('[DRY-RUN]', YELLOW)} Would execute: {cmd_str}")
        return True

    print(f"{format_text('🚀 Trying batch upgrade (single resolver run)...', BLUE)}")
    try:
        p = run_pip(pip_args, timeout=timeout * max(1, len(names)))
    except subprocess.TimeoutExpired:
        print(format_text("  ⚠️  Batch upgrade timed out.", YELLOW))
        return False
    if p.returncode == 0:
        return True
    print(format_text("  ⚠️  Batch upgrade failed — falling back to per-package upgrades to isolate the failure.", YELLOW))
    return False


def run_package_upgrade(pkg: str, dry_run: bool, pre: bool, only_binary: bool, max_retries: int, timeout: int) -> tuple[str, bool, str]:
    """Upgrade a single package with retries. Returns (name, success, error_message)."""
    pip_args = install_args([pkg], pre, only_binary)
    cmd_str = f"{sys.executable} -m pip {' '.join(pip_args)}"

    if dry_run:
        print(f"{format_text('[DRY-RUN]', YELLOW)} Would execute: {cmd_str}")
        return (pkg, True, "")

    error = ""
    for attempt in range(1, max_retries + 1):
        suffix = f" (attempt {attempt}/{max_retries})" if attempt > 1 else ""
        print(f"{format_text('Running:', BLUE)} {cmd_str}{suffix}")
        try:
            p = run_pip(pip_args, timeout=timeout)
        except subprocess.TimeoutExpired:
            error = f"timed out after {timeout}s"
            if attempt < max_retries:
                print(format_text("  ⚠️  Timed out, retrying...", YELLOW))
            continue
        if p.returncode == 0:
            return (pkg, True, "")
        error = p.stderr.strip() or p.stdout.strip()
        if attempt < max_retries:
            print(format_text("  ⚠️  Retrying...", YELLOW))

    return (pkg, False, error or "no attempts made")


def prefetch_wheels(pkgs: list[dict], pre: bool, only_binary: bool, timeout: int):
    """Download wheels in parallel so per-package installs hit pip's HTTP cache."""
    if not pkgs:
        return
    print(f"{format_text(f'⬇️  Prefetching {len(pkgs)} download(s) in parallel...', BLUE)}")

    def fetch(spec: str, dest: str):
        args = ["download", "--no-deps", "--dest", dest]
        if pre:
            args.append("--pre")
        if only_binary:
            args.append("--only-binary=:all:")
        try:
            subprocess.run([sys.executable, "-m", "pip"] + args + [spec],
                           capture_output=True, env=PIP_ENV, timeout=timeout)
        except subprocess.TimeoutExpired:
            pass  # the install step will retry the download itself

    with tempfile.TemporaryDirectory(prefix="pakman_prefetch_") as dest:
        with ThreadPoolExecutor(max_workers=4) as ex:
            for pkg in pkgs:
                latest = pkg.get("latest_version", "")
                spec = f"{pkg['name']}=={latest}" if latest else pkg["name"]
                ex.submit(fetch, spec, dest)


def check_venv(require: bool) -> bool:
    """Warn (or refuse, with require=True) when running outside a virtualenv."""
    if sys.prefix != sys.base_prefix:
        return True
    if require:
        print(format_text("\n❌ Not in a virtual environment and --require-venv is set. Refusing to touch global packages.", RED))
        log("Refused: --require-venv outside a virtualenv.")
        return False
    print(format_text("\n⚠️  WARNING: You are NOT running in a virtual environment.", YELLOW))
    print(format_text("   Installing/Upgrading global packages can break system tools.", YELLOW))
    print(f"   Interpreter: {sys.executable}\n")
    return True


def upgrade_pip(dry_run: bool):
    """Upgrade pip itself before upgrading packages."""
    print(f"\n{format_text('⬆️  Upgrading pip...', BLUE)}")
    cmd = [sys.executable, "-m", "pip", "install", "--upgrade", "pip"]
    run_command(cmd, stream=True, dry_run=dry_run, env=PIP_ENV)


def get_outdated_packages(no_uv: bool) -> list[dict]:
    """Return a list of outdated packages, preferring uv's fast resolver when available."""
    print("🔍 Checking for outdated packages...")

    if not no_uv:
        uv = shutil.which("uv")
        if uv:
            p = subprocess.run(
                [uv, "pip", "list", "--outdated", "--format=json", "--python", sys.executable],
                text=True, capture_output=True
            )
            log(f"AUDIT: {uv} pip list --outdated -> exit {p.returncode}")
            if p.returncode == 0:
                try:
                    data = json.loads(p.stdout)
                    print(format_text("   (via uv)", BLUE))
                    return data
                except json.JSONDecodeError:
                    pass
            print(format_text("   uv check failed — falling back to pip.", YELLOW))

    result = run_pip(["list", "--outdated", "--format=json"])
    if result.returncode != 0:
        print(format_text("❌ Error: pip list --outdated failed.", RED))
        return []
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        print(format_text("❌ Error: Could not parse pip output.", RED))
        return []


def prune_rollbacks(keep: int = MAX_ROLLBACKS):
    """Delete all but the newest `keep` rollback files created by this tool."""
    rollbacks = sorted(Path.home().glob(".pakman_rollback_*.txt"))
    for old in rollbacks[:-keep]:
        old.unlink()
        print(format_text(f"   🗑  Pruned old rollback: {old.name}", YELLOW))
        log(f"Pruned old rollback: {old}")


def write_rollback(outdated: list[dict], dry_run: bool):
    """Snapshot current versions so the run can be undone with pip install -r."""
    path = Path.home() / f".pakman_rollback_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    if dry_run:
        print(f"{format_text('[DRY-RUN]', YELLOW)} Would write rollback file: {path}")
        return
    lines = [f"{p['name']}=={p['version']}" for p in outdated]
    path.write_text("\n".join(lines) + "\n")
    path.chmod(0o600)
    print(f"{format_text('💾 Rollback file:', BLUE)} {path}")
    print(format_text(f"   Undo this run with: pip install -r {path}", BLUE))
    log(f"Rollback file written: {path}")
    prune_rollbacks()


def check_dependencies(dry_run: bool) -> list[str]:
    """Run pip check after upgrades; return conflict lines (empty = healthy)."""
    if dry_run:
        print(f"{format_text('[DRY-RUN]', YELLOW)} Would verify dependencies: pip check")
        return []
    print(f"\n{format_text('🩺 Verifying dependencies (pip check)...', BLUE)}")
    p = run_pip(["check"])
    if p.returncode == 0:
        print(format_text("   No broken dependencies.", GREEN))
        return []
    conflicts = [line for line in p.stdout.strip().splitlines() if line.strip()]
    for line in conflicts:
        print(format_text(f"   ⚠️  {line}", YELLOW))
        log(f"CONFLICT: {line}")
    return conflicts


def run_audit(dry_run: bool):
    """Scan the environment for known vulnerabilities via pip-audit, if installed."""
    if dry_run:
        print(f"{format_text('[DRY-RUN]', YELLOW)} Would run: pip-audit")
        return
    print(f"\n{format_text('🔒 Auditing for known vulnerabilities (pip-audit)...', BLUE)}")
    p = subprocess.run([sys.executable, "-m", "pip_audit"], text=True, capture_output=True, env=PIP_ENV)
    if p.returncode != 0 and "No module named" in p.stderr:
        print(format_text("   pip-audit not installed — skipping. Install with: pip install pip-audit", YELLOW))
        return
    log(f"AUDIT: pip_audit -> exit {p.returncode}")
    output = p.stdout.strip() or p.stderr.strip()
    if p.returncode == 0:
        print(format_text("   No known vulnerabilities found.", GREEN))
    else:
        print(format_text("   ⚠️  Vulnerabilities found:", RED, bold=True))
        for line in output.splitlines():
            print(f"   {line}")
        log(f"pip-audit found vulnerabilities:\n{output}")


def export_freeze(path: str, dry_run: bool):
    """Run pip freeze and write to a file."""
    if dry_run:
        print(f"{format_text('[DRY-RUN]', YELLOW)} Would export: pip freeze > {path}")
        return
    print(f"\n{format_text('💾 Exporting freeze to:', BLUE)} {path}")
    result = run_pip(["freeze"])
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


def matches_any(name: str, patterns: list[str]) -> bool:
    """Case-insensitive fnmatch against a list of glob patterns."""
    lowered = name.lower()
    return any(fnmatch.fnmatch(lowered, pat.lower()) for pat in patterns)


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


def select_packages(pkgs: list[dict]) -> list[dict]:
    """Interactive per-package selection. Returns the chosen subset."""
    print(f"\n{format_text('Select packages to upgrade:', BLUE, bold=True)}")
    for i, pkg in enumerate(pkgs, 1):
        print(f"  {i:>3}. {pkg['name']}  {format_text(pkg['version'], YELLOW)} → {format_text(pkg['latest_version'], GREEN)}")
    while True:
        raw = input(f"{format_text('Selection (e.g. 1,3,5-7 | all | none): ', BLUE)}").strip().lower()
        if raw in ("all", "a", ""):
            return pkgs
        if raw in ("none", "n", "q"):
            return []
        idxs = parse_selection(raw, len(pkgs))
        if idxs is not None:
            return [pkgs[i] for i in idxs]
        print(format_text("  Invalid selection, try again.", YELLOW))


def write_history(record: dict):
    """Append one structured JSON record per run to the history file."""
    HISTORY_PATH.touch(mode=0o600, exist_ok=True)
    with open(HISTORY_PATH, "a") as f:
        f.write(json.dumps(record) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="PakMan: A robust Python package updater.")
    parser.add_argument("-y", "--yes", action="store_true", help="Auto-approve upgrades")
    parser.add_argument("-i", "--interactive", action="store_true", help="Pick packages to upgrade from a numbered list")
    parser.add_argument("--check-only", action="store_true", help="List outdated packages and exit (exit 3 if any found)")
    parser.add_argument("--dry-run", action="store_true", help="Simulate commands without executing")
    parser.add_argument("--exclude", nargs="+", default=[], metavar="PKG", help="Packages to exclude; glob patterns supported (e.g. --exclude 'boto*')")
    parser.add_argument("--only", nargs="+", default=[], metavar="PKG", help="Upgrade only these packages; glob patterns supported")
    parser.add_argument("--upgrade-pip", action="store_true", help="Upgrade pip itself before upgrading packages")
    parser.add_argument("--pre", action="store_true", help="Include pre-release versions when upgrading")
    parser.add_argument("--only-binary", action="store_true", help="Refuse source distributions (pass --only-binary=:all: to pip)")
    parser.add_argument("--require-venv", action="store_true", help="Refuse to run outside a virtual environment")
    parser.add_argument("--audit", action="store_true", help="Run pip-audit after upgrading (skipped if not installed)")
    parser.add_argument("--no-uv", action="store_true", help="Don't use uv for the outdated check even if installed")
    parser.add_argument("--no-rollback", action="store_true", help="Skip writing the rollback snapshot file")
    parser.add_argument("--no-batch", action="store_true", help="Skip the batch upgrade attempt; go straight to per-package upgrades")
    parser.add_argument("--export", metavar="FILE", help="Run pip freeze after upgrading and save to FILE")
    parser.add_argument("--notify", action="store_true", help="Send a macOS notification when done")
    parser.add_argument("--json", action="store_true", help="Output outdated packages as JSON and exit")
    parser.add_argument("--log-json", action="store_true", help=f"Append a structured JSON record per run to {HISTORY_PATH}")
    parser.add_argument("--retries", type=int, default=2, metavar="N", help="Retries per package on failure [Default: 2, min: 1]")
    parser.add_argument("--timeout", type=int, default=600, metavar="SECS", help="Timeout per package upgrade [Default: 600]")

    args = parser.parse_args()

    if args.retries < 1:
        parser.error("--retries must be at least 1")
    if args.timeout < 1:
        parser.error("--timeout must be at least 1")
    if args.interactive and args.yes:
        parser.error("--interactive and --yes are mutually exclusive")

    if args.only and args.exclude:
        overlap = {p.lower() for p in args.only} & {p.lower() for p in args.exclude}
        if overlap:
            parser.error(f"package(s) appear in both --only and --exclude: {', '.join(sorted(overlap))}")

    # Fail fast in cron/launchd instead of hanging on input()
    needs_tty = args.interactive or not (args.yes or args.dry_run or args.check_only or args.json)
    if needs_tty and not sys.stdin.isatty():
        print(format_text("❌ Non-interactive session and no -y/--yes flag; refusing to prompt.", RED))
        return EXIT_FATAL

    start_time = time.time()
    log("--- PakMan run started ---")

    print(format_text("\n📦 --- PakMan: Python Package Manager ---", BLUE, bold=True))

    if not check_venv(args.require_venv):
        return EXIT_FATAL

    if args.upgrade_pip:
        upgrade_pip(args.dry_run)

    outdated = get_outdated_packages(args.no_uv)

    # --json: output raw list and exit
    if args.json:
        print(json.dumps(outdated, indent=2))
        return EXIT_OK

    # Apply --only / --exclude filters (case-insensitive, glob-aware)
    if args.only:
        outdated = [p for p in outdated if matches_any(p["name"], args.only)]

    if args.exclude:
        before = len(outdated)
        outdated = [p for p in outdated if not matches_any(p["name"], args.exclude)]
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
        if args.log_json:
            write_history({
                "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
                "upgraded": [], "failures": [], "conflicts": [],
                "elapsed_secs": round(elapsed, 1), "interrupted": False, "exit_code": EXIT_OK,
            })
        return EXIT_OK

    print_outdated_table(outdated)

    if args.check_only:
        elapsed = time.time() - start_time
        print(format_text(f"⏱  Completed in {elapsed:.1f}s", BLUE))
        log(f"Check-only run: {len(outdated)} package(s) outdated.")
        return EXIT_OUTDATED

    # Interactive selection or confirmation prompt
    if args.interactive:
        outdated = select_packages(outdated)
        if not outdated:
            print(format_text("\n⏭️  Nothing selected. Upgrade canceled.", YELLOW))
            return EXIT_OK
    elif not args.yes:
        if args.dry_run:
            print(f"{format_text('[DRY-RUN]', YELLOW)} Skipping confirmation.")
        else:
            choice = input(f"{format_text('❓ Upgrade all displayed packages? (y/N): ', BLUE)}").strip().lower()
            if choice not in ("y", "yes"):
                print(format_text("\n⏭️  Upgrade canceled.", YELLOW))
                return EXIT_OK

    # Reject suspicious names before they reach a subprocess
    failures: list[tuple[str, str]] = []
    valid: list[dict] = []
    for pkg in outdated:
        name = pkg.get("name", "")
        if VALID_PKG.match(name):
            valid.append(pkg)
        else:
            failures.append((name, "invalid package name — skipped"))
            print(format_text(f"  ❌ Skipping invalid package name: {name!r}", RED))
            log(f"SKIPPED invalid package name: {name!r}")

    if not args.no_rollback:
        write_rollback(valid, args.dry_run)

    names = [p["name"] for p in valid]
    upgraded: list[str] = []
    interrupted = False

    print(f"\n{format_text('⬆️  Upgrading packages...', BLUE)}")
    try:
        batch_ok = False
        if valid and not args.no_batch:
            batch_ok = batch_upgrade(names, args.pre, args.only_binary, args.dry_run, args.timeout)

        if batch_ok:
            upgraded = names
            for pkg in valid:
                log(f"Upgraded (batch): {pkg['name']} {pkg['version']} -> {pkg['latest_version']}")
        elif valid:
            # Fallback: prefetch in parallel, then isolate failures per package
            if not args.dry_run:
                prefetch_wheels(valid, args.pre, args.only_binary, args.timeout)
            for pkg in valid:
                name = pkg["name"]
                _, success, error = run_package_upgrade(name, args.dry_run, args.pre, args.only_binary, args.retries, args.timeout)
                if success:
                    upgraded.append(name)
                    log(f"Upgraded: {name} {pkg['version']} -> {pkg['latest_version']}")
                else:
                    failures.append((name, error))
                    print(format_text(f"  ❌ Failed: {name} — {error}", RED))
                    log(f"FAILED: {name} — {error}")
    except KeyboardInterrupt:
        interrupted = True
        remaining = len(valid) - len(upgraded) - len(failures)
        print(format_text(f"\n⏹️  Interrupted — {len(upgraded)} upgraded, {len(failures)} failed, {remaining} not attempted.", YELLOW, bold=True))
        log(f"Run interrupted: {len(upgraded)} upgraded, {len(failures)} failed, {remaining} not attempted.")

    # Post-upgrade health checks
    conflicts: list[str] = []
    if not interrupted:
        conflicts = check_dependencies(args.dry_run)
        if args.audit:
            run_audit(args.dry_run)
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
    elif not interrupted:
        print(f"\n{format_text('✅ Done.', GREEN, bold=True)}")
        log(f"Run complete. All upgrades successful. Elapsed: {elapsed:.1f}s")
        if args.notify:
            send_notification("PakMan", "All packages upgraded successfully!")

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
            "failures": [{"name": n, "error": e} for n, e in failures],
            "conflicts": conflicts,
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
