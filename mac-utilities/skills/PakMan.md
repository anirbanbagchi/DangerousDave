# PakMan

A graphical, fast, careful Python package updater built on pip: boxed tables
and a live progress bar, batch upgrades with per-package fallback, rollback
snapshots, new-versus-pre-existing dependency conflict detection, an instance
lock, and a full audit log.

## Usage

```bash
python3 PakMan.py [OPTIONS]
```

PakMan always operates on the interpreter that runs it. To update a virtualenv,
invoke it with that virtualenv's Python: `path/to/venv/bin/python PakMan.py`.

## Options

### Selection

| Flag | Default | Description |
| --- | --- | --- |
| `-y`, `--yes` | `false` | Auto-approve all upgrades without prompting |
| `-i`, `--interactive` | `false` | Pick packages from the numbered table (mutually exclusive with `-y`) |
| `--exclude PKG [PKG ...]` | — | Skip packages; case-insensitive globs (e.g. `--exclude 'boto*'`) |
| `--only PKG [PKG ...]` | — | Upgrade only these packages; case-insensitive globs |

### Behaviour

| Flag | Default | Description |
| --- | --- | --- |
| `--check-only` | `false` | List outdated packages and exit (exit 3 if any found) |
| `--dry-run` | `false` | Print commands that would run without executing them |
| `--upgrade-pip` | `false` | Upgrade pip itself first (a failure here no longer aborts the run) |
| `--pre` | `false` | Include pre-release versions when upgrading |
| `--only-binary` | `false` | Refuse source distributions (no sdist build code executes) |
| `--require-venv` | `false` | Refuse to run outside a virtual environment |
| `--audit` | `false` | Run `pip-audit` after upgrading (skipped if not installed) |
| `--no-rollback` | `false` | Skip writing the rollback snapshot file |
| `--no-batch` | `false` | Skip the batch attempt; go straight to per-package upgrades |
| `--no-lock` | `false` | Allow concurrent PakMan runs (skips the instance lock) |
| `--no-config` | `false` | Ignore `~/.pakmanrc.json` |
| `--export FILE` | — | Run `pip freeze` after upgrading and save to FILE |
| `--notify` | `false` | Send a macOS notification when the run finishes |

### Performance

| Flag | Default | Description |
| --- | --- | --- |
| `--uv` | `false` | Use uv for the installs too, not just the outdated check |
| `--no-uv` | `false` | Don't use uv at all, even if installed |
| `--jobs N` | `6` | Parallel wheel-prefetch workers (1–16) |
| `--no-prefetch` | `false` | Don't pre-download wheels in parallel |
| `--retries N` | `2` | Attempts per package before it is marked failed (min: 1) |
| `--timeout SECS` | `600` | Timeout per package (batch gets timeout × package count) |

### Output

| Flag | Default | Description |
| --- | --- | --- |
| `--color {auto,always,never}` | `auto` | Colorise output |
| `--ascii` | `false` | ASCII-only output — no box drawing or emoji |
| `-q`, `--quiet` | `false` | Print only warnings and errors |
| `-v`, `--verbose` | `false` | Stream raw pip output instead of progress indicators |
| `--json` | `false` | Output the **outdated package list** as JSON and exit |
| `--summary-json` | `false` | Print a machine-readable **run summary** to stdout when the run ends |
| `--log-json` | `false` | Append a JSON record per run to `~/.pakman_history.jsonl` |
| `--history [N]` | `15` | Show the last N recorded runs and exit |
| `--rollbacks` | `false` | List the rollback snapshots on disk and exit |
| `--version` | — | Print the version and exit |

`--json` and `--summary-json` are different things: the first dumps what is
outdated and exits without upgrading, the second reports what a completed run
did. Both move the human-readable UI to stderr so stdout stays parseable.

## Exit Codes

| Code | Meaning |
| --- | --- |
| `0` | Success — nothing to do, or all upgrades succeeded |
| `1` | Fatal error (non-TTY without `-y`, `--require-venv` outside a venv, lock held, unreadable outdated list) |
| `2` | Run completed but one or more packages failed |
| `3` | `--check-only` found outdated packages |
| `130` | Interrupted with Ctrl-C or SIGTERM |

A run that introduces new dependency conflicts still exits `0` — no package
*failed*. The conflicts are reported in the summary, the log, and the JSON
record.

## Examples

