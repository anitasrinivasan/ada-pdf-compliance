# ADA / Section 508 / PDF-UA Compliance Checklist

## Standards Reference
- **Section 508**: Requires WCAG 2.0 Level AA conformance for electronic documents
- **PDF/UA (ISO 14289)**: Technical standard for accessible PDF structure
- **WCAG 2.1**: Web Content Accessibility Guidelines (Level AA)

---

## CRITICAL — Must Fix

| # | Check | Requirement | Auto-fixable? |
|---|-------|-------------|---------------|
| 1 | Document Language | `/Lang` must be set in document catalog | Yes |
| 2 | Tagged PDF | `/MarkInfo` `/Marked` must be `true` | Yes |
| 3 | Document Title | Must be a meaningful title (not filename) | Yes |
| 4 | Display Title | `/ViewerPreferences` `/DisplayDocTitle` = `true` | Yes |
| 5 | Figure Alt Text | All `/Figure` tags must have `/Alt` attribute | Yes (Claude generates) |
| 6 | Font Embedding | All fonts must be embedded in the document | No (re-export needed) |
| 7 | Heading Hierarchy | Single H1, no skipped levels (H1→H3 without H2) | No (tag tree edit) |

## IMPORTANT — Should Fix

| # | Check | Requirement | Auto-fixable? |
|---|-------|-------------|---------------|
| 8 | Author | Author metadata should be populated | Yes |
| 9 | Subject / Description | Should describe the document's purpose | Yes |
| 10 | Table Headers | Tables must have `/TH` (header) tagged cells | No (tag tree edit) |
| 11 | List Structure | Lists must use `/L` → `/LI` → `/Lbl` + `/LBody` | No (tag tree edit) |
| 12 | Descriptive Links | Link text must not be "click here" or raw URLs | Yes (Claude generates) |
| 13 | Bookmarks | Documents > 20 pages should have bookmarks/outlines | Yes |
| 14 | PDF/UA Identifier | `pdfuaid:part` should be declared in XMP metadata | Yes |
| 15 | Unicode Text | All text should use Unicode encoding | No (re-export) |

## ADVISORY — Nice to Have

| # | Check | Requirement | Auto-fixable? |
|---|-------|-------------|---------------|
| 16 | Keywords | Keywords metadata for discoverability | Yes |
| 17 | Page Labels | Meaningful page labels (vs. just page numbers) | No |
| 18 | Content Copying | Accessibility content copying must be allowed | No (security setting) |

## REQUIRES HUMAN REVIEW

| Check | Why |
|-------|-----|
| Reading Order | Automated tools cannot determine if reading order is correct for the content |
| Alt Text Quality | Must be reviewed in context — is the description meaningful and accurate? |
| Decorative Images | Whether images are truly decorative requires human judgment |
| Link Destinations | Links should go where the text describes |
| Color Contrast | Text-to-background contrast ratio must meet WCAG requirements |
| Logical Tab Order | Form field tab order must follow visual layout |

---

## Remediation Instructions by Issue Type

### Missing Document Title
**Acrobat:** File → Properties → Description tab → Title field
**Source fix:** Set title in PowerPoint/Word before exporting to PDF
**Script:** The fix script sets this automatically

### Missing Language
**Acrobat:** File → Properties → Advanced tab → Language dropdown
**Script:** The fix script sets this automatically (default: en-US)

### Missing Alt Text on Figures
**Acrobat:** Accessibility → Set Alternate Text → select each image
**Script:** The fix script embeds Claude-generated alt text automatically
**Alt text guidelines:**
- Be concise but descriptive (1-2 sentences)
- Describe what the image conveys, not just what it looks like
- For charts: describe the data trend and key takeaway
- For decorative images: mark as artifact (empty alt text)

### Heading Hierarchy Issues
**Acrobat:** View → Navigation Panels → Tags → find heading tags → right-click → Properties → change Type
**PowerPoint fix:** Use consistent heading styles in slide layouts before re-exporting

### Tables Missing Headers
**Acrobat:** Tags panel → find Table → TR[1] → select each TD → Properties → change Type to TH
**Also:** Right-click table in Tags panel → Table Editor → mark header row

### Non-Descriptive Links
**Acrobat:** Tags panel → find Link → edit text content to be descriptive
**Source fix:** Use descriptive hyperlink text in the original document

### Unembedded Fonts
**PowerPoint:** File → Options → Save → check "Embed fonts in the file"
**Word:** File → Options → Save → check "Embed fonts in the file"
**Acrobat Preflight:** Advanced → Print Production → Preflight → Embed Fonts

### Missing Bookmarks
**Acrobat:** View → Navigation Panels → Bookmarks → manually create bookmarks for major sections
**Source fix:** Use heading styles consistently; PDF export settings usually auto-generate bookmarks from headings
**Script:** The fix script auto-generates bookmarks from each page's largest/boldest text

---

## Processing Paths — Preview.app Compatibility

This plugin offers two processing paths for untagged PDFs:

### Path A: Acrobat + Plugin (pypdf) — Default
- User runs Acrobat Pro > Accessibility > Autotag Document **first** on the original PDF
- Then `pdf_metadata_fix.py` (pypdf) applies remaining fixes on the tagged file:
  title, subject, language, display title, tagged flag, PDF/UA, bookmarks, link descriptions, alt text
- ✅ Opens in macOS Preview, browsers, Adobe Acrobat, all PDF viewers
- ✅ Structure tree comes from Acrobat (higher quality than automated heuristics)

### Path B: Maximum Automation (pikepdf) — Opt-In
- Uses `pdf_structure_generator.py` (pikepdf library)
- Fixes: everything from Path A PLUS structure tree with headings, paragraphs, lists
- ⚠️ Does NOT render in macOS Preview (pages appear blank)
- ✅ Opens in web browsers (Chrome, Safari, Brave, Edge) and Adobe Acrobat
- Use this path when the user doesn't have Acrobat Pro or primarily views PDFs in browsers

**Why the difference:** pikepdf re-serializes the entire PDF during save, which produces
valid PDF that most viewers handle correctly but macOS Preview's strict parser cannot render.
This is a known limitation with no workaround short of using Acrobat Pro for structure tagging.
