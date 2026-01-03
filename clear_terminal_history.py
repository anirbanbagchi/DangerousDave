import os
import sys

def get_file_path(shell_type):
    """Returns the standard file path for the given shell's history."""
    home_dir = os.path.expanduser("~")
    if shell_type == 'zsh':
        return os.path.join(home_dir, ".zsh_history")
    elif shell_type == 'bash':
        return os.path.join(home_dir, ".bash_history")
    return None

def view_history(file_path):
    """Reads and displays the content of the history file."""
    if not os.path.exists(file_path):
        print(f"[-] No history file found at: {file_path}")
        return

    try:
        print(f"\n--- Content of {file_path} ---")
        with open(file_path, 'r', errors='replace') as f:
            content = f.read()
            if not content:
                print("(File is empty)")
            else:
                # Limit output if it's extremely long to prevent terminal flooding
                lines = content.splitlines()
                if len(lines) > 20:
                    print(f"... (showing last 20 of {len(lines)} lines) ...\n")
                    print("\n".join(lines[-20:]))
                else:
                    print(content)
        print("-----------------------------------\n")
    except Exception as e:
        print(f"[!] Error reading file: {e}")

def clear_history(file_path):
    """Permanently wipes the history file by truncating it."""
    if not os.path.exists(file_path):
        print(f"[-] File does not exist: {file_path}")
        return

    confirm = input(f"Are you sure you want to PERMANENTLY clear {file_path}? (yes/no): ").lower()
    if confirm == 'yes':
        try:
            # Opening in 'w' mode truncates the file to 0 bytes
            with open(file_path, 'w') as f:
                pass 
            print(f"[+] Successfully cleared {file_path}")
        except Exception as e:
            print(f"[!] Failed to clear history: {e}")
    else:
        print("[*] Operation cancelled.")

def main():
    while True:
        print("\n=== macOS Shell History Cleaner ===")
        print("1. View Zsh History")
        print("2. Clear Zsh History")
        print("3. View Bash History")
        print("4. Clear Bash History")
        print("5. Exit")
        
        choice = input("\nEnter your choice (1-5): ")

        if choice == '1':
            view_history(get_file_path('zsh'))
        elif choice == '2':
            clear_history(get_file_path('zsh'))
        elif choice == '3':
            view_history(get_file_path('bash'))
        elif choice == '4':
            clear_history(get_file_path('bash'))
        elif choice == '5':
            print("Exiting...")
            sys.exit()
        else:
            print("[!] Invalid choice, please try again.")

if __name__ == "__main__":
    main()