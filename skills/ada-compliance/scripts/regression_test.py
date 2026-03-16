#!/usr/bin/env python3
"""
Regression test for pdf_structure_generator.py

Compares pikepdf-generated structure trees against Acrobat-tagged ground truth.
Run after any heuristic changes to verify improvements don't cause regressions.

Usage:
    python3 regression_test.py [test_dir]

Default test_dir: ../../../test files/
Expects pairs: <name>.pdf (original) + <name>_acrobat_tagged.pdf (ground truth)

Output: comparison table + pass/warn/fail per metric per file.
"""

import json
import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
GENERATOR = os.path.join(SCRIPT_DIR, "pdf_structure_generator.py")
AUDIT = os.path.join(SCRIPT_DIR, "pdf_accessibility_audit.py")

# Tolerance thresholds: pikepdf count must be within this ratio of Acrobat
THRESHOLDS = {
    "H1":     {"ratio": 2.0, "severity": "warn"},
    "H2":     {"ratio": 2.0, "severity": "warn"},
    "H3":     {"ratio": 3.0, "severity": "info"},   # H3 detection is still developing
    "H4":     {"ratio": 3.0, "severity": "info"},
    "Figure": {"ratio": 2.0, "severity": "warn"},
    "Table":  {"ratio": 2.0, "severity": "warn"},
    "LBody":  {"ratio": 2.0, "severity": "warn"},
    "Lbl":    {"ratio": 2.0, "severity": "warn"},
}


def find_test_pairs(test_dir):
    """Find original + acrobat_tagged PDF pairs."""
    pairs = []
    files = os.listdir(test_dir)
    tagged = [f for f in files if f.endswith("_acrobat_tagged.pdf")]

    for tagged_file in sorted(tagged):
        # Find the original file
        # tagged_file = "Foo_acrobat_tagged.pdf" → original could be "Foo.pdf"
        base = tagged_file.replace("_acrobat_tagged.pdf", "")
        original = None
        for f in files:
            if f == tagged_file or "_pikepdf" in f or "_accessible" in f:
                continue
            f_base = os.path.splitext(f)[0]
            if f_base == base or f.startswith(base):
                original = f
                break

        if original:
            pairs.append({
                "label": base[:40],
                "original": os.path.join(test_dir, original),
                "acrobat": os.path.join(test_dir, tagged_file),
            })

    return pairs


def run_audit(pdf_path):
    """Run accessibility audit and return parsed JSON."""
    result = subprocess.run(
        ["python3", AUDIT, pdf_path],
        capture_output=True, text=True, timeout=120
    )
    if result.returncode != 0:
        return None
    return json.loads(result.stdout)


def run_generator(input_path, output_path):
    """Run structure generator on a PDF."""
    fixes = {"title": "test", "language": "en-US",
             "display_doc_title": True, "set_pdfua": True}
    fixes_path = output_path + ".fixes.json"
    with open(fixes_path, "w") as f:
        json.dump(fixes, f)

    result = subprocess.run(
        ["python3", GENERATOR, input_path, output_path, fixes_path],
        capture_output=True, text=True, timeout=120
    )
    os.remove(fixes_path)
    return result.returncode == 0


def compare(acrobat_val, pikepdf_val, threshold_ratio):
    """Compare two values. Returns (status, ratio_str)."""
    if acrobat_val == 0 and pikepdf_val == 0:
        return "skip", "—"
    if acrobat_val == 0 and pikepdf_val > 0:
        return "new", f"+{pikepdf_val}"
    if acrobat_val > 0 and pikepdf_val == 0:
        return "fail", "0"

    ratio = max(acrobat_val, pikepdf_val) / max(min(acrobat_val, pikepdf_val), 1)
    if ratio <= 1.5:
        return "pass", f"{ratio:.1f}x"
    elif ratio <= threshold_ratio:
        return "warn", f"{ratio:.1f}x"
    else:
        return "fail", f"{ratio:.1f}x"


def main():
    test_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        SCRIPT_DIR, "..", "..", "..", "test files"
    )
    test_dir = os.path.abspath(test_dir)

    if not os.path.isdir(test_dir):
        print(f"Test directory not found: {test_dir}")
        sys.exit(1)

    pairs = find_test_pairs(test_dir)
    if not pairs:
        print(f"No test pairs found in {test_dir}")
        print("Expected: <name>.pdf + <name>_acrobat_tagged.pdf")
        sys.exit(1)

    print(f"Found {len(pairs)} test pairs in {test_dir}\n")

    metrics = list(THRESHOLDS.keys())
    totals = {"pass": 0, "warn": 0, "fail": 0, "skip": 0, "new": 0}

    # Header
    print(f"{'File':<42} {'Metric':<8} {'Acrobat':>8} {'pikepdf':>8} {'Status':>8} {'Ratio':>8}")
    print("=" * 82)

    for pair in pairs:
        # Generate pikepdf output
        pikepdf_out = pair["original"].replace(".pdf", "_regression.pdf")
        if not run_generator(pair["original"], pikepdf_out):
            print(f"{pair['label']:<42} GENERATOR FAILED")
            continue

        # Audit both
        acrobat_audit = run_audit(pair["acrobat"])
        pikepdf_audit = run_audit(pikepdf_out)

        # Clean up
        if os.path.exists(pikepdf_out):
            os.remove(pikepdf_out)

        if not acrobat_audit or not pikepdf_audit:
            print(f"{pair['label']:<42} AUDIT FAILED")
            continue

        a_tags = acrobat_audit["structure"]["tag_counts"]
        p_tags = pikepdf_audit["structure"]["tag_counts"]

        for metric in metrics:
            av = a_tags.get(metric, 0)
            pv = p_tags.get(metric, 0)
            threshold = THRESHOLDS[metric]["ratio"]
            status, ratio_str = compare(av, pv, threshold)
            totals[status] += 1

            status_icon = {"pass": "✅", "warn": "⚠️", "fail": "❌",
                          "skip": "—", "new": "🆕"}.get(status, "?")

            print(f"{pair['label']:<42} {metric:<8} {av:>8} {pv:>8} {status_icon:>8} {ratio_str:>8}")

        print()

    # Summary
    print("=" * 82)
    print(f"SUMMARY: ✅ {totals['pass']} pass | ⚠️ {totals['warn']} warn | "
          f"❌ {totals['fail']} fail | 🆕 {totals['new']} new | — {totals['skip']} skip")

    if totals["fail"] > 0:
        print("\n⚠️  REGRESSIONS DETECTED — review fail items above")
        sys.exit(1)
    else:
        print("\n✅ No regressions detected")
        sys.exit(0)


if __name__ == "__main__":
    main()
