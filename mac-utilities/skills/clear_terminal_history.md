# HistClean (`clear_terminal_history.py`)

Inspect, audit and clear shell history — carefully. Finds the history files your
shells and REPLs actually use, shows what is in them, flags entries that look
like leaked credentials, and removes entries either wholesale or one pattern at
a time, taking a compressed 0600 backup before it changes anything.

## Usage

```bash
python3 clear_terminal_history.py [OPTIONS]
```

With no action flag it opens an interactive menu, as it always has.

## Options

### Actions

| Flag | Description |
| --- | --- |
| `--list` | List the history files found, with entry counts, sizes and permissions |
| `--show` | Show the most recent entries (see `--limit`), credentials masked |
| `--stats` | Entry counts, unique ratio, date span and most-used commands |
| `--scan` | Report entries that look like leaked credentials (**exit 3** if any) |
| `--dedupe` | Remove duplicate commands, keeping the most recent occurrence |
| `--redact PATTERN [...]` | Remove entries containing these substrings (regexes with `--regex`) |
| `--redact-secrets` | Remove every entry `--scan` would flag |
| `--clear` | Empty the selected history files |
| `--fix-perms` | Set `0600` on any history file other users can read |
| `--backups` | List the backups taken before previous changes |
| `--restore [ARCHIVE]` | Restore a backup (prompts when no archive is named) |

### Targets

| Flag | Default | Description |
| --- | --- | --- |
| `--files LABEL [...]` | see below | `zsh`, `bash`, `fish`, `python`, `node`, `sqlite`, `psql`, `mysql`, `redis`, `irb`, `less`, or `all` |
| `--tools` | `false` | Include REPL and client histories even for destructive actions |

**Scan widely, destroy narrowly.** With no `--files`, read-only actions cover
every history file that exists — a scanner that silently skips
`~/.psql_history` is worse than useless. Actions that *delete* default to the
shells alone and say so:

```text
not touching tool histories (python, psql) — add --tools or --files to include them
```

### Safety

| Flag | Default | Description |
| --- | --- | --- |
| `-y`, `--yes` | `false` | Do not prompt for confirmation |
| `--dry-run` | `false` | Report what would change without writing anything |
| `--no-backup` | `false` | Do not take a backup before changing a file |
| `--shred` | `false` | Overwrite the bytes before clearing (read the caveat below) |

### Output

| Flag | Default | Description |
| --- | --- | --- |
| `--limit N` | `20` | How many entries or findings to display |
| `--regex` | `false` | Treat `--redact` patterns as regular expressions |
| `--show-secrets` | `false` | Print matched credentials in full instead of masking them |
| `--color {auto,always,never}` | `auto` | Colorise output |
| `--ascii` | `false` | ASCII-only output — no box drawing or emoji |
| `-q`, `--quiet` | `false` | Print only warnings and errors |
| `--json` | `false` | Emit a machine-readable report to stdout (UI goes to stderr) |
| `--version` | — | Print the version and exit |

## Exit Codes

| Code | Meaning |
| --- | --- |
| `0` | Success — nothing to do, or everything applied |
| `1` | Fatal error (unknown label, non-interactive session without `-y`, no backup to restore) |
| `2` | Run completed but one or more files could not be changed |
| `3` | `--scan` found credential-shaped entries |
| `130` | Interrupted with Ctrl-C or SIGTERM |

## Examples

```bash
# What history files exist, how big, and who can read them
python3 clear_terminal_history.py --list

# Audit every history on the machine for leaked credentials
python3 clear_terminal_history.py --scan

# ...and remove the entries it flagged, from the shells
python3 clear_terminal_history.py --redact-secrets

# Forget every command that mentions a particular token
python3 clear_terminal_history.py --redact 'ghp_abc123' --files zsh

# Regex removal: anything that exported a variable ending in _TOKEN
python3 clear_terminal_history.py --redact 'export \w+_TOKEN=' --regex

# See exactly what would go, without writing anything
python3 clear_terminal_history.py --redact aws --dry-run

# Collapse duplicate commands
python3 clear_terminal_history.py --dedupe --files zsh

# Empty zsh history, overwriting the bytes first
python3 clear_terminal_history.py --clear --files zsh --shred

# Tighten permissions on any world-readable history file
python3 clear_terminal_history.py --fix-perms

# Undo the last change
python3 clear_terminal_history.py --backups
python3 clear_terminal_history.py --restore zsh_20260912_103843.gz

# Feed an audit into something else
python3 clear_terminal_history.py --json | jq '.files[] | select(.findings | length > 0)'

# Cron-safe: no prompts, nothing interactive
python3 clear_terminal_history.py --redact-secrets -y -q
```

## Features

