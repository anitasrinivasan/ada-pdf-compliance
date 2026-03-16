# ADA PDF Compliance

A [Claude Code](https://docs.anthropic.com/en/docs/claude-code) plugin that analyzes and fixes PDF accessibility for ADA/Section 508/PDF-UA compliance.

## The Problem

Public institutions -- universities, government agencies, courts -- are required by law to make their digital documents accessible to people with disabilities. For PDFs, this means complying with:

- **Section 508** of the Rehabilitation Act -- requires WCAG 2.0 Level AA conformance for all electronic documents published by federally funded organizations
- **ADA Title II** -- requires state and local governments (including public universities) to make their services accessible, which courts have interpreted to include digital documents
- **PDF/UA (ISO 14289)** -- the technical standard defining what an "accessible PDF" actually looks like at the file format level

In practice, most PDFs exported from Google Slides, PowerPoint, or Word are **not compliant**. They're missing critical accessibility metadata that screen readers need: no document language set, no structure tree (so headings and lists are invisible to assistive tech), no alt text on images, raw URLs instead of descriptive link text, no bookmarks for navigation.

Fixing these issues manually in Adobe Acrobat is tedious and error-prone -- especially for course materials where faculty may need to remediate dozens of slide decks per semester.

## What Compliance Requires

A fully ADA-compliant PDF needs all of the following:

| Requirement | Why It Matters | Status Without This Plugin |
|-------------|---------------|---------------------------|
| **Document language** (`/Lang`) | Screen readers need to know which language to use for pronunciation | Usually missing |
| **Tagged PDF** with structure tree | Defines headings, paragraphs, lists, figures -- the semantic structure screen readers navigate by | Missing on most Google Slides/PPT exports |
| **Meaningful document title** | Displayed in browser tabs and announced by screen readers (instead of a filename) | Often just the filename |
| **Display title enabled** | PDF viewer shows the title bar, not the filename | Almost never set |
| **Alt text on all images** | Screen readers read this aloud to describe images to blind users | Almost never present |
| **Embedded fonts** | Ensures text renders correctly on all systems | Usually fine, but not always |
| **Heading hierarchy** (H1 > H2 > H3) | Screen reader users navigate by headings -- skipped levels are confusing | Requires structure tree first |
| **Descriptive link text** | "DHS AI use case inventory" instead of "https://www.dhs.gov/ai/..." | Almost never set |
| **Bookmarks** for long documents | Screen reader users use bookmarks to jump between sections | Missing on exports |
| **PDF/UA identifier** | Declares the PDF claims compliance with the PDF/UA standard | Never set on exports |
| **Table headers** marked as `<TH>` | Screen readers announce column/row headers when navigating tables | Requires structure tree |

## How This Plugin Solves It

Point it at a PDF (or folder of PDFs) and it **audits** every compliance requirement above, then **auto-fixes** everything it can:

```
/ada-pdf-compliance:ada-check path/to/slides.pdf
```

### What gets auto-fixed (no human input needed)

- Document title (inferred from page 1 content)
- Document language (defaults to `en-US`)
- Display title flag
- PDF/UA identifier in XMP metadata
- Tagged PDF flag
- Bookmarks generated from page titles (101 bookmarks for a 102-page slide deck)

### What Claude generates (AI-assisted)

- **Alt text** for every image -- Claude reads each page visually and writes concise descriptions
- **Link descriptions** -- Claude reads the surrounding page context and the URL to generate meaningful text (e.g., "YouTube: Technical Due Process lecture" instead of a raw URL)
- **Document subject** -- inferred from the content

### What requires Adobe Acrobat (manual step)

- **Structure tree** -- the most important accessibility feature. For untagged PDFs (most Google Slides exports), the structure tree defines all headings, lists, figures, and reading order. Acrobat Pro's Autotag does this well. The plugin can also generate one automatically via pikepdf (see Path B below).

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

Single file:

```
/ada-pdf-compliance:ada-check path/to/document.pdf
```

Batch-process a folder:

```
/ada-pdf-compliance:ada-check path/to/folder/
```

Or just describe what you want:

> "Make this PDF ADA compliant"
> "Check the accessibility of my slides"
> "Fix the metadata on all PDFs in this folder"

## Two Processing Paths

When a PDF has no structure tree (common with Google Slides exports), you're offered a choice:

**Path A -- Acrobat + plugin (default)** -- You first run Acrobat Pro's Autotag to generate a structure tree, then provide the tagged file back. The plugin applies all remaining fixes (metadata, bookmarks, link descriptions, alt text, PDF/UA flag) on top of Acrobat's structure tree. Output opens everywhere including macOS Preview.

**Path B -- Maximum automation (opt-in)** -- Uses `pikepdf` to generate a complete structure tree automatically: headings (H1-H4) via font-size heuristics, paragraphs, bullet lists with proper Lbl/LBody structure, tables with TH/TD header detection via x-position clustering, and `/Figure` tags for images (with smart filtering to exclude logos, icons, and decorative borders). Also applies all metadata fixes in a single pass. Output works in browsers and Acrobat but not macOS Preview.

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

## Compliance Reference

The full compliance checklist (18 checks across Critical, Important, and Advisory tiers) is bundled at `skills/ada-compliance/references/compliance-checklist.md`, including remediation instructions for each issue type.

## License

MIT
