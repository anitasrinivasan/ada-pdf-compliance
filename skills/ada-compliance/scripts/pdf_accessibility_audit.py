#!/usr/bin/env python3
"""
PDF Accessibility Audit Script

Analyzes a PDF for ADA/Section 508/PDF-UA compliance metadata.
Outputs structured JSON to stdout with check results.

Usage:
    python3 pdf_accessibility_audit.py <path_to_pdf>

Dependencies: pypdf (stdlib: json, sys, os, re, xml.etree.ElementTree)
"""

import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict

from pypdf import PdfReader


def check_document_properties(reader):
    """Check document info dict metadata fields."""
    results = {}
    meta = reader.metadata or {}

    # Title
    title = meta.get("/Title", "") or ""
    title = str(title).strip()
    if not title:
        results["document_title"] = {
            "status": "fail",
            "value": None,
            "detail": "No document title set",
        }
    elif _looks_like_filename(title):
        results["document_title"] = {
            "status": "warn",
            "value": title,
            "detail": "Title appears to be a filename rather than a descriptive title",
        }
    else:
        results["document_title"] = {
            "status": "pass",
            "value": title,
            "detail": "",
        }

    # Author
    author = meta.get("/Author", "") or ""
    author = str(author).strip()
    results["author"] = {
        "status": "pass" if author else "warn",
        "value": author or None,
        "detail": "" if author else "No author set",
    }

    # Subject
    subject = meta.get("/Subject", "") or ""
    subject = str(subject).strip()
    results["subject"] = {
        "status": "pass" if subject else "warn",
        "value": subject or None,
        "detail": "" if subject else "No subject/description set",
    }

    # Keywords
    keywords = meta.get("/Keywords", "") or ""
    keywords = str(keywords).strip()
    results["keywords"] = {
        "status": "info" if keywords else "info",
        "value": keywords or None,
        "detail": "" if keywords else "No keywords set (optional)",
    }

    # Producer / Creator
    results["producer"] = {
        "status": "info",
        "value": str(meta.get("/Producer", "") or "").strip() or None,
        "detail": "",
    }
    results["creator"] = {
        "status": "info",
        "value": str(meta.get("/Creator", "") or "").strip() or None,
        "detail": "",
    }

    return results


def check_accessibility_flags(reader):
    """Check catalog-level accessibility flags."""
    results = {}
    root = reader.trailer["/Root"]

    # Tagged PDF
    mark_info = root.get("/MarkInfo")
    if mark_info:
        mark_info = _resolve(mark_info)
        marked = mark_info.get("/Marked", False)
        results["tagged_pdf"] = {
            "status": "pass" if marked else "fail",
            "value": bool(marked),
            "detail": "" if marked else "PDF is not marked as tagged",
        }
    else:
        results["tagged_pdf"] = {
            "status": "fail",
            "value": False,
            "detail": "No MarkInfo dictionary found — PDF is not tagged",
        }

    # Language
    lang = root.get("/Lang")
    if lang:
        lang = str(lang).strip()
    results["language"] = {
        "status": "pass" if lang else "fail",
        "value": lang or None,
        "detail": "" if lang else "No document language set",
    }

    # Display Doc Title
    viewer_prefs = root.get("/ViewerPreferences")
    if viewer_prefs:
        viewer_prefs = _resolve(viewer_prefs)
        display_title = viewer_prefs.get("/DisplayDocTitle", False)
        results["display_doc_title"] = {
            "status": "pass" if display_title else "fail",
            "value": bool(display_title),
            "detail": ""
            if display_title
            else "Initial view does not show document title",
        }
    else:
        results["display_doc_title"] = {
            "status": "fail",
            "value": False,
            "detail": "No ViewerPreferences found — display title not enabled",
        }

    # PDF/UA identifier from XMP
    pdfua_part = _check_pdfua_xmp(reader)
    results["pdfua_identifier"] = {
        "status": "pass" if pdfua_part else "warn",
        "value": pdfua_part,
        "detail": f"PDF/UA-{pdfua_part}" if pdfua_part else "No PDF/UA identifier in XMP metadata",
    }

    return results


