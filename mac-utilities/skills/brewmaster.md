# BrewMaster

A graphical, fast, careful Homebrew upgrader: boxed tables and a live progress
bar, pipelined parallel downloads, per-package retries and timeouts, an
instance lock, and a full audit log.

## Usage

```bash
python3 brewmaster.py [OPTIONS]
```

## Options

### Selection

| Flag | Default | Description |
| --- | --- | --- |
| `-y`, `--yes` | `false` | Auto-approve all upgrades without prompting |
| `-i`, `--interactive` | `false` | Pick packages from the numbered table (mutually exclusive with `-y`) |
| `--skip PKG [PKG ...]` | — | Skip packages; glob patterns supported (e.g. `--skip 'python@*'`) |
| `--only PKG [PKG ...]` | — | Upgrade *only* packages matching these names/globs |
| `--formula-only` | `false` | Only upgrade formulae (mutually exclusive with `--cask-only`) |
| `--cask-only` | `false` | Only upgrade casks (mutually exclusive with `--formula-only`) |
| `--greedy` / `--no-greedy` | `true` | Include auto-updating casks in the outdated check |

### Behaviour

| Flag | Default | Description |
| --- | --- | --- |
| `--check-only` | `false` | Report outdated packages without upgrading (exit 3 if any found) |
| `--dry-run` | `false` | Simulate all commands without executing them |
| `--backup` | `false` | Snapshot state to a `.Brewfile` first; keeps the 5 newest |
| `--no-update` | `false` | Skip `brew update` entirely |
| `--force-update` | `false` | Run `brew update` even if it ran within the last hour |
| `--no-cleanup` | `false` | Skip the `brew cleanup` step at the end of the run |
| `--no-lock` | `false` | Allow concurrent BrewMaster runs (skips the instance lock) |
| `--no-config` | `false` | Ignore `~/.brewmasterrc.json` |
| `--notify` | `false` | Send a macOS notification when the run finishes |

### Performance

| Flag | Default | Description |
| --- | --- | --- |
| `--jobs N` | `6` | Parallel download workers (1–16) |
| `--no-prefetch` | `false` | Don't pre-download; let each `brew upgrade` fetch for itself |
| `--sizes` | `false` | Download everything up front and show per-package sizes before confirming |
| `--retries N` | `2` | Attempts per package before it is marked failed (min: 1) |
| `--timeout SECS` | `600` | Timeout per package upgrade |

### Output

| Flag | Default | Description |
| --- | --- | --- |
| `--color {auto,always,never}` | `auto` | Colorise output |
| `--ascii` | `false` | ASCII-only output — no box drawing or emoji |
| `-q`, `--quiet` | `false` | Print only warnings and errors |
| `-v`, `--verbose` | `false` | Stream raw brew output instead of progress indicators |
| `--json` | `false` | Print a machine-readable run summary to stdout (the UI moves to stderr) |
| `--log-json` | `false` | Append a JSON record per run to `~/.brewmaster_history.jsonl` |
| `--history [N]` | `15` | Show the last N recorded runs and exit |
| `--version` | — | Print the version and exit |

## Exit Codes

| Code | Meaning |
| --- | --- |
| `0` | Success — nothing to do, or all upgrades succeeded |
| `1` | Fatal error (brew missing, non-TTY without `-y`, lock held, out of disk, ...) |
| `2` | Run completed but one or more packages failed |
| `3` | `--check-only` found outdated packages |
| `130` | Interrupted with Ctrl-C or SIGTERM |

## Examples

```bash
# Standard interactive upgrade
python3 brewmaster.py

# Pick exactly which packages to upgrade from the numbered table
python3 brewmaster.py -i

# Auto-approve, skip node and all python versions, notify on completion
python3 brewmaster.py -y --skip node 'python@*' --notify

# Upgrade only the Rust toolchain packages
python3 brewmaster.py --only 'rust*' -y

# Preview what's outdated with version diffs, don't upgrade (exit 3 if any)
python3 brewmaster.py --check-only

# Dry run — see exactly what would run, nothing executed
python3 brewmaster.py --dry-run

# Download everything first and show per-package sizes before confirming
python3 brewmaster.py --sizes

# Upgrade formulae only, with a bundle backup first
python3 brewmaster.py --formula-only --backup

# Cron-friendly: quiet, auto-approve, JSON history
python3 brewmaster.py -y -q --log-json

# Feed the result to another tool
python3 brewmaster.py -y --json | jq '.failures'

# Review the last 30 recorded runs
python3 brewmaster.py --history 30

# Give a slow cask 20 minutes before treating it as hung
python3 brewmaster.py --cask-only --timeout 1200 -y
```

