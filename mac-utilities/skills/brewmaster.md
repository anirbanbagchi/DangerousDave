# BrewMaster

A smarter Homebrew upgrader with version diffs, per-package retries, parallel checks, and full logging.

## Usage

```bash
python3 brewmaster.py [OPTIONS]
```

## Options

| Flag | Default | Description |
|---|---|---|
| `-y`, `--yes` | `false` | Auto-approve all upgrades without prompting |
| `--greedy` / `--no-greedy` | `true` | Include auto-updating casks in outdated check |
| `--check-only` | `false` | Report outdated packages without upgrading |
| `--dry-run` | `false` | Simulate all commands without executing them |
| `--skip PKG [PKG ...]` | — | Skip one or more named packages |
| `--formula-only` | `false` | Only upgrade formulae, ignore casks (mutually exclusive with `--cask-only`) |
| `--cask-only` | `false` | Only upgrade casks, ignore formulae (mutually exclusive with `--formula-only`) |
| `--notify` | `false` | Send a macOS notification when the run finishes |
| `--backup` | `false` | Snapshot current state to a `.Brewfile` before upgrading |
| `--retries N` | `2` | Number of retry attempts per package on failure (min: 1) |

## Examples

```bash
# Standard interactive upgrade
python3 brewmaster.py

# Auto-approve, skip node and python, notify on completion
python3 brewmaster.py -y --skip node python --notify

# Preview what's outdated with version diffs, don't upgrade
python3 brewmaster.py --check-only

# Dry run — see exactly what would run, nothing executed
python3 brewmaster.py --dry-run

# Upgrade formulae only, with a bundle backup first
python3 brewmaster.py --formula-only --backup

# Disable greedy cask checking, auto-approve
python3 brewmaster.py --no-greedy -y

# Upgrade casks only, retry failures up to 3 times
python3 brewmaster.py --cask-only --retries 3
```

## Features

### Version Diff Display
Uses `brew outdated --json=v2` to show installed vs. available version for every package:
```
  • ffmpeg  6.1.0 → 7.1.0
  • node    20.11.0 → 22.3.0
```

### Parallel Outdated Checks
Formula and cask outdated checks run concurrently via `ThreadPoolExecutor`. Exceptions in either worker are surfaced immediately rather than silently swallowed.

### Per-Package Retries
Each package is upgraded individually. On failure it retries up to `--retries N` times before being marked failed. Other packages continue regardless.

### Failure Summary
Failed packages are collected and displayed in a summary at the end rather than aborting the run:
```
⚠️  Completed with failures:
  • [cask] some-app: error message here
```

### Pin Awareness
Reads `brew list --pinned` and automatically skips pinned formulae with a warning. If the pinned-package query itself fails, a warning is printed and the run continues:
```
  📌 Skipping pinned: python@3.11
```

### Bundle Backup
`--backup` runs `brew bundle dump` before any upgrades, saving a snapshot to:
```
~/.brewmaster_backup_YYYYMMDD_HHMMSS.Brewfile
```
If the dump command fails (e.g. the bundle tap is missing), an error is printed and the run aborts the backup step cleanly rather than writing an empty file.

Restore with: `brew bundle install --file=~/.brewmaster_backup_<timestamp>.Brewfile`

### Upgrade Log
Every run appends timestamped entries to `~/.brewmaster.log` via Python's `logging` module:
```
[2026-03-28 14:05:01] --- BrewMaster run started ---
[2026-03-28 14:05:20] Upgraded formula: ffmpeg
[2026-03-28 14:05:45] FAILED cask: some-app — error details
[2026-03-28 14:06:10] Run complete with 1 failure(s). Elapsed: 69.2s
```

### macOS Notifications
`--notify` sends a native notification on completion via `osascript`. Special characters in package names and error messages are escaped to prevent AppleScript injection. Requires macOS.

## Requirements

- Python 3.10+
- Homebrew installed and available as `brew` in `PATH`
- macOS (notifications require `osascript`)
- `brew bundle` tap for `--backup` (included with Homebrew by default)