def analyze_structure_tree(reader):
    """Walk the structure tree and analyze tags."""
    root = reader.trailer["/Root"]
    struct_root = root.get("/StructTreeRoot")
    if not struct_root:
        return {
            "has_structure_tree": False,
            "tag_counts": {},
            "heading_analysis": {
                "h1_count": 0,
                "hierarchy_valid": False,
                "sequence": [],
                "issues": ["No structure tree found"],
            },
            "figure_analysis": {
                "total": 0,
                "with_alt": 0,
                "without_alt": 0,
                "figures_missing_alt": [],
            },
            "table_analysis": {"total": 0, "with_headers": 0, "without_headers": 0, "tables_detail": []},
            "list_analysis": {"total": 0, "properly_structured": 0},
        }

    struct_root = _resolve(struct_root)
    tag_counts = defaultdict(int)
    heading_sequence = []
    figures_missing_alt = []
    figures_with_alt = []
    figure_index = 0
    tables = []
    lists = []
    visited_ids = set()  # Cycle detection
    MAX_DEPTH = 100

    def walk(node, depth=0, page_hint=None):
        nonlocal figure_index
        if depth > MAX_DEPTH:
            return
        if not isinstance(node, dict):
            return

        # Cycle detection using id()
        node_id = id(node)
        if node_id in visited_ids:
            return
        visited_ids.add(node_id)

        tag = str(node.get("/S", "")).strip()
        if tag:
            tag_counts[tag] += 1

        # Track page from /Pg
        pg = node.get("/Pg")
        current_page = page_hint
        if pg:
            pg_obj = _resolve(pg)
            current_page = _find_page_number(reader, pg_obj)

        # Headings
        if tag in ("/H1", "/H2", "/H3", "/H4", "/H5", "/H6", "H1", "H2", "H3", "H4", "H5", "H6"):
            level = int(tag[-1])
            heading_sequence.append({"level": level, "tag": tag, "page": current_page})

        # Figures
        if tag in ("/Figure", "Figure"):
            alt = node.get("/Alt")
            fig_info = {"index": figure_index, "page": current_page}
            if alt:
                fig_info["alt"] = str(alt)
                figures_with_alt.append(fig_info)
            else:
                figures_missing_alt.append(fig_info)
            figure_index += 1

        # Tables
        if tag in ("/Table", "Table"):
            table_info = _analyze_table(node, current_page)
            tables.append(table_info)

        # Lists
        if tag in ("/L", "L"):
            list_info = _analyze_list(node)
            lists.append(list_info)

        # Recurse into children
        kids = node.get("/K")
        if kids is not None:
            kids = _resolve(kids)
            if isinstance(kids, list):
                for child in kids:
                    child = _resolve(child)
                    if isinstance(child, dict):
                        walk(child, depth + 1, current_page)
            elif isinstance(kids, dict):
                walk(kids, depth + 1, current_page)

    walk(struct_root)

    # Clean tag names (remove leading /)
    clean_counts = {}
    for k, v in tag_counts.items():
        clean_key = k.lstrip("/")
        clean_counts[clean_key] = clean_counts.get(clean_key, 0) + v

    # Heading analysis
    heading_issues = []
    h1_count = sum(1 for h in heading_sequence if h["level"] == 1)
    if h1_count == 0:
        heading_issues.append("No H1 heading found")
    elif h1_count > 1:
        heading_issues.append(f"Multiple H1 headings found ({h1_count})")

    for i in range(1, len(heading_sequence)):
        prev = heading_sequence[i - 1]["level"]
        curr = heading_sequence[i]["level"]
        if curr > prev + 1:
            heading_issues.append(
                f"Heading level skips from H{prev} to H{curr} (page {heading_sequence[i].get('page', '?')})"
            )

    # Table analysis
    tables_with_headers = sum(1 for t in tables if t.get("has_headers"))
    tables_without_headers = sum(1 for t in tables if not t.get("has_headers"))

    # List analysis
    properly_structured = sum(1 for l in lists if l.get("proper"))

    return {
        "has_structure_tree": True,
        "tag_counts": clean_counts,
        "heading_analysis": {
            "h1_count": h1_count,
            "hierarchy_valid": len(heading_issues) == 0,
            "sequence": [
                {"level": h["level"], "page": h.get("page")}
                for h in heading_sequence
            ],
            "issues": heading_issues,
        },
        "figure_analysis": {
            "total": len(figures_with_alt) + len(figures_missing_alt),
            "with_alt": len(figures_with_alt),
            "without_alt": len(figures_missing_alt),
            "figures_missing_alt": figures_missing_alt,
        },
        "table_analysis": {
            "total": len(tables),
            "with_headers": tables_with_headers,
            "without_headers": tables_without_headers,
            "tables_detail": tables,
        },
        "list_analysis": {
            "total": len(lists),
            "properly_structured": properly_structured,
        },
    }


