"""
Python package installer script that reads a requirements file, removes version
specifiers, and installs each package individually while logging the output. If
an installation fails, it continues with the next package instead of stopping.
This is particularly useful for macOS environments where certain packages may  
fail to install due to compatibility issues.
------------------------------------------------------------------------------
Author :  Anirban Bagchi
"""

import subprocess
import sys
import os
import datetime
import json
from typing import List, Dict, Any

# Define a type hint for the package information structure
PackageInfo = Dict[str, str]

def log_and_print(message: str, log_file):
    """Prints a message to the console and writes it to the log file."""
    # Ensure all output is encoded to UTF-8 to prevent 'charmap' errors
    # We strip any non-ASCII characters that might still sneak through on Windows
    try:
        clean_message = message.encode('ascii', 'ignore').decode('ascii')
    except:
        clean_message = message # Fallback if cleaning fails
        
    timestamp = datetime.datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
    full_message = f"{timestamp} {clean_message}"
    
    print(clean_message)
    log_file.write(full_message + '\n')
    log_file.flush() # Ensure the message is written immediately

def get_top_level_packages(requirements_file="requirements.txt") -> list[str]:
    """
    Reads the requirements file and strips version specifiers to create a 
    clean list of base package names for safe installation.
    """
    if not os.path.exists(requirements_file):
        print(f"ERROR: Requirements file '{requirements_file}' not found. Please ensure it exists.")
        return []

    print(f"Reading packages from '{requirements_file}'...")
    with open(requirements_file, 'r') as f:
        all_lines = f.readlines()
    
    cleaned_packages = []
    
    for line in all_lines:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
            
        # Strip all version specifiers (e.g., '==1.2.3', '>=2.0')
        package_name = line.split('==')[0].split('>=')[0].split('<=')[0].split('~=')[0]
        cleaned_packages.append(package_name)

    print(f"Reduced package list to {len(cleaned_packages)} base packages (version locking removed).\n")
    return cleaned_packages

def safe_install_packages(package_list: list[str]):
    """
    Installs packages one by one, logs output, and continues to the next package 
    if an installation fails.
    """
    if not package_list:
        print("No packages to install. Script stopping.")
        return

    # Generate the timestamped log filename: mmddyyyyhhmmss
    timestamp_format = "%m%d%Y%H%M%S"
    log_filename = f"pip_install_{datetime.datetime.now().strftime(timestamp_format)}.log"
    
    # Open the log file for writing
    with open(log_filename, 'w', encoding='utf-8') as log_file: # Use UTF-8 for better character support
        
        log_and_print("--- Starting Safe Package Installation ---", log_file)
        log_and_print(f"Log file created: {log_filename}", log_file)
        log_and_print(f"Total packages to install: {len(package_list)}", log_file)
        log_and_print("------------------------------------------", log_file)

        while True:
            choice = input("Proceed with installing the cleaned package list? (yes/no): ").lower().strip()
            if choice == 'yes':
                log_and_print("\nStarting package-by-package installation...", log_file)
                
                failed_packages = []
                
                # *** KEY CHANGE: Iterate through the package list ***
                for package_name in package_list:
                    log_and_print(f"\n--- Installing {package_name} ---", log_file)
                    
                    install_command = [sys.executable, '-m', 'pip', 'install', package_name]
                    
                    log_and_print(f"Executing: {' '.join(install_command)}", log_file)
                    
                    try:
                        # Use subprocess.Popen for real-time streaming of stdout/stderr
                        process = subprocess.Popen(install_command, 
                                                   stdout=subprocess.PIPE, 
                                                   stderr=subprocess.STDOUT, 
                                                   # Use 'utf-8' encoding for better compatibility
                                                   text=True, encoding='utf-8') 
                        
                        # Stream output line by line to console and log file
                        while True:
                            line = process.stdout.readline()
                            if not line and process.poll() is not None:
                                break
                            if line:
                                log_and_print(f"PIP OUTPUT: {line.strip()}", log_file)
                        
                        # Wait for the process to finish and get the return code
                        return_code = process.wait()
                        
                        if return_code == 0:
                            log_and_print(f"✅ Successfully installed {package_name}.", log_file)
                        else:
                            log_and_print(f"❌ Failed to install {package_name}. Continuing to next package.", log_file)
                            failed_packages.append(package_name)
                            
                    except Exception as e:
                        log_and_print(f"An unexpected error occurred during installation of {package_name}: {e}", log_file)
                        failed_packages.append(package_name)
                
                log_and_print("\n--- Installation Summary ---", log_file)
                if not failed_packages:
                    log_and_print("🎉 All packages processed successfully!", log_file)
                else:
                    log_and_print(f"⚠️ Installation finished with {len(failed_packages)} failures.", log_file)
                    log_and_print("Failed packages:", log_file)
                    for pkg in failed_packages:
                        log_and_print(f"  - {pkg}", log_file)
                        
                log_and_print("--- Package Installation Process Complete ---", log_file)
                break
                
            elif choice == 'no':
                log_and_print("Installation cancelled by user. Exiting.", log_file)
                break
            else:
                print("Invalid choice. Please enter 'yes' or 'no'.")

if __name__ == "__main__":
    # 1. Clean the list of packages (remove version specifiers)
    packages_to_install = get_top_level_packages()
    
    # 2. Safely install the cleaned list with logging
    if packages_to_install:
        safe_install_packages(packages_to_install)