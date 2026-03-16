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
- Fix (metadata-only, for pre-tagged PDFs): `${CLAUDE_SKILL_DIR}/scripts/pdf_metadata_fix.py`
- Structure tree + metadata (full automation): `${CLAUDE_SKILL_DIR}/scripts/pdf_structure_generator.py`
- Regression test: `${CLAUDE_SKILL_DIR}/scripts/regression_test.py`

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
- `author`: If missing, **always ask the user** before proceeding: "Who is the author of this
  document?" Do not leave blank or skip — author is a required accessibility metadata field.
  In batch mode, ask once and apply the same author to all files unless the user specifies otherwise.
- `subject`: If missing, infer from content.
- `language`: If missing, default to `"en-US"`.
- `display_doc_title`: Set to `true`.
- `set_tagged`: Set to `true` ONLY after confirming the PDF has a structure tree (from Acrobat Autotag or Path B). Do NOT set on an untagged PDF — it would make the audit falsely report the PDF as tagged.
- `set_pdfua`: Set to `true`.

**Bookmarks (always auto-fixable):**
- `generate_bookmarks`: Set to `true` if no bookmarks exist and document has more than 1 page.

**Link descriptions (Claude generates):**
- If audit reports non-descriptive links, look at the `non_descriptive_links` array.
- For each link, read the surrounding page content and generate descriptive text.
- Build a `link_descriptions` dict mapping `"pageNum_linkIndex"` to description string.
- Example: `{"2_0": "YouTube: Technical Due Process lecture", "7_0": "DHS AI use case inventory"}`

**Alt text (Claude generates — MANDATORY for all figures):**
- You MUST read EVERY page that contains figures and generate alt text for ALL of them.
- Do NOT skip figures or ask the user to provide alt text. This is the skill's job.
- For large documents, read pages in batches (e.g., 10-20 pages at a time) to cover all figures.
- The figure index is sequential: figure 0 is the first content image in the document,
  figure 1 is the second, etc. (after filtering out repeated logos/headers).
- Generate concise but descriptive alt text (1-2 sentences). For charts/graphs, describe
  the data story. For screenshots, describe the key content shown.
- Add to `alt_texts` dict mapping figure index (as string) to alt text string.

### 4. Check for Untagged PDFs

If the audit reports `structure.has_structure_tree == false`, the PDF has no structure tree.
This is the single most important accessibility feature — without it, screen readers
get unstructured text with no headings, lists, or figure descriptions.

**Ask the user:**

> This PDF has no structure tree (the most important feature for screen readers).
>
> **Do you have an Acrobat-tagged version of this PDF?**
> If you've already run Adobe Acrobat Pro > Accessibility > Autotag Document on this file,
> give me the tagged version and I'll apply all remaining fixes (metadata, bookmarks,
> link descriptions, alt text, PDF/UA flag) on top of Acrobat's structure tree.
>
> **If not, I'll handle everything automatically** — I'll generate a structure tree with
> headings, lists, figures, and tables, plus all metadata fixes, in one pass.
>
> Note: Acrobat's structure tree is higher quality (deeper heading hierarchy, better table
> detection, MCID-linked content). But our automated path produces a solid structure tree
> that works well for most documents, especially slide decks.

### 5. Apply Fixes

#### Path A: User Provides Acrobat-Tagged PDF

1. **Wait for the user to provide the tagged file path.** Once they do, re-run the
   audit on the tagged file to confirm the structure tree now exists:
   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/pdf_accessibility_audit.py" "<tagged_pdf_path>" 2>/dev/null
   ```
   Verify `structure.has_structure_tree == true`. If it's still false, the user may
   not have saved correctly — ask them to try again.

2. **Re-determine fixes** based on the new audit of the tagged file. Now that the
   structure tree exists, set `set_tagged: true` and generate alt text targeting the
   actual `/Figure` elements in the structure tree.

3. **Run pypdf on the tagged file:**
   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/pdf_metadata_fix.py" "<tagged_pdf_path>" "<fixes_json_path>" 2>/dev/null
   ```

   Clean up the temp fixes JSON.

   The output `_accessible.pdf` will have the Acrobat structure tree PLUS all metadata,
   bookmarks, link descriptions, and PDF/UA identifier.