```bash
# Standard interactive upgrade
python3 PakMan.py

# Pick exactly which packages to upgrade from the numbered table
python3 PakMan.py -i

# Auto-approve, skip all boto packages, notify on completion
python3 PakMan.py -y --exclude 'boto*' --notify

# Much faster: let uv do the installs as well as the outdated check
python3 PakMan.py -y --uv

# Preview outdated packages only (exit 3 if any found)
python3 PakMan.py --check-only

# Update a specific virtualenv
~/projects/api/.venv/bin/python PakMan.py -y

# Dry run — see exactly what would run, nothing executed
python3 PakMan.py --dry-run

# Refuse to touch anything outside a venv, and refuse source builds
python3 PakMan.py --require-venv --only-binary -y

# Upgrade, then audit for known vulnerabilities and export a freeze
python3 PakMan.py -y --audit --export requirements.lock

# Cron-friendly: quiet, auto-approve, JSON history
python3 PakMan.py -y -q --log-json

# Feed the outdated list to another tool
python3 PakMan.py --json | jq -r '.[].name'

# Feed the run result to another tool
python3 PakMan.py -y --summary-json | jq '.new_conflicts'

# Review recent runs and available rollbacks
python3 PakMan.py --history 30
python3 PakMan.py --rollbacks
```

## Features

### Graphical Terminal Output

Outdated packages are rendered as a box-drawn, column-aligned table:

```text
╭───┬───────────┬─────────┬────────┬───────╮
│ # │ Package   │ Current │ Latest │ Type  │
├───┼───────────┼─────────┼────────┼───────┤
│ 1 │ idna      │ 3.3     │ 3.19   │ wheel │
│ 2 │ packaging │ 23.0    │ 26.3   │ sdist │
╰───┴───────────┴─────────┴────────┴───────╯
```

`sdist` is highlighted because a source distribution *builds on install* —
arbitrary code from the package runs on your machine. `--only-binary` refuses
them outright.

During the per-package phase a live progress bar sits at the bottom of the
terminal with a spinner, counts, and elapsed time, while finished packages
scroll above it:

```text
  ✔ flake8                       6.0.0 → 7.3.0 (1.3s)
  ✖ six                          ERROR: No matching distribution found
  ⠹ ████████████░░░░░░░░░░░░░░░░  2/6 0m 21s  packaging
```

The run ends in a summary panel with counts, the installer used, the rollback
file, and elapsed time.

Column arithmetic is done in terminal *columns*, not characters: emoji and CJK
text are double-width, and combining marks, variation selectors and joiners take
no space at all. Borders line up whatever a package name contains, and
truncation never splits a double-width character in half.

Everything degrades on its own. A non-TTY, `NO_COLOR`, `TERM=dumb`, or a
non-UTF-8 stream drops colors, the live line, or the box-drawing characters
independently — the content is never lost. `--color` and `--ascii` force the
decision, `--quiet` prints only warnings and errors, and `--verbose` streams
raw pip output instead of the progress display.

### New vs. Pre-existing Dependency Conflicts

A `pip check` baseline is taken *before* the upgrades — concurrently with the
outdated query, so it costs nothing — and compared against a `pip check` after
them. The run then reports only the conflicts **it introduced**, points at the
rollback file that undoes them, and separately notes any pre-existing conflicts
it resolved:

```text
  ✖ 1 new dependency conflict(s) introduced by this run
  ⚠ flake8 6.0.0 has requirement pycodestyle<2.11.0,>=2.10.0, but you have pycodestyle 2.14.0.
  undo with: pip install -r ~/.pakman_rollback_20260912_102004.txt
```

A conflict that was already there before you started is not reported as though
you caused it.

### Batch Upgrade with Per-Package Fallback

Everything is first attempted in a single resolver run — dramatically faster
than N runs, and the only way the resolver can satisfy packages that constrain
each other. If the batch fails, PakMan falls back to upgrading each package
individually so a single bad package cannot block the rest, and the failure is
attributed to the package that actually caused it.

### uv

When `uv` is on `PATH` it is used for the outdated check by default (it is far
faster than `pip list --outdated`). `--uv` additionally routes the *installs*
through `uv pip install`, which is typically several times faster than pip.
`--no-uv` disables it entirely.

### Pipelined Parallel Prefetch