### It Finds the File Your Shell Actually Uses

`$HISTFILE` and `$ZDOTDIR` are honoured before the conventional paths. A tool
that clears `~/.zsh_history` while your shell writes somewhere else is worse
than useless: it reports success having deleted nothing. Covered:

| Label | Path | Format |
| --- | --- | --- |
| `zsh` | `$HISTFILE`, `$ZDOTDIR/.zsh_history`, or `~/.zsh_history` | zsh extended |
| `bash` | `$HISTFILE` or `~/.bash_history` | plain, with `#epoch` stamps |
| `fish` | `$XDG_DATA_HOME/fish/fish_history` or `~/.local/share/...` | fish record list |
| `python` `node` `sqlite` `psql` `mysql` `redis` `irb` `less` | `~/.<tool>_history` | plain |

### Removal Preserves Every Surviving Byte

Entries are parsed keeping the exact bytes they came from, and a rewrite emits
those bytes back verbatim. zsh extended timestamps, multi-line continuation
entries, and non-UTF-8 bytes all survive a redaction untouched — only the
entries you asked to remove go.

### Credential Scanning

Seventeen rules cover AWS access and secret keys, GitHub, Slack, Google,
Anthropic and OpenAI tokens, JWTs, private-key headers, passwords embedded in
URLs, `Authorization:` headers, `curl -u`, `mysql -p`, `PGPASSWORD`,
`ssh-keygen -N`, base64 payloads, and generic `SOMETHING_TOKEN=value`
assignments.

**Values are masked by default.** A tool that prints your secrets to the
terminal in order to tell you they leaked has simply leaked them again, into
your scrollback. `--show-secrets` overrides.

```text
╭─────────────────┬──────────────────┬─────────────────────────┬───────────────────────╮
│ Rule            │ When             │ Value                   │ Command               │
├─────────────────┼──────────────────┼─────────────────────────┼───────────────────────┤
│ github-token    │ 2026-08-29 22:55 │ ghp_******bb (40 chars) │ export GITHUB_TOKEN=… │
╰─────────────────┴──────────────────┴─────────────────────────┴───────────────────────╯
```

Removing the entry does not un-leak the secret — the tool says so, every time.
Rotate it.

### Backups Before Anything Destructive

Every destructive action first writes a gzipped copy to
`~/.histclean_backups/<label>_<timestamp>.gz` (mode 0600, in a 0700 directory),
keeping the 10 newest per file. If the backup cannot be taken, the change is
skipped rather than done blind. `--restore` puts a backup back byte-for-byte,
backing up the current state first. `--no-backup` opts out.

### It Tells You About the Shell That Will Undo Your Work

The failure everyone hits: clear the file, close the terminal, and the history
is back — because the exiting shell wrote its in-memory copy over the top.
After any content change the tool says so and gives the incantation per shell:

```text
⚠ Shells already running still hold their history in memory.
  any open session will write its copy back over the file when it exits
  zsh — drop the in-memory list in each open session:  HISTSIZE=0; HISTSIZE=10000
  bash — drop the in-memory list in each open session:  history -c
  surest route: close every other terminal first
```

### Permission Auditing

History files are private by definition. `--list` flags any that others can
read and `--fix-perms` sets them to `0600`.

### Honest About Shredding

`--shred` overwrites the file's bytes with random data before truncating. On
APFS — or any SSD — copy-on-write and wear levelling mean the old blocks may
still exist. The tool says exactly that rather than promising an erase it
cannot deliver. For a real guarantee, use FileVault and rotate the credential.

### Graphical Output That Degrades

Box-drawn tables and panels, a spinner while scanning, colour, and correct
column arithmetic (emoji and CJK are double-width; combining marks are
zero-width), so borders line up whatever a command contains. A non-TTY,
`NO_COLOR`, `TERM=dumb` or a non-UTF-8 stream each drop what they must and
nothing else; `--color`, `--ascii` and `--quiet` force the decision.

### Interactive Menu

Running with no flags opens the menu, as before — now covering every action,
with a selectable target set, previews before every removal, and `y/N`
confirmation (or typing `yes` in full, for `--clear`).

### Audit Log

Every change writes a timestamped line to `~/.histclean.log` (mode 0600,
rotating at 1 MB, 2 generations) recording what was backed up, what was
removed, and what failed.

## Files

| Path | Purpose |
| --- | --- |
| `~/.histclean.log` | Timestamped log of every run (mode 0600, rotates at 1 MB × 2) |
| `~/.histclean_backups/` | Gzipped backups taken before each change (dir 0700, files 0600) |

## Requirements

- Python 3.10+, standard library only
- macOS or any POSIX system (paths and defaults are tuned for macOS)
