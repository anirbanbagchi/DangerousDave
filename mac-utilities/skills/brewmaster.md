# BrewMaster

A smarter Homebrew upgrader with version diffs, parallel prefetch, per-package retries, interactive selection, and full logging.

## Usage

```bash
python3 brewmaster.py [OPTIONS]
```

## Options

| Flag | Default | Description |
| --- | --- | --- |
| `-y`, `--yes` | `false` | Auto-approve all upgrades without prompting |
| `-i`, `--interactive` | `false` | Pick packages from a numbered list (mutually exclusive with `-y`) |
| `--greedy` / `--no-greedy` | `true` | Include auto-updating casks in outdated check |
| `--check-only` | `false` | Report outdated packages without upgrading (exit 3 if any found) |
| `--dry-run` | `false` | Simulate all commands without executing them |
| `--skip PKG [PKG ...]` | — | Skip packages; glob patterns supported (e.g. `--skip 'python@*'`) |
| `--formula-only` | `false` | Only upgrade formulae (mutually exclusive with `--cask-only`) |
| `--cask-only` | `false` | Only upgrade casks (mutually exclusive with `--formula-only`) |
| `--notify` | `false` | Send a macOS notification when the run finishes |
| `--backup` | `false` | Snapshot state to a `.Brewfile` first; keeps the 5 newest |
| `--no-update` | `false` | Skip `brew update` entirely |
| `--force-update` | `false` | Run `brew update` even if it ran within the last hour |
| `--sizes` | `false` | Prefetch downloads and show total size before confirming |
| `--log-json` | `false` | Append a JSON record per run to `~/.brewmaster_history.jsonl` |
| `--retries N` | `2` | Retry attempts per package on failure (min: 1) |
| `--timeout SECS` | `600` | Timeout per package upgrade |

## Exit Codes

| Code | Meaning |
| --- | --- |
| `0` | Success — nothing to do, or all upgrades succeeded |
| `1` | Fatal error (brew missing, non-TTY without `-y`, ...) |
| `2` | Run completed but one or more packages failed |
| `3` | `--check-only` found outdated packages |
| `130` | Interrupted with Ctrl-C |

## Examples

```bash
# Standard interactive upgrade
python3 brewmaster.py

# Pick exactly which packages to upgrade from a numbered list
python3 brewmaster.py -i

# Auto-approve, skip node and all python versions, notify on completion
python3 brewmaster.py -y --skip node 'python@*' --notify

# Preview what's outdated with version diffs, don't upgrade (exit 3 if any)
python3 brewmaster.py --check-only

# Dry run — see exactly what would run, nothing executed
python3 brewmaster.py --dry-run

# Show total download size before confirming
python3 brewmaster.py --sizes

# Upgrade formulae only, with a bundle backup first
python3 brewmaster.py --formula-only --backup

# Cron-friendly: auto-approve, skip update if fresh, log JSON history
python3 brewmaster.py -y --log-json

# Give a slow cask 20 minutes before treating it as hung
python3 brewmaster.py --cask-only --timeout 1200 -y
```

## Features

### Version Diff Display

Uses a single `brew outdated --json=v2` call to show installed vs. available version for every package:

```text
  • ffmpeg  6.1.0 → 7.1.0
  • node    20.11.0 → 22.3.0
```

### Interactive Selection

`-i` presents a numbered list and accepts selections like `1,3,5-7`, `all`, or `none`. Selecting implies consent — no second confirmation prompt.

### Parallel Download Prefetch

All bottles and casks are prefetched via `brew fetch` on a 4-worker thread pool before the sequential upgrade loop, so each `brew upgrade` hits the local cache. With `--sizes`, prefetch happens before the confirmation prompt and the real on-disk download total is displayed (note: this downloads before you confirm).

### Smart brew update

`brew update` is skipped automatically when it already ran within the last hour (detected via the Homebrew repository's `FETCH_HEAD`). Override with `--force-update`, or skip always with `--no-update`.

### Per-Package Retries and Timeouts

Each package is upgraded individually. On failure or timeout (`--timeout`, default 600s) it retries up to `--retries N` times before being marked failed. Other packages continue regardless. A hung cask installer becomes a recorded failure instead of stalling the run forever.

### Failure Summary and Exit Codes

Failed packages are collected into a summary at the end, and the exit code distinguishes success (0), failures (2), and outdated-found (3) for scripting and cron use.

### Pin Awareness

Reads `brew list --pinned` and automatically skips pinned formulae. If the pinned-package query fails, a warning is printed and the run continues.

### Bundle Backup with Pruning

`--backup` runs `brew bundle dump` before any upgrades, saving to `~/.brewmaster_backup_YYYYMMDD_HHMMSS.Brewfile` and pruning to the 5 newest snapshots. A failed dump prints an error and writes nothing.

Restore with: `brew bundle install --file=~/.brewmaster_backup_<timestamp>.Brewfile`

### Security Hardening

- `brew` is resolved once to an absolute path; a warning is printed if it lives outside `/opt/homebrew/bin` or `/usr/local/bin` (PATH-hijack detection).
- Package names are validated against brew's naming alphabet before reaching any subprocess.
- The log file is created with `0600` permissions.
- Notification text is escaped to prevent AppleScript injection.

### Audit Log and JSON History

Every upgrade attempt writes an `AUDIT:` line with the exact command and exit code to `~/.brewmaster.log`. With `--log-json`, each run also appends one structured record (upgraded, failures, elapsed, exit code) to `~/.brewmaster_history.jsonl` — easy to graph or feed into other tools.

### Clean Interrupts and Cron Safety

Ctrl-C mid-upgrade prints "N upgraded, N failed, N not attempted" and exits 130. In a non-TTY session (cron, launchd) without `-y`, the tool exits 1 immediately instead of hanging on the prompt.

### macOS Notifications

`--notify` sends a native notification on completion via `osascript`. Requires macOS.

## Files

| Path | Purpose |
| --- | --- |
| `~/.brewmaster.log` | Timestamped run log with per-command audit lines (mode 0600) |
| `~/.brewmaster_history.jsonl` | One JSON record per run when `--log-json` is set |
| `~/.brewmaster_backup_*.Brewfile` | Bundle snapshots from `--backup` (5 newest kept) |

## Requirements

- Python 3.10+
- Homebrew installed and available as `brew` in `PATH`
- macOS (notifications require `osascript`)
- `brew bundle` tap for `--backup` (included with Homebrew by default)