On the per-package path, wheels are downloaded on a thread pool (`--jobs`,
default 6) *while* installs run, not merely before them. Downloads are
submitted in install order and the install loop waits only on the future for
the package it is about to install, so the download of package N+1 overlaps the
installation of package N. Skipped automatically under `--uv` (uv resolves and
downloads in parallel already, and does not read pip's cache).

### Single-Instance Lock

An `flock` on `~/.pakman.lock` refuses to start a second run while one is in
progress. Two pip processes writing the same `site-packages` is the classic way
to end up with a half-installed distribution and no way to tell which run did
it. `--no-lock` overrides; `--dry-run` never takes the lock. If the lock file
cannot be created at all, the run continues with a warning rather than
refusing.

### Per-Package Retries, Timeouts, and Backoff

Each package gets up to `--retries N` attempts with exponential backoff (1s,
2s, 4s…), and a `--timeout` (default 600s) per attempt. Errors that will fail
identically every time — "No matching distribution found", an
externally-managed environment, a read-only filesystem — are not retried at all.

### Environment Awareness

Running outside a virtualenv prints a warning naming the interpreter;
`--require-venv` turns that into a refusal (exit 1). PEP 668
externally-managed interpreters (Homebrew and system Pythons) are detected and
called out by name, because pip will refuse to install into them.

### Rollback Snapshots

Before upgrading, current versions are pinned to
`~/.pakman_rollback_YYYYMMDD_HHMMSS.txt` (mode 0600), keeping the 5 newest.
Undo any run with `pip install -r <file>`; `--rollbacks` lists what is
available. `--no-rollback` skips the snapshot.

### Vulnerability Audit and Freeze Export

`--audit` runs `pip-audit` after upgrading, detecting its absence properly via
`pip show` rather than by matching an error string. `--export FILE` writes a
`pip freeze` of the resulting environment.

### Security Hardening

- Package names are validated against PEP 508 naming rules before reaching any
  subprocess.
- The log, history, lock, and rollback files are all created mode `0600`.
- Notification text is escaped before reaching `osascript`.
- Subprocesses get no inherited stdin, and `PIP_NO_INPUT=1` is set, so pip
  never stops to ask a question there is nothing to answer with.

### Audit Log and JSON History

*Every* subprocess call — not only upgrades — writes an `AUDIT:` line with the
exact shell-quoted command, its exit code, and its duration to `~/.pakman.log`.
The log rotates at 2 MB, keeping 3 generations, all at mode 0600.

With `--log-json`, each run also appends one structured record (upgraded,
failures, excluded, conflicts, new conflicts, rollback path, installer, elapsed,
exit code) to `~/.pakman_history.jsonl`, trimmed to the newest 500 runs.
`--history` renders those records as a table.

### Config File

`~/.pakmanrc.json` supplies defaults for any of `exclude`, `only`, `pre`,
`only_binary`, `require_venv`, `audit`, `no_uv`, `uv`, `no_rollback`,
`no_batch`, `notify`, `jobs`, `retries`, `timeout`, `log_json`, `color`,
`ascii`, and `export`. Command-line flags override it; unknown or mistyped keys
warn and are ignored; `--no-config` skips the file entirely.

```json
{
  "exclude": ["boto*", "awscli"],
  "uv": true,
  "log_json": true
}
```

### Clean Interrupts and Cron Safety

Ctrl-C or SIGTERM mid-upgrade prints "N upgraded, N failed, N not attempted",
cancels pending downloads, and exits 130. In a non-TTY session (cron, launchd)
without `-y`, the tool exits 1 immediately instead of hanging on the prompt.

### macOS Notifications

`--notify` sends a native notification on completion via `osascript`, reporting
upgrades, failures, or new conflicts. Silently skipped off macOS.

## Files

| Path | Purpose |
| --- | --- |
| `~/.pakman.log` | Timestamped run log with per-command AUDIT lines (mode 0600, rotates at 2 MB × 3) |
| `~/.pakman_history.jsonl` | One JSON record per run when `--log-json` is set (newest 500 kept) |
| `~/.pakman.lock` | Single-instance `flock` held for the duration of a run |
| `~/.pakmanrc.json` | Optional defaults for command-line flags |
| `~/.pakman_rollback_*.txt` | Version snapshots (5 newest kept); restore with `pip install -r` |

## Requirements

- Python 3.10+, standard library only
- pip available as `python -m pip`
- macOS for `--notify` (`osascript`); the lock requires a POSIX `flock`
- Optional: [`uv`](https://github.com/astral-sh/uv) for the fast outdated check and `--uv` installs
- Optional: `pip-audit` for `--audit`
