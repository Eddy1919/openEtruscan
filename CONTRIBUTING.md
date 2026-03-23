# Contributing to OpenEtruscan

Thank you for your interest in contributing! Whether you're an epigrapher adding data, a linguist correcting a mapping, or a developer improving the engine — every contribution matters.

## Ways to Contribute

### 📝 Add Inscription Data

We accept contributions through CSV bulk imports or CLI registration.

#### Option 1: CLI Registration (Single Inscriptions)

If you have a single new inscription finding, use the CLI locally:

1. Fork and clone this repository.
2. Setup your local Environment (optional): see `.env.example`.
3. Register the inscription:
   ```bash
   openetruscan register "ET_Vc_1.1" --text "larθal" --classification funerary --findspot "Volterra"
   ```
4. Attach an image if available:
   ```bash
   openetruscan upload-image --id "ET_Vc_1.1" --file photo.jpg --description "Front view"
   ```
5. Open a Pull Request with your `.db` updates or CSV export if working disconnected.

#### Option 2: Bulk CSV Import

1. Fork this repository.
2. Create a CSV file in `data/contributions/` with your data:
   ```csv
   id,text,findspot,date_approx,medium,object_type,source,notes
   YOUR_001,"arnθal velchas","Cerveteri",-350,tufa,urn,"Your Name 2026",""
   ```
3. Run validation: `openetruscan validate data/contributions/your_file.csv`
4. Open a Pull Request with a brief description of your source.

### 🔤 Improve Mappings

The YAML adapter files in `src/openetruscan/adapters/` define transliteration mappings. If you find a missing variant or incorrect mapping:

1. Edit the relevant `.yaml` file
2. Add a test case in `tests/` proving the fix
3. Open a Pull Request

### 🌍 Add a New Language

1. Copy `src/openetruscan/adapters/etruscan.yaml` as a template
2. Fill in your language's alphabet, Unicode ranges, and equivalence classes
3. Add onomastic patterns if applicable
4. Add test cases
5. Open a Pull Request

### 🐛 Report Bugs

Open an issue with:
- What you expected to happen
- What actually happened
- The input text that caused the issue
- Your Python version and OS

### 💻 Improve the Code

```bash
git clone https://github.com/open-etruscan/openetruscan.git
cd openetruscan
pip install -e ".[dev]"
pytest
```

We use [Ruff](https://docs.astral.sh/ruff/) for linting. Run `ruff check .` before submitting.

## Data Licensing

- **Code contributions** are MIT-licensed (matching the project)
- **Data contributions** are CC0 (public domain) — inscriptions are facts, not copyrightable content

## Code of Conduct

Be kind. Be constructive. Remember that some contributors are archaeologists who have never used Git, and some are developers who don't read Etruscan. Both are essential.