## Features

### Graphical Terminal Output

Outdated packages are rendered as a box-drawn, column-aligned table with
version diffs and (with `--sizes`) download sizes:

```text
╭───┬─────────┬────────────────────┬───────────┬───────────┬──────────╮
│ # │ Kind    │ Package            │ Installed │ Available │ Download │
├───┼─────────┼────────────────────┼───────────┼───────────┼──────────┤
│ 1 │ formula │ ffmpeg             │ 6.1.0     │ 7.1.0     │  38.4 MB │
│ 2 │ cask    │ visual-studio-code │ 1.88.1    │ 1.91.0    │ 124.9 MB │
╰───┴─────────┴────────────────────┴───────────┴───────────┴──────────╯
```

During the upgrade a live progress bar sits at the bottom of the terminal with
a spinner, counts, and elapsed time, while finished packages scroll above it:

```text
  ✔ ffmpeg                   6.1.0 → 7.1.0 (41.2s)
  ✖ node                     Error: node 22.3.0 is already installed
  ⠹ ████████████░░░░░░░░░░░░░░░░  2/7 1m 04s  python@3.12
```

The run ends in a summary panel with counts, download total, space freed, and
elapsed time.

Column arithmetic is done in terminal *columns*, not characters: emoji and CJK
text are double-width, and combining marks, variation selectors and joiners take
no space at all. Borders line up whatever a package name contains, and
truncation never splits a double-width character in half.

Every one of these degrades on its own. A non-TTY, `NO_COLOR`, `TERM=dumb`, or
a non-UTF-8 stream drops colors, the live line, or the box-drawing characters
independently — the content is never lost. `--color` and `--ascii` force the
decision, `--quiet` prints only warnings and errors, and `--verbose` streams
raw brew output instead of the progress display.

### Pipelined Parallel Downloads

Downloads run on a thread pool (`--jobs`, default 6) *while* upgrades install,
not merely before them. Fetches are submitted in upgrade order and the upgrade
loop waits only on the future for the package it is about to install, so the
download of package N+1 overlaps the installation of package N. `--no-prefetch`
disables it; `--sizes` reverts to downloading everything up front, because
reporting real byte counts requires the files to be on disk first.

### Faster brew Calls

Every brew subprocess runs with `HOMEBREW_NO_AUTO_UPDATE=1` and
`HOMEBREW_NO_INSTALL_CLEANUP=1`. BrewMaster updates and cleans up itself, once
per run, instead of letting Homebrew re-check and re-clean on every single
package — the largest speedup available on a multi-package run.
`brew outdated` and `brew list --pinned` are issued concurrently.

