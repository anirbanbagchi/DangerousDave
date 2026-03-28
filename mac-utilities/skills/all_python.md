# all_python

Discover and manage every Python installation on macOS or Windows — Homebrew, pyenv, conda, system, and official installer — from a single interactive or scriptable CLI.

## Usage

```bash
python3 all_python.py [OPTIONS]
```

Running without flags launches the interactive mode: scan, display the table, then prompt for an action.

## Options

| Flag | Default | Description |
|---|---|---|
| `--list` | `false` | Print installation table and exit (non-interactive) |
| `--json` | `false` | Output all installations as JSON and exit |
| `--switch N` | — | Switch default Python to installation #N (non-interactive) |
| `--remove N` | — | Remove installation #N (non-interactive) |
| `--verbose` | `false` | Add a SITE-PACKAGES column to the table |
| `--no-color` | `false` | Disable ANSI color output (useful for piping) |
| `--sort` | `version` | Sort by `version` (desc), `vendor`, or `path` |

## Examples

```bash
# Interactive mode (default)
python3 all_python.py

# Just list all installations and exit
python3 all_python.py --list

# List with site-packages paths
python3 all_python.py --list --verbose

# Output as JSON for scripting
python3 all_python.py --json

# Sort by vendor in interactive mode
python3 all_python.py --sort vendor

# Switch default to installation #3 non-interactively
python3 all_python.py --switch 3

# Remove installation #2 non-interactively
python3 all_python.py --remove 2

# Pipe-friendly output (no color)
python3 all_python.py --list --no-color | grep Homebrew
```

## Table Columns

| Column | Description |
|---|---|
| `#` | Selection index used with `--switch` / `--remove` |
| `VERSION` | Full `x.y.z` version — green for 3.x, red for 2.x |
| `ARCH` | `Apple Silicon`, `Intel 64`, `Universal`, `64-bit`, `32-bit` |
| `PIP` | Whether `pip` is available for this installation |
| `VENDOR` | How Python was installed (see Vendor Detection) |
| `ALIASES` | Binary names pointing to this install (`python`, `python3`, etc.) |
| `LOCATION` | Resolved real path; annotated with `(Current Default)` or `(Protected)` |
| `SITE-PACKAGES` | *(verbose only)* Path to the site-packages directory |

## Features

### Parallel Scanning
All per-binary checks (version, architecture, pip, site-packages) run concurrently via `ThreadPoolExecutor`, making scans fast even with many installations.

### Vendor Detection
Automatically identifies how each Python was installed:

| Vendor | Detection |
|---|---|
| `macOS System` | Path under `/usr/bin` or `/System/Library` |
| `Homebrew` | Path contains `homebrew` or `Cellar` |
| `Official Installer` | Path under `/Library/Frameworks/Python.framework` |
| `pyenv` | Path contains `.pyenv` |
| `Conda` | Path contains `anaconda` or `miniconda` |
| `Microsoft Store` | Path contains `WindowsApps` |
| `User/Other` | Everything else |

### pyenv Detection
Scans `$PYENV_ROOT/versions/` (defaults to `~/.pyenv/versions/`) and adds every installed pyenv version to the table.

### Conda Detection
Discovers the base environment and all named conda environments under `~/anaconda3`, `~/miniconda3`, `/opt/anaconda3`, `/opt/miniconda3`, and any path inferred from `$CONDA_PREFIX`.

### Active Virtualenv
If `$VIRTUAL_ENV` is set, the active virtualenv path is shown above the table.

### Switch Default
Updates `~/.zshrc` (or `~/.bash_profile`) on macOS with `alias python=` and `alias python3=` entries. Automatically backs up the config file before writing. On Windows, updates the PowerShell profile with equivalent functions.

### Safety Guardrails for Removal
Removal is blocked if the target is:
- A Protected/System installation (e.g. macOS system Python, Microsoft Store)
- The currently active default
- The Python interpreter running the script itself

On Windows, manual removal is redirected to **Settings > Apps** to avoid Registry corruption.

### JSON Output
`--json` outputs a machine-readable array, useful for shell scripting or other tools:

```json
[
  {
    "version": "3.12.3",
    "vendor": "Homebrew",
    "arch": "Apple Silicon",
    "pip": true,
    "commands": "python3, python3.12",
    "path": "/opt/homebrew/bin/python3.12",
    "site_packages": "/opt/homebrew/lib/python3.12/site-packages",
    "is_default": true,
    "protected": false
  }
]
```

## Requirements

- Python 3.10+
- macOS or Windows
- `lipo` for architecture detection on macOS (included with Xcode Command Line Tools)
- `brew` for Homebrew-managed removal (optional)
