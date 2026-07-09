# 🚀 DangerousDave

**DangerousDave** is a personal playground and experimental repository for building, testing, and showcasing **cool, practical, and occasionally dangerous ideas** across data engineering, automation, analytics, and tooling.

This repo is intentionally flexible: it can host **proof-of-concepts, utilities, experiments, and reusable components** that don’t yet warrant their own standalone repositories.

---

## 📌 Purpose & Philosophy

The goal of **DangerousDave** is to:

- Experiment fast without over-engineering
- Capture useful patterns before they’re forgotten
- Build things that are *practically useful*, not just theoretically interesting
- Maintain **clean structure**, **clear documentation**, and **reproducibility**

> If it’s clever, useful, or just fun-but not production-ready yet-it belongs here.

---

## 🧠 What Lives in This Repo

This repository may include (but is not limited to):

- 🔧 **Automation scripts** (Python, Bash, Zsh, etc.)
- 📊 **Data engineering utilities** (ETL helpers, Spark snippets, SQL patterns)
- ☁️ **Cloud & DevOps experiments** (AWS, Databricks, CI/CD ideas)
- 🤖 **AI & LLM prototypes** (prompting, agents, evaluations)
- 🎓 **Claude Agent Skills** (see `claude-skills/`)
- 🧪 **Proofs of concept** and exploratory code
- 🧪 **VS Code Theme**, maybe experimental
- 📝 **Notes & references** worth preserving

Each project or experiment should live in its **own clearly named folder**.

---

## 🔧 mac-utilities

macOS productivity scripts. Each tool has full docs under `mac-utilities/skills/`.

| Tool | Description |
| --- | --- |
| [`brewmaster.py`](mac-utilities/brewmaster.py) | Homebrew upgrader — version diffs, per-package retries, pin awareness, bundle backup, macOS notifications |
| [`PakMan.py`](mac-utilities/PakMan.py) | Python package upgrader — per-package retries, outdated table, freeze export, macOS notifications |
| [`all_aliases.py`](mac-utilities/all_aliases.py) | Shell alias management |
| [`all_python.py`](mac-utilities/all_python.py) | Python environment utilities |
| [`drive_size.py`](mac-utilities/drive_size.py) | Disk usage reporter |
| [`paths.py`](mac-utilities/paths.py) | PATH inspection and repair |
| [`clear_terminal_history.py`](mac-utilities/clear_terminal_history.py) | Terminal history cleaner |

### Quick start — BrewMaster

```bash
# Check what's outdated (no changes made)
python3 mac-utilities/brewmaster.py --check-only

# Full upgrade with backup and macOS notification
python3 mac-utilities/brewmaster.py --backup --notify -y
```

See [`mac-utilities/skills/brewmaster.md`](mac-utilities/skills/brewmaster.md) for all options.

---

## 🎓 claude-skills

Agent Skills that extend Claude with domain expertise, scripts, and reference material. Eighteen skills in total: seventeen vendored from [anthropics/skills](https://github.com/anthropics/skills), plus a first-party `mac-utilities` skill that drives the tools above.

Skills are model-invoked — Claude loads one automatically when your request matches its description. They are **not active where they sit**; see [`claude-skills/README.md`](claude-skills/README.md) for how to install them into `~/.claude/skills/` or `.claude/skills/`.

```bash
# Install every skill for your user, as symlinks
mkdir -p ~/.claude/skills
for d in claude-skills/*/; do
  ln -sfn "$(pwd)/${d%/}" ~/.claude/skills/"$(basename "$d")"
done
```

⚠️ **Licensing varies.** The vendored skills are *not* MIT — four carry Anthropic proprietary terms. See [`claude-skills/README.md`](claude-skills/README.md#-licensing) and [`claude-skills/SOURCE.md`](claude-skills/SOURCE.md).

---

## 📁 Recommended Repository Structure

```text
DangerousDave/
├── README.md
|   mac-utilities
│   ├── utility_name_1.py
│   ├── utility_name_2.py
|   vs-code-theme
│   ├── theme_1
│   ├── theme_2
├── claude-skills/
│   ├── README.md
│   ├── SOURCE.md          # vendoring provenance + digests
│   ├── mac-utilities/     # first-party skill
│   └── <skill-name>/
│       └── SKILL.md
├── projects/
│   ├── project-name-1/
│   │   ├── README.md
│   │   ├── src/
│   │   └── tests/
│   └── project-name-2/
│   │   ├── README.md
│   │   ├── src/
│   │   └── tests/
├── scripts/
│   ├── automation/
│   └── utilities/
├── notebooks/
│   └── experiments/
├── docs/
│   └── references/
└── .gitignore
```

---

## ▶️ Getting Started

1. Clone the repository:
   ```bash
   git clone https://github.com/anirbanbagchi/DangerousDave.git
   cd DangerousDave
   ```

2. Navigate to the project or script you’re interested in:
   ```bash
   cd projects/<project-name>
   ```

3. Follow the instructions in the relevant **Wiki**.

---

## 📜 License

MIT License - See LICENSE file for details.

**Exception:** the vendored skills under [`claude-skills/`](claude-skills/) carry their own terms (Apache-2.0 or Anthropic proprietary, depending on the skill) and are **not** MIT-licensed. See [`claude-skills/README.md`](claude-skills/README.md#-licensing).
