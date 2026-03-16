#!/usr/bin/env python3
"""
PDF Metadata Fix Script

Reads a PDF and a JSON fixes file, applies accessibility metadata fixes,
and writes a new PDF with _accessible suffix.

Usage:
    python3 pdf_metadata_fix.py <path_to_pdf> <path_to_fixes_json>

The fixes JSON should have this structure:
{
    "title": "Descriptive Document Title",
    "author": "Author Name",
    "subject": "Document description",
    "language": "en-US",
    "display_doc_title": true,
    "set_tagged": true,
    "set_pdfua": true,
    "generate_bookmarks": true,
    "link_descriptions": {
        "1_0": "YouTube: Technical Due Process lecture",
        "5_0": "DHS AI use case inventory for ICE"
    },
    "alt_texts": {
        "0": "Description of first figure",
        "3": "Description of fourth figure"
    }
}

All fields are optional — only provided fields will be updated.
link_descriptions keys are "pageNum_annotIndex" (1-indexed page numbers).

Dependencies: pypdf (stdlib: json, sys, os, re, copy)
"""

import copy
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    BooleanObject,
    DictionaryObject,
    NameObject,
    NullObject,
    TextStringObject,
    DecodedStreamObject,
    create_string_object,
)


def apply_fixes(input_path, fixes):
    """Apply metadata fixes to a PDF and return the output path."""
    reader = PdfReader(input_path)
    writer = PdfWriter(clone_from=input_path)

    changes = []

    # 1. Document metadata (Title, Author, Subject)
    if any(k in fixes for k in ("title", "author", "subject", "keywords")):
        meta = {}
        if "title" in fixes:
            meta["/Title"] = fixes["title"]
            changes.append(f'Title set to "{fixes["title"]}"')
        if "author" in fixes:
            meta["/Author"] = fixes["author"]
            changes.append(f'Author set to "{fixes["author"]}"')
        if "subject" in fixes:
            meta["/Subject"] = fixes["subject"]
            changes.append(f'Subject set to "{fixes["subject"]}"')
        if "keywords" in fixes:
            meta["/Keywords"] = fixes["keywords"]
            changes.append(f'Keywords set to "{fixes["keywords"]}"')
        writer.add_metadata(meta)

    # 2. Language
    if "language" in fixes:
        lang = fixes["language"]
        writer._root_object[NameObject("/Lang")] = TextStringObject(lang)
        changes.append(f"Language set to {lang}")

    # 3. Display Doc Title
    if fixes.get("display_doc_title"):
        if "/ViewerPreferences" not in writer._root_object:
            writer._root_object[NameObject("/ViewerPreferences")] = DictionaryObject()
        vp = writer._root_object["/ViewerPreferences"]
        if hasattr(vp, "get_object"):
            vp = vp.get_object()
        vp[NameObject("/DisplayDocTitle")] = BooleanObject(True)
        changes.append("Display doc title enabled")

    # 4. Tagged PDF flag
    if fixes.get("set_tagged"):
        if "/MarkInfo" not in writer._root_object:
            writer._root_object[NameObject("/MarkInfo")] = DictionaryObject()
        mi = writer._root_object["/MarkInfo"]
        if hasattr(mi, "get_object"):
            mi = mi.get_object()
        mi[NameObject("/Marked")] = BooleanObject(True)
        changes.append("Tagged PDF flag set to true")

    # 5. Alt text for figures
    alt_texts = fixes.get("alt_texts", {})
    if alt_texts:
        alt_count = _embed_alt_texts(writer, alt_texts)
        if alt_count > 0:
            changes.append(f"Alt text added to {alt_count} figures")

    # 6. PDF/UA identifier in XMP
    if fixes.get("set_pdfua"):
        _set_pdfua_xmp(writer)
        changes.append("PDF/UA-1 identifier added to XMP metadata")

    # 7. Generate bookmarks from page titles
    if fixes.get("generate_bookmarks"):
        bookmark_count = _generate_bookmarks(reader, writer)
        if bookmark_count > 0:
            changes.append(f"Bookmarks generated for {bookmark_count} pages")

    # 8. Fix link descriptive text
    link_descs = fixes.get("link_descriptions", {})
    if link_descs:
        link_count = _fix_link_descriptions(writer, link_descs)
        if link_count > 0:
            changes.append(f"Descriptive text added to {link_count} links")

    # Write output
    base, ext = os.path.splitext(input_path)
    output_path = f"{base}_accessible{ext}"
    with open(output_path, "wb") as f:
        writer.write(f)

    return {
        "input": input_path,
        "output": output_path,
        "changes": changes,
        "change_count": len(changes),
    }