`brew update` is also skipped automatically when it already ran within the last
hour (detected via the Homebrew repository's `FETCH_HEAD`). Override with
`--force-update`, or skip always with `--no-update`.

### Single-Instance Lock

An `flock` on `~/.brewmaster.lock` refuses to start a second run while one is
in progress — overlapping cron runs otherwise fight over Homebrew's own locks
and produce confusing partial failures. `--no-lock` overrides; `--dry-run`
never takes the lock.

### Per-Package Retries, Timeouts, and Backoff

Each package is upgraded individually. On failure it retries up to `--retries N`
times with exponential backoff (1s, 2s, 4s…), and on timeout (`--timeout`,
default 600s) it is recorded as a failure rather than stalling the run. Errors
that will fail identically every time — "no available formula", "is not
installed", a cask that needs a password — are not retried at all.

Upgrades get `/dev/null` on stdin, so a cask that demands an interactive sudo
password fails immediately with a clear error instead of hanging until the
timeout.

### Nothing Fatal That Shouldn't Be

A failed `brew update` warns and continues against cached metadata. A failed
`brew cleanup` warns after the upgrades have already succeeded. A failed
prefetch is advisory — `brew upgrade` just fetches the file itself. Only a
genuinely unrecoverable condition (no brew, unreadable `brew outdated`, lock
held, not enough disk) exits 1.

### Disk Space Check

Before upgrading, free space on the Homebrew prefix is checked. A run that
cannot possibly fit its queued downloads is refused up front (exit 1); a tight
one warns and proceeds.

### Interactive Selection

`-i` presents the numbered table and accepts selections like `1,3,5-7`, `all`,
or `none`. Selecting implies consent — no second confirmation prompt.

### Pin Awareness

Reads `brew list --pinned` and automatically skips pinned formulae. If the
pinned-package query fails, the run continues without pin protection.

### Config File

`~/.brewmasterrc.json` supplies defaults for any of `skip`, `only`, `greedy`,
`notify`, `backup`, `jobs`, `retries`, `timeout`, `log_json`, `no_cleanup`,
`no_prefetch`, `color`, and `ascii`. Command-line flags override it; unknown
or mistyped keys warn and are ignored; `--no-config` skips the file entirely.

```json
{
  "skip": ["python@*", "node"],
  "jobs": 8,
  "log_json": true
}
```

### Bundle Backup with Pruning

`--backup` runs `brew bundle dump` before any upgrades, saving to
`~/.brewmaster_backup_YYYYMMDD_HHMMSS.Brewfile` (mode 0600) and pruning to the
5 newest snapshots. A failed dump warns and writes nothing.

Restore with: `brew bundle install --file=~/.brewmaster_backup_<timestamp>.Brewfile`

### Security Hardening

- `brew` is resolved once to an absolute path; a warning is printed if it lives
  outside `/opt/homebrew/bin` or `/usr/local/bin` (PATH-hijack detection).
- Package names are validated against brew's naming alphabet before reaching
  any subprocess.
- The log, history, lock, and backup files are all created mode `0600`.
- Notification text is escaped before reaching `osascript`.
- Subprocesses get no inherited stdin.

### Audit Log and JSON History

*Every* subprocess call — not only upgrades — writes an `AUDIT:` line with the
exact shell-quoted command, its exit code, and its duration to
`~/.brewmaster.log`. The log rotates at 2 MB, keeping 3 generations, all at
mode 0600.

With `--log-json`, each run also appends one structured record (upgraded,
failures, skipped, elapsed, bytes downloaded, space freed, exit code) to
`~/.brewmaster_history.jsonl`, trimmed to the newest 500 runs. `--history`
renders those records as a table. `--json` prints the same record for the
current run to stdout, with the human UI redirected to stderr so the two never
mix.

### Clean Interrupts and Cron Safety

Ctrl-C or SIGTERM mid-upgrade prints "N upgraded, N failed, N not attempted",
cancels pending downloads, and exits 130. In a non-TTY session (cron, launchd)
without `-y`, the tool exits 1 immediately instead of hanging on the prompt.

### macOS Notifications

`--notify` sends a native notification on completion via `osascript`, reporting
the number upgraded or failed. Silently skipped off macOS.

## Files

| Path | Purpose |
| --- | --- |
| `~/.brewmaster.log` | Timestamped run log with per-command AUDIT lines (mode 0600, rotates at 2 MB × 3) |
| `~/.brewmaster_history.jsonl` | One JSON record per run when `--log-json` is set (newest 500 kept) |
| `~/.brewmaster.lock` | Single-instance `flock` held for the duration of a run |
| `~/.brewmasterrc.json` | Optional defaults for command-line flags |
| `~/.brewmaster_backup_*.Brewfile` | Bundle snapshots from `--backup` (5 newest kept) |

## Requirements

- Python 3.10+, standard library only
- Homebrew installed and available as `brew` in `PATH`
- macOS (notifications require `osascript`; the lock requires a POSIX `flock`)
- `brew bundle` tap for `--backup` (included with Homebrew by default)
