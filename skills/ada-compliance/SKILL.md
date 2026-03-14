---
name: ada-check
description: >
  Use this skill when the user asks to check PDF accessibility, ADA compliance,
  Section 508 compliance, PDF/UA compliance, populate PDF metadata, make a PDF accessible,
  fix PDF metadata, run an accessibility audit, check alt text, verify heading hierarchy,
  or discusses PDF accessibility requirements and WCAG compliance for PDFs.
argument-hint: <path-to-pdf-or-folder>
allowed-tools: Read, Bash, Glob, Grep, Write, Edit, Agent
---

# ADA PDF Accessibility Compliance Skill

You are helping the user make their PDFs ADA-compliant by analyzing them for missing
accessibility metadata and fixing what can be fixed programmatically.

## Scripts Location

The scripts are bundled with this skill at:
- Analysis: `${CLAUDE_SKILL_DIR}/scripts/pdf_accessibility_audit.py`
- Fix (Preview-compatible): `${CLAUDE_SKILL_DIR}/scripts/pdf_metadata_fix.py`
- Structure tree (pikepdf, NOT Preview-compatible): `${CLAUDE_SKILL_DIR}/scripts/pdf_structure_generator.py`

**Required:** `pypdf` — `pip install pypdf`
**Optional:** `pikepdf` — `pip install pikepdf` (enables structure tree generation for untagged PDFs)

## Workflow

### 1. Determine Input

The user's argument is: $ARGUMENTS

- If a single PDF path is provided, process that file.
- If a folder path is provided, glob for all `*.pdf` files and process each.
- If no argument is provided, ask the user which PDF(s) to check.

### 2. Run the Audit Script

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/pdf_accessibility_audit.py" "<pdf_path>" 2>/dev/null
```

Parse the JSON output.

### 3. Determine Fixes

Build a fixes JSON object:

**Metadata (always auto-fixable):**
- `title`: If missing or looks like a filename, read page 1 visually and infer a meaningful title.
- `author`: If missing, ask the user or leave blank.
- `subject`: If missing, infer from content.
- `language`: If missing, default to `"en-US"`.
- `display_doc_title`: Set to `true`.
- `set_tagged`: Set to `true` if structure tree exists.
- `set_pdfua`: Set to `true`.

**Bookmarks (always auto-fixable):**
- `generate_bookmarks`: Set to `true` if no bookmarks exist and document has more than 1 page.

**Link descriptions (Claude generates):**
- If audit reports non-descriptive links, look at the `non_descriptive_links` array.
- For each link, read the surrounding page content and generate descriptive text.
- Build a `link_descriptions` dict mapping `"pageNum_linkIndex"` to description string.
- Example: `{"2_0": "YouTube: Technical Due Process lecture", "7_0": "DHS AI use case inventory"}`

**Alt text (Claude generates):**
- If figures missing alt text, read affected pages visually.
- Generate concise alt text for each image.
- Add to `alt_texts` dict mapping figure index to text.

### 4. Check for Untagged PDFs — User Choice

If the audit reports `structure.has_structure_tree == false`, the PDF has no structure tree.
This is the single most important accessibility feature — without it, screen readers
get unstructured text with no headings, lists, or figure descriptions.

**Present this choice to the user:**

> This PDF has no structure tree (the most important feature for screen readers).
>
> **Option A — Preview-compatible** *(recommended if you have Adobe Acrobat Pro)*
> I'll auto-fix: title, subject, language, bookmarks, link descriptions, PDF/UA flag.
> You then run: Acrobat > Accessibility > Autotag Document to add the structure tree.
> ✅ Opens everywhere including macOS Preview.
>
> **Option B — Maximum automation** *(requires pikepdf)*
> I'll auto-fix everything above PLUS generate a structure tree with headings.
> ⚠️ The output will NOT render in macOS Preview (pages appear blank).
> ✅ Opens fine in web browsers (Chrome, Safari, Brave, Edge) and Adobe Acrobat.
>
> Which approach?

**If user is unsure:** Recommend Option A if they have Acrobat Pro access.
Recommend Option B if they don't have Acrobat Pro and primarily use browsers.

### 5. Apply Fixes

#### Path A: Preview-Compatible (pypdf only)

Write the fixes JSON to a temp file, then run:
```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/pdf_metadata_fix.py" "<pdf_path>" "<fixes_json_path>" 2>/dev/null
```

Clean up the temp fixes JSON.

The output `_accessible.pdf` will have metadata, bookmarks, link descriptions, and PDF/UA
identifier — but NO structure tree. The checklist should include manual Acrobat steps.

#### Path B: Maximum Automation (pikepdf)

1. Check if pikepdf is available:
   ```bash
   python3 -c "import pikepdf; print('available')" 2>/dev/null
   ```

2. **If pikepdf IS available:**
   Write the fixes JSON to a temp file, then run the structure tree generator
   with the fixes included (single-pass pipeline — all changes via pikepdf):
   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/pdf_structure_generator.py" "<pdf_path>" "<output_accessible.pdf>" "<fixes_json_path>" 2>/dev/null
   ```
   This generates the structure tree, bookmarks, and applies all metadata fixes
   in a single operation. Do NOT run `pdf_metadata_fix.py` afterward — the
   pikepdf output should not be re-processed by pypdf (this corrupts the file).

