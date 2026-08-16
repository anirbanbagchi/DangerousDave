# Changelog

All notable changes to the Databricks theme are documented here. This project
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] — 2026-08-16

A deliberate turn toward more colour in both variants, without giving up the
accent rule or the contrast floor.

### Added

- **Two new syntax hues, cyan and magenta**, taking the supporting palette from
  five hues to seven. The seven are spread around the wheel (amber 37, green 92,
  teal 168, cyan 192, blue 223, purple 265, magenta 318) so adjacent tokens never
  land in the same wedge. Lava sits alone at hue 7 — no supporting hue is
  allowed into the warm-red wedge.
- **A `deep` ramp** (`palette.json`), used in the light variant wherever a hue
  sits on the Oat Medium side bar or panel rather than the Oat Light editor
  background. Several base hues clear 4.5:1 on one and not the other.
- **33 `symbolIcon.*` keys**, so the suggest widget and outline view carry the
  same hues as the code they describe. Previously left to VS Code's defaults.
- **`scmGraph.foreground4`/`foreground5`**, extending the source-control graph
  to five distinguishable branch colours.
- **Lava-reserve assertion** in `scripts/check-contrast.mjs`: 23 accent roles
  (focus border, cursor, badges, progress, active tab indicator, errors, …) are
  verified to come from the Lava ramp, so "Lava is the accent, not the
  wallpaper" is machine-checked rather than asserted.

### Changed

- **Roles that used to share a hue now have their own.** Variables move off the
  plain foreground to magenta; properties, object keys, JSON/YAML keys and tags
  move off function-blue to cyan; parameters become cyan italic. Operators,
  punctuation and comments deliberately stay Navy — they are the page's
  structure, not its content.
- **All five original hues re-saturated** to the most vivid version that still
  clears the contrast floor on its background, in both variants.
- **Terminal ANSI `magenta` and `cyan` now map to magenta and cyan**, instead of
  borrowing purple and teal.
- **Side-bar and panel section headers, and selected/hovered list rows, are
  tinted** with a translucent blue wash instead of a flat neutral.
- **Inlay hints are hue-coded** — type hints teal, parameter hints cyan.
- Contrast coverage grew from 315 to 381 pairs per variant; workbench keys from
  614 to 649.

### Unchanged, on purpose

- The status bar stays Navy 800 in both variants.
- Lava keeps sole ownership of focus, cursor, badges, progress, the active tab
  indicator and errors. No new hue was allowed near those roles.
- Every text pair still clears 4.5:1, every meaningful border/icon 3:1.

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
