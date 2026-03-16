#!/usr/bin/env python3
"""
PDF Structure Tree Generator

Generates a tagged structure tree for untagged PDFs (slide decks, text
documents, academic papers, etc.). Uses font metrics and positioning
heuristics to classify page content into headings (H1-H4), paragraphs,
lists (with Lbl/LBody), tables, and figures.

Also applies metadata fixes (title, subject, language, bookmarks, link
descriptions, PDF/UA identifier) in a single pass using pikepdf, so the
output does not need to be re-processed by pypdf.

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
    from pikepdf import Dictionary, Name, Array, String, Pdf, Operator
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
    except Exception as e:
        print(f"Warning: text extraction failed on page {page_num + 1}: {e}", file=sys.stderr)

    return items


def detect_document_type(all_page_items, page_count):
    """Detect whether the PDF is a slide deck or a text document.

    Heuristics:
    - Slide decks: few text items per page (typically <30), one large title
    - Text documents: many text items per page (typically >30), dense text

    Returns "slides" or "document".
    """
    if page_count == 0 or not all_page_items:
        return "slides"

    items_per_page = []
    for page_items in all_page_items:
        items_per_page.append(len(page_items))

    avg_items = sum(items_per_page) / len(items_per_page) if items_per_page else 0

    # Slide decks typically have <30 text items per page
    # Text documents have >40 text items per page
    if avg_items > 40:
        return "document"
    return "slides"


def classify_content(items, page_height=792, doc_type="slides",
                     is_first_page=False, global_max_size=None):
    """Classify content items into semantic roles using heuristics.

    Handles both slide decks and text documents differently:
    - Slides: largest text on page → H1, everything else → P
    - Documents: only first page top text → H1, bold section headers → H2,
      sub-headers → H3, smaller bold → H4

    Returns a list of classified blocks with bullet text preserved for
    Lbl/LBody splitting.
    """
    if not items:
        return []

    # Sort by y-position descending (top of page first)
    items_sorted = sorted(items, key=lambda x: -x["y"])

    # Find size statistics
    sizes = [item["size"] for item in items_sorted]
    max_size = max(sizes)

    # For slides: use per-page max size so each slide's title is detected
    # For documents: use global max for consistent cross-page heading levels
    if doc_type == "slides":
        ref_max = max_size  # per-page max
    else:
        ref_max = global_max_size if global_max_size else max_size

    blocks = []
    bullet_pattern = re.compile(r"^([\u2022\u2023\u25E6\u2043\u2219•\-\*])\s*")
    h1_assigned_this_page = False
    h1_y = 0
    h1_line_done = False

    for item in items_sorted:
        text = item["text"]
        size = item["size"]
        y = item["y"]
        bold = item["bold"]

        # Check for bullet
        bullet_match = bullet_pattern.match(text)
        if bullet_match:
            bullet_char = bullet_match.group(1)
            body_text = bullet_pattern.sub("", text)
            blocks.append({
                "role": "LI",
                "text": body_text,
                "bullet": bullet_char,
                "size": size,
                "x": item["x"],
                "y": y,
            })
            continue

        # Heading classification — different for slides vs documents
        if doc_type == "slides":
            # Slides: only check the first 3 items at the top of the slide.
            # The first heading-sized item becomes H1; tag its entire line.
            # Everything else is P. No H2/H3/H4 for slides.
            item_index = items_sorted.index(item)
            if (not h1_assigned_this_page
                    and item_index < 3
                    and size >= max_size * 0.95):
                role = "H1"
                h1_assigned_this_page = True
                h1_y = y
            elif (h1_assigned_this_page
                      and not h1_line_done
                      and abs(y - h1_y) < 2
                      and size >= max_size * 0.90):
                # Continue the heading line (same y-position, similar size)
                role = "H1"
            else:
                role = "P"
                if h1_assigned_this_page:
                    h1_line_done = True
        else:
            # Document mode: stricter heading assignment
            # H1: only on first page, largest text at top
            # H2: bold text at the same size as section headers
            # H3: bold text at a smaller tier
            # H4: even smaller bold
            if is_first_page and not h1_assigned_this_page and size >= ref_max * 0.95:
                role = "H1"
                h1_assigned_this_page = True
            elif bold and size >= ref_max * 0.85:
                role = "H2"
            elif bold and size >= ref_max * 0.70:
                role = "H3"
            elif bold and size >= ref_max * 0.55:
                role = "H4"
            else:
                role = "P"

        blocks.append({
            "role": role,
            "text": text,
            "size": size,
            "x": item["x"],
            "y": y,
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


def detect_tables(items, page_width=612):
    """Detect tabular layouts by clustering text items by x-position.

    If 3+ distinct x-columns are found with consistent alignment across
    3+ rows, the region is classified as a table.

    Returns a list of table structures with rows and cells.
    """
    if len(items) < 6:
        return []

    # Cluster by x-position (±8px tolerance)
    x_tolerance = 8
    x_clusters = {}  # cluster_center → list of items
    for item in items:
        x = item["x"]
        matched = False
        for center in list(x_clusters.keys()):
            if abs(x - center) <= x_tolerance:
                x_clusters[center].append(item)
                matched = True
                break
        if not matched:
            x_clusters[x] = [item]

    # Need at least 3 columns for a table
    if len(x_clusters) < 3:
        return []

    # Sort columns by x-position
    sorted_columns = sorted(x_clusters.keys())

    # Cluster items by y-position to find rows (±5px tolerance)
    y_tolerance = 5
    y_positions = set()
    for item in items:
        y_positions.add(round(item["y"] / y_tolerance) * y_tolerance)

    # Need at least 3 rows
    if len(y_positions) < 3:
        return []

    # Build row-column grid: check that most rows have entries in most columns
    sorted_rows = sorted(y_positions, reverse=True)  # top to bottom
    grid_rows = []
    for y_center in sorted_rows:
        row_cells = []
        for x_center in sorted_columns:
            cell_items = [
                item for item in items
                if abs(item["x"] - x_center) <= x_tolerance
                and abs(item["y"] - y_center) <= y_tolerance
            ]
            if cell_items:
                row_cells.append(" ".join(c["text"] for c in cell_items))
            else:
                row_cells.append("")
        # Only count as a row if at least half the columns have content
        filled = sum(1 for c in row_cells if c)
        if filled >= len(sorted_columns) * 0.5:
            grid_rows.append(row_cells)

    # Need at least 3 qualifying rows to call it a table
    if len(grid_rows) < 3:
        return []

    return [{
        "rows": grid_rows,
        "num_columns": len(sorted_columns),
        "num_rows": len(grid_rows),
    }]


def _detect_page_images(pike_page, image_counts=None):
    """Detect content images on a PDF page by checking XObject resources.

    Filters out:
    - Tiny images (<50x50 pixels) — likely icons/bullets
    - Extreme aspect ratios (>5:1 or <1:5) — likely decorative borders/lines
    - Images that appear on most pages (tracked via image_counts) — likely
      headers/footers/logos

    Args:
        pike_page: pikepdf page object
        image_counts: optional dict tracking how many pages each image name
                      appears on (for repeated-image filtering)

    Returns a list of image dicts found on the page.
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
                        width = int(xobj.get("/Width", 0))
                        height = int(xobj.get("/Height", 0))

                        # Skip tiny images (icons/bullets)
                        if width <= 50 or height <= 50:
                            continue

                        # Skip extreme aspect ratios (decorative lines/borders)
                        if height > 0 and width > 0:
                            aspect = width / height
                            if aspect > 5 or aspect < 0.2:
                                continue

                        # Track for repeated-image filtering
                        # Include colorspace and bits to reduce false collisions
                        # between different images that share dimensions
                        cs = str(xobj.get("/ColorSpace", ""))
                        bpc = str(xobj.get("/BitsPerComponent", ""))
                        img_key = f"{width}x{height}_{cs}_{bpc}"
                        if image_counts is not None:
                            image_counts[img_key] = image_counts.get(img_key, 0) + 1

                        images.append({
                            "name": str(name),
                            "width": width,
                            "height": height,
                            "img_key": img_key,
                        })
            except Exception as e:
                print(f"Warning: failed to inspect XObject {name}: {e}", file=sys.stderr)
                continue
    except Exception:
        pass
    return images