def analyze_fonts(reader):
    """Check font embedding across all pages."""
    all_fonts = {}

    for page_num, page in enumerate(reader.pages):
        resources = page.get("/Resources")
        if not resources:
            continue
        resources = _resolve(resources)
        fonts = resources.get("/Font")
        if not fonts:
            continue
        fonts = _resolve(fonts)

        for font_name, font_ref in fonts.items():
            if font_name in all_fonts:
                continue
            font_obj = _resolve(font_ref)
            embedded = _is_font_embedded(font_obj)
            base_font = str(font_obj.get("/BaseFont", font_name)).lstrip("/")
            all_fonts[font_name] = {
                "name": base_font,
                "embedded": embedded,
                "first_seen_page": page_num + 1,
            }

    embedded_count = sum(1 for f in all_fonts.values() if f["embedded"])
    unembedded = [f for f in all_fonts.values() if not f["embedded"]]

    return {
        "total_fonts": len(all_fonts),
        "embedded": embedded_count,
        "not_embedded": len(unembedded),
        "unembedded_fonts": [f["name"] for f in unembedded],
        "all_fonts": list(all_fonts.values()),
    }


def analyze_links(reader):
    """Analyze link annotations across all pages."""
    total_links = 0
    non_descriptive = []

    for page_num, page in enumerate(reader.pages):
        annots = page.get("/Annots")
        if not annots:
            continue
        annots = _resolve(annots)
        if not isinstance(annots, list):
            continue

        for annot_ref in annots:
            annot = _resolve(annot_ref)
            if not isinstance(annot, dict):
                continue
            subtype = str(annot.get("/Subtype", ""))
            if subtype not in ("/Link", "Link"):
                continue

            total_links += 1
            contents = str(annot.get("/Contents", "") or "").strip()
            action = annot.get("/A")
            uri = ""
            if action:
                action = _resolve(action)
                uri = str(action.get("/URI", "") or "")

            if not contents:
                non_descriptive.append({
                    "page": page_num + 1,
                    "issue": "empty_contents",
                    "uri": uri,
                    "detail": "Link has no descriptive text",
                })
            elif contents.lower() in ("click here", "here", "link", "more", "read more"):
                non_descriptive.append({
                    "page": page_num + 1,
                    "issue": "generic_text",
                    "text": contents,
                    "uri": uri,
                    "detail": f'Link uses generic text "{contents}"',
                })
            elif re.match(r"https?://", contents):
                non_descriptive.append({
                    "page": page_num + 1,
                    "issue": "raw_url",
                    "text": contents,
                    "uri": uri,
                    "detail": "Link text is a raw URL",
                })

    return {
        "total": total_links,
        "with_descriptive_text": total_links - len(non_descriptive),
        "non_descriptive": len(non_descriptive),
        "non_descriptive_links": non_descriptive,
    }


def analyze_navigation(reader):
    """Check bookmarks and page labels."""
    root = reader.trailer["/Root"]

    # Bookmarks
    outlines = root.get("/Outlines")
    bookmark_count = 0
    if outlines:
        outlines = _resolve(outlines)
        bookmark_count = _count_bookmarks(outlines)

    # Page labels
    page_labels = root.get("/PageLabels")
    has_page_labels = page_labels is not None

    page_count = len(reader.pages)

    return {
        "has_bookmarks": bookmark_count > 0,
        "bookmark_count": bookmark_count,
        "has_page_labels": has_page_labels,
        "page_count": page_count,
        "needs_bookmarks": page_count > 20 and bookmark_count == 0,
    }


