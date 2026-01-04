#!/usr/bin/env python3
import os
import sys
import subprocess
import shutil
import re
import datetime
import platform
from pathlib import Path

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

    # Disable colors if terminal doesn't support them (e.g. old Windows CMD)
    if os.name == 'nt':
        # Enable ANSI for Windows 10+
        os.system('')

# --- OS Detection ---
IS_WINDOWS = os.name == 'nt'
IS_MAC = platform.system() == 'Darwin'

# --- Helper Functions ---

def strip_ansi(text):
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

def clean_len(text):
    return len(strip_ansi(text))

def get_architecture(binary_path):
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
        # On Windows, we ask the python executable itself
        try:
            cmd = [binary_path, "-c", "import platform; print(platform.machine())"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
            arch = result.stdout.strip()
            return "64-bit" if "64" in arch else "32-bit"
        except: return "Unknown"
    
    return "Unknown"

def get_pip_status(binary_path):
    try:
        subprocess.run(
            [binary_path, "-m", "pip", "--version"], 
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL, 
            timeout=1,
            check=True
        )
        return f"{Colors.GREEN}Yes{Colors.RESET}"
    except:
        return f"{Colors.RED}No{Colors.RESET}"

def get_vendor_info(path_str):
    path_str = path_str.lower()
    
    if IS_MAC:
        if "/system/library" in path_str or "/usr/bin" in path_str:
            return "macOS System", 1
        elif "homebrew" in path_str or "cellar" in path_str:
            return "Homebrew", 0
        elif "/library/frameworks/python.framework" in path_str:
            return "Official Installer", 0
    
    if IS_WINDOWS:
        if "windowsapps" in path_str:
            return "Microsoft Store", 1 # Protected
        elif "program files" in path_str:
            return "System Install", 0
        elif "anaconda" in path_str or "miniconda" in path_str:
            return "Conda", 0

    if "anaconda" in path_str or "miniconda" in path_str:
        return "Conda", 0
    elif ".pyenv" in path_str:
        return "pyenv", 0
        
    return "User/Other", 0

def get_version(binary_path):
    try:
        result = subprocess.run([binary_path, "--version"], capture_output=True, text=True, timeout=2)
        output = result.stdout.strip() or result.stderr.strip()
        match = re.search(r'Python (\d+\.\d+\.\d+)', output)
        if match: return match.group(1)
        return "Unknown"
    except: return "Unverifiable"

# --- Scanning Logic ---

def scan_installations():
    print(f"{Colors.CYAN}Scanning system for Python installations...{Colors.RESET}")
    search_paths = []

    # 1. Gather Search Paths based on OS
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
        # Add common Windows locations
        user_base = os.environ.get("LOCALAPPDATA", "")
        if user_base:
            search_paths.append(os.path.join(user_base, "Programs", "Python"))
        search_paths.append("C:\\Python")
        search_paths.append("C:\\Program Files\\Python")
        search_paths.append("C:\\Program Files")
    
    search_paths = list(set(search_paths))
    found_binaries = []

    # 2. Walk paths
    target_name = "python.exe" if IS_WINDOWS else "python"
    
    for path in search_paths:
        if not os.path.exists(path): continue
        try:
            with os.scandir(path) as entries:
                for entry in entries:
                    if not entry.is_file(): continue
                    
                    name = entry.name.lower()
                    full_path = entry.path

                    # Match logic
                    is_match = False
                    if IS_WINDOWS:
                        # Match python.exe or python3.11.exe
                        if name == "python.exe" or (name.startswith("python") and name.endswith(".exe") and "config" not in name):
                            is_match = True
                    else:
                        # Match python, python3, python3.11
                        if re.match(r'^python(\d+(\.\d+)?)?$', entry.name):
                            is_match = True

                    if is_match:
                        # Skip shim/wrappers if possible (simple size check or logic)
                        found_binaries.append(full_path)
        except PermissionError: continue

    # 3. Process & Deduplicate
    unique_installs = {}
    for binary in found_binaries:
        try:
            # Resolve symlinks on Mac, absolute paths on Windows
            real_path = os.path.realpath(binary)
            
            # Windows Store apps often use 0kb execution aliases, filter those if broken
            if IS_WINDOWS and os.path.getsize(real_path) == 0:
                continue

            if real_path not in unique_installs:
                vendor, safety = get_vendor_info(real_path)
                unique_installs[real_path] = {
                    'aliases': set(),
                    'version': None,
                    'vendor': vendor,
                    'safety': safety,
                    'arch': None,
                    'pip': None
                }
            unique_installs[real_path]['aliases'].add(binary)
        except OSError: continue

    results = []
    for real_path, data in unique_installs.items():
        version = get_version(real_path)
        # Filter out results that failed to return a version (broken binaries)
        if version in ["Unknown", "Unverifiable"]:
            continue

        arch = get_architecture(real_path)
        pip = get_pip_status(real_path)
        
        aliases = sorted(list(data['aliases']), key=len)
        alias_names = [os.path.basename(a) for a in aliases]
        
        results.append({
            'version': version,
            'vendor': data['vendor'],
            'safety': data['safety'],
            'arch': arch,
            'pip': pip,
            'commands': ", ".join(list(set(alias_names))[:3]),
            'path': real_path
        })

    results.sort(key=lambda x: x['version'], reverse=True)
    return results

# --- Display Logic ---

def pad_str(text, width):
    visible_len = clean_len(text)
    padding = width - visible_len
    if padding < 0: padding = 0
    return text + (" " * padding)

def print_table(data, current_default_path):
    if not data:
        print(f"{Colors.RED}No Python installations found.{Colors.RESET}")
        return

    display_rows = []
    headers = ["#", "VERSION", "ARCH", "PIP", "VENDOR", "ALIASES", "LOCATION"]
    
    for idx, row in enumerate(data):
        # Normalize paths for comparison
        row_path_norm = os.path.normpath(row['path']).lower()
        curr_path_norm = os.path.normpath(current_default_path).lower() if current_default_path else ""
        
        is_active = (row_path_norm == curr_path_norm)
        
        if row['safety'] == 1: base_color = Colors.GREY
        elif is_active: base_color = Colors.GREEN
        else: base_color = Colors.RESET
            
        v_str = row['version']
        v_color = Colors.GREEN if v_str.startswith("3.") else (Colors.RED if v_str.startswith("2.") else Colors.YELLOW)
        
        path_display = row['path']
        if is_active: path_display += f" {Colors.GREEN}(Current Default){Colors.RESET}"
        elif row['safety'] == 1: path_display += f" {Colors.RED}(Protected){Colors.RESET}"

        display_rows.append([
            f"[{idx+1}]",
            f"{v_color}{v_str}{Colors.RESET}",
            f"{base_color}{row['arch']}{Colors.RESET}",
            row['pip'],
            f"{base_color}{row['vendor']}{Colors.RESET}",
            f"{Colors.YELLOW}{row['commands']}{Colors.RESET}",
            path_display
        ])

    col_widths = [len(h) for h in headers]
    for row in display_rows:
        for i, col_text in enumerate(row):
            if i == len(headers) - 1: continue
            w = clean_len(col_text)
            if w > col_widths[i]: col_widths[i] = w

    col_widths = [w + 2 for w in col_widths]

    header_str = ""
    for i, h in enumerate(headers):
        if i == len(headers) - 1: header_str += h
        else: header_str += pad_str(h, col_widths[i])
             
    print(f"\n{Colors.HEADER}{header_str}{Colors.RESET}")
    print(f"{Colors.BOLD}{'-'*(sum(col_widths[:-1]) + 20)}{Colors.RESET}")

    for row in display_rows:
        row_str = ""
        for i, col_text in enumerate(row):
            if i == len(row) - 1: row_str += col_text
            else: row_str += pad_str(col_text, col_widths[i])
        print(row_str)
    print("")

# --- Action: Switch Default ---

def switch_default(installations):
    print(f"\n{Colors.BLUE}--- Switch Default Python ---{Colors.RESET}")
    choice = input(f"Enter # to set as default (or Enter to cancel): ")
    if not choice.strip().isdigit(): return

    idx = int(choice) - 1
    if not (0 <= idx < len(installations)):
        print(f"{Colors.RED}Invalid selection.{Colors.RESET}")
        return

    target = installations[idx]
    target_path = target['path']

    if IS_MAC:
        # Mac Logic: .zshrc alias
        shell = os.environ.get("SHELL", "/bin/zsh")
        config_file = Path.home() / ".zshrc" if "zsh" in shell else Path.home() / ".bash_profile"
        print(f"Targeting Config: {Colors.CYAN}{config_file}{Colors.RESET}")
        
        try:
            timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            if config_file.exists():
                shutil.copy(config_file, config_file.with_suffix(f".backup-{timestamp}"))
            
            block = f'\n# --- Python Selection (Updated {timestamp}) ---\nalias python="{target_path}"\nalias python3="{target_path}"\n'
            with open(config_file, "a") as f:
                f.write(block)
            print(f"{Colors.GREEN}Success! Run 'source {config_file}' to apply.{Colors.RESET}")
        except Exception as e:
            print(f"{Colors.RED}Error: {e}{Colors.RESET}")

    elif IS_WINDOWS:
        # Windows Logic: PowerShell Profile
        # We cannot easily change CMD "default" without editing system PATH (dangerous).
        # We will assume PowerShell usage for modern Windows management.
        print(f"{Colors.YELLOW}Note: This will update your PowerShell Profile.{Colors.RESET}")
        
        # Get PowerShell Profile path
        try:
            # We use subprocess to ask PowerShell where the profile is
            ps_cmd = ["powershell", "-NoProfile", "-Command", "echo $PROFILE"]
            result = subprocess.run(ps_cmd, capture_output=True, text=True)
            profile_path = Path(result.stdout.strip())
            
            if not profile_path.parent.exists():
                os.makedirs(profile_path.parent, exist_ok=True)
                
            timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            
            # Create Backup
            if profile_path.exists():
                shutil.copy(profile_path, profile_path.with_suffix(f".backup-{timestamp}"))
            
            # Use Functions for Windows aliases
            func_block = f"""
# --- Python Selection (Updated {timestamp}) ---
function python {{ & '{target_path}' @args }}
function python3 {{ & '{target_path}' @args }}
# ----------------------------------------------
"""
            with open(profile_path, "a") as f:
                f.write(func_block)
            
            print(f"{Colors.GREEN}Success! PowerShell Profile updated at:{Colors.RESET}")
            print(f"{profile_path}")
            print(f"Please restart PowerShell to apply changes.")
            
        except Exception as e:
            print(f"{Colors.RED}Error updating PowerShell profile: {e}{Colors.RESET}")

# --- Action: Remove Version ---

def remove_version(installations, current_default_path):
    print(f"\n{Colors.RED}--- Remove Python Version ---{Colors.RESET}")
    choice = input(f"Enter # to REMOVE (or Enter to cancel): ")
    if not choice.strip().isdigit(): return

    idx = int(choice) - 1
    if not (0 <= idx < len(installations)): return

    target = installations[idx]
    
    # SAFETY CHECKS
    if target['safety'] == 1:
        print(f"\n{Colors.RED}⛔ BLOCKED: Cannot remove Protected/System Python.{Colors.RESET}")
        return

    # Check active default
    tgt_norm = os.path.normpath(target['path']).lower()
    cur_norm = os.path.normpath(current_default_path).lower() if current_default_path else ""
    
    if tgt_norm == cur_norm:
        print(f"\n{Colors.RED}⛔ BLOCKED: Cannot remove active default.{Colors.RESET}")
        return

    if os.path.normpath(sys.executable).lower() == tgt_norm:
        print(f"\n{Colors.RED}⛔ BLOCKED: Script is running on this version.{Colors.RESET}")
        return

    print(f"\nTarget: {Colors.BOLD}Python {target['version']} ({target['vendor']}){Colors.RESET}")
    print(f"Path: {target['path']}")

    if IS_WINDOWS:
        print(f"\n{Colors.YELLOW}WINDOWS SAFETY NOTICE:{Colors.RESET}")
        print("Python on Windows is deeply integrated into the Registry.")
        print("This script will NOT delete files manually to prevent Registry corruption.")
        print(f"\nPlease go to {Colors.BOLD}Settings > Apps > Installed Apps{Colors.BOLD} and uninstall:")
        print(f"{Colors.CYAN}Python {target['version']}{Colors.RESET}")
        return

    # Mac Removal Logic
    confirm = input(f"{Colors.RED}Type 'delete' to confirm removal: {Colors.RESET}")
    if confirm.lower() != 'delete': return

    if target['vendor'] == "Homebrew":
        v_short = ".".join(target['version'].split('.')[:2])
        subprocess.run(["brew", "uninstall", f"python@{v_short}"])
    elif target['vendor'] == "Official Installer" and "Python.framework" in target['path']:
        print(f"\n{Colors.YELLOW}Run manually (Requires Root):{Colors.RESET}")
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

def main():
    while True:
        # Determine current default
        cmd = "python.exe" if IS_WINDOWS else "python3"
        sys_python = shutil.which(cmd)
        if not sys_python and IS_WINDOWS: sys_python = shutil.which("python")
        
        current_real = os.path.realpath(sys_python) if sys_python else None
        
        installs = scan_installations()
        print_table(installs, current_real)
        
        print(f"{Colors.BOLD}Actions:{Colors.RESET}")
        print(f"[{Colors.GREEN}S{Colors.RESET}] Switch Default  [{Colors.RED}R{Colors.RESET}] Remove Version  [{Colors.YELLOW}E{Colors.RESET}] Exit")
        
        choice = input(f"\n{Colors.BOLD}> {Colors.RESET}").lower().strip()
        
        if choice == 's': switch_default(installs)
        elif choice == 'r': remove_version(installs, current_real)
        elif choice == 'e' or choice == '': sys.exit(0)
        
        input(f"\n{Colors.BLUE}Press Enter...{Colors.RESET}")
        print("\n"*2)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nExiting.")