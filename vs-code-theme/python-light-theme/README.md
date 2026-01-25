# Python Light (VS Code Theme)
A clean, modern light theme optimized for Python development and data engineering workflows. Built with the official Python color palette (#306998 blue and #FFD43B yellow), this theme provides excellent readability and syntax highlighting for Python, SQL, Databricks, JSON, YAML, Docker, C#, Jupyter notebooks, and CI/CD configuration files.

### Features
- **Python-Optimized** : Enhanced syntax highlighting for Python keywords, decorators, magic methods, and built-in functions
- **Data Engineering Ready**: Optimized for SQL, Databricks notebooks, and data pipeline development
- **Multi-Language Support**: Excellent support for JSON, YAML, Docker, C#, and Markdown
- **CI/CD Friendly**: Clear highlighting for GitHub Actions, GitLab CI, Azure Pipelines, and other CI/CD YAML files
- **Jupyter Integration**: Beautiful syntax highlighting for Jupyter notebooks in VS Code
- **Git Integration**: Clear git decoration colors for modified, deleted, untracked, and conflicting files
- **Accessibility**: High contrast ratios for improved readability

### Color Palette
The theme uses the official Python color palette:

- **Primary Blue (#306998)**: Keywords, classes, structural elements
- **Python Yellow (#FFD43B)**: Constants, numbers, highlights, accents
- **Sky Blue (#5A9FD4)**: Strings, functions, methods, links
- **Light Yellow (#FFE873)**: Selection highlights, magic methods, special elements
- **Gray (#7F7F7F)**: Comments, punctuation, inactive elements
- **Background (#F4F4F4)**: Clean, easy-on-the-eyes light background

## Screenshot
![Python Light](https://raw.githubusercontent.com/anirbanbagchi/DangerousDave/main/vs-code-theme/python-light-theme/images/python-light.png)

## Install (Marketplace)
1. Open VS Code
2. Extensions view → search **Python Light**
3. Install → Command Palette → **Preferences: Color Theme** → select **Python Light**

## Install (Local / VSIX)
### Option A — Install from a `.vsix` file (recommended)
1. Package the extension:
   ```bash
   npm install -g @vscode/vsce
   vsce package
   ```
2. Install it into **VS Code**:
- **VS Code** → **Extensions panel** → ... → **Install from VSIX**
- Or via CLI:
   ```bash
   code --install-extension python-light-0.1.0.vsix
   ```

### Option B — Use as an unpacked local extension (dev workflow)
1. Copy the folder to your VS Code extensions directory:
    ```bash
    mkdir -p ~/.vscode/extensions
    cp -R python-light ~/.vscode/extensions/python-light
    ```
2. Restart **VS Code**
3. Pick the theme: **Command Palette** → Preferences: **Color Theme** → **Python Light**

## Customization settings (optional)
You can customize this theme further by modifying your ```settings.json```:
```json
{
  "editor.tokenColorCustomizations": {
    "[Python Light]": {
      "comments": "#7F7F7F",
      "strings": "#5A9FD4",
      "keywords": "#306998"
    }
  },
  "workbench.colorCustomizations": {
    "[Python Light]": {
      "editor.background": "#F4F4F4",
      "statusBar.background": "#306998"
    }
  }
}
```

## Recommended Settings
For the best experience with this theme, consider these VS Code settings:
```json
{
  "editor.fontSize": 14,
  "editor.lineHeight": 22,
  "editor.fontFamily": "'Fira Code', 'JetBrains Mono', 'Cascadia Code', Consolas, monospace",
  "editor.fontLigatures": true,
  "editor.cursorBlinking": "smooth",
  "editor.cursorSmoothCaretAnimation": "on",
  "editor.smoothScrolling": true,
  "editor.bracketPairColorization.enabled": true,
  "editor.guides.bracketPairs": "active",
  "workbench.tree.indent": 16,
  "terminal.integrated.fontSize": 13
}
```

## Recommended Font
This theme looks best with programming fonts that support ligatures:
- Fira Code
- JetBrains Mono
- Cascadia Code

### Semantic highlighting is enabled in the theme and works best with the setting above.
See VS Code semantic highlighting docs.

## Design goals
- Readable in notebooks: strong foreground contrast on white, subtle highlights.
- SQL legibility: bold blue keywords, magenta numbers, green strings.
- Config-first projects: clear YAML/JSON keys vs values, minimal visual noise.
- Databricks-friendly: clean colors for code and diffs; clear git decorations.

## Contributing
Feedback and contributions are welcome! If you find issues or have suggestions for improvements:
- Report issues or suggest features
- Test the theme with different file types
- Share screenshots of any highlighting problems
- Suggest color palette adjustments

## License
MIT License - Feel free to use, modify, and distribute this theme.

## Credits
- Color palette inspired by the official Python logo colors
- Designed for optimal readability and reduced eye strain
- Optimized based on feedback from Python developers and data engineers
