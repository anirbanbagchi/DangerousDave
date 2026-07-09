# Vendoring Provenance

Most skills in this directory are **vendored copies of Anthropic's published Agent Skills**. They are not authored here. This file records where they came from so they can be audited, diffed, and re-synced.

**Exception — first-party skills.** The following are authored in this repository, are not vendored, and are covered by the repo's MIT license:

| Skill | Origin |
| --- | --- |
| [`mac-utilities/`](mac-utilities/) | First-party. Wraps the CLIs in [`../mac-utilities/`](../mac-utilities/). |

Everything else below is upstream.

| Field | Value |
| --- | --- |
| Upstream | [anthropics/skills](https://github.com/anthropics/skills) |
| Upstream commit | ⚠️ **Not recorded at vendoring time — unknown** |
| Vendored on | Unknown; file mtimes read `2026-05-03` |
| Recorded on | 2026-07-09 |
| Local modifications | None known — never diffed against upstream |

> **The commit SHA is genuinely unknown.** These files were copied in without provenance, and there is no way to recover the exact upstream revision after the fact. The digests below were captured on 2026-07-09 to establish a baseline: they cannot tell you *which* upstream version this is, but they will tell you whether anything changes locally from here on.
>
> **Fix this on the next sync.** Re-vendor from a known commit and fill in the SHA above.

---

## Content Digests

Captured 2026-07-09. Each digest is the SHA-256 of the sorted per-file SHA-256 list for that skill, truncated to 12 characters. `.DS_Store` is excluded.

| Skill | Files | Digest |
| --- | --- | --- |
| `algorithmic-art` | 4 | `43297863b51a` |
| `brand-guidelines` | 2 | `119059e23149` |
| `canvas-design` | 83 | `d997e69065d9` |
| `claude-api` | 41 | `1b5da852423f` |
| `doc-coauthoring` | 1 | `74adad7f4f8d` |
| `docx` | 61 | `e3dfba0b0013` |
| `frontend-design` | 2 | `5cfd911484ff` |
| `internal-comms` | 6 | `2f2b1f6337a5` |
| `mcp-builder` | 10 | `086ffd304525` |
| `pdf` | 12 | `bac2d32dce3c` |
| `pptx` | 59 | `ef55c1b89314` |
| `skill-creator` | 18 | `235299c5752f` |
| `slack-gif-creator` | 7 | `4226e63adbdb` |
| `theme-factory` | 13 | `030b6262cb7c` |
| `web-artifacts-builder` | 5 | `0db42c9c3c6c` |
| `webapp-testing` | 6 | `b520caf9b375` |
| `xlsx` | 54 | `561d9acdad4e` |

### Verify nothing has drifted

```bash
cd claude-skills
for d in */; do n="${d%/}"
  h=$(find "$n" -type f ! -name '.DS_Store' -exec shasum -a 256 {} \; \
      | sort -k2 | shasum -a 256 | cut -c1-12)
  printf "%-24s %s\n" "$n" "$h"
done
```

Compare against the table. A mismatch means the skill was edited locally — intentionally or not.

---

## Re-syncing from upstream

```bash
git clone --depth 1 https://github.com/anthropics/skills /tmp/upstream-skills
git -C /tmp/upstream-skills rev-parse HEAD    # ← record this in the table above

# Diff a single skill before overwriting
diff -ru claude-skills/pdf /tmp/upstream-skills/document-skills/pdf
```

Upstream reorganizes directories periodically, so paths may not map one-to-one. Diff before replacing, and update the digest table afterward.

---

## Policy

**Do not edit these files in place.** Local edits fork you from upstream with no rebase path, and the digest table above is the only thing that would reveal it. If a skill needs different behavior:

1. Prefer opening an issue or PR upstream.
2. If it must be local, copy it under a new, clearly first-party name (as `mac-utilities/` is) rather than shadowing the upstream one.

The digest table covers vendored skills only. First-party skills are tracked by git like any other source file and are expected to change.

### Known upstream issues

- **`doc-coauthoring` ships no `LICENSE.txt`** and omits the `license` key from its frontmatter, unlike all 16 sibling skills. Its terms are therefore undetermined. Worth reporting upstream.
- **`docx/SKILL.md` is 590 lines**, exceeding the "keep SKILL.md under 500 lines" guidance that `skill-creator/SKILL.md` itself sets. Cosmetic; upstream's call.

Both were verified on 2026-07-09. All 17 skills pass `python3 skill-creator/scripts/quick_validate.py <skill>`.

---

## Licensing

Terms vary per skill and are **not** this repository's MIT license. See the [Licensing section of the README](README.md#-licensing) for the per-skill breakdown, and each skill's own `LICENSE.txt`.