def _embed_alt_texts(writer, alt_texts):
    """Walk the structure tree and set alt text on figure elements."""
    root = writer._root_object
    struct_root = root.get("/StructTreeRoot")
    if not struct_root:
        return 0

    struct_root = _resolve(struct_root)
    figure_index = [0]
    updated_count = [0]

    def walk(node):
        if not isinstance(node, dict):
            return
        node = _resolve(node)
        tag = str(node.get("/S", "")).strip()

        if tag in ("/Figure", "Figure"):
            idx_str = str(figure_index[0])
            if idx_str in alt_texts:
                alt_text = alt_texts[idx_str]
                try:
                    node[NameObject("/Alt")] = TextStringObject(alt_text)
                    updated_count[0] += 1
                except Exception as e:
                    print(f"Warning: failed to set alt text on figure {idx_str}: {e}", file=sys.stderr)
            figure_index[0] += 1

        kids = node.get("/K")
        if kids is not None:
            kids = _resolve(kids)
            if isinstance(kids, list):
                for child in kids:
                    child = _resolve(child)
                    if isinstance(child, dict):
                        walk(child)
            elif isinstance(kids, dict):
                walk(kids)

    walk(struct_root)
    return updated_count[0]


def _generate_bookmarks(reader, writer):
    """Generate bookmarks by extracting the largest/boldest text from each page."""
    # Google Slides PDFs have a NullObject /Outlines entry that causes
    # add_outline_item to fail. Detect and remove it.
    root = writer._root_object
    outlines_ref = root.get('/Outlines')
    if outlines_ref is not None:
        outlines_obj = outlines_ref.get_object() if hasattr(outlines_ref, 'get_object') else outlines_ref
        if isinstance(outlines_obj, NullObject):
            del root[NameObject('/Outlines')]

    bookmark_count = 0

    for page_num in range(len(reader.pages)):
        title = _extract_page_title(reader.pages[page_num])
        if title:
            # Clean up title text
            title = title.strip()
            if len(title) > 80:
                title = title[:77] + "..."
            try:
                writer.add_outline_item(title=title, page_number=page_num)
                bookmark_count += 1
            except Exception as e:
                print(f"Warning: failed to add bookmark for page {page_num + 1}: {e}", file=sys.stderr)

    return bookmark_count


class _TitleFound(Exception):
    """Raised to short-circuit text extraction once we have enough data."""
    pass


def _extract_page_title(page):
    """Extract the likely title from a page using font size heuristics.

    For slide decks: the largest text near the top of the page is the title.
    Uses early exit: stops after 30 text items to avoid parsing entire pages.
    """
    text_items = []

    def visitor(text, ctm, tm, font_dict, font_size):
        if not text or not text.strip():
            return
        # tm[5] is the y-position (higher = closer to top of page)
        # font_size is the size of the text
        y_pos = tm[5] if tm else 0
        effective_size = font_size
        # Scale by CTM if significant
        if ctm and len(ctm) >= 4:
            scale = abs(ctm[3]) if ctm[3] != 0 else abs(ctm[0])
            if scale > 0:
                effective_size = font_size * scale

        # Check if font is bold from font_dict BaseFont name
        is_bold = False
        if font_dict:
            base_font = str(font_dict.get("/BaseFont", "")).lower()
            is_bold = "bold" in base_font

        text_items.append({
            "text": text.strip(),
            "size": effective_size,
            "y_pos": y_pos,
            "is_bold": is_bold,
        })

        # Early exit: after 30 items we have enough to find the title
        if len(text_items) >= 30:
            raise _TitleFound()

    try:
        page.extract_text(visitor_text=visitor)
    except _TitleFound:
        pass  # We have enough text items
    except Exception as e:
        print(f"Warning: text extraction failed during title detection: {e}", file=sys.stderr)
        return None

    if not text_items:
        return None

    # Find the largest text (prioritize bold, high position)
    max_size = max(item["size"] for item in text_items)

    # Get all text items at or near the max size (within 10%)
    title_items = [
        item for item in text_items
        if item["size"] >= max_size * 0.9
    ]

    if not title_items:
        return None

    # Sort by y-position (highest first — top of page) then concatenate
    title_items.sort(key=lambda x: -x["y_pos"])

    # Take the first line of largest text as the title
    title = " ".join(item["text"] for item in title_items[:3])

    # Clean up whitespace
    title = re.sub(r"\s+", " ", title).strip()
    return title if title else None


def _fix_link_descriptions(writer, link_descs):
    """Set descriptive /Contents on link annotations.

    link_descs: dict mapping "pageNum_annotIndex" to description string.
    Page numbers are 1-indexed to match audit script output.
    """
    updated_count = 0

    for key, description in link_descs.items():
        try:
            parts = key.split("_")
            page_num = int(parts[0]) - 1  # Convert to 0-indexed
            annot_idx = int(parts[1]) if len(parts) > 1 else 0

            page = writer.pages[page_num]
            annots = page.get("/Annots")
            if not annots:
                continue
            annots = _resolve(annots)
            if not isinstance(annots, list):
                continue

            # Find link annotations on this page
            link_idx = 0
            for annot_ref in annots:
                annot = _resolve(annot_ref)
                if not isinstance(annot, dict):
                    continue
                subtype = str(annot.get("/Subtype", ""))
                if subtype not in ("/Link", "Link"):
                    continue

                if link_idx == annot_idx:
                    annot[NameObject("/Contents")] = TextStringObject(description)
                    updated_count += 1
                    break
                link_idx += 1
        except Exception as e:
            print(f"Warning: failed to set link description for {key}: {e}", file=sys.stderr)
            continue

    return updated_count


