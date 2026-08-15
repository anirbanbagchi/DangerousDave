# DangerousDave

## PR comments and descriptions

Always follow [`.github/PULL_REQUEST_TEMPLATE.md`](../.github/PULL_REQUEST_TEMPLATE.md) when writing a PR comment or description. Read it first — the HTML comments in it carry the guidance, not just the section order.

Deliver the result as raw markdown inside a fenced block so it can be pasted straight into GitHub. Use a four-backtick outer fence when the comment itself contains triple-backtick code blocks.

Two rules matter more than the structure:

- **Risks go in the `⚠️` section, never a footnote.** Anything needing a human decision before merge — licensing, security, breaking changes to a documented interface, gaps that can't be fixed after the fact.
- **Back claims with commands a reviewer can re-run.** If something couldn't be verified or recovered, write "unknown" rather than guessing.

## claude-skills/

Skills under [`claude-skills/`](../claude-skills/) are mostly **vendored** from [anthropics/skills](https://github.com/anthropics/skills). Do not edit them in place — see [`claude-skills/SOURCE.md`](../claude-skills/SOURCE.md) for the policy, digests, and re-sync procedure. `mac-utilities/` is the one first-party skill.

Their licenses are **not** this repo's MIT: four are Anthropic proprietary, one has no license file. Check before reusing or redistributing.

## mac-utilities/

`brewmaster.py` and `PakMan.py` are production utilities with a documented interface. When editing them, preserve:

- The exit-code contract (`0` ok, `1` fatal, `2` partial failure, `3` outdated found, `130` interrupt). Exit `3` is **not** an error; cron jobs depend on this.
- Safety invariants: `0600` log files, AppleScript escaping before `osascript`, package-name validation before any subprocess, absolute-path resolution of `brew`.
- An `AUDIT:` log line, with the exact command and exit code, for every subprocess call.
- Python 3.10+, standard library only.

Full docs live in [`mac-utilities/skills/`](../mac-utilities/skills/).