def analyze_forms(reader):
    """Check for form fields."""
    root = reader.trailer["/Root"]
    acroform = root.get("/AcroForm")
    if not acroform:
        return {"has_forms": False, "field_count": 0}

    acroform = _resolve(acroform)
    fields = acroform.get("/Fields", [])
    fields = _resolve(fields)
    field_count = len(fields) if isinstance(fields, list) else 0

    return {
        "has_forms": True,
        "field_count": field_count,
    }


# --- Helper functions ---


def _resolve(obj):
    """Resolve IndirectObject references, skipping numeric/string primitives."""
    from pypdf.generic import NumberObject
    # Don't try to resolve numeric or string primitives
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
    except Exception:
        pass
    return obj


def _looks_like_filename(title):
    """Heuristic: does this title look like a filename?"""
    extensions = [".pdf", ".pptx", ".ppt", ".docx", ".doc", ".xlsx", ".xls"]
    title_lower = title.lower()
    for ext in extensions:
        if title_lower.endswith(ext):
            return True
    if re.match(r"^[A-Za-z0-9_\-. ]+\.[a-z]{2,4}$", title):
        return True
    return False


def _check_pdfua_xmp(reader):
    """Check for PDF/UA identifier in XMP metadata."""
    try:
        root = reader.trailer["/Root"]
        metadata = root.get("/Metadata")
        if not metadata:
            return None
        metadata = _resolve(metadata)
        xmp_data = metadata.get_data()
        if isinstance(xmp_data, bytes):
            xmp_data = xmp_data.decode("utf-8", errors="replace")

        # Look for pdfuaid:part — handles both inline and namespace-declared forms:
        #   <pdfuaid:part>1</pdfuaid:part>
        #   <pdfuaid:part xmlns:pdfuaid="...">1</pdfuaid:part>
        match = re.search(
            r"pdfuaid:part[^>]*>\s*(\d+)",
            xmp_data, re.IGNORECASE
        )
        if match:
            return match.group(1)

        # Try XML parsing with namespace expansion
        try:
            xmp_root = ET.fromstring(xmp_data)
            pdfuaid_ns = "http://www.aiim.org/pdfua/ns/id/"
            for elem in xmp_root.iter():
                tag = elem.tag.lower()
                # Match expanded form {ns}part or prefixed form pdfuaid:part
                if (tag == f"{{{pdfuaid_ns}}}part"
                        or ("part" in tag and "pdfuaid" in tag)):
                    if elem.text and elem.text.strip():
                        return elem.text.strip()
        except ET.ParseError:
            pass

        return None
    except Exception:
        return None


_page_id_cache = {}


def _find_page_number(reader, page_obj):
    """Find the page number for a page object (cached)."""
    global _page_id_cache
    if not _page_id_cache:
        # Build cache on first call
        for i, page in enumerate(reader.pages):
            try:
                _page_id_cache[id(page.get_object())] = i + 1
            except Exception:
                pass
    try:
        return _page_id_cache.get(id(page_obj))
    except Exception:
        return None


def _analyze_table(node, page):
    """Check if a table has header cells."""
    has_th = False
    seen = set()

    def walk_table(n, depth=0):
        nonlocal has_th
        if depth > 50:
            return
        n = _resolve(n)
        if not isinstance(n, dict):
            return
        nid = id(n)
        if nid in seen:
            return
        seen.add(nid)
        tag = str(n.get("/S", ""))
        if tag in ("/TH", "TH"):
            has_th = True
            return
        kids = n.get("/K")
        if kids:
            kids = _resolve(kids)
            if isinstance(kids, list):
                for child in kids:
                    walk_table(child, depth + 1)
            elif isinstance(kids, dict):
                walk_table(kids, depth + 1)

    walk_table(node)

    # Count rows
    row_count = 0
    col_count = 0
    seen2 = set()

    def count_rows(n, depth=0):
        nonlocal row_count, col_count
        if depth > 50:
            return
        n = _resolve(n)
        if not isinstance(n, dict):
            return
        nid = id(n)
        if nid in seen2:
            return
        seen2.add(nid)
        tag = str(n.get("/S", ""))
        if tag in ("/TR", "TR"):
            row_count += 1
            if row_count == 1:
                kids = n.get("/K")
                if kids:
                    kids = _resolve(kids)
                    if isinstance(kids, list):
                        col_count = len(kids)
        kids = n.get("/K")
        if kids:
            kids = _resolve(kids)
            if isinstance(kids, list):
                for child in kids:
                    count_rows(child, depth + 1)
            elif isinstance(kids, dict):
                count_rows(kids, depth + 1)

    count_rows(node)

    return {
        "page": page,
        "has_headers": has_th,
        "rows": row_count,
        "cols": col_count,
    }


