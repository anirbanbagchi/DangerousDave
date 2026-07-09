# 🎓 claude-skills

A local collection of **Agent Skills** — reusable, model-invoked capability packages that extend Claude with domain expertise, scripts, and reference material.

Each skill is a folder containing a `SKILL.md` (instructions + YAML frontmatter) and optionally supporting scripts, templates, references, and assets. Claude reads the frontmatter `description` to decide *when* to load a skill, then pulls the body into context on demand.

> Most of these are skills published by Anthropic (from [anthropics/skills](https://github.com/anthropics/skills) and the Claude Code bundle), vendored here for local use. `mac-utilities/` is first-party. See [`SOURCE.md`](SOURCE.md) for provenance and drift detection, and [Licensing](#-licensing) — not all of them carry the same terms.

---

## 📚 Skills Included

### This Repo

| Skill | What it does | Notable contents |
| --- | --- | --- |
| [`mac-utilities/`](mac-utilities/) | Drives this repo's macOS maintenance CLIs — BrewMaster, PakMan, `all_python`, and friends. Encodes their exit-code contract and safety invariants. | Points at [`../mac-utilities/skills/`](../mac-utilities/skills/) |

### Document & File Formats

| Skill | What it does | Notable contents |
| --- | --- | --- |
| [`docx/`](docx/) | Create, read, edit, and manipulate Word documents. Tracked changes, comments, find-and-replace, images, TOCs. | `scripts/` |
| [`pdf/`](pdf/) | Read/extract text and tables, merge, split, rotate, watermark, fill forms, encrypt, OCR. | `scripts/`, `reference.md`, `forms.md` |
| [`pptx/`](pptx/) | Build and edit slide decks — layouts, templates, speaker notes, comments. | `scripts/`, `pptxgenjs.md`, `editing.md` |
| [`xlsx/`](xlsx/) | Open, edit, and create spreadsheets (`.xlsx`, `.xlsm`, `.csv`, `.tsv`); formulas, formatting, charts, data cleaning. | `scripts/recalc.py` |

### Design & Visual

| Skill | What it does | Notable contents |
| --- | --- | --- |
| [`algorithmic-art/`](algorithmic-art/) | Generative art with p5.js — seeded randomness, flow fields, particle systems, interactive parameter exploration. | `templates/` |
| [`canvas-design/`](canvas-design/) | Static visual art as `.png` / `.pdf` — posters, layouts, design-philosophy-driven composition. | `canvas-fonts/` |
| [`brand-guidelines/`](brand-guidelines/) | Applies Anthropic's official brand colors and typography to artifacts. | — |
| [`theme-factory/`](theme-factory/) | 10 preset themes (colors + fonts) applicable to slides, docs, and HTML, or generate a theme on the fly. | `themes/`, `theme-showcase.pdf` |
| [`frontend-design/`](frontend-design/) | Production-grade frontend interfaces that avoid generic AI aesthetics. | — |
| [`web-artifacts-builder/`](web-artifacts-builder/) | Multi-component HTML artifacts with React, Tailwind, and shadcn/ui. | `scripts/` |
| [`slack-gif-creator/`](slack-gif-creator/) | Animated GIFs sized and validated for Slack's constraints. | `core/`, `requirements.txt` |

### Engineering & Agents

| Skill | What it does | Notable contents |
| --- | --- | --- |
| [`claude-api/`](claude-api/) | Build, debug, optimize, and migrate Claude API / Anthropic SDK apps. Covers prompt caching, tool use, thinking, batch, and Managed Agents. | Per-language guides (`python/`, `typescript/`, `go/`, `java/`, `ruby/`, `php/`, `csharp/`, `curl/`) + `shared/` deep-dives |
| [`mcp-builder/`](mcp-builder/) | Author high-quality MCP servers in Python (FastMCP) or Node/TypeScript (MCP SDK). | `scripts/`, `reference/` |
| [`skill-creator/`](skill-creator/) | Create, edit, evaluate, and benchmark skills — including description tuning for better trigger accuracy. | `scripts/`, `agents/`, `eval-viewer/`, `references/` |
| [`webapp-testing/`](webapp-testing/) | Drive and test local web apps with Playwright — screenshots, browser logs, UI debugging. | `scripts/`, `examples/` |

### Writing & Communication

| Skill | What it does | Notable contents |
| --- | --- | --- |
| [`doc-coauthoring/`](doc-coauthoring/) | Structured workflow for co-authoring docs, proposals, specs, and decision records. | — |
| [`internal-comms/`](internal-comms/) | Status reports, leadership updates, newsletters, FAQs, incident reports. | `examples/` |

---

## 🚀 Usage

Skills are **model-invoked**: you don't call them explicitly. Claude matches your request against each skill's `description` and loads the relevant one automatically. Asking *"turn this data into a spreadsheet"* is enough to trigger `xlsx`.

Claude Code discovers skills in two places:

| Scope | Location | Available in |
| --- | --- | --- |
| Personal | `~/.claude/skills/<name>/SKILL.md` | Every project |
| Project | `<repo>/.claude/skills/<name>/SKILL.md` | That repo (commit to share with the team) |

Nothing in this folder is active as-is — `claude-skills/` is a staging area, not a discovery path. Link or copy the skills you want:

```bash
# Install every skill for your user, as symlinks (edits here stay live)
mkdir -p ~/.claude/skills
for d in claude-skills/*/; do
  ln -sfn "$(pwd)/${d%/}" ~/.claude/skills/"$(basename "$d")"
done

# Or install a single skill into the current project
mkdir -p .claude/skills
cp -R claude-skills/pdf .claude/skills/
```

Then confirm they registered:

```bash
claude
> /help          # skills appear in the available-skills list
```

To use one, just describe the task:

```text
> Merge these three PDFs and add page numbers
> Build me an MCP server that wraps the GitHub issues API
> Write a 3P update for the Q3 migration project
```

### Runtime dependencies

Skills declare their own tooling. Install only what the skills you use need:

```bash
pip install pillow imageio imageio-ffmpeg numpy   # slack-gif-creator (see its requirements.txt)
pip install pytesseract pdf2image                 # pdf — OCR paths only
npm install -g docx pptxgenjs                     # docx, pptx — document generation
npx playwright install                            # webapp-testing
```

`slack-gif-creator` pins exact versions in [`slack-gif-creator/requirements.txt`](slack-gif-creator/requirements.txt).

---

## 🛠️ Adding or Modifying a Skill

Use [`skill-creator/`](skill-creator/) — it's the skill for authoring skills. It scaffolds the structure, validates frontmatter, packages the result, and can run evals to measure whether the description actually triggers when it should.

```text
> Create a skill that generates Terraform modules from a spec
> My xlsx skill isn't triggering on CSV requests — improve its description
```

The minimum viable skill is one file:

```markdown
---
name: my-skill
description: What it does, and the specific cues that should trigger it.
---

# My Skill

Instructions for Claude go here.
```

Keep `description` precise about *when to use* and *when not to* — that string is the only thing Claude sees before deciding to load the skill, so vague descriptions cause both misfires and misses.

---

## 📜 Licensing

**The vendored skills are not covered by this repository's MIT license.** Terms vary per skill, and each folder ships its own `LICENSE.txt`.

| Terms | Skills |
| --- | --- |
| **MIT** (this repo) | `mac-utilities` |
| **Apache-2.0** | `algorithmic-art`, `brand-guidelines`, `canvas-design`, `claude-api`, `frontend-design`, `internal-comms`, `mcp-builder`, `skill-creator`, `slack-gif-creator`, `theme-factory`, `web-artifacts-builder`, `webapp-testing` |
| **Anthropic proprietary** — governed by your agreement with Anthropic regarding use of Anthropic's services | `docx`, `pdf`, `pptx`, `xlsx` |
| **No license file included** | `doc-coauthoring` |

Read the `LICENSE.txt` in a skill's folder before redistributing or reusing it.

---

## 🔗 References

- [Agent Skills documentation](https://docs.claude.com/en/docs/claude-code/skills)
- [anthropics/skills](https://github.com/anthropics/skills) — upstream source
- [Model Context Protocol](https://modelcontextprotocol.io) — relevant to `mcp-builder`
