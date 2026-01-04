"""
Package List Generator
--------------------------------
Author :  Anirban Bagchi
"""

import subprocess
import sys
import os

def generate_requirements_file(filename="requirements.txt"):
    """
    Generates a requirements.txt file listing all currently installed packages
    with their exact versions using 'pip freeze'.

    Args:
        filename (str): The name of the file to create (default is 'requirements.txt').
    """
    print(f"Starting process to generate {filename}...")
    
    try:
        # 1. Execute 'pip freeze'
        # 'pip freeze' outputs packages in the format: package_name==version
        result = subprocess.run([sys.executable, '-m', 'pip', 'freeze'], 
                                capture_output=True, text=True, check=True)
        
        requirements_content = result.stdout.strip()

        if not requirements_content:
            print("No installed packages found to write to the file.")
            return

        # 2. Write the output to the specified file
        with open(filename, 'w') as f:
            f.write(requirements_content)
        
        # 3. Confirmation and instructions
        print("\n✅ Successfully generated package list!")
        print(f"File created: {os.path.abspath(filename)}")
        print("----------------------------------------------------------------------")
        print(f"The file contains {len(requirements_content.splitlines())} packages.")
        print("To reinstall these packages later in a new environment, use this command:")
        print(f"   pip install -r {filename}")
        print("----------------------------------------------------------------------")

    except subprocess.CalledProcessError as e:
        print(f"Error executing pip freeze: {e.stderr}")
        print("Please ensure pip is installed and accessible.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    generate_requirements_file()