def _analyze_list(node):
    """Check if a list is properly structured with LI > Lbl + LBody."""
    has_li = False
    has_lbl = False
    has_lbody = False
    seen = set()

    def walk_list(n, depth=0):
        nonlocal has_li, has_lbl, has_lbody
        if depth > 50:
            return
        n = _resolve(n)
        if not isinstance(n, dict):
            return
        nid = id(n)
        if nid in seen:
            return
        seen.add(nid)
        tag = str(n.get("/S", ""))
        if tag in ("/LI", "LI"):
            has_li = True
        elif tag in ("/Lbl", "Lbl"):
            has_lbl = True
        elif tag in ("/LBody", "LBody"):
            has_lbody = True
        kids = n.get("/K")
        if kids:
            kids = _resolve(kids)
            if isinstance(kids, list):
                for child in kids:
                    walk_list(child, depth + 1)
            elif isinstance(kids, dict):
                walk_list(kids, depth + 1)

    walk_list(node)
    return {"proper": has_li and has_lbody}


def _is_font_embedded(font_obj):
    """Check if a font is embedded."""
    font_obj = _resolve(font_obj)

    # Direct FontDescriptor check
    fd = font_obj.get("/FontDescriptor")
    if fd:
        fd = _resolve(fd)
        if fd.get("/FontFile") or fd.get("/FontFile2") or fd.get("/FontFile3"):
            return True

    # Type0 composite font — check DescendantFonts
    descendants = font_obj.get("/DescendantFonts")
    if descendants:
        descendants = _resolve(descendants)
        if isinstance(descendants, list):
            for desc in descendants:
                desc = _resolve(desc)
                if isinstance(desc, dict):
                    fd = desc.get("/FontDescriptor")
                    if fd:
                        fd = _resolve(fd)
                        if fd.get("/FontFile") or fd.get("/FontFile2") or fd.get("/FontFile3"):
                            return True

    return False


def _count_bookmarks(outlines, max_count=500):
    """Count bookmark entries with cycle detection."""
    count = 0
    seen = set()
    try:
        first = outlines.get("/First")
        if not first:
            return 0
        current = _resolve(first)
        while current and count < max_count:
            node_id = id(current)
            if node_id in seen:
                break
            seen.add(node_id)
            title = current.get("/Title")
            if title:
                count += 1
            # Count children recursively
            child_first = current.get("/First")
            if child_first:
                count += _count_bookmarks(current, max_count - count)
            next_item = current.get("/Next")
            if next_item:
                current = _resolve(next_item)
            else:
                break
    except Exception:
        pass
    return count


