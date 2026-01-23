# Python Light (VS Code Theme)

**Python Light** is a crisp light theme with deep purple UI chrome and high-contrast editor colors tuned for:

- **Python** (apps, libs, notebooks)
- **SQL** (including Databricks SQL)
- **Jupyter / .ipynb** workflows
- **CI/CD** configs (GitHub Actions, Azure DevOps, GitLab CI)
- **JSON / YAML / TOML** configuration-heavy projects

Primary palette used throughout:

- Deep Purple: `#3F0E40`
- Purple: `#350D36`
- Blue (keywords/functions): `#1164A3`
- Green (strings/success): `#2BAC76`
- Magenta/Red (numbers/errors/decorators): `#CD2553`
- White: `#FFFFFF`

---

## Screenshots

> Add screenshots to make the Marketplace listing pop:
- `images/python.png`
- `images/sql.png`
- `images/yaml.png`
- `images/notebook.png`

Tip: In VS Code, open Command Palette → **Developer: Generate Color Theme From Current Settings** (optional) and/or just take screenshots.

---

## Install (Marketplace)

1. Open VS Code
2. Extensions view → search **Python Light**
3. Install → Command Palette → **Preferences: Color Theme** → select **Python Light**

---

## Install (Local / VSIX)

### Option A — Install from a `.vsix` file (recommended)
1. Package the extension:
   ```bash
   npm install -g @vscode/vsce
   vsce package
   ```
2.	Install it into VS Code:
- VS Code → Extensions panel → ... → Install from VSIX…
- Or via CLI:
   ```bash
   code --install-extension python-light-0.1.0.vsix
   ```

### Option B — Use as an unpacked local extension (dev workflow)
1.	Copy the folder to your VS Code extensions directory:
   ```bash
   mkdir -p ~/.vscode/extensions
   cp -R python-light ~/.vscode/extensions/python-light
   ```
2. Restart VS Code
3.	Pick the theme:
	•	Command Palette → Preferences: Color Theme → Python Light

---

## Recommended settings (optional)

These make the theme feel extra sharp:
```json
{
  "editor.semanticHighlighting.enabled": "configuredByTheme",
  "editor.renderWhitespace": "selection",
  "editor.bracketPairColorization.enabled": true,
  "editor.guides.bracketPairs": true,
  "workbench.colorTheme": "Python Light"
}
```

### Semantic highlighting is enabled in the theme and works best with the setting above.
### See VS Code semantic highlighting docs.

Design goals
- Readable in notebooks: strong foreground contrast on white, subtle highlights.
- SQL legibility: bold blue keywords, magenta numbers, green strings.
- Config-first projects: clear YAML/JSON keys vs values, minimal visual noise.
- Databricks-friendly: clean colors for code and diffs; clear git decorations.

---

## Contributing

PRs welcome:
- Improve TextMate scope coverage (Python, SQL, YAML, JSON, Markdown)
- Add more semantic token rules for language servers
- Add screenshots and real-world examples
