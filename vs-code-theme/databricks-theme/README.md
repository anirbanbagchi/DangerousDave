# Databricks (VS Code Theme)

A two-variant VS Code colour theme built strictly from the Databricks brand
palette — **Databricks Light** (the default) and **Databricks Dark**.

Seven syntax hues spread evenly around the colour wheel, so code reads as
colour rather than as one long stretch of grey — while Lava stays the accent
and never becomes the wallpaper. Lava is reserved for focus borders, the active
tab indicator, the cursor, badges, progress bars and errors, and nothing else
is allowed into those roles (`scripts/check-contrast.mjs` enforces it). The
status bar is Navy 800 in *both* variants, so the theme reads as Databricks at
a glance whichever variant you are in.

## Screenshots

![Light](https://raw.githubusercontent.com/anirbanbagchi/DangerousDave/main/vs-code-theme/databricks-theme/images/light.png)

![Dark](https://raw.githubusercontent.com/anirbanbagchi/DangerousDave/main/vs-code-theme/databricks-theme/images/dark.png)

## Install

### From a local checkout (development)

```bash
git clone https://github.com/anirbanbagchi/DangerousDave.git
code DangerousDave/vs-code-theme/databricks-theme
```

Press `F5` to launch an Extension Development Host, then
**Preferences → Theme → Color Theme** and pick `Databricks Light` or
`Databricks Dark`.

### As a VSIX

A packaged build is checked in at
[`dist/databricks-theme-0.2.0.vsix`](dist/databricks-theme-0.2.0.vsix):

```bash
code --install-extension dist/databricks-theme-0.2.0.vsix
```

To rebuild it:

```bash
npm i -g @vscode/vsce
cd vs-code-theme/databricks-theme
vsce package --out dist/databricks-theme-0.2.0.vsix
```

The extension ID is `anirbanbagchi.databricks-theme`, matching the other themes
in this repository. Change `publisher` in `package.json` if you are packaging
under a different Marketplace publisher.

### Settings

```jsonc
{
  "workbench.colorTheme": "Databricks Light",
  // The theme ships semantic highlighting on; this is the default.
  "editor.semanticHighlighting.enabled": true,
  "editor.bracketPairColorization.enabled": true
}
```

## Palette

Every colour lives in [`palette.json`](palette.json) so the whole theme can be
re-tuned in one place.

### Brand colours

| Token | Hex | Role |
| --- | --- | --- |
| Lava 600 | `#FF3621` | Primary brand accent |
| Navy 800 | `#1B3139` | Secondary / dark surfaces, status bar |
| Navy 900 | `#0B2026` | Deepest surface (dark editor background) |
| Oat Light | `#F9F7F4` | Light editor background |
| Oat Medium | `#EEEDE9` | Light secondary surface |
| White | `#FFFFFF` | Light elevated surface |

### Derived ramps

Six colours are not enough for a theme. These steps are extrapolated from the
brand colours — they are **not** officially published Databricks values.

| Ramp | Steps |
| --- | --- |
| Lava | `#FFE9E5` · `#FFB4A6` · `#FF8A76` · `#FF6A52` · **`#FF3621`** · `#D62B18` · `#A62011` · `#75160B` |
| Navy | `#EDF1F2` · `#D6DFE2` · `#B4C2C7` · `#8DA1A9` · `#67808A` · `#4A636E` · `#33505A` · **`#1B3139`** · `#122B33` · **`#0B2026`** |
| Oat | **`#FFFFFF`** · **`#F9F7F4`** · **`#EEEDE9`** · `#DBD7CE` · `#C4BFB3` |

### Supporting hues

Seven hues, spread around the wheel so adjacent tokens never land in the same
wedge. Lava sits alone at hue ~7 at full chroma; **no supporting hue is allowed
into the warm-red wedge**, which is how the accent stays the accent while
everything else gets more colourful. The same semantic role keeps the same hue
family in both variants — only lightness shifts.

| Hue | ~Angle | Light | Dark | Deep (light surfaces) |
| --- | --- | --- | --- | --- |
| Amber | 37° | `#9A5E00` | `#F0AE4A` | `#6B4100` |
| Green | 92° | `#3A7A00` | `#A5D24A` | `#2A5800` |
| Teal | 168° | `#0A7A5E` | `#45C99A` | `#075843` |
| Cyan | 192° | `#0B7B93` | `#4FC3DD` | `#08596B` |
| Blue | 223° | `#1D5FD1` | `#7FA8FF` | `#0F4A9E` |
| Purple | 265° | `#6A3FC0` | `#B98CFF` | `#4A2A8C` |
| Magenta | 318° | `#B01E8E` | `#F07FD0` | `#7D1463` |

The **Deep** column is used in the light variant wherever a hue sits on the Oat
Medium side bar or panel instead of the Oat Light editor background — several
base hues clear 4.5:1 on one and not the other. In the dark variant the base
hues clear both, so Deep mirrors the base.

## Surfaces

| Surface | Light | Dark |
| --- | --- | --- |
| Editor background | `#F9F7F4` | `#0B2026` |
| Side bar / activity bar / panel | `#EEEDE9` | `#122B33` |
| Widgets, hovers, dropdowns | `#FFFFFF` | `#1B3139` |
| Foreground | `#1B3139` | `#D6DFE2` |
| Comments | `#4A636E` (Navy 600) | `#8DA1A9` (Navy 400) |
| Decorative borders | `#DBD7CE` (Oat Dark) | `#33505A` (Navy 700) |
| Functional borders (inputs, focus) | `#67808A` / `#FF3621` | `#67808A` / `#FF3621` |
| Status bar | `#1B3139` on `#F9F7F4` text | `#1B3139` on `#F9F7F4` text |

## Token philosophy

| Role | Hue |
| --- | --- |
| Strings, inserted diff lines | Green |
| Numbers, constants, enum members, attributes | Amber |
| Keywords, control flow, storage, `self`/`this`, YAML anchors, SQL keywords | Purple |
| Functions, methods | Blue |
| Types, classes, interfaces, enums, structs, namespaces, escapes, regex | Teal |
| Properties, object keys, JSON/YAML keys, tags, parameters *(italic)* | Cyan |
| Variables, shell variables, references | Magenta |
| Decorators, Markdown headings, invalid, deleted diff lines | Lava |
| Operators, punctuation, comments *(italic)* | Navy |

Operators, punctuation and comments stay Navy on purpose: they are the page's
structure, not its content, and colouring them fights the seven hues that carry
meaning. Loudness runs inversely to frequency — the most common tokens are the
quietest.

The same mapping drives the 33 `symbolIcon.*` colours, so the suggest widget
and outline view match the code they describe.

Bracket-pair colorization cycles **Lava → Blue → Teal → Purple → Green →
Amber**. Terminal ANSI maps all 16 slots, with `red` → Lava, `magenta` →
Magenta and `cyan` → Cyan.

Language details that get explicit treatment: Python decorators (Lava) and
f-string placeholders (Teal), SQL DML/DDL keywords (Purple) vs. SQL functions
(Blue) vs. table and database names (Cyan), YAML anchors and aliases (bold
Purple) vs. YAML keys (Cyan), JSON keys (Cyan), Scala declarations, R
functions, shell variables (Magenta), and the full Markdown set.

## Accessibility

The bar this theme holds itself to:

- Normal-weight text on its own background — **≥ 4.5:1**. That includes
  comments, dimmed text, every syntax token, and the terminal's chromatic ANSI
  slots.
- Meaningful borders, focus rings, indicators and icons — **≥ 3:1**.
- Errors and warnings never differ by hue alone: errors additionally carry a
  background tint (`editorError.background`) and a border, warnings carry a
  border only, and the two sit in different overview-ruler lanes.

Verify it yourself:

```bash
node scripts/check-contrast.mjs        # full pass/fail table
node scripts/check-contrast.mjs --fail # failures only
```

The script parses both theme files, flattens translucent layers onto their
backgrounds before measuring, checks 381 foreground/background pairs per
variant (including every symbol icon against both surfaces it is drawn on),
detects duplicate JSON keys, asserts both variants declare the same set of
workbench colour keys, and verifies the **Lava reserve** — that all 23 accent
roles come from the Lava ramp and no supporting hue has crept into them. It
exits non-zero on any failure. Current status: **381/381 pass in each variant,
0 duplicate keys, 649 keys in both, Lava reserve intact**.

The tightest passing ratios sit at 3.09:1 — brand Lava (`#FF3621`) used as an
active indicator on the Oat Medium side bar. That is above the 3:1 bar for
non-text UI, but it is the least headroom in the theme; if you need more,
switch `focusBorder` to Lava 700 (`#D62B18`).

## Repository structure

```text
databricks-theme/
├── package.json
├── README.md
├── CHANGELOG.md
├── LICENSE
├── .vscodeignore
├── palette.json
├── dist/
│   └── databricks-theme-0.2.0.vsix
├── images/
├── scripts/
│   └── check-contrast.mjs
└── themes/
    ├── databricks-light-color-theme.json
    └── databricks-dark-color-theme.json
```

## Customize

- **Comments too dim / too loud** — `editor.foreground`'s neighbour
  `tokenColors → Comment`, or the `comment` entry in `semanticTokenColors`.
- **Selection intensity** — `editor.selectionBackground`. Selection, find match
  and word highlight are all 8-digit hex, so they layer correctly over one
  another; keep the alpha channel when you change them.
- **Less Lava** — `focusBorder`, `tab.activeBorderTop`, `editorCursor.foreground`,
  `activityBar.activeBorder`, `progressBar.background`, `badge.background`.
- **Re-tune the whole theme** — edit `palette.json`, apply the same values to
  the two theme files, then re-run the contrast script.

## Deviations from the brand palette

Documented rather than hidden:

1. **Everything outside the six brand colours is derived.** The Lava, Navy and
   Oat ramps, `#122B33` (dark secondary surface), and all seven supporting hues
   (plus their Deep and Bright steps) are extrapolations. They are collected in
   `palette.json` so they can be replaced wholesale if official values are
   published.
2. **The spec asked for restrained saturation; this theme is not restrained.**
   `SPECS.md` says to "keep saturation restrained so Lava stays the loudest
   colour on screen". Both variants were deliberately made more colourful than
   that: two hues added (cyan, magenta), the original five re-saturated to the
   limit of the contrast floor, and side-bar/panel headers and list rows tinted.
   The accent rule was kept instead — Lava has *exclusive* ownership of focus,
   cursor, badges, progress, the active tab indicator and errors, and the
   contrast script fails if any other hue appears in those 23 roles. Note the
   trade: several supporting hues now have a *higher* luminance than Lava; what
   is protected is Lava's exclusivity, not its brightness.
3. **No orange.** The obvious hue for variables would have been orange, but
   orange sits next to Lava on the wheel and would compete with the accent.
   Magenta and cyan were chosen instead, keeping the entire warm-red wedge for
   Lava alone.
4. **Two Lava steps do the accent's text work.** Brand Lava on Oat Light is
   3.38:1 — fine for a cursor or a focus ring, below the bar for text. Light-mode
   error text, active line numbers and links therefore use Lava 700 (`#D62B18`),
   and Lava on the Oat Medium side bar drops to Lava 800 (`#A62011`).
5. **Buttons and badges use Lava 700, not brand Lava.** White text on `#FF3621`
   is 3.62:1; on `#D62B18` it is 4.98:1.
6. **Light-mode terminal "bright" colours go deeper, not lighter.** A lighter
   bright-green is unreadable on an Oat background, so the light variant's
   bright ANSI slots are darker, more saturated versions of their base hues.
   ANSI black/bright-black and white/bright-white are excluded from the contrast
   gate in both variants — those four slots are the extremes of the terminal's
   own palette and are low-contrast against one end of the background range by
   definition.
7. **`charts.orange` is a second Lava step.** The brand palette has exactly one
   warm hue. Rather than invent an orange, the chart series use two ends of the
   Lava ramp (`#A62011` / `#FF3621` in light, `#FF3621` / `#FFB4A6` in dark).
8. **Validation backgrounds are neutral surfaces with coloured borders.** There
   is no brand-derived pale amber or pale blue, so warning and info inputs use
   the Oat/Navy surface with a coloured border instead of an invented tint.
   Error validation does use Lava 100 (`#FFE9E5`), which is on the ramp.
9. **Decorative borders sit below 3:1 on purpose.** Oat Dark (`#DBD7CE`) is
   ~1.4:1 against Oat Light. Per WCAG 1.4.11 the 3:1 bar applies to UI
   components and meaningful state, not to decorative separators, so panel and
   tab separators keep the brand-adjacent Oat Dark while inputs, checkboxes,
   dropdowns and focus rings use Navy 500 or Lava.

## Trademark

Databricks is a trademark of Databricks, Inc. This is an unofficial,
community-built theme; it is not affiliated with, endorsed by, or sponsored by
Databricks, Inc.

## License

MIT — see [LICENSE](LICENSE).
