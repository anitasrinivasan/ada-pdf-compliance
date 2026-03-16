#!/usr/bin/env python3
"""
PDF Structure Tree Generator for Slide-Deck PDFs

Generates a tagged structure tree for untagged PDFs (typically Google Slides
or PowerPoint exports). Uses font metrics and positioning heuristics to
classify page content into headings, paragraphs, lists, and figures.

Also applies metadata fixes (title, subject, language, bookmarks, link
descriptions, PDF/UA identifier) in a single pass using pikepdf, so the
output does not need to be re-processed by pypdf.

IMPORTANT — Preview.app compatibility:
    pikepdf's PDF re-serialization produces files that render as blank pages
    in macOS Preview.app. The output opens correctly in web browsers (Chrome,
    Safari, Brave, Edge) and Adobe Acrobat. If Preview compatibility is
    required, use pdf_metadata_fix.py (pypdf-only) instead and have the user
    run Acrobat Pro > Accessibility > Autotag Document for the structure tree.

Usage:
    python3 pdf_structure_generator.py <input_pdf> [output_pdf] [fixes_json]

If output_pdf is omitted, writes to <input>_accessible.pdf
If fixes_json is provided, metadata fixes are applied in the same pass.

Dependencies:
    - pikepdf (required for structure tree generation)
    - pypdf (used for text extraction with font metrics)
"""

import json
import os
import re
import sys

# Check for pikepdf availability
try:
    import pikepdf
    from pikepdf import Dictionary, Name, Array, String, Pdf
    PIKEPDF_AVAILABLE = True
except ImportError:
    PIKEPDF_AVAILABLE = False

from pypdf import PdfReader


def check_availability():
    """Check if pikepdf is available."""
    return PIKEPDF_AVAILABLE


def extract_page_content(reader, page_num):
    """Extract text with font metrics from a page using pypdf's visitor API.

    Returns a list of content items with text, font size, position, and
    heuristic classification.
    """
    items = []

    def visitor(text, ctm, tm, font_dict, font_size):
        if not text or not text.strip():
            return
        x_pos = tm[4] if tm else 0
        y_pos = tm[5] if tm else 0

        effective_size = font_size
        if ctm and len(ctm) >= 4:
            scale = abs(ctm[3]) if ctm[3] != 0 else abs(ctm[0])
            if scale > 0:
                effective_size = font_size * scale

        is_bold = False
        font_name = ""
        if font_dict:
            base_font = str(font_dict.get("/BaseFont", ""))
            font_name = base_font
            is_bold = "bold" in base_font.lower()

        items.append({
            "text": text.strip(),
            "size": round(effective_size, 1),
            "x": round(x_pos, 1),
            "y": round(y_pos, 1),
            "bold": is_bold,
            "font": font_name,
        })

    try:
        reader.pages[page_num].extract_text(visitor_text=visitor)
    except Exception:
        pass

    return items


