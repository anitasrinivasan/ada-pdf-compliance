# ADA PDF Compliance

A [Claude Code](https://docs.anthropic.com/en/docs/claude-code) plugin that analyzes and fixes PDF accessibility for ADA/Section 508/PDF-UA compliance.

Point it at a PDF (or folder of PDFs) and it auto-fixes what it can: document title, author, subject, language, bookmarks, link descriptions, PDF/UA flags, and optionally structure trees for untagged PDFs.

## Install

### Option 1: Plugin Marketplace (recommended)

In Claude Code, run:

```
/plugin marketplace add https://github.com/anitasrinivasan/ada-pdf-compliance.git
/plugin install ada-pdf-compliance
```

### Option 2: Local Install

```bash
git clone https://github.com/anitasrinivasan/ada-pdf-compliance.git
claude --plugin-dir ./ada-pdf-compliance
```

### Python Dependency

```bash
pip install pypdf
```

## Usage

In Claude Code, run:

```
/ada-pdf-compliance:ada-check path/to/document.pdf
```

Or point it at a folder to batch-process:

```
/ada-pdf-compliance:ada-check path/to/folder/
```

You can also just describe what you want:

> "Make this PDF ADA compliant"
> "Check the accessibility of my slides"
> "Fix the metadata on all PDFs in this folder"

## What It Does

### Audit

Runs a comprehensive accessibility audit checking:

- Document title, author, subject
- Language declaration
- Tagged PDF flag and PDF/UA identifier
- Structure tree (headings, lists, figures)
- Alt text on images
- Descriptive link text
- Bookmarks/outline for navigation
- Font embedding
- Reading order

### Auto-Fix

Generates a fixes plan and applies it:

| Feature | Auto-Fixed? |
|---------|------------|
| Document title | Yes (inferred from content) |
| Author / Subject | Yes (with user input) |
| Language | Yes (defaults to en-US) |
| Display doc title | Yes |
| PDF/UA identifier | Yes |
| Bookmarks | Yes (from page titles) |
| Link descriptions | Yes (Claude generates from context) |
| Alt text | Yes (Claude describes images) |
| Structure tree | Optional (see below) |

### Two Processing Paths

When a PDF has no structure tree (common with Google Slides exports), you're offered a choice:

**Path A -- Acrobat + plugin (default)** -- You first run Acrobat Pro's Autotag to generate a structure tree, then provide the tagged file back. The plugin applies all remaining fixes (metadata, bookmarks, link descriptions, alt text, PDF/UA flag) on top of Acrobat's structure tree. Output opens everywhere including macOS Preview.

**Path B -- Maximum automation (opt-in)** -- Uses `pikepdf` to generate a structure tree automatically along with all other fixes. Output works in browsers and Acrobat but not macOS Preview.

## Requirements

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code)
- Python 3.8+
- `pypdf` (required): `pip install pypdf`
- `pikepdf` (optional, for Path B): `pip install pikepdf`

## Example Output (Path A)

```
## Auto-Fixed
- [x] Structure tree (Acrobat Autotag)
- [x] Document title set to "Spring 2026 Class 2: Technical Due Process"
- [x] Language set to en-US
- [x] Tagged PDF flag set
- [x] Display title enabled
- [x] PDF/UA identifier added
- [x] Bookmarks generated for 101 pages
- [x] Descriptive text added to 7 links
- [x] Alt text added to 12 figures

## Needs Human Review
- [ ] Verify heading hierarchy matches document structure
- [ ] Review alt text accuracy for each image
- [ ] Check reading order on multi-column slides

Saved: document_accessible.pdf
```

## License

MIT