def _tag_page_content_stream(pdf, pike_page, text_mcids, figure_mcids,
                             content_image_names):
    """Insert BDC/EMC marked content operators into a page's content stream.

    Wraps BT/ET text blocks with tagged BDC (using MCIDs from the structure
    tree). Wraps Do operators for content images as /Figure. All remaining
    content (graphics, decorative images) is marked as /Artifact.

    This enables the TaggedCont check in Acrobat's accessibility audit.

    Args:
        pdf: pikepdf.Pdf instance
        pike_page: pikepdf page object
        text_mcids: list of (mcid, role) for text structure elements
        figure_mcids: list of mcid values for figure structure elements
        content_image_names: set of XObject names that are content images

    Returns:
        Number of content blocks tagged
    """
    try:
        raw_ops = pikepdf.parse_content_stream(pike_page)
    except Exception as e:
        print(f"Warning: cannot parse content stream: {e}", file=sys.stderr)
        return 0

    tagged_ops = []
    text_idx = 0
    fig_idx = 0
    tagged_count = 0
    artifact_buf = []

    def flush_artifacts():
        if artifact_buf:
            tagged_ops.append(([Name("/Artifact")], Operator("BMC")))
            tagged_ops.extend(artifact_buf)
            tagged_ops.append(([], Operator("EMC")))
            artifact_buf.clear()

    i = 0
    while i < len(raw_ops):
        operands, operator = raw_ops[i]
        op_str = str(operator)

        if op_str == "BT":
            flush_artifacts()
            # Collect entire BT...ET block
            bt_block = [(operands, operator)]
            i += 1
            while i < len(raw_ops):
                o, p = raw_ops[i]
                bt_block.append((o, p))
                if str(p) == "ET":
                    break
                i += 1

            if text_idx < len(text_mcids):
                mcid, role = text_mcids[text_idx]
                text_idx += 1
                tagged_ops.append((
                    [Name(f"/{role}"), Dictionary({"/MCID": mcid})],
                    Operator("BDC"),
                ))
                tagged_ops.extend(bt_block)
                tagged_ops.append(([], Operator("EMC")))
                tagged_count += 1
            else:
                # Extra text block not in structure tree — mark as artifact
                tagged_ops.append(([Name("/Artifact")], Operator("BMC")))
                tagged_ops.extend(bt_block)
                tagged_ops.append(([], Operator("EMC")))

        elif op_str == "Do":
            xobj_name = str(operands[0]).lstrip("/") if operands else ""
            if xobj_name in content_image_names and fig_idx < len(figure_mcids):
                flush_artifacts()
                mcid = figure_mcids[fig_idx]
                fig_idx += 1
                tagged_ops.append((
                    [Name("/Figure"), Dictionary({"/MCID": mcid})],
                    Operator("BDC"),
                ))
                tagged_ops.append((operands, operator))
                tagged_ops.append(([], Operator("EMC")))
                tagged_count += 1
            else:
                artifact_buf.append((operands, operator))

        else:
            artifact_buf.append((operands, operator))

        i += 1

    flush_artifacts()

    # Write tagged content stream back to page
    try:
        new_content = pikepdf.unparse_content_stream(tagged_ops)
        pike_page.Contents = pdf.make_stream(new_content)
    except Exception as e:
        print(f"Warning: failed to write tagged content stream: {e}",
              file=sys.stderr)
        return 0

    return tagged_count


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

    # Phase 1: Extract all page content for document type detection
    all_raw_items = []
    for page_num in range(page_count):
        items = extract_page_content(reader, page_num)
        all_raw_items.append(items)

    # Detect document type (slides vs text document)
    doc_type = detect_document_type(all_raw_items, page_count)

    # Compute global max font size for consistent heading detection
    all_sizes = [item["size"] for page_items in all_raw_items
                 for item in page_items if item["size"] > 0]
    global_max_size = max(all_sizes) if all_sizes else 12

    # Phase 2: First pass — detect images on all pages to identify repeated ones
    image_counts = {}  # img_key → count of pages it appears on
    all_raw_images = []
    for page_num in range(page_count):
        page_images = _detect_page_images(pdf.pages[page_num], image_counts)
        all_raw_images.append(page_images)

    # Determine which images are repeated (appear on >80% of pages = logo/header)
    repeated_threshold = max(3, int(page_count * 0.8))
    repeated_images = {k for k, v in image_counts.items() if v >= repeated_threshold}

    # Phase 3: Classify content and build structure elements
    all_page_elements = []
    mcid_counter = 0
    figure_index = 0

    for page_num in range(page_count):
        items = all_raw_items[page_num]
        classified = classify_content(
            items,
            doc_type=doc_type,
            is_first_page=(page_num == 0),
            global_max_size=global_max_size,
        )

        # Detect tables from raw items
        tables = detect_tables(items)

        page_elements = []
        for block in classified:
            if block.get("children"):
                # List with children — now with Lbl/LBody structure
                list_elem = {
                    "role": "L",
                    "children": [],
                }
                for child in block["children"]:
                    list_elem["children"].append({
                        "role": "LI",
                        "mcid": mcid_counter,
                        "text": child["text"],
                        "bullet": child.get("bullet", "\u2022"),
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

        # Add Table elements for detected tables
        for table in tables:
            table_elem = {
                "role": "Table",
                "rows": [],
            }
            for row_idx, row in enumerate(table["rows"]):
                row_elem = {
                    "role": "TR",
                    "cells": [],
                }
                for cell_text in row:
                    # First row gets TH, rest get TD
                    cell_role = "TH" if row_idx == 0 else "TD"
                    row_elem["cells"].append({
                        "role": cell_role,
                        "mcid": mcid_counter,
                        "text": cell_text,
                    })
                    mcid_counter += 1
                table_elem["rows"].append(row_elem)
            page_elements.append(table_elem)

        # Add Figure elements for detected images (with filtering)
        for img in all_raw_images[page_num]:
            # Skip repeated images (logos, headers, footers)
            if img.get("img_key") in repeated_images:
                continue

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
    all_page_mcid_data = {}  # page_num → list of (mcid, role) for BDC/EMC insertion

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
            if block["role"] == "Table" and block.get("rows"):
                # Build table structure
                table_elem = pdf.make_indirect(Dictionary({
                    "/S": Name("/Table"),
                    "/P": sect_elem,
                    "/K": Array(),
                }))

                for row in block["rows"]:
                    tr_elem = pdf.make_indirect(Dictionary({
                        "/S": Name("/TR"),
                        "/P": table_elem,
                        "/K": Array(),
                    }))

                    for cell in row["cells"]:
                        mcid = cell["mcid"]
                        cell_role = cell["role"]  # TH or TD
                        mcr = Dictionary({
                            "/Type": Name("/MCR"),
                            "/Pg": page_ref,
                            "/MCID": mcid,
                        })

                        cell_elem = pdf.make_indirect(Dictionary({
                            "/S": Name(f"/{cell_role}"),
                            "/P": tr_elem,
                            "/K": Array([mcr]),
                        }))

                        tr_elem["/K"].append(cell_elem)
                        page_mcid_ops.append((mcid, cell_role))
                        parent_tree_nums.append(mcid)
                        parent_tree_nums.append(cell_elem)
                        total_elements += 1

                    table_elem["/K"].append(tr_elem)
                    total_elements += 1

                sect_elem["/K"].append(table_elem)
                total_elements += 1

            elif block["role"] == "L" and block.get("children"):
                # Build list structure with Lbl/LBody children
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

                    # Create Lbl (bullet) and LBody (text) children
                    bullet = child.get("bullet", "\u2022")
                    lbl_elem = pdf.make_indirect(Dictionary({
                        "/S": Name("/Lbl"),
                        "/K": Array([String(bullet)]),
                    }))
                    lbody_elem = pdf.make_indirect(Dictionary({
                        "/S": Name("/LBody"),
                        "/K": Array([mcr]),
                    }))

                    li_elem = pdf.make_indirect(Dictionary({
                        "/S": Name("/LI"),
                        "/P": list_elem,
                        "/K": Array([lbl_elem, lbody_elem]),
                    }))
                    lbl_elem["/P"] = li_elem
                    lbody_elem["/P"] = li_elem

                    list_elem["/K"].append(li_elem)
                    page_mcid_ops.append((mcid, "LI"))
                    parent_tree_nums.append(mcid)
                    parent_tree_nums.append(lbody_elem)
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

        # Tag link annotations on this page as /Link structure elements
        # with /OBJR (object reference) so Acrobat's TaggedAnnots check passes
        try:
            annots = pike_page.get("/Annots")
            if annots:
                for annot in annots:
                    if not hasattr(annot, "get"):
                        continue
                    subtype = str(annot.get("/Subtype", ""))
                    if subtype not in ("/Link", "Link"):
                        continue
                    objr = Dictionary({
                        "/Type": Name("/OBJR"),
                        "/Pg": page_ref,
                        "/Obj": annot,
                    })
                    link_elem = pdf.make_indirect(Dictionary({
                        "/S": Name("/Link"),
                        "/P": sect_elem,
                        "/K": Array([objr]),
                    }))
                    sect_elem["/K"].append(link_elem)
                    total_elements += 1
        except Exception as e:
            print(f"Warning: failed to tag annotations on page {page_num + 1}: {e}", file=sys.stderr)

        # Set tab order to follow structure order (fixes Acrobat TabOrder check)
        pike_page["/Tabs"] = Name("/S")

        doc_elem["/K"].append(sect_elem)

        # Store per-page MCID data for content stream tagging
        all_page_mcid_data[page_num] = page_mcid_ops

    # Phase 4: Insert BDC/EMC marked content into page content streams.
    # This wraps every BT/ET text block and content image (Do) with tagged
    # BDC/EMC operators, and marks all other content as /Artifact.
    # Enables the TaggedCont check in Acrobat's accessibility audit.
    tagged_pages = 0
    for page_num in range(page_count):
        if page_num not in all_page_mcid_data:
            continue

        page_mcid_ops = all_page_mcid_data[page_num]

        # Split MCIDs: text elements vs figure elements
        text_mcids = [(mcid, role) for mcid, role in page_mcid_ops
                      if role != "Figure"]
        figure_mcids = [mcid for mcid, role in page_mcid_ops
                        if role == "Figure"]

        # Get content image XObject names for this page (exclude repeated)
        page_image_names = set()
        for img in all_raw_images[page_num]:
            if img.get("img_key") not in repeated_images:
                page_image_names.add(img["name"])

        try:
            count = _tag_page_content_stream(
                pdf, pdf.pages[page_num],
                text_mcids, figure_mcids, page_image_names,
            )
            if count > 0:
                tagged_pages += 1
        except Exception as e:
            print(f"Warning: content stream tagging failed on page "
                  f"{page_num + 1}: {e}", file=sys.stderr)

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
    except Exception as e:
        print(f"Warning: bookmark generation failed: {e}", file=sys.stderr)

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
        except Exception as e:
            print(f"Warning: failed to set link description for {key}: {e}", file=sys.stderr)
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
    output_path = None
    fixes_path = None

    # Parse remaining args: distinguish output PDF from fixes JSON
    for arg in sys.argv[2:]:
        if arg.lower().endswith(".json"):
            fixes_path = arg
        elif arg.lower().endswith(".pdf"):
            output_path = arg
        elif output_path is None:
            output_path = arg
        else:
            fixes_path = arg

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
