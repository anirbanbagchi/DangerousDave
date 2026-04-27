# PakMan

A robust Python package updater built on pip — per-package retries, failure summaries, freeze export, and full logging.

## Usage

```bash
python3 PakMan.py [OPTIONS]
```

## Options

| Flag | Default | Description |
| --- | --- | --- |
| `-y`, `--yes` | `false` | Auto-approve all upgrades without prompting |
| `--check-only` | `false` | List outdated packages and exit without upgrading |
| `--dry-run` | `false` | Print commands that would run without executing them |
| `--exclude PKG [PKG ...]` | — | Skip specific packages (case-insensitive) |
| `--only PKG [PKG ...]` | — | Upgrade only these packages (case-insensitive, must appear in outdated list) |
| `--upgrade-pip` | `false` | Upgrade pip itself before upgrading packages |
| `--pre` | `false` | Include pre-release versions when upgrading |
| `--export FILE` | — | Run `pip freeze` after upgrading and save to FILE |
| `--notify` | `false` | Send a macOS notification when the run finishes |
| `--json` | `false` | Output outdated packages as JSON and exit |
| `--retries N` | `2` | Retry attempts per package on failure (min: 1) |

## Examples

```bash
# Standard interactive upgrade
python3 PakMan.py

# Auto-approve, skip a package, notify on completion
python3 PakMan.py -y --exclude pip setuptools --notify

# Preview outdated packages only
python3 PakMan.py --check-only

# Dry run — see exactly what would run
python3 PakMan.py --dry-run

# Upgrade only specific packages (case-insensitive)
python3 PakMan.py --only requests boto3 -y

# Upgrade pip first, then everything, export freeze when done
python3 PakMan.py --upgrade-pip --export requirements.txt -y

# Include pre-release versions
python3 PakMan.py --pre -y

# Output outdated list as JSON for scripting
python3 PakMan.py --json

# Retry each failure up to 3 times
python3 PakMan.py --retries 3 -y
```

## Features

### Per-Package Upgrade with Retries
Each package is upgraded individually rather than in one batch. On failure it retries up to `--retries N` times (minimum 1). Remaining packages continue regardless, and all failures are collected into a summary at the end:

```
⚠️  Completed with failures:
  • some-package: error details here
```

### Outdated Table
Shows package name, current version, latest version, and release type. Column widths adjust dynamically to fit the actual package names, so long names like `tensorflow-io-gcs-filesystem` never truncate:

```
Package     Current    Latest     Type
----------------------------------------
requests    2.28.0     2.31.0     wheel
boto3       1.26.0     1.34.0     wheel
  2 package(s) outdated
```

### Case-Insensitive Package Filtering

`--only` and `--exclude` match package names case-insensitively (`--only pillow` matches `Pillow` as returned by pip). Specifying the same package in both flags is rejected at parse time with a clear error.

### Virtualenv Warning
Detects whether a virtualenv is active and warns before touching global packages:

```
⚠️  WARNING: You are NOT running in a virtual environment.
   Installing/Upgrading global packages can break system tools.
```

### pip Self-Upgrade
`--upgrade-pip` upgrades pip itself before any other package, ensuring the latest resolver is used.

### Freeze Export
`--export FILE` runs `pip freeze` after all upgrades complete and writes the result to the specified file. If `pip freeze` fails, a warning is printed and the file is not written. Useful for keeping `requirements.txt` in sync:

```bash
python3 PakMan.py -y --export requirements.txt
```

### JSON Output
`--json` outputs the raw outdated list from pip as pretty-printed JSON and exits — useful for scripting or piping into other tools:

```json
[
  {
    "name": "requests",
    "version": "2.28.0",
    "latest_version": "2.31.0",
    "latest_filetype": "wheel"
  }
]
```

### Upgrade Log
Every run appends timestamped entries to `~/.pakman.log` via Python's `logging` module:

```
[2026-03-28 14:05:01] --- PakMan run started ---
[2026-03-28 14:05:08] Upgraded: requests 2.28.0 -> 2.31.0
[2026-03-28 14:05:12] FAILED: some-pkg — error details
[2026-03-28 14:05:13] Run complete with 1 failure(s). Elapsed: 12.4s
```

### macOS Notifications
`--notify` sends a native notification on completion via `osascript`. Special characters in package names and error messages are escaped to prevent AppleScript injection. Requires macOS.

## Requirements

- Python 3.10+
- `pip` available for the active interpreter (`python -m pip`)
- macOS for `--notify` (requires `osascript`)
