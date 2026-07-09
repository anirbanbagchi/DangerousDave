---
name: mac-utilities
description: "Run and reason about this repo's macOS maintenance CLIs in mac-utilities/. TRIGGER when the user wants to: upgrade or audit Homebrew packages (brewmaster.py); upgrade, roll back, or vulnerability-scan pip packages (PakMan.py); inventory or switch Python installations (all_python.py); inspect shell aliases, PATH, or disk usage; clear terminal history; or asks 'what's outdated', 'update my packages', 'which pythons do I have'. Also use when editing these scripts, so their exit codes, safety flags, and logging conventions are preserved. SKIP for general Homebrew/pip questions unrelated to these scripts, and for non-macOS package management."
---

# mac-utilities

Seven macOS maintenance CLIs living in [`mac-utilities/`](../../mac-utilities/). Two of them — BrewMaster and PakMan — are substantial tools with retry logic, rollback snapshots, audit logs, and scripting-oriented exit codes. Treat them as production utilities, not scratch scripts.

All commands below are run from the repository root.

## Full reference docs

Read the relevant one before answering detailed questions about flags or behavior. Do not guess at flags — these tools have many, and several are mutually exclusive.

| Tool | Reference |
| --- | --- |
| BrewMaster | [`mac-utilities/skills/brewmaster.md`](../../mac-utilities/skills/brewmaster.md) |
| PakMan | [`mac-utilities/skills/PakMan.md`](../../mac-utilities/skills/PakMan.md) |
| all_python | [`mac-utilities/skills/all_python.md`](../../mac-utilities/skills/all_python.md) |

Man pages ship alongside as `*.py.1` and install via `mac-utilities/skills/install_man.sh`.

## The tools

| Script | Purpose |
| --- | --- |
| `brewmaster.py` | Homebrew upgrader — version diffs, parallel prefetch, per-package retries, pin awareness, bundle backup |
| `PakMan.py` | pip upgrader — batch-with-fallback, rollback snapshots, `pip check`, `pip-audit`, uv-accelerated outdated check |
| `all_python.py` | Inventory every Python install (Homebrew, pyenv, conda, system, installer); switch or remove one |
| `all_aliases.py` | Shell alias viewer |
| `paths.py` | PATH inspection and repair |
| `drive_size.py` | Disk usage reporter |
| `clear_terminal_history.py` | Clears Zsh and Bash history files |

`PakFriend.py` (installs from a requirements file, stripping version pins) and `PakGuy.py` (package list generator) also exist but have no reference doc.

## Shared conventions

Both BrewMaster and PakMan follow the same contract. Preserve it when editing either.

**Exit codes** — the whole point is cron/script friendliness:

| Code | Meaning |
| --- | --- |
| `0` | Nothing to do, or everything succeeded |
| `1` | Fatal error (tool missing, non-TTY without `-y`) |
| `2` | Completed, but one or more packages failed |
| `3` | `--check-only` found outdated packages |
| `130` | Ctrl-C |

Exit `3` is **not** an error — it signals "outdated packages exist." Scripts that treat nonzero as failure will misread it.

**Universal flags:** `-y`/`--yes` (auto-approve), `-i`/`--interactive` (numbered selection; mutually exclusive with `-y`), `--check-only`, `--dry-run`, `--notify`, `--log-json`, `--retries N` (default 2), `--timeout SECS` (default 600).

**Safety properties that must not regress:**

- Log files are created mode `0600`.
- Notification text is escaped before reaching `osascript` (AppleScript injection).
- Package names are validated before hitting any subprocess — brew's naming alphabet for BrewMaster, PEP 508 for PakMan.
- `brew` is resolved to an absolute path, with a warning if it sits outside `/opt/homebrew/bin` or `/usr/local/bin` (PATH-hijack detection).
- In a non-TTY session without `-y`, both exit `1` rather than hanging on a prompt.

**State files** (`~/.brewmaster.log`, `~/.pakman.log`, `~/.brewmaster_history.jsonl`, `~/.pakman_history.jsonl`, and the `*_backup_*.Brewfile` / `*_rollback_*.txt` snapshots) prune to the 5 newest.

## Common tasks

```bash
# What's outdated? Changes nothing. Exits 3 if anything is.
python3 mac-utilities/brewmaster.py --check-only
python3 mac-utilities/PakMan.py --check-only

# Preview exactly what would run
python3 mac-utilities/brewmaster.py --dry-run

# Full upgrade, backed up, with a notification when done
python3 mac-utilities/brewmaster.py --backup --notify -y

# Upgrade pip packages safely: wheels only, never touch global site-packages
python3 mac-utilities/PakMan.py --only-binary --require-venv -y

# Upgrade, then scan for known CVEs
python3 mac-utilities/PakMan.py -y --audit

# Inventory Python installs as JSON
python3 mac-utilities/all_python.py --json
```

## Undoing a run

This is the first thing to reach for when an upgrade breaks something.

```bash
# pip — restore the pre-upgrade snapshot
pip install -r ~/.pakman_rollback_<timestamp>.txt

# Homebrew — restore from the --backup bundle
brew bundle install --file=~/.brewmaster_backup_<timestamp>.Brewfile
```

A Homebrew rollback only exists if the run used `--backup`. PakMan writes its snapshot by default, unless `--no-rollback` was passed.

## Guidance

**Default to `--check-only` first.** When a user asks "what's outdated," they want the report, not a mutation. Never pass `-y` on the user's behalf unless they asked to actually upgrade.

**Don't suggest `--sizes` casually.** It prefetches downloads *before* the confirmation prompt, so it consumes bandwidth and disk whether or not the user then confirms.

**`--audit` is a no-op without `pip-audit` installed** — it skips with a hint rather than failing.

**These are macOS-only.** `--notify` requires `osascript`; `all_python.py` also supports Windows, the rest do not.

## When editing these scripts

- Requirements are Python 3.10+, standard library only. Adding a third-party dependency to `brewmaster.py` or `PakMan.py` would break their run-anywhere property.
- Every subprocess invocation writes an `AUDIT:` line with the exact command and exit code to the tool's log. New subprocess calls must do the same.
- The two tools deliberately share a JSON history schema family. Keep new fields consistent across both.
- After any change, verify the exit-code contract still holds — it is the documented interface, and cron jobs depend on it.