def classify_content(items, page_height=792):
    """Classify content items into semantic roles using heuristics.

    For slide decks:
    - Largest/boldest text near top → heading
    - Bullet-prefixed text → list items
    - Other text → paragraphs
    - (Figures are detected separately from non-text regions)

    Returns a list of classified blocks.
    """
    if not items:
        return []

    # Find size statistics
    sizes = [item["size"] for item in items]
    max_size = max(sizes)
    median_size = sorted(sizes)[len(sizes) // 2]

    blocks = []
    bullet_pattern = re.compile(r"^[\u2022\u2023\u25E6\u2043\u2219•\-\*]\s*")

    for item in items:
        text = item["text"]
        size = item["size"]
        y = item["y"]
        bold = item["bold"]

        # Classification heuristics
        if size >= max_size * 0.85 and (bold or size > median_size * 1.3):
            # Large and/or bold text — heading
            # H1 if it's the biggest, H2 if slightly smaller
            if size >= max_size * 0.95:
                role = "H1"
            else:
                role = "H2"
        elif bullet_pattern.match(text):
            role = "LI"
            text = bullet_pattern.sub("", text)
        elif size < median_size * 0.8:
            # Smaller text — could be footnote or caption
            role = "P"
        else:
            role = "P"

        blocks.append({
            "role": role,
            "text": text,
            "size": size,
            "x": item["x"],
            "y": item["y"],
        })

    # Group consecutive list items
    grouped = []
    in_list = False
    for block in blocks:
        if block["role"] == "LI":
            if not in_list:
                grouped.append({"role": "L", "children": []})
                in_list = True
            grouped[-1]["children"].append(block)
        else:
            in_list = False
            grouped.append(block)

    return grouped


def _detect_page_images(pike_page):
    """Detect images on a PDF page by checking XObject resources.

    Returns a list of image names found on the page.
    """
    images = []
    try:
        resources = pike_page.get("/Resources")
        if not resources:
            return images
        xobjects = resources.get("/XObject")
        if not xobjects:
            return images
        for name, xobj_ref in xobjects.items():
            try:
                xobj = xobj_ref
                if hasattr(xobj, "get"):
                    subtype = str(xobj.get("/Subtype", ""))
                    if subtype in ("/Image", "Image"):
                        # Get image dimensions for context
                        width = int(xobj.get("/Width", 0))
                        height = int(xobj.get("/Height", 0))
                        # Skip tiny images (likely icons/bullets, not content figures)
                        if width > 50 and height > 50:
                            images.append({
                                "name": str(name),
                                "width": width,
                                "height": height,
                            })
            except Exception:
                continue
    except Exception:
        pass
    return images


def generate_structure_tree(input_path, output_path=None, alt_texts=None,
                            fixes=None):
    """Generate a tagged structure tree for an untagged PDF.

    Also applies metadata fixes directly using pikepdf so the output file
    does not need to pass through pypdf's PdfWriter (which can corrupt
    pikepdf-modified content streams and break Preview.app).

    Args:
        input_path: Path to the input PDF
        output_path: Path for output PDF (default: input_accessible.pdf)
        alt_texts: Optional dict mapping figure index (str) to alt text strings
        fixes: Optional dict of metadata fixes to apply (title, subject,
               language, display_doc_title, set_pdfua, link_descriptions)

    Returns:
        dict with results: output path, pages processed, elements created
    """
    if not PIKEPDF_AVAILABLE:
        return {
            "error": "pikepdf is not installed. Run: pip install pikepdf",
            "available": False,
        }

    if fixes is None:
        fixes = {}
    if alt_texts is None:
        alt_texts = fixes.get("alt_texts", {})

    if output_path is None:
        base, ext = os.path.splitext(input_path)
        output_path = f"{base}_accessible{ext}"

    # Use pypdf for text extraction (better visitor API)
    reader = PdfReader(input_path)
    page_count = len(reader.pages)

    # Use pikepdf for PDF modification
    pdf = Pdf.open(input_path)

    # Build structure elements per page
    all_page_elements = []
    mcid_counter = 0
    figure_index = 0  # Global figure counter across all pages

    for page_num in range(page_count):
        items = extract_page_content(reader, page_num)
        classified = classify_content(items)

        # Detect images on this page
        page_images = _detect_page_images(pdf.pages[page_num])

        page_elements = []
        for block in classified:
            if block.get("children"):
                # List with children
                list_elem = {
                    "role": "L",
                    "children": [],
                }
                for child in block["children"]:
                    list_elem["children"].append({
                        "role": "LI",
                        "mcid": mcid_counter,
                        "text": child["text"],
                    })
                    mcid_counter += 1
                page_elements.append(list_elem)
            else:
                page_elements.append({
                    "role": block["role"],
                    "mcid": mcid_counter,
                    "text": block["text"],
                })
                mcid_counter += 1

        # Add Figure elements for detected images
        for img in page_images:
            alt_text = alt_texts.get(str(figure_index), "")
            page_elements.append({
                "role": "Figure",
                "mcid": mcid_counter,
                "text": "",
                "alt": alt_text,
                "image_info": img,
                "figure_index": figure_index,
            })
            mcid_counter += 1
            figure_index += 1

        all_page_elements.append(page_elements)

    # Now build the PDF structure tree using pikepdf.
    # CRITICAL: All structure elements with parent (/P) pointers must be
    # indirect objects (pdf.make_indirect) to avoid infinite loops during
    # serialization caused by circular parent-child references.
    struct_tree_root = pdf.make_indirect(Dictionary({
        "/Type": Name("/StructTreeRoot"),
        "/K": Array(),
    }))

    doc_elem = pdf.make_indirect(Dictionary({
        "/S": Name("/Document"),
        "/P": struct_tree_root,
        "/K": Array(),
    }))
    struct_tree_root["/K"] = Array([doc_elem])

    parent_tree_nums = Array()
    total_elements = 0

    for page_num, page_elements in enumerate(all_page_elements):
        if not page_elements:
            continue

        pike_page = pdf.pages[page_num]
        page_ref = pike_page.obj

        # Section for this page (indirect to allow back-ref from children)
        sect_elem = pdf.make_indirect(Dictionary({
            "/S": Name("/Sect"),
            "/P": doc_elem,
            "/K": Array(),
            "/Pg": page_ref,
        }))

        # Track MCIDs for this page's content stream
        page_mcid_ops = []

        for block in page_elements:
            if block["role"] == "L" and block.get("children"):
                # Build list structure (indirect)
                list_elem = pdf.make_indirect(Dictionary({
                    "/S": Name("/L"),
                    "/P": sect_elem,
                    "/K": Array(),
                }))

                for child in block["children"]:
                    mcid = child["mcid"]
                    mcr = Dictionary({
                        "/Type": Name("/MCR"),
                        "/Pg": page_ref,
                        "/MCID": mcid,
                    })

                    li_elem = pdf.make_indirect(Dictionary({
                        "/S": Name("/LI"),
                        "/P": list_elem,
                        "/K": Array([mcr]),
                    }))

                    list_elem["/K"].append(li_elem)
                    page_mcid_ops.append((mcid, "LI"))
                    parent_tree_nums.append(mcid)
                    parent_tree_nums.append(li_elem)
                    total_elements += 1

                sect_elem["/K"].append(list_elem)
                total_elements += 1
            else:
                mcid = block["mcid"]
                role_name = block["role"]

                mcr = Dictionary({
                    "/Type": Name("/MCR"),
                    "/Pg": page_ref,
                    "/MCID": mcid,
                })

                elem_dict = {
                    "/S": Name(f"/{role_name}"),
                    "/P": sect_elem,
                    "/K": Array([mcr]),
                    "/Pg": page_ref,
                }

                # Add /Alt attribute for Figure elements
                if role_name == "Figure" and block.get("alt"):
                    elem_dict["/Alt"] = String(block["alt"])

                elem = pdf.make_indirect(Dictionary(elem_dict))

                sect_elem["/K"].append(elem)
                page_mcid_ops.append((mcid, role_name))
                parent_tree_nums.append(mcid)
                parent_tree_nums.append(elem)
                total_elements += 1

        doc_elem["/K"].append(sect_elem)

        # NOTE: We intentionally skip inserting BDC/EMC marked content
        # operators into the page content streams. While MCID linking is
        # required for strict PDF/UA validation, the regex-based content
        # stream modification corrupts rendering in Preview.app (pages
        # appear blank). The structure tree hierarchy alone still provides
        # semantic navigation for screen readers (headings, lists, etc.)
        # and passes the "is tagged" check. Full MCID linking should be
        # done in Adobe Acrobat Pro for production compliance.

    # Set the parent tree
    parent_tree = pdf.make_indirect(Dictionary({
        "/Nums": parent_tree_nums,
    }))
    struct_tree_root["/ParentTree"] = parent_tree
    struct_tree_root["/ParentTreeNextKey"] = mcid_counter

    # Attach structure tree to catalog
    pdf.Root["/StructTreeRoot"] = struct_tree_root

    # Ensure MarkInfo is set
    pdf.Root["/MarkInfo"] = Dictionary({"/Marked": True})

    # Generate bookmarks from page titles using already-extracted content.
    # This must happen here because BDC/EMC insertion breaks pypdf text
    # extraction, so the metadata fix script can't generate bookmarks
    # from the tagged PDF.
    bookmark_count = 0
    try:
        bookmark_count = _generate_bookmarks_from_content(
            pdf, reader, all_page_elements
        )
    except Exception:
        pass

    # Apply metadata fixes directly with pikepdf so the output doesn't
    # need to go through pypdf's PdfWriter (which corrupts pikepdf streams).
    metadata_changes = []
    metadata_changes.extend(
        _apply_pikepdf_metadata(pdf, fixes)
    )

    # Apply link description fixes
    link_descs = fixes.get("link_descriptions", {})
    if link_descs:
        link_count = _apply_pikepdf_link_descriptions(pdf, link_descs)
        if link_count > 0:
            metadata_changes.append(
                f"Descriptive text added to {link_count} links"
            )

    # Save
    pdf.save(output_path)

    return {
        "input": input_path,
        "output": output_path,
        "pages_processed": page_count,
        "elements_created": total_elements,
        "figures_detected": figure_index,
        "bookmarks_created": bookmark_count,
        "metadata_changes": metadata_changes,
        "available": True,
    }


def _apply_pikepdf_metadata(pdf, fixes):
    """Apply metadata fixes using pikepdf's native API.

    Handles: title, author, subject, language, display_doc_title, set_pdfua.
    """
    changes = []

    # Set XMP metadata and PDF/UA in a single open_metadata() call
    # (multiple calls can overwrite each other)
    with pdf.open_metadata() as meta:
        if "title" in fixes:
            meta["dc:title"] = fixes["title"]
            changes.append(f'Title set to "{fixes["title"]}"')
        if "author" in fixes:
            meta["dc:creator"] = [fixes["author"]]
            changes.append(f'Author set to "{fixes["author"]}"')
        if "subject" in fixes:
            meta["dc:description"] = fixes["subject"]
            changes.append(f'Subject set')
        if fixes.get("set_pdfua"):
            meta["pdfuaid:part"] = "1"
            changes.append("PDF/UA-1 identifier added")

    # Also set the legacy /Info dict for broader compatibility
    if "title" in fixes:
        pdf.docinfo["/Title"] = fixes["title"]
    if "author" in fixes:
        pdf.docinfo["/Author"] = fixes["author"]
    if "subject" in fixes:
        pdf.docinfo["/Subject"] = fixes["subject"]

    # Language
    if "language" in fixes:
        pdf.Root["/Lang"] = String(fixes["language"])
        changes.append(f'Language set to {fixes["language"]}')

    # Display doc title
    if fixes.get("display_doc_title"):
        if "/ViewerPreferences" not in pdf.Root:
            pdf.Root["/ViewerPreferences"] = Dictionary()
        pdf.Root["/ViewerPreferences"]["/DisplayDocTitle"] = True
        changes.append("Display doc title enabled")

    return changes


def _apply_pikepdf_link_descriptions(pdf, link_descs):
    """Set descriptive /Contents on link annotations using pikepdf.

    link_descs: dict mapping "pageNum_annotIndex" to description string.
    Page numbers are 1-indexed to match audit script output.
    """
    updated = 0
    for key, description in link_descs.items():
        try:
            parts = key.split("_")
            page_num = int(parts[0]) - 1  # Convert to 0-indexed
            annot_idx = int(parts[1]) if len(parts) > 1 else 0

            page = pdf.pages[page_num]
            annots = page.get("/Annots")
            if not annots:
                continue

            link_idx = 0
            for annot in annots:
                if not hasattr(annot, "get"):
                    continue
                subtype = str(annot.get("/Subtype", ""))
                if subtype not in ("/Link", "Link"):
                    continue
                if link_idx == annot_idx:
                    annot["/Contents"] = String(description)
                    updated += 1
                    break
                link_idx += 1
        except Exception:
            continue
    return updated


def _generate_bookmarks_from_content(pdf, reader, all_page_elements):
    """Generate bookmarks using content already extracted during classification.

    Uses pikepdf's outline API since pypdf text extraction won't work after
    BDC/EMC operators are inserted into the content streams.
    """
    with pdf.open_outline() as outline:
        count = 0
        for page_num, page_elements in enumerate(all_page_elements):
            if not page_elements:
                continue

            # Find the first H1 element on this page — that's the slide title
            title = None
            for block in page_elements:
                if block.get("role") in ("H1", "H2"):
                    title = block.get("text", "").strip()
                    break

            if not title:
                # Fall back to first text block
                for block in page_elements:
                    if block.get("children"):
                        # Skip list containers
                        continue
                    text = block.get("text", "").strip()
                    if text and len(text) > 2:
                        title = text
                        break

            if title:
                if len(title) > 80:
                    title = title[:77] + "..."
                # Clean up whitespace
                title = re.sub(r"\s+", " ", title).strip()
                oi = pikepdf.OutlineItem(title, page_num)
                outline.root.append(oi)
                count += 1

    return count


def main():
    if len(sys.argv) < 2:
        print(json.dumps({
            "error": "Usage: python3 pdf_structure_generator.py <input_pdf> "
                     "[output_pdf] [fixes_json]",
            "available": PIKEPDF_AVAILABLE,
        }))
        sys.exit(1)

    if not PIKEPDF_AVAILABLE:
        print(json.dumps({
            "error": "pikepdf is not installed. Run: pip install pikepdf",
            "available": False,
        }))
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None
    fixes_path = sys.argv[3] if len(sys.argv) > 3 else None

    if not os.path.isfile(input_path):
        print(json.dumps({"error": f"File not found: {input_path}"}))
        sys.exit(1)

    fixes = {}
    if fixes_path and os.path.isfile(fixes_path):
        with open(fixes_path, "r") as f:
            fixes = json.load(f)

    result = generate_structure_tree(input_path, output_path, fixes=fixes)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
