# 🤝 Contributing to DangerousDave

Thanks for your interest in contributing to **mac_utilities** or other **projects** in the repository! 🎉  
This repository is a collection of **small, safety-first, script-oriented utilities** focused on clarity, visibility, and defensive operations.

Contributions are welcome—whether that’s:
- Bug fixes
- New utilities
- Improvements to existing scripts
- Documentation enhancements
- Ideas and discussions

---

## 🧭 Guiding Principles

When contributing, please align with the core philosophy of this repo:

### ✅ Safety First
- No destructive actions by default
- Always prefer **confirmation prompts**
- Clearly warn users about global/system-level changes

### 🔍 Transparency
- Show what the script will do *before* it does it
- Prefer readable output over silent execution
- Log actions when appropriate

### 🧩 Simplicity
- One script = one clear responsibility
- Avoid unnecessary abstractions
- Prefer standard library over third‑party dependencies

---

## 🛠 How to Contribute

### 1️⃣ Fork & Clone

```bash
git clone https://github.com/anirbanbagchi/mac_utilities.git
cd mac_utilities
```

### 2️⃣ Create a Branch

```bash
git checkout -b feature/my-improvement
```

Use descriptive branch names:
- `fix/…`
- `feature/…`
- `docs/…`
- `refactor/…`

---

### 3️⃣ Make Your Changes

Please ensure:
- Scripts run with **Python 3.x**
- No destructive defaults
- Errors are handled gracefully
- Output is human-readable

If adding a new script:
- Use a clear, descriptive filename
- Add usage instructions to the Wiki or README
- Include safety notes and limitations

---

### 4️⃣ Test Locally

Before submitting:
- Run the script manually
- Test edge cases (empty input, missing files, permissions)
- Test on macOS if the script is macOS-specific

---

### 5️⃣ Commit Guidelines

Write clear, concise commit messages:

```text
Add dry-run mode to PakMan
Fix PATH shadow detection edge case
Improve BrewMaster summary output
Docs: add usage examples for paths.py
```

---

### 6️⃣ Open a Pull Request

When opening a PR:
- Describe **what** changed and **why**
- Mention any safety implications
- Reference related issues (if any)
- Include screenshots or output samples when helpful

---

## 🧪 Coding Style

- Python 3.x compatible
- Prefer explicit code over clever code
- Use meaningful variable names
- Add comments where behavior may be surprising
- Avoid global side effects

Type hints are welcome but not required.

---

## 📖 Documentation Contributions

Docs matter a lot in this repo ❤️

You can contribute by:
- Improving README/Wiki clarity
- Adding examples
- Fixing typos or inconsistencies
- Suggesting better workflows

---

## 💡 Ideas & Discussions

Not ready to code yet? No problem.

Feel free to:
- Open an issue with an idea
- Suggest a new utility
- Propose refactors or design changes

Discussion before implementation is encouraged.

---

## ⚠️ Disclaimer

All contributions should assume:
- Scripts may be run on real machines
- Mistakes can have real consequences

Please think defensively and err on the side of caution.

---

## 📜 License

By contributing, you agree that your contributions will be licensed under the **MIT License**, consistent with the rest of the project.

---

Thanks again for contributing!  
Your effort helps keep these utilities **useful, safe, and trustworthy** 🙌
