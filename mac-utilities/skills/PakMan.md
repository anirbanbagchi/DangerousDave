# PakMan

A robust Python package updater built on pip — batch upgrades with per-package fallback, rollback snapshots, dependency checks, vulnerability audits, and full logging.

## Usage

```bash
python3 PakMan.py [OPTIONS]
```

## Options

| Flag | Default | Description |
| --- | --- | --- |
| `-y`, `--yes` | `false` | Auto-approve all upgrades without prompting |
| `-i`, `--interactive` | `false` | Pick packages from a numbered list (mutually exclusive with `-y`) |
| `--check-only` | `false` | List outdated packages and exit (exit 3 if any found) |
| `--dry-run` | `false` | Print commands that would run without executing them |
| `--exclude PKG [PKG ...]` | — | Skip packages; case-insensitive globs (e.g. `--exclude 'boto*'`) |
| `--only PKG [PKG ...]` | — | Upgrade only these packages; case-insensitive globs |
| `--upgrade-pip` | `false` | Upgrade pip itself before upgrading packages |
| `--pre` | `false` | Include pre-release versions when upgrading |
| `--only-binary` | `false` | Refuse source distributions (no sdist build code executes) |
| `--require-venv` | `false` | Refuse to run outside a virtual environment |
| `--audit` | `false` | Run `pip-audit` after upgrading (skipped if not installed) |
| `--no-uv` | `false` | Don't use uv for the outdated check even if installed |
| `--no-rollback` | `false` | Skip writing the rollback snapshot file |
| `--no-batch` | `false` | Skip the batch attempt; go straight to per-package upgrades |
| `--export FILE` | — | Run `pip freeze` after upgrading and save to FILE |
| `--notify` | `false` | Send a macOS notification when the run finishes |
| `--json` | `false` | Output outdated packages as JSON and exit |
| `--log-json` | `false` | Append a JSON record per run to `~/.pakman_history.jsonl` |
| `--retries N` | `2` | Retry attempts per package on failure (min: 1) |
| `--timeout SECS` | `600` | Timeout per package (batch gets timeout × package count) |

## Exit Codes

| Code | Meaning |
| --- | --- |
| `0` | Success — nothing to do, or all upgrades succeeded |
| `1` | Fatal error (non-TTY without `-y`, `--require-venv` outside a venv, ...) |
| `2` | Run completed but one or more packages failed |
| `3` | `--check-only` found outdated packages |
| `130` | Interrupted with Ctrl-C |

## Examples

```bash
# Standard interactive upgrade
python3 PakMan.py

# Pick exactly which packages to upgrade from a numbered list
python3 PakMan.py -i

# Auto-approve, skip all boto packages, notify on completion
python3 PakMan.py -y --exclude 'boto*' --notify

# Preview outdated packages only (exit 3 if any found)
python3 PakMan.py --check-only

# Wheels only — never execute sdist build code
python3 PakMan.py --only-binary -y

# Refuse to touch global site-packages
python3 PakMan.py --require-venv -y

# Upgrade, then scan for known vulnerabilities
python3 PakMan.py -y --audit

# Upgrade pip first, then everything, export freeze when done
python3 PakMan.py --upgrade-pip --export requirements.txt -y

# Cron-friendly: auto-approve, JSON history, no rollback file
python3 PakMan.py -y --log-json --no-rollback

# Output outdated list as JSON for scripting
python3 PakMan.py --json
```

## Features

### Batch Upgrade with Per-Package Fallback

All packages are first upgraded in a **single** `pip install --upgrade` call — one resolver run instead of N, typically 5–10x faster. Only if the batch fails does PakMan fall back to per-package upgrades (with parallel wheel prefetch) to isolate the failing package. `--no-batch` forces the per-package path.

Note: in a batch run the resolver may pick a version other than "Latest" if a newer version conflicts with another package's requirements — the post-run `pip check` covers this.

### Rollback Snapshot

Before upgrading, current versions are written to `~/.pakman_rollback_YYYYMMDD_HHMMSS.txt` as `pkg==version` lines. Undo an entire run with:

```bash
pip install -r ~/.pakman_rollback_<timestamp>.txt
```

The 5 newest snapshots are kept; older ones are pruned. Disable with `--no-rollback`.

### Dependency Health Check

`pip check` runs automatically after every upgrade and surfaces broken dependency graphs (e.g. A upgraded, but B needs the older A) in the output, the log, and the JSON history.

### Vulnerability Audit

`--audit` runs [pip-audit](https://pypi.org/project/pip-audit/) after upgrading and reports known CVEs. If pip-audit isn't installed, the step is skipped with an install hint.

### Fast Outdated Check via uv

If [uv](https://github.com/astral-sh/uv) is on PATH, the outdated check uses `uv pip list --outdated` targeted at the same interpreter — often 10x faster than pip's. Falls back to pip automatically on any error; `--no-uv` disables it.

### Interactive Selection

`-i` presents a numbered list and accepts selections like `1,3,5-7`, `all`, or `none`. Selecting implies consent — no second confirmation prompt.

### Glob Package Filtering

`--only` and `--exclude` match case-insensitively and support glob patterns: `--exclude 'boto*'` matches `boto3`, `botocore`, and `BOTOcore`. The same name in both flags is rejected at parse time.

### Per-Package Retries and Timeouts

On the fallback path each package retries up to `--retries N` times, and every pip call is bounded by `--timeout` (default 600s) — a package stuck building from source becomes a recorded failure instead of hanging the run.

### Security Hardening

- Package names are validated against PEP 508 naming rules before reaching any subprocess.
- `--only-binary` guarantees no `setup.py` code executes at install time.
- `--require-venv` refuses to modify global site-packages.
- The log file is created with `0600` permissions.
- Notification text is escaped to prevent AppleScript injection.

### Audit Log and JSON History

Every pip invocation writes an `AUDIT:` line with the exact command and exit code to `~/.pakman.log`. With `--log-json`, each run appends one structured record (upgraded, failures, conflicts, elapsed, exit code) to `~/.pakman_history.jsonl` — same schema family as BrewMaster's history.

### Clean Interrupts and Cron Safety

Ctrl-C mid-upgrade prints "N upgraded, N failed, N not attempted" and exits 130. In a non-TTY session (cron, launchd) without `-y`, the tool exits 1 immediately instead of hanging on the prompt. Pip's own version self-check is disabled on every call for speed.

### Virtualenv Warning

Without `--require-venv`, running outside a virtualenv still prints a prominent warning before touching global packages.

### macOS Notifications

`--notify` sends a native notification on completion via `osascript`. Requires macOS.

## Files

| Path | Purpose |
| --- | --- |
| `~/.pakman.log` | Timestamped run log with per-command audit lines (mode 0600) |
| `~/.pakman_history.jsonl` | One JSON record per run when `--log-json` is set |
| `~/.pakman_rollback_*.txt` | Pre-upgrade version snapshots (5 newest kept) |

## Requirements

- Python 3.10+
- `pip` available for the active interpreter (`python -m pip`)
- macOS for `--notify` (requires `osascript`)
- Optional: `uv` for fast outdated checks, `pip-audit` for `--audit`
