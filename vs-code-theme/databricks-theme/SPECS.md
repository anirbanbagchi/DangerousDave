# Prompt: Build the "Databricks" VS Code Theme

Copy everything below the line into Claude Code, Cursor, or any coding agent.

---

You are a senior VS Code theme author. Build a complete, publishable VS Code color theme extension named **Databricks**, containing two variants: **Databricks Light** (the default) and **Databricks Dark**. Both must be derived strictly from the Databricks brand palette below.

## 1. Palette

These are the official brand colors. Do not substitute them.

| Token | Hex | Role |
|---|---|---|
| Lava 600 | `#FF3621` | Primary brand accent |
| Navy 800 | `#1B3139` | Secondary / dark surfaces |
| Navy 900 | `#0B2026` | Deepest surface |
| Oat Light | `#F9F7F4` | Light background |
| Oat Medium | `#EEEDE9` | Light secondary surface |
| White | `#FFFFFF` | Light elevated surface |

A theme needs more steps than six. Use this derived ramp — it is extrapolated from the brand colors, not officially published, so keep every value in one `palette.json` (or a `colors.ts` constants file) so it can be swapped in one place later.

**Lava (accent):**
`#FFE9E5` · `#FFB4A6` · `#FF8A76` · `#FF6A52` · `#FF3621` (brand) · `#D62B18` · `#A62011` · `#75160B`

**Navy (neutral spine):**
`#EDF1F2` · `#D6DFE2` · `#B4C2C7` · `#8DA1A9` · `#67808A` · `#4A636E` · `#33505A` · `#1B3139` (brand) · `#0B2026`

**Oat (light neutrals):**
`#FFFFFF` · `#F9F7F4` · `#EEEDE9` · `#DBD7CE` · `#C4BFB3`

**Supporting hues** (harmonized with the brand, used only for syntax and status; keep saturation restrained so Lava stays the loudest color on screen):

| Hue | Light-mode value | Dark-mode value |
|---|---|---|
| Blue | `#1B6FA8` | `#6FB6E0` |
| Teal | `#0B7B7B` | `#4FBFBB` |
| Green | `#0F7A52` | `#4FC08D` |
| Yellow / Amber | `#8A5A00` | `#E5A93C` |
| Purple | `#6B4FA8` | `#B396E8` |

## 2. Design rules

**Databricks Light** (`"type": "light"`)
- Editor background `#F9F7F4` (Oat Light). Sidebar, activity bar, and panel `#EEEDE9` (Oat Medium). Editor widgets, hovers, and dropdowns `#FFFFFF` for elevation.
- Foreground `#1B3139`. Comments and dimmed text from the Navy 500–600 steps.
- Borders from Oat Dark `#DBD7CE`; never pure black or pure gray.

**Databricks Dark** (`"type": "dark"`)
- Editor background `#0B2026` (Navy 900). Sidebar, activity bar, and panel `#122B33`. Editor widgets and hovers `#1B3139` (Navy 800).
- Foreground `#D6DFE2`. Comments from the Navy 400 step.
- Borders from `#33505A`.

**Both**
- Lava is the accent, not the wallpaper. Reserve it for: focus borders, the active tab's top border, the cursor, badges, active activity-bar indicator, progress bars, and errors. It should never be a large fill.
- Status bar: Navy 800 background with Oat foreground in both variants, so the theme reads as Databricks at a glance. Debugging state uses Lava.
- Selection and find-match highlights must be translucent (8-digit hex with alpha) so they layer correctly over one another.
- Bracket-pair colorization: cycle Lava → Blue → Teal → Purple → Green → Yellow.
- Terminal ANSI: map all 16 slots from the palette above, `red` → Lava.

## 3. Accessibility

Non-negotiable, and verify each one:
- All normal-weight text on its own background: contrast ratio **≥ 4.5:1**.
- Comments and disabled text: **≥ 4.5:1** as well. Do not let comments fade into the background.
- UI borders, focus rings, and icons: **≥ 3:1**.
- Never rely on hue alone to distinguish errors from warnings — differentiate by squiggle and badge placement too.