def audit_pdf(filepath):
    """Run all accessibility checks on a PDF file."""
    try:
        reader = PdfReader(filepath)
    except Exception as e:
        return {
            "file": filepath,
            "error": str(e),
            "page_count": 0,
        }

    result = {
        "file": filepath,
        "filename": os.path.basename(filepath),
        "page_count": len(reader.pages),
        "pdf_version": reader.pdf_header if hasattr(reader, "pdf_header") else None,
    }

    result["document_properties"] = check_document_properties(reader)
    result["accessibility_flags"] = check_accessibility_flags(reader)
    result["structure"] = analyze_structure_tree(reader)
    result["fonts"] = analyze_fonts(reader)
    result["links"] = analyze_links(reader)
    result["navigation"] = analyze_navigation(reader)
    result["forms"] = analyze_forms(reader)

    # Compute summary
    all_checks = {}
    all_checks.update(result["document_properties"])
    all_checks.update(result["accessibility_flags"])

    # Add derived checks
    struct = result["structure"]
    if not struct["has_structure_tree"]:
        all_checks["structure_tree"] = {
            "status": "fail",
            "detail": "No structure tree found",
        }
    else:
        all_checks["structure_tree"] = {"status": "pass", "detail": ""}

    if struct["figure_analysis"]["without_alt"] > 0:
        all_checks["figure_alt_text"] = {
            "status": "fail",
            "detail": f"{struct['figure_analysis']['without_alt']} figures missing alt text",
        }
    elif struct["figure_analysis"]["total"] > 0:
        all_checks["figure_alt_text"] = {
            "status": "pass",
            "detail": f"All {struct['figure_analysis']['total']} figures have alt text",
        }

    if not struct["heading_analysis"]["hierarchy_valid"]:
        all_checks["heading_hierarchy"] = {
            "status": "warn",
            "detail": "; ".join(struct["heading_analysis"]["issues"]),
        }
    else:
        all_checks["heading_hierarchy"] = {"status": "pass", "detail": ""}

    if struct["table_analysis"]["without_headers"] > 0:
        all_checks["table_headers"] = {
            "status": "warn",
            "detail": f"{struct['table_analysis']['without_headers']} tables missing header cells",
        }

    if result["fonts"]["not_embedded"] > 0:
        all_checks["font_embedding"] = {
            "status": "warn",
            "detail": f"Unembedded fonts: {', '.join(result['fonts']['unembedded_fonts'])}",
        }
    else:
        all_checks["font_embedding"] = {"status": "pass", "detail": ""}

    if result["links"]["non_descriptive"] > 0:
        all_checks["descriptive_links"] = {
            "status": "warn",
            "detail": f"{result['links']['non_descriptive']} links with non-descriptive text",
        }

    if result["navigation"]["needs_bookmarks"]:
        all_checks["bookmarks"] = {
            "status": "warn",
            "detail": f"Document has {result['navigation']['page_count']} pages but no bookmarks",
        }

    # Count by status
    summary = {"pass": 0, "warn": 0, "fail": 0, "info": 0}
    for check in all_checks.values():
        status = check.get("status", "info")
        summary[status] = summary.get(status, 0) + 1

    result["summary"] = summary
    result["all_checks"] = all_checks

    return result


def summarize_audit(result):
    """Return a compact summary of an audit result (no font list, heading sequence, etc.)."""
    if "error" in result:
        return result

    return {
        "file": result.get("file"),
        "filename": result.get("filename"),
        "page_count": result.get("page_count"),
        "summary": result.get("summary"),
        "has_structure_tree": result.get("structure", {}).get("has_structure_tree", False),
        "figures_missing_alt": result.get("structure", {}).get("figure_analysis", {}).get("without_alt", 0),
        "non_descriptive_links": result.get("links", {}).get("non_descriptive", 0),
        "has_bookmarks": result.get("navigation", {}).get("has_bookmarks", False),
        "bookmark_count": result.get("navigation", {}).get("bookmark_count", 0),
        "unembedded_fonts": result.get("fonts", {}).get("not_embedded", 0),
        "key_issues": [
            check_name
            for check_name, check in result.get("all_checks", {}).items()
            if check.get("status") in ("fail", "warn")
        ],
    }


def main():
    args = sys.argv[1:]

    # Parse flags
    summary_mode = False
    filepaths = []
    for arg in args:
        if arg == "--summary":
            summary_mode = True
        else:
            filepaths.append(arg)

    if not filepaths:
        print(json.dumps({"error": "Usage: python3 pdf_accessibility_audit.py [--summary] <pdf> [pdf2 pdf3 ...]"}))
        sys.exit(1)

    # Process all files
    results = []
    for filepath in filepaths:
        global _page_id_cache
        _page_id_cache = {}  # Reset cache between files
        if not os.path.isfile(filepath):
            results.append({"file": filepath, "error": f"File not found: {filepath}"})
            continue
        result = audit_pdf(filepath)
        if summary_mode:
            result = summarize_audit(result)
        results.append(result)

    # Backwards compatible: single file = single object, multiple = array
    if len(results) == 1:
        print(json.dumps(results[0], indent=2, default=str))
    else:
        print(json.dumps(results, indent=2, default=str))


if __name__ == "__main__":
    main()
