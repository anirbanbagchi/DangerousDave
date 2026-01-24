# System76 (VS Code Theme)

System76 is a VS Code theme pack with **Dark** and **Light** variants built on this palette:

- Base: `#574f4a`
- Cyan: `#48b9c7`
- Orange: `#faa41a`
- White: `#FFFFFF`
- Green: `#26d076`
- Red/Orange: `#dc4405`

Optimized for **Python, Databricks, Spark SQL / Delta Lake, C#, SQL, CI/CD pipelines, JSON, YAML, Docker**, and data engineering workflows.

## Themes

- **System76** (Dark)
- **System76 Light**

## Install (Marketplace)

1. Install the extension **System76** from the VS Code Marketplace.
2. Command Palette → **Preferences: Color Theme** → choose **System76** or **System76 Light**.

## Local Development (macOS)

### Prereqs

- Node.js (LTS recommended)
- VS Code
- `vsce`

Install `vsce`:

```bash
npm i -g @vscode/vsce
```

### Create PNG icon from SVG

PNG is required for Marketplace.

From repo root:
```bash
brew install librsvg
rsvg-convert images/icon.svg -w 512 -h 512 -o images/icon.png
```

### Run locally
```bash
code .
```
Press F5 to launch the Extension Development Host.

### Scope tuning notes

#### Spark SQL / Delta Lake keywords (MERGE, OPTIMIZE, ZORDER, VACUUM, etc.)

VS Code themes can only style token scopes produced by your SQL grammar/extension.
This theme includes a dedicated rule for common Spark/Databricks/Delta scopes. If your extension doesn’t emit those scopes, the keywords still use the general SQL keyword style.

#### CI/CD YAML

Includes rules targeting common scopes for:
- GitHub Actions YAML
- Azure DevOps / Azure Pipelines YAML

Token scopes vary by YAML extension; these rules are additive and safe.

## Quick test + package
```bash
npm i -g @vscode/vsce
code .
# Press F5 to test in Extension Development Host
vsce package
```
## Package & Publish (vsce)
Login:
```
vsce login <PublisherID>
```
Package:
```
vsce package
```
Publish:
```
vsce publish
```

## Recommended Settings
```json
{
  "editor.semanticHighlighting.enabled": true,
  "editor.bracketPairColorization.enabled": true,
  "editor.renderWhitespace": "selection"
}
```

## Contributing
Feedback and contributions are welcome! If you find issues or have suggestions for improvements:

- Report issues or suggest features
- Test the theme with different file types
- Share screenshots of any highlighting problems
- Suggest color palette adjustments

## License
MIT License - Feel free to use, modify, and distribute this theme.