Write a small script (`scripts/check-contrast.mjs`) that parses both theme JSON files, computes WCAG contrast ratios for the foreground/background pairs above, and prints a pass/fail table. Run it and fix any failures before you finish.

## 4. Deliverables

Produce a complete extension:

```
dangerousdave
└── vs-code-theme
    └── databricks-vscode-theme/
        ├── package.json
        ├── README.md
        ├── CHANGELOG.md
        ├── LICENSE
        ├── .vscodeignore
        ├── palette.json
        ├── scripts/check-contrast.mjs
        └── themes/
            ├── databricks-light-color-theme.json
            └── databricks-dark-color-theme.json
```

`package.json` must declare `contributes.themes` with both entries, `uiTheme` set to `vs` and `vs-dark` respectively, `"engines": { "vscode": "^1.75.0" }`, `"categories": ["Themes"]`, a `publisher` placeholder, and a `galleryBanner` using Navy 800.

## 5. Coverage requirements

**Workbench `colors`** — do not leave VS Code to fall back on defaults. Explicitly set keys across at least: `editor.*` (background, foreground, lineHighlight, selection, findMatch, wordHighlight, indentGuide, bracket match, whitespace), `editorCursor.*`, `editorLineNumber.*`, `editorGutter.*`, `editorError/Warning/Info.foreground`, `editorBracketHighlight.foreground1-6`, `editorOverviewRuler.*`, `activityBar.*`, `sideBar.*`, `sideBarSectionHeader.*`, `list.*` (active/inactive/hover/focus, including `list.activeSelectionBackground`), `tab.*` (active/inactive/hover, borders, modified indicator), `editorGroup*`, `statusBar.*` (plus `statusBarItem.remote*` and debugging states), `titleBar.*`, `panel.*`, `terminal.*` including all `terminal.ansi*`, `debugToolBar.*`, `input.*`, `dropdown.*`, `button.*` (primary uses Lava; secondary uses Navy), `badge.*`, `progressBar.background`, `scrollbarSlider.*`, `notification*`, `quickInput*`, `peekView*`, `merge.*` and `diffEditor.*`, `gitDecoration.*`, `breadcrumb.*`, `minimap*`, `focusBorder`, `contrastBorder`, `selection.background`, `widget.shadow`, `settings.*`, `keybindingLabel.*`, and `charts.*`.

**`tokenColors`** — TextMate scopes covering comments, strings (and string escapes/templates), numbers/constants/booleans, keywords and control flow, storage/modifiers, operators, functions and method calls, function parameters, classes and types, interfaces and enums, variables (with `variable.other.constant` distinguished), object properties, decorators, regex, JSX/TSX tags and attributes, markup (headings, bold, italic, links, quotes, code spans), invalid/deprecated, and diff added/removed.

**`semanticTokenColors`** — set `"semanticHighlighting": true` and map at least: `namespace`, `class`, `enum`, `interface`, `struct`, `typeParameter`, `type`, `parameter`, `variable`, `variable.readonly`, `property`, `property.readonly`, `enumMember`, `function`, `function.declaration`, `method`, `macro`, `keyword`, `comment`, `string`, `number`, `operator`, `decorator`, and the `*.deprecated` modifier (struck through, dimmed).

Given Databricks' domain, make sure **Python, SQL, Scala, R, YAML, JSON, and Markdown** all look deliberate — check that SQL keywords, Python decorators and f-strings, and YAML anchors are each distinctly colored. Consistency across the two variants matters: the same semantic role should keep the same hue family in light and dark, only shifting lightness.

## 6. Finish

1. Run the contrast script; fix failures.
2. Validate both theme files parse as JSON and contain no duplicate keys.
3. Write a README with an install section, a palette table, and placeholders (`![Light](images/light.png)`) for screenshots.
4. Print a short summary of any place you deviated from the brand palette and why.

Do not add telemetry, dependencies, or build tooling beyond the contrast script. Plain JSON themes only.