3. **If pikepdf is NOT available:**
   Tell the user: "pikepdf is not installed. Run `pip install pikepdf` to enable
   structure tree generation, or switch to Option A."

### 6. Present Results Inline

Show a structured checklist. Adapt based on which path was used:

#### Path A Checklist:
```markdown
## Auto-Fixed
- [x] Document title set to "<title>"
- [x] Language set to en-US
- [x] Display title enabled
- [x] PDF/UA identifier added
- [x] Bookmarks generated for N pages
- [x] Descriptive text added to N links

## Needs Manual Fix (Acrobat Pro)
- [ ] **Structure tree** — Open in Acrobat Pro > Accessibility > Autotag Document
- [ ] **Heading hierarchy** — After autotagging, verify H1/H2/H3 levels match slide structure
- [ ] **Figure alt text** — After autotagging, add alt text to each Figure in the Tags panel
      (suggested alt text provided below)

## Needs Human Review
- [ ] Review alt text accuracy for each image
- [ ] Check reading order on multi-column slides

Saved: `filename_accessible.pdf`
✅ Opens in Preview, browsers, and all PDF viewers.
```

#### Path B Checklist:
```markdown
## Auto-Fixed
- [x] Document title set to "<title>"
- [x] Language set to en-US
- [x] Display title enabled
- [x] PDF/UA identifier added
- [x] Bookmarks generated for N pages
- [x] Descriptive text added to N links
- [x] Structure tree generated (N elements)

## Needs Human Review
- [ ] Verify heading hierarchy matches slide structure (heuristic-based)
- [ ] Review alt text accuracy for each image
- [ ] Check reading order on multi-column slides

Saved: `filename_accessible.pdf`
⚠️ Note: This file may not render correctly in macOS Preview (pages appear blank).
   It opens normally in web browsers and Adobe Acrobat.
```

After showing the checklist, ask:
> Want me to save this checklist as a file? (markdown / spreadsheet)

### 7. Export Options

If user asks to save:
- **Markdown**: Write `filename_remediation.md` with full checklist, page numbers, Acrobat instructions
- **Spreadsheet**: Create .xlsx with columns: Page, Issue Type, Description, Fix Instruction, Status

### 8. Batch Mode

When processing a folder:
1. Audit all PDFs
2. Show summary table:
   ```
   | File | Pages | Pass | Warn | Fail | Has Tags | Figures No Alt |
   |------|-------|------|------|------|----------|----------------|
   ```
3. Ask: "Fix all files, or select specific ones?"
4. Ask Path A or B (applies to all selected files)
5. Process selected files
6. Show per-file results

## Compliance Reference

See `${CLAUDE_SKILL_DIR}/references/compliance-checklist.md` for the full checklist.

## Important Notes

- Never overwrite the original PDF — save as `_accessible.pdf`
- When generating alt text: concise but descriptive (1-2 sentences)
- For charts/graphs: describe the data story, not just "a bar chart"
- For link descriptions: use the URL + page context to write meaningful text
- Encrypted/password-protected PDFs cannot be processed — inform the user
- **Path B warning**: Always remind the user that pikepdf output won't render in macOS Preview
- **Never run pypdf's pdf_metadata_fix.py on pikepdf output** — this corrupts the file
