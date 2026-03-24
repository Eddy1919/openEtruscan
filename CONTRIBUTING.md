# Contributing to OpenEtruscan

Thank you for your interest in contributing! Whether you're an epigrapher adding data, a linguist correcting a mapping, or a developer improving the engine — every contribution matters.

## Getting Started

```bash
# Fork and clone
git clone https://github.com/YOUR_USERNAME/openEtruscan.git
cd openEtruscan

# Install in development mode
pip install -e ".[dev]"

# Run the test suite
pytest

# Run the linter
ruff check src/ tests/
```

> **Note:** You do not need a database to contribute. By default, OpenEtruscan runs entirely offline with a local SQLite database.

## Ways to Contribute

### 📝 Add Inscription Data

We accept contributions through CSV bulk imports or CLI registration.

#### Option 1: CLI Registration (Single Inscriptions)

If you have a single new inscription finding:

1. Fork and clone this repository
2. Register the inscription:
   ```bash
   openetruscan register "ET_Vc_1.1" --text "larθal" --classification funerary --findspot "Volterra"
   ```
3. Attach an image if available:
   ```bash
   openetruscan upload-image --id "ET_Vc_1.1" --file photo.jpg --description "Front view"
   ```
4. Open a Pull Request

#### Option 2: Bulk CSV Import

1. Fork this repository
2. Create a CSV file in `data/contributions/` with your data:
   ```csv
   id,text,findspot,date_approx,medium,object_type,source,notes
   YOUR_001,"arnθal velchas","Cerveteri",-350,tufa,urn,"Your Name 2026",""
   ```
3. Run validation: `openetruscan validate data/contributions/your_file.csv`
4. Open a Pull Request with a brief description of your source

### 🔤 Improve Transliteration Mappings

The YAML adapter files in `src/openetruscan/adapters/` define transliteration mappings. If you find a missing variant or incorrect mapping:

1. Edit the relevant `.yaml` file
2. Add a test case in `tests/` proving the fix
3. Run `pytest` to verify
4. Open a Pull Request

### 🌍 Add a New Language

OpenEtruscan's engine is language-agnostic. To add support for another ancient script:

1. Copy `src/openetruscan/adapters/etruscan.yaml` as a template
2. Fill in your language's alphabet, Unicode ranges, and equivalence classes
3. Add onomastic patterns if applicable
4. Add test cases in `tests/`
5. Open a Pull Request

See the existing [Oscan](src/openetruscan/adapters/oscan.yaml) and [Faliscan](src/openetruscan/adapters/faliscan.yaml) adapters for reference.

### 🐛 Report Bugs

[Open an issue](https://github.com/Eddy1919/openEtruscan/issues/new?template=bug_report.md) with:
- What you expected to happen
- What actually happened
- The input text that caused the issue
- Your Python version and OS

### 💡 Request Features

[Open a feature request](https://github.com/Eddy1919/openEtruscan/issues/new?template=feature_request.md) describing:
- The problem you're trying to solve
- How you envision the solution
- Any relevant academic references

### 💻 Improve the Code

1. Check the [open issues](https://github.com/Eddy1919/openEtruscan/issues) for something that interests you
2. Comment on the issue to claim it
3. Fork, implement, test, and open a PR

## Development Workflow

### Branch Strategy

- `main` is the production branch (auto-deploys to [openetruscan.com](https://openetruscan.com))
- Create feature branches from `main`: `feature/your-feature-name`
- Open Pull Requests against `main`

### Code Standards

- **Linter:** [Ruff](https://docs.astral.sh/ruff/) — run `ruff check src/ tests/` before submitting
- **Tests:** [pytest](https://docs.pytest.org/) — all PRs must pass the existing test suite
- **Line length:** 100 characters max
- **Python:** 3.10+ compatible

### Pull Request Checklist

Before submitting a PR, confirm:

- [ ] All tests pass: `pytest`
- [ ] Linter is clean: `ruff check src/ tests/`
- [ ] Security scan passes: `bandit -r src/openetruscan/`
- [ ] New features include test cases
- [ ] Documentation is updated if applicable

### CI Pipeline

Every PR triggers:
1. **SAST** — Bandit security scan (`bandit -r src/openetruscan/`)
2. **Lint** — Ruff checks across all Python files
3. **Test** — pytest on Python 3.10, 3.11, 3.12, and 3.13
4. **Coverage** — pytest-cov on Python 3.12

## Data Licensing

- **Code contributions** are MIT-licensed (matching the project)
- **Data contributions** are CC0 (public domain) — inscriptions are facts, not copyrightable content

## Security

If you discover a security vulnerability, please report it responsibly.
See [SECURITY.md](SECURITY.md) for instructions. **Do not open a public issue for security vulnerabilities.**

## Code of Conduct

Be kind. Be constructive. Remember that some contributors are archaeologists who have never used Git, and some are developers who don't read Etruscan. Both are essential.

We follow a simple principle: **treat every contributor with the same respect you'd give a colleague presenting a paper at a conference.** Disagreements about transliteration conventions are welcome; personal attacks are not.
