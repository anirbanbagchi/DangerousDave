<!--
PR comment format for DangerousDave.

Fill in every section. Delete a section only if it genuinely does not apply —
an empty "Risks" section is a claim that there are none, so make it deliberately.

Two rules that matter more than the structure:
  1. Anything needing a human decision before merge goes in Risks, marked ⚠️,
     never in a footnote. Licensing, security, and unrecoverable gaps qualify.
  2. Back claims with commands a reviewer can re-run. If something could not be
     verified or recovered, say "unknown" — do not guess.
-->

## <title: what this PR does, one line>

<!-- One sentence of framing. What changed, and why it exists. -->

### What's in here

<!-- Key facts at a glance: counts, new files, validation status. Keep it short. -->

| | |
| --- | --- |
| **Scope** | |
| **New files** | |
| **Validation** | |

### Changes

<!-- One bullet per file or file group: what it does, and why. -->

- **`path/to/file`** —

### ⚠️ Risks — needs a look before merge

<!--
Anything a reviewer must consciously decide on, not just notice. Examples:
  - Licensing that differs from the repo's LICENSE
  - Security-relevant changes, new subprocess calls, relaxed validation
  - Known gaps that cannot be fixed after the fact
  - Breaking changes to a documented interface (e.g. exit codes)

If there are none, write "None." and mean it.
-->

### Known gaps

<!-- Things left unresolved on purpose, and what would resolve them. Omit if none. -->

### Verification

<!-- Commands a reviewer can paste and run. Then a prose line on what else was checked and found clean. -->

```bash

```

### Notes for reviewers

<!--
Caveats, deliberate non-changes, and follow-ups. Call out anything that could
otherwise read as an oversight — e.g. "left as-is, upstream's call", or
"file X should be gitignored before merge".
-->

-
