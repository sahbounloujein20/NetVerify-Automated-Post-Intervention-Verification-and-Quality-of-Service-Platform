# Contributing to NetVerify

Thank you for your interest in contributing to **NetVerify**! This document provides guidelines for contributing to the project.

## Getting Started

1. **Fork** the repository on GitHub.
2. **Clone** your fork locally:
   ```bash
   git clone https://github.com/your-username/NetVerify.git
   cd NetVerify
   ```
3. Create a new **feature branch**:
   ```bash
   git checkout -b feature/your-feature-name
   ```
4. Set up your development environment following the [README.md](README.md).

## Development Workflow

### Code Style
- Follow **PEP 8** for all Python code.
- Use descriptive variable and function names (French or English, but stay consistent within a file).
- Add docstrings to all public functions and classes.

### Commit Messages
Use clear, descriptive commit messages:
```
feat: add SNR threshold configuration to audit engine
fix: correct database session leak in /mesures/rafraichir
docs: update README installation instructions
```

### Testing
Before submitting a pull request:
1. Ensure the FastAPI backend starts without errors:
   ```bash
   python -m uvicorn main:app --reload --port 8000
   ```
2. Verify the Streamlit dashboard loads correctly:
   ```bash
   streamlit run frontend/dashboard.py
   ```
3. Run the audit engine to check for regressions:
   ```bash
   python Backend/audit.py
   ```

## Pull Request Process

1. Ensure your code follows the project style guidelines.
2. Update the `README.md` if you change any setup steps or add new features.
3. Make sure your branch is up to date with `main`.
4. Open a Pull Request with a clear description of the changes.

## Reporting Issues

If you find a bug or have a feature request, please open an issue on GitHub with:
- A clear title and description.
- Steps to reproduce (for bugs).
- Expected vs. actual behavior.
- Your environment (OS, Python version, n8n version).

## Security

**Do NOT** commit `.env` files, API keys, database passwords, or JWT secrets. Use `.env.example` as a template and keep your real credentials local.
