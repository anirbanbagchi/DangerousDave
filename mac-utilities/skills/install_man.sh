#!/usr/bin/env bash
# Installs man pages for mac-utilities scripts.
# Usage:
#   bash install_man.sh              # install all
#   bash install_man.sh brewmaster   # install one

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MAN_DIR="/usr/local/share/man/man1"

install_page() {
    local name="$1"
    local src="$SCRIPT_DIR/${name}.py.1"
    local dest="$MAN_DIR/${name}.py.1"

    if [[ ! -f "$src" ]]; then
        echo "Error: $src not found." >&2
        return 1
    fi

    echo "Installing: $dest"
    sudo mkdir -p "$MAN_DIR"
    sudo cp "$src" "$dest"
    sudo chmod 644 "$dest"
    echo "  -> man ${name}.py"
}

if [[ $# -gt 0 ]]; then
    for arg in "$@"; do
        install_page "$arg"
    done
else
    install_page "brewmaster"
    install_page "all_python"
    install_page "PakMan"
fi

# Rebuild the whatis database so man -k / apropos picks pages up
if command -v /usr/libexec/makewhatis &>/dev/null; then
    sudo /usr/libexec/makewhatis "$(dirname "$MAN_DIR")"
fi

echo ""
echo "Done. Try:"
echo "  man brewmaster.py"
echo "  man all_python.py"
echo "  man PakMan.py"