def _set_pdfua_xmp(writer):
    """Add PDF/UA-1 identifier to XMP metadata."""
    root = writer._root_object
    metadata = root.get("/Metadata")

    pdfuaid_ns = "http://www.aiim.org/pdfua/ns/id/"

    if metadata:
        metadata = _resolve(metadata)
        try:
            xmp_data = metadata.get_data()
            if isinstance(xmp_data, bytes):
                xmp_str = xmp_data.decode("utf-8", errors="replace")
            else:
                xmp_str = xmp_data

            # Check if pdfuaid:part already exists
            if "pdfuaid:part" in xmp_str or "pdfuaid" in xmp_str:
                return  # Already has PDF/UA identifier

            # Insert pdfuaid declaration into the rdf:Description
            # Find the main rdf:Description and add pdfuaid:part
            insertion = (
                f'\n    xmlns:pdfuaid="{pdfuaid_ns}"'
            )
            part_element = '\n    <pdfuaid:part>1</pdfuaid:part>'

            # Add namespace to first rdf:Description
            xmp_str = re.sub(
                r'(<rdf:Description[^>]*)(>)',
                lambda m: m.group(1) + insertion + m.group(2) + part_element,
                xmp_str,
                count=1,
            )

            # Write back (must be indirect object for Preview compatibility)
            new_stream = DecodedStreamObject()
            new_stream.set_data(xmp_str.encode("utf-8"))
            new_stream[NameObject("/Type")] = NameObject("/Metadata")
            new_stream[NameObject("/Subtype")] = NameObject("/XML")
            root[NameObject("/Metadata")] = writer._add_object(new_stream)
        except Exception as e:
            print(f"Warning: failed to update existing XMP metadata: {e}", file=sys.stderr)
    else:
        # Create minimal XMP with PDF/UA identifier
        xmp = f"""<?xpacket begin="\xef\xbb\xbf" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
  <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
    <rdf:Description rdf:about=""
      xmlns:pdfuaid="{pdfuaid_ns}">
      <pdfuaid:part>1</pdfuaid:part>
    </rdf:Description>
  </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>"""
        new_stream = DecodedStreamObject()
        new_stream.set_data(xmp.encode("utf-8"))
        new_stream[NameObject("/Type")] = NameObject("/Metadata")
        new_stream[NameObject("/Subtype")] = NameObject("/XML")
        root[NameObject("/Metadata")] = writer._add_object(new_stream)


def _resolve(obj):
    """Resolve IndirectObject references, skipping numeric primitives."""
    from pypdf.generic import NumberObject
    if isinstance(obj, (int, float, str, bytes, bool)):
        return obj
    if isinstance(obj, NumberObject):
        return obj
    try:
        while hasattr(obj, "get_object") and not isinstance(obj, NumberObject):
            resolved = obj.get_object()
            if resolved is obj:
                break
            obj = resolved
    except Exception as e:
        print(f"Warning: failed to resolve indirect object: {e}", file=sys.stderr)
    return obj


def main():
    args = sys.argv[1:]

    # Batch mode: --batch <batch_json>
    if len(args) >= 2 and args[0] == "--batch":
        batch_path = args[1]
        if not os.path.isfile(batch_path):
            print(json.dumps({"error": f"Batch JSON not found: {batch_path}"}))
            sys.exit(1)
        with open(batch_path, "r") as f:
            batch = json.load(f)
        results = []
        for entry in batch:
            input_path = entry.get("input")
            fixes = entry.get("fixes", {})
            if not input_path or not os.path.isfile(input_path):
                results.append({"input": input_path, "error": "File not found"})
                continue
            result = apply_fixes(input_path, fixes)
            results.append(result)
        print(json.dumps(results, indent=2, default=str))
        return

    # Single-file mode (backwards compatible)
    if len(args) < 2:
        print(json.dumps({
            "error": "Usage: python3 pdf_metadata_fix.py <pdf> <fixes_json>\n"
                     "       python3 pdf_metadata_fix.py --batch <batch_json>"
        }))
        sys.exit(1)

    pdf_path = args[0]
    fixes_path = args[1]

    if not os.path.isfile(pdf_path):
        print(json.dumps({"error": f"PDF not found: {pdf_path}"}))
        sys.exit(1)

    if not os.path.isfile(fixes_path):
        print(json.dumps({"error": f"Fixes JSON not found: {fixes_path}"}))
        sys.exit(1)

    with open(fixes_path, "r") as f:
        fixes = json.load(f)

    result = apply_fixes(pdf_path, fixes)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
