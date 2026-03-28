#!/usr/bin/env python3
"""
All Python Versions Manager for macOS and Windows
--------------------------------
Author :  Anirban Bagchi
"""

import os
import sys
import subprocess
import shutil
import re
import datetime
import platform
import json
import argparse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- Configuration & Colors ---
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    GREY = '\033[90m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

    if os.name == 'nt':
        os.system('')

NO_COLOR = False

def c(color: str) -> str:
    return color if not NO_COLOR else ""

# --- OS Detection ---
IS_WINDOWS = os.name == 'nt'
IS_MAC = platform.system() == 'Darwin'

# --- Helper Functions ---

def strip_ansi(text: str) -> str:
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

def clean_len(text: str) -> int:
    return len(strip_ansi(text))

def get_architecture(binary_path: str) -> str:
    """Cross-platform architecture check."""
    if IS_MAC:
        try:
            result = subprocess.run(["lipo", "-archs", binary_path], capture_output=True, text=True, timeout=1)
            archs = result.stdout.strip()
            if "x86_64" in archs and "arm64" in archs: return "Universal"
            elif "arm64" in archs: return "Apple Silicon"
            elif "x86_64" in archs: return "Intel 64"
            return archs
        except: return "Unknown"
    elif IS_WINDOWS:
        try:
            cmd = [binary_path, "-c", "import platform; print(platform.machine())"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
            arch = result.stdout.strip()
            return "64-bit" if "64" in arch else "32-bit"
        except: return "Unknown"
    return "Unknown"

def get_pip_status(binary_path: str) -> bool:
    try:
        subprocess.run(
            [binary_path, "-m", "pip", "--version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=1,
            check=True
        )
        return True
    except:
        return False

def get_pip_display(has_pip: bool) -> str:
    if has_pip:
        return f"{c(Colors.GREEN)}Yes{c(Colors.RESET)}"
    return f"{c(Colors.RED)}No{c(Colors.RESET)}"

def get_vendor_info(path_str: str) -> tuple[str, int]:
    path_lower = path_str.lower()

    if IS_MAC:
        if "/system/library" in path_lower or "/usr/bin" in path_lower:
            return "macOS System", 1
        elif "homebrew" in path_lower or "cellar" in path_lower:
            return "Homebrew", 0
        elif "/library/frameworks/python.framework" in path_lower:
            return "Official Installer", 0
        elif ".pyenv" in path_lower:
            return "pyenv", 0

    if IS_WINDOWS:
        if "windowsapps" in path_lower:
            return "Microsoft Store", 1
        elif "program files" in path_lower:
            return "System Install", 0
        elif "anaconda" in path_lower or "miniconda" in path_lower:
            return "Conda", 0

    if "anaconda" in path_lower or "miniconda" in path_lower:
        return "Conda", 0
    elif ".pyenv" in path_lower:
        return "pyenv", 0

    return "User/Other", 0

def get_version(binary_path: str) -> str:
    try:
        result = subprocess.run([binary_path, "--version"], capture_output=True, text=True, timeout=2)
        output = result.stdout.strip() or result.stderr.strip()
        match = re.search(r'Python (\d+\.\d+\.\d+)', output)
        if match: return match.group(1)
        return "Unknown"
    except: return "Unverifiable"

def get_site_packages(binary_path: str) -> str | None:
    """Get the site-packages path for a Python binary."""
    try:
        result = subprocess.run(
            [binary_path, "-c", "import site; print(site.getsitepackages()[0])"],
            capture_output=True, text=True, timeout=2
        )
        return result.stdout.strip() or None
    except:
        return None

# --- Source Discovery ---

def get_pyenv_binaries() -> list[str]:
    """Return paths to all pyenv-managed Python binaries."""
    pyenv_root = Path(os.environ.get("PYENV_ROOT", Path.home() / ".pyenv"))
    versions_dir = pyenv_root / "versions"
    if not versions_dir.exists():
        return []
    binaries = []
    for version_dir in versions_dir.iterdir():
        for name in ("bin/python3", "bin/python"):
            b = version_dir / name
            if b.exists():
                binaries.append(str(b))
                break
    return binaries

def get_conda_binaries() -> list[str]:
    """Return paths to Python binaries in conda base and all environments."""
    conda_roots: list[Path] = []
    for env_var in ("CONDA_PREFIX", "CONDA_EXE"):
        val = os.environ.get(env_var)
        if val:
            conda_roots.append(Path(val).resolve().parent.parent)
    for p in [Path.home() / "anaconda3", Path.home() / "miniconda3",
              Path("/opt/anaconda3"), Path("/opt/miniconda3")]:
        if p.exists():
            conda_roots.append(p.resolve())

    binaries: list[str] = []
    seen: set[Path] = set()
    for root in conda_roots:
        if root in seen:
            continue
        seen.add(root)
        # base env
        for name in ("bin/python3", "bin/python"):
            b = root / name
            if b.exists():
                binaries.append(str(b))
                break
        # named envs
        envs_dir = root / "envs"
        if envs_dir.exists():
            for env_dir in envs_dir.iterdir():
                for name in ("bin/python3", "bin/python"):
                    b = env_dir / name
                    if b.exists():
                        binaries.append(str(b))
                        break
    return binaries

# --- Scanning Logic ---

def scan_installations(verbose: bool = False) -> list[dict]:
    print(f"{c(Colors.CYAN)}Scanning system for Python installations...{c(Colors.RESET)}")
    search_paths: list[str] = []

    if IS_MAC:
        search_paths = os.environ.get("PATH", "").split(os.pathsep)
        search_paths.extend([
            "/Library/Frameworks/Python.framework/Versions",
            "/opt/homebrew/bin",
            "/usr/local/bin",
            "/usr/bin"
        ])
    elif IS_WINDOWS:
        search_paths = os.environ.get("PATH", "").split(os.pathsep)
        user_base = os.environ.get("LOCALAPPDATA", "")
        if user_base:
            search_paths.append(os.path.join(user_base, "Programs", "Python"))
        search_paths.append("C:\\Python")
        search_paths.append("C:\\Program Files\\Python")
        search_paths.append("C:\\Program Files")

    search_paths = list(set(search_paths))
    found_binaries: list[str] = []

    for path in search_paths:
        if not os.path.exists(path): continue
        try:
            with os.scandir(path) as entries:
                for entry in entries:
                    if not entry.is_file(): continue
                    name = entry.name.lower()
                    is_match = False
                    if IS_WINDOWS:
                        if name == "python.exe" or (name.startswith("python") and name.endswith(".exe") and "config" not in name):
                            is_match = True
                    else:
                        if re.match(r'^python(\d+(\.\d+)?)?$', entry.name):
                            is_match = True
                    if is_match:
                        found_binaries.append(entry.path)
        except PermissionError:
            continue

    # Additional sources
    found_binaries.extend(get_pyenv_binaries())
    found_binaries.extend(get_conda_binaries())

    # Deduplicate by real path
    unique_installs: dict[str, dict] = {}
    for binary in found_binaries:
        try:
            real_path = os.path.realpath(binary)
            if IS_WINDOWS and os.path.getsize(real_path) == 0:
                continue
            if real_path not in unique_installs:
                vendor, safety = get_vendor_info(real_path)
                unique_installs[real_path] = {
                    'aliases': set(),
                    'vendor': vendor,
                    'safety': safety,
                }
            unique_installs[real_path]['aliases'].add(binary)
        except OSError:
            continue

    # Parallel enrichment
    def enrich(real_path: str, data: dict) -> dict | None:
        version = get_version(real_path)
        if version in ("Unknown", "Unverifiable"):
            return None
        arch = get_architecture(real_path)
        has_pip = get_pip_status(real_path)
        site_pkgs = get_site_packages(real_path) if verbose else None
        aliases = sorted(list(data['aliases']), key=len)
        alias_names = list(set(os.path.basename(a) for a in aliases))[:3]
        return {
            'version': version,
            'vendor': data['vendor'],
            'safety': data['safety'],
            'arch': arch,
            'pip': has_pip,
            'commands': ", ".join(alias_names),
            'path': real_path,
            'site_packages': site_pkgs,
        }

    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(enrich, p, d): p for p, d in unique_installs.items()}
        for future in as_completed(futures):
            result = future.result()
            if result:
                results.append(result)

    return results

# --- Sorting ---

def sort_installs(installs: list[dict], sort_by: str):
    if sort_by == "vendor":
        installs.sort(key=lambda x: x['vendor'])
    elif sort_by == "path":
        installs.sort(key=lambda x: x['path'])
    else:
        installs.sort(key=lambda x: x['version'], reverse=True)

# --- Display Logic ---

def pad_str(text: str, width: int) -> str:
    padding = width - clean_len(text)
    return text + (" " * max(0, padding))

def print_table(data: list[dict], current_default_path: str | None, verbose: bool = False):
    if not data:
        print(f"{c(Colors.RED)}No Python installations found.{c(Colors.RESET)}")
        return

    venv = os.environ.get("VIRTUAL_ENV")
    if venv:
        print(f"{c(Colors.CYAN)}Active virtualenv: {venv}{c(Colors.RESET)}")

    headers = ["#", "VERSION", "ARCH", "PIP", "VENDOR", "ALIASES", "LOCATION"]
    if verbose:
        headers.append("SITE-PACKAGES")

    display_rows: list[list[str]] = []
    for idx, row in enumerate(data):
        row_path_norm = os.path.normpath(row['path']).lower()
        curr_path_norm = os.path.normpath(current_default_path).lower() if current_default_path else ""
        is_active = (row_path_norm == curr_path_norm)

        if row['safety'] == 1:
            base_color = c(Colors.GREY)
        elif is_active:
            base_color = c(Colors.GREEN)
        else:
            base_color = c(Colors.RESET)

        v_str = row['version']
        if v_str.startswith("3."): v_color = c(Colors.GREEN)
        elif v_str.startswith("2."): v_color = c(Colors.RED)
        else: v_color = c(Colors.YELLOW)

        path_display = row['path']
        if is_active:
            path_display += f" {c(Colors.GREEN)}(Current Default){c(Colors.RESET)}"
        elif row['safety'] == 1:
            path_display += f" {c(Colors.RED)}(Protected){c(Colors.RESET)}"

        cols = [
            f"[{idx+1}]",
            f"{v_color}{v_str}{c(Colors.RESET)}",
            f"{base_color}{row['arch']}{c(Colors.RESET)}",
            get_pip_display(row['pip']),
            f"{base_color}{row['vendor']}{c(Colors.RESET)}",
            f"{c(Colors.YELLOW)}{row['commands']}{c(Colors.RESET)}",
            path_display,
        ]
        if verbose:
            cols.append(row.get('site_packages') or "N/A")
        display_rows.append(cols)

    col_widths = [len(h) for h in headers]
    for row in display_rows:
        for i, col_text in enumerate(row):
            if i == len(headers) - 1: continue
            w = clean_len(col_text)
            if w > col_widths[i]: col_widths[i] = w
    col_widths = [w + 2 for w in col_widths]

    header_str = "".join(
        pad_str(h, col_widths[i]) if i < len(headers) - 1 else h
        for i, h in enumerate(headers)
    )
    print(f"\n{c(Colors.HEADER)}{header_str}{c(Colors.RESET)}")
    print(f"{c(Colors.BOLD)}{'-' * (sum(col_widths[:-1]) + 20)}{c(Colors.RESET)}")

    for row in display_rows:
        row_str = "".join(
            pad_str(col, col_widths[i]) if i < len(row) - 1 else col
            for i, col in enumerate(row)
        )
        print(row_str)
    print("")

def print_json_output(data: list[dict], current_default_path: str | None):
    out = []
    for row in data:
        row_path_norm = os.path.normpath(row['path']).lower()
        curr_path_norm = os.path.normpath(current_default_path).lower() if current_default_path else ""
        out.append({
            "version": row['version'],
            "vendor": row['vendor'],
            "arch": row['arch'],
            "pip": row['pip'],
            "commands": row['commands'],
            "path": row['path'],
            "site_packages": row.get('site_packages'),
            "is_default": row_path_norm == curr_path_norm,
            "protected": row['safety'] == 1,
        })
    print(json.dumps(out, indent=2))

# --- Actions ---

def get_current_default() -> str | None:
    cmd = "python.exe" if IS_WINDOWS else "python3"
    sys_python = shutil.which(cmd)
    if not sys_python and IS_WINDOWS:
        sys_python = shutil.which("python")
    return os.path.realpath(sys_python) if sys_python else None

def switch_default(installations: list[dict], idx: int | None = None):
    print(f"\n{c(Colors.BLUE)}--- Switch Default Python ---{c(Colors.RESET)}")
    if idx is None:
        choice = input("Enter # to set as default (or Enter to cancel): ")
        if not choice.strip().isdigit(): return
        idx = int(choice) - 1

    if not (0 <= idx < len(installations)):
        print(f"{c(Colors.RED)}Invalid selection.{c(Colors.RESET)}")
        return

    target = installations[idx]
    target_path = target['path']

    if IS_MAC:
        shell = os.environ.get("SHELL", "/bin/zsh")
        config_file = Path.home() / ".zshrc" if "zsh" in shell else Path.home() / ".bash_profile"
        print(f"Targeting Config: {c(Colors.CYAN)}{config_file}{c(Colors.RESET)}")
        try:
            timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            if config_file.exists():
                shutil.copy(config_file, config_file.with_suffix(f".backup-{timestamp}"))
            block = f'\n# --- Python Selection (Updated {timestamp}) ---\nalias python="{target_path}"\nalias python3="{target_path}"\n'
            with open(config_file, "a") as f:
                f.write(block)
            print(f"{c(Colors.GREEN)}Success! Run 'source {config_file}' to apply.{c(Colors.RESET)}")
        except Exception as e:
            print(f"{c(Colors.RED)}Error: {e}{c(Colors.RESET)}")

    elif IS_WINDOWS:
        print(f"{c(Colors.YELLOW)}Note: This will update your PowerShell Profile.{c(Colors.RESET)}")
        try:
            ps_cmd = ["powershell", "-NoProfile", "-Command", "echo $PROFILE"]
            result = subprocess.run(ps_cmd, capture_output=True, text=True)
            profile_path = Path(result.stdout.strip())
            if not profile_path.parent.exists():
                os.makedirs(profile_path.parent, exist_ok=True)
            timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            if profile_path.exists():
                shutil.copy(profile_path, profile_path.with_suffix(f".backup-{timestamp}"))
            func_block = f"""
# --- Python Selection (Updated {timestamp}) ---
function python {{ & '{target_path}' @args }}
function python3 {{ & '{target_path}' @args }}
# ----------------------------------------------
"""
            with open(profile_path, "a") as f:
                f.write(func_block)
            print(f"{c(Colors.GREEN)}Success! PowerShell Profile updated at:{c(Colors.RESET)}\n{profile_path}")
            print("Please restart PowerShell to apply changes.")
        except Exception as e:
            print(f"{c(Colors.RED)}Error updating PowerShell profile: {e}{c(Colors.RESET)}")

def remove_version(installations: list[dict], current_default_path: str | None, idx: int | None = None):
    print(f"\n{c(Colors.RED)}--- Remove Python Version ---{c(Colors.RESET)}")
    if idx is None:
        choice = input("Enter # to REMOVE (or Enter to cancel): ")
        if not choice.strip().isdigit(): return
        idx = int(choice) - 1

    if not (0 <= idx < len(installations)): return

    target = installations[idx]

    if target['safety'] == 1:
        print(f"\n{c(Colors.RED)}⛔ BLOCKED: Cannot remove Protected/System Python.{c(Colors.RESET)}")
        return

    tgt_norm = os.path.normpath(target['path']).lower()
    cur_norm = os.path.normpath(current_default_path).lower() if current_default_path else ""

    if tgt_norm == cur_norm:
        print(f"\n{c(Colors.RED)}⛔ BLOCKED: Cannot remove active default.{c(Colors.RESET)}")
        return

    if os.path.normpath(sys.executable).lower() == tgt_norm:
        print(f"\n{c(Colors.RED)}⛔ BLOCKED: Script is running on this version.{c(Colors.RESET)}")
        return

    print(f"\nTarget: {c(Colors.BOLD)}Python {target['version']} ({target['vendor']}){c(Colors.RESET)}")
    print(f"Path: {target['path']}")

    if IS_WINDOWS:
        print(f"\n{c(Colors.YELLOW)}WINDOWS SAFETY NOTICE:{c(Colors.RESET)}")
        print("Python on Windows is deeply integrated into the Registry.")
        print("This script will NOT delete files manually to prevent Registry corruption.")
        print(f"\nPlease go to {c(Colors.BOLD)}Settings > Apps > Installed Apps{c(Colors.RESET)} and uninstall:")
        print(f"{c(Colors.CYAN)}Python {target['version']}{c(Colors.RESET)}")
        return

    confirm = input(f"{c(Colors.RED)}Type 'delete' to confirm removal: {c(Colors.RESET)}")
    if confirm.lower() != 'delete': return

    if target['vendor'] == "Homebrew":
        v_short = ".".join(target['version'].split('.')[:2])
        subprocess.run(["brew", "uninstall", f"python@{v_short}"])
    elif target['vendor'] == "Official Installer" and "Python.framework" in target['path']:
        print(f"\n{c(Colors.YELLOW)}Run manually (Requires Root):{c(Colors.RESET)}")
        print(f"sudo rm -rf \"{os.path.dirname(target['path'])}\"")
    else:
        try:
            if os.access(os.path.dirname(target['path']), os.W_OK):
                os.remove(target['path'])
                print("Binary removed.")
            else:
                print(f"Permission denied. Run: sudo rm \"{target['path']}\"")
        except Exception as e:
            print(f"Error: {e}")

# --- Entry Point ---

def main():
    global NO_COLOR

    parser = argparse.ArgumentParser(description="all_python: Discover and manage all Python installations.")
    parser.add_argument("--list", action="store_true", help="Print installation table and exit (non-interactive)")
    parser.add_argument("--json", action="store_true", help="Output installations as JSON and exit")
    parser.add_argument("--switch", type=int, metavar="N", help="Switch default to installation #N (non-interactive)")
    parser.add_argument("--remove", type=int, metavar="N", help="Remove installation #N (non-interactive)")
    parser.add_argument("--verbose", action="store_true", help="Show site-packages path for each installation")
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI color output")
    parser.add_argument("--sort", choices=["version", "vendor", "path"], default="version",
                        help="Sort order [Default: version]")
    args = parser.parse_args()

    if args.no_color:
        NO_COLOR = True

    current_real = get_current_default()

    if args.json:
        installs = scan_installations(verbose=True)
        sort_installs(installs, args.sort)
        print_json_output(installs, current_real)
        return

    if args.list:
        installs = scan_installations(verbose=args.verbose)
        sort_installs(installs, args.sort)
        print_table(installs, current_real, verbose=args.verbose)
        return

    if args.switch is not None:
        installs = scan_installations()
        sort_installs(installs, args.sort)
        print_table(installs, current_real)
        switch_default(installs, idx=args.switch - 1)
        return

    if args.remove is not None:
        installs = scan_installations()
        sort_installs(installs, args.sort)
        print_table(installs, current_real)
        remove_version(installs, current_real, idx=args.remove - 1)
        return

    # Interactive loop
    while True:
        current_real = get_current_default()
        installs = scan_installations(verbose=args.verbose)
        sort_installs(installs, args.sort)
        print_table(installs, current_real, verbose=args.verbose)

        print(f"{c(Colors.BOLD)}Actions:{c(Colors.RESET)}")
        print(f"[{c(Colors.GREEN)}S{c(Colors.RESET)}] Switch Default  [{c(Colors.RED)}R{c(Colors.RESET)}] Remove Version  [{c(Colors.YELLOW)}E{c(Colors.RESET)}] Exit")

        choice = input(f"\n{c(Colors.BOLD)}> {c(Colors.RESET)}").lower().strip()

        if choice == 's': switch_default(installs)
        elif choice == 'r': remove_version(installs, current_real)
        elif choice == 'e' or choice == '': sys.exit(0)

        input(f"\n{c(Colors.BLUE)}Press Enter...{c(Colors.RESET)}")
        print("\n" * 2)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nExiting.")
