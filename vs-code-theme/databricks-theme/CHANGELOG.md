# Changelog

All notable changes to the Databricks theme are documented here. This project
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-08-15

### Added

- **Databricks Light** (`vs`) and **Databricks Dark** (`vs-dark`), both derived
  from the Databricks brand palette (Lava, Navy, Oat).
- 614 explicitly-set workbench colour keys per variant — editor, activity bar,
  side bar, lists, tabs, editor groups, status bar, title bar, panel, terminal
  (all 16 ANSI slots), debug, inputs, buttons, badges, notifications, quick
  input, peek view, merge/diff, git decorations, breadcrumbs, minimap,
  settings, keybinding labels, charts and notebooks. Both variants define the
  same key set.
- 47 TextMate `tokenColors` rules and 27 `semanticTokenColors` entries, with
  `semanticHighlighting` enabled.
- Language-specific attention for Python (decorators, f-string placeholders,
  `self`), SQL (DML/DDL keywords vs. functions), Scala, R, YAML (anchors and
  aliases), JSON, and Markdown.
- Navy status bar in both variants, Lava reserved for focus, cursor, active
  indicators, badges, progress and errors.
- `palette.json` — every colour the themes use, in one swappable file.
- `scripts/check-contrast.mjs` — WCAG contrast audit (315 pairs per variant),
  duplicate-key detection, and a light/dark key-parity check.
