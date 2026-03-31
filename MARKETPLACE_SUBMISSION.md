# Claude Plugin Marketplace Submission

## Plugin Name

ada-pdf-compliance

## Short Description (one line)

Audit and fix PDF accessibility for ADA/Section 508/PDF-UA compliance — auto-generates alt text, link descriptions, structure trees, bookmarks, and metadata.

## Full Description

**ada-pdf-compliance** makes PDFs accessible to people with disabilities. Point it at a PDF (or a folder of PDFs) and it audits every ADA/Section 508/PDF-UA compliance requirement, then auto-fixes everything it can — no manual Acrobat work required for most issues.

The plugin uses Claude's vision to read every page and generate alt text for images and descriptive text for links. It sets document language, title, author, and subject metadata. It generates bookmarks for navigation. For untagged PDFs (the norm for Google Slides and PowerPoint exports), it can generate a full structure tree with headings, paragraphs, lists, figures, and tables — the single most important feature screen readers need.

### Key Features

- **Comprehensive audit**: Checks 18 accessibility requirements across three severity tiers (Critical, Important, Advisory), with clear pass/warn/fail reporting
- **AI-generated alt text**: Claude reads each page visually and writes concise, descriptive alt text for every image — charts get data descriptions, screenshots get content summaries
- **AI-generated link descriptions**: Replaces raw URLs with meaningful text based on surrounding page context (e.g., "YouTube: Technical Due Process lecture" instead of a bare URL)
- **Structure tree generation**: For untagged PDFs, generates a complete PDF/UA-compliant structure tree with semantic headings (H1 via font-size heuristics), paragraphs, bullet lists (L/LI/Lbl/LBody), tables (with TH/TD header detection), and figure tags — plus BDC/EMC marked content operators, tagged annotations, and structure-ordered tab order
- **Metadata auto-population**: Sets document title (inferred from content), language, author, subject, display-title flag, tagged-PDF flag, and PDF/UA identifier
- **Bookmark generation**: Creates page-level bookmarks from slide titles for screen reader navigation
- **Batch processing**: Process an entire folder of PDFs in one go — asks for author once, audits all files, then fixes each with full alt text and link descriptions
- **Two processing paths**: Path A uses Acrobat's Autotag for the structure tree (higher quality, universal viewer compatibility) with the plugin handling everything else; Path B is fully automated via pikepdf (no Acrobat needed)
- **Remediation worksheets**: Export results as markdown checklists or spreadsheets for compliance tracking

### Example Use Cases

1. **University compliance officer** remediating a semester's worth of lecture slides (50+ PDFs) exported from Google Slides. Run batch mode on the folder — the plugin audits everything, generates alt text for hundreds of figures, replaces raw URLs with descriptive link text, and produces accessible PDFs with structure trees and bookmarks.

2. **Faculty member** who just exported a 100-page slide deck from Google Slides and needs it ADA-compliant before posting to the course website. Run the plugin on the single file — it handles everything from metadata to alt text to bookmarks in one pass.

3. **Government agency** publishing policy documents as PDFs. The plugin audits each document against Section 508 requirements and auto-fixes metadata, link descriptions, and alt text. For documents that already have Acrobat-generated structure trees, it layers on the remaining fixes without touching the existing tags.

4. **Disability services team** reviewing incoming documents for accessibility. Use the audit-only mode to generate compliance reports across a batch of files, then selectively fix the ones that need remediation.

5. **Legal professional** preparing court filings or briefs as accessible PDFs. The plugin ensures all required metadata is set, generates bookmarks for long documents, and adds alt text to any embedded exhibits or charts.

## Category

Accessibility

## Tags

accessibility, ada, section-508, pdf, pdf-ua, wcag, compliance, alt-text, screen-reader, remediation