#### Path B: Full Automation (pikepdf)

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
   structure tree generation, or provide an Acrobat-tagged version of the PDF."

### 6. Present Results Inline

Show a structured checklist. Adapt based on which path was used:

#### Path A Checklist:
```markdown
## Auto-Fixed
- [x] Structure tree (Acrobat Autotag)
- [x] Document title set to "<title>"
- [x] Language set to en-US
- [x] Tagged PDF flag set
- [x] Display title enabled
- [x] PDF/UA identifier added
- [x] Bookmarks generated for N pages
- [x] Descriptive text added to N links
- [x] Alt text added to N figures

## Needs Human Review
- [ ] Verify heading hierarchy matches document structure
- [ ] Review alt text accuracy for each image
- [ ] Check reading order on multi-column slides

Saved: `filename_accessible.pdf`
```

#### Path B Checklist:
```markdown
## Auto-Fixed (Acrobat Accessibility Checks)
- [x] Document title set to "<title>"
- [x] Language set to en-US
- [x] Display title enabled
- [x] PDF/UA identifier added
- [x] Bookmarks generated for N pages
- [x] Descriptive text added to N links
- [x] Structure tree generated (N elements: headings, lists, figures, tables)
- [x] Tagged content (BDC/EMC) — all page content marked with structure MCIDs
- [x] Tagged annotations — link annotations tagged as /Link structure elements
- [x] Tab order set to structure order on all pages

## Needs Human Review
- [ ] Verify heading hierarchy matches document structure (heuristic-based)
- [ ] Review alt text accuracy for each image
- [ ] Check reading order on multi-column slides

Saved: `filename_accessible.pdf`
```

After showing the checklist, ask:
> Want me to save this checklist as a file? (markdown / spreadsheet)

### 7. Export Options

If user asks to save:
- **Markdown**: Write `filename_remediation.md` with full checklist, page numbers, Acrobat instructions
- **Spreadsheet**: Create .xlsx with columns: Page, Issue Type, Description, Fix Instruction, Status

### 8. Batch Mode

When processing a folder:

**Step 1: Collect shared metadata upfront.**
Before auditing, ask the user TWO questions:
> 1. Who is the author of these documents?
> 2. Fix all files, or do you want to select specific ones after seeing the summary?

This avoids re-asking per file. Store the author for all files.

**Step 2: Audit all PDFs.**
```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/pdf_accessibility_audit.py" --summary file1.pdf file2.pdf file3.pdf 2>/dev/null
```
This outputs a JSON array of compact summaries (one Python process for all files).

Show summary table:
```
| File | Pages | Pass | Warn | Fail | Has Tags | Figures No Alt |
|------|-------|------|------|------|----------|----------------|
```

**Step 3: Process each file fully.**
For each file (or user-selected subset):
1. Run the full audit (not `--summary`) to get link and figure details
2. Read ALL pages visually to generate alt text for every figure and descriptions for every link
3. Infer title and subject from content; apply the shared author
4. Use the appropriate path (A or B) based on whether the file has a structure tree
5. **Do NOT skip alt text or link descriptions** — generate everything automatically

For Path B files (untagged), process sequentially since each needs pikepdf:
```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/pdf_structure_generator.py" "<pdf_path>" "<output_accessible.pdf>" "<fixes_json_path>" 2>/dev/null
```

For Path A files (already tagged), batch mode is available:
```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/pdf_metadata_fix.py" --batch batch_fixes.json 2>/dev/null
```
Where `batch_fixes.json` is an array of `{"input": "path.pdf", "fixes": {...}}` entries.

**Step 4: Show per-file results** with individual checklists and a final summary table.

## Compliance Reference

See `${CLAUDE_SKILL_DIR}/references/compliance-checklist.md` for the full checklist.

## Important Notes

- Never overwrite the original PDF — save as `_accessible.pdf`
- When generating alt text: concise but descriptive (1-2 sentences)
- For charts/graphs: describe the data story, not just "a bar chart"
- For link descriptions: use the URL + page context to write meaningful text
- Encrypted/password-protected PDFs cannot be processed — inform the user
- **Never run pypdf's pdf_metadata_fix.py on pikepdf output** — this corrupts the file
