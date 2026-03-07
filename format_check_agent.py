"""
Format Check Agent — Validates Output Structure and Presentation

Ensures paper outputs, tables, and JSON artifacts meet format standards before
Judge evaluation. Catches issues that cause garbled text, table misalignment,
or PDF rendering problems.

Checks:
- Markdown table structure (alignment, column consistency, no duplicate headers)
- JSON validity and required keys
- Text encoding (no replacement chars, valid Unicode)
- LaTeX syntax (basic escapes, table structure)
- EU AI Act threshold clarity in tables

Usage:
  python format_check_agent.py              # Check all outputs
  python format_check_agent.py --paper      # Paper only
  python format_check_agent.py --json       # JSON artifacts only
"""

import os
import re
import json
import argparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "outputs")
SECTIONS_DIR = os.path.join(OUTPUT_DIR, "paper_sections")

# Expected table columns (metrics + violation flags)
EXPECTED_TABLE_COLUMNS = ["Model", "Acc", "F1", "AUC", "FPR", "DPD", "EOD", "DI", "SPD Viol", "EOD Viol"]
# Violation columns should NOT duplicate metric names (old: SPD, EOD caused confusion)
VIOLATION_COLUMN_NAMES = ("SPD Viol", "EOD Viol", "SPD Viol?", "EOD Viol?")
EU_THRESHOLD_PATTERN = re.compile(
    r"(?:\|\s*SPD\s*\|\s*[≤<]\s*0\.1|EU AI Act.*0\.1|SPD.*0\.1)",
    re.IGNORECASE
)
REPLACEMENT_CHAR = "\ufffd"  # Unicode replacement character (garbled)


def _read_file(path: str, default: str = "") -> str:
    if not os.path.exists(path):
        return default
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except (OSError, UnicodeDecodeError):
        return default


def _load_json(path: str) -> dict | None:
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


# ========================================================================
# Table format checks
# ========================================================================


def _parse_markdown_table(text: str) -> list[dict]:
    """Extract markdown tables and return list of {header, rows, raw}."""
    tables = []
    # Match | header | header | ... \n |:---|:---| \n | row | row |
    pattern = r"\|([^\n]+)\|\s*\n\|([^\n]+)\|\s*\n((?:\|[^\n]+\|\s*\n?)+)"
    for m in re.finditer(pattern, text):
        header_line = m.group(1)
        align_line = m.group(2)
        rows_block = m.group(3)
        headers = [c.strip() for c in header_line.split("|") if c.strip()]
        rows = []
        for line in rows_block.strip().split("\n"):
            cells = [c.strip() for c in line.split("|") if c.strip()]
            if len(cells) == len(headers):
                rows.append(cells)
        tables.append({"headers": headers, "rows": rows, "raw": m.group(0)})
    return tables


def check_table_headers(tables: list[dict]) -> list[str]:
    """Check for duplicate or ambiguous column headers (SPD/EOD used for both metric and violation)."""
    issues = []
    for i, t in enumerate(tables):
        headers = t["headers"]
        # Duplicate header names
        seen = {}
        for h in headers:
            if h in seen:
                issues.append(f"Table {i+1}: Duplicate column '{h}'")
            seen[h] = True
        # Ambiguous: SPD and EOD as last two columns without "Viol" — confuses with metric columns
        if len(headers) >= 2:
            last_two = headers[-2:]
            if "SPD" in last_two and "EOD" in last_two and "Viol" not in " ".join(last_two):
                issues.append(
                    f"Table {i+1}: Columns '{last_two[0]}' and '{last_two[1]}' should be "
                    "'SPD Viol' and 'EOD Viol' to avoid confusion with metric columns."
                )
    return issues


def check_table_alignment(tables: list[dict]) -> list[str]:
    """Check that all rows have same column count as header."""
    issues = []
    for i, t in enumerate(tables):
        n = len(t["headers"])
        for j, row in enumerate(t["rows"]):
            if len(row) != n:
                issues.append(
                    f"Table {i+1} row {j+1}: Expected {n} columns, got {len(row)}. "
                    f"Row: {row[:3]}..."
                )
    return issues


def check_threshold_footnote(text: str) -> list[str]:
    """Ensure EU AI Act thresholds are stated near fairness tables."""
    issues = []
    if "| DPD " in text or "| DPD" in text:
        if not EU_THRESHOLD_PATTERN.search(text) and "0.1" not in text and "0.05" not in text:
            issues.append(
                "Fairness tables present but EU AI Act thresholds (|SPD| ≤ 0.1, |EOD| ≤ 0.05, DI ≥ 0.8) "
                "not clearly stated in caption or adjacent text."
            )
    return issues


# ========================================================================
# Text / encoding checks
# ========================================================================


def check_garbled_text(text: str, source: str = "") -> list[str]:
    """Detect replacement chars and common OCR-style garbling."""
    issues = []
    if REPLACEMENT_CHAR in text:
        issues.append(f"{source}: Contains Unicode replacement character (garbled/encoding error).")
    # Common OCR-style errors
    garbled_patterns = [
        (r"adjurent\s+fun\s+equalibes", "Possible garbled: 'adjustment further equalises'"),
        (r"legi@rik\d*regression", "Possible garbled: 'logistic regression'"),
        (r"fake-pofive", "Possible garbled: 'false-positive'"),
        (r"inimes?improvement", "Possible garbled: 'minimal improvement'"),
    ]
    for pat, msg in garbled_patterns:
        if re.search(pat, text, re.IGNORECASE):
            issues.append(f"{source}: {msg}")
    return issues


def check_incomplete_content(text: str, source: str = "") -> list[str]:
    """
    Detect incomplete/truncated content that causes white chunks in the PDF.
    Delegates to paper_quality_guardrail when available.
    """
    try:
        from paper_quality_guardrail import (
            check_incomplete_sentences,
            check_truncated_starts,
            check_duplicate_incomplete_fragments,
        )
        issues = []
        issues.extend(check_incomplete_sentences(text, source))
        issues.extend(check_truncated_starts(text, source))
        issues.extend(check_duplicate_incomplete_fragments(text, source))
        return issues
    except ImportError:
        return []


def check_markdown_syntax(text: str, source: str = "") -> list[str]:
    """Basic markdown structure checks."""
    issues = []
    # Table delimiter line should have consistent structure
    lines = text.split("\n")
    in_table = False
    for i, line in enumerate(lines):
        if line.strip().startswith("|") and line.strip().endswith("|"):
            if in_table:
                # Check pipe count consistency
                pipes = line.count("|")
                if pipes < 3:
                    issues.append(f"{source} line {i+1}: Malformed table row (too few pipes).")
            else:
                in_table = True
        else:
            in_table = False
    return issues


# ========================================================================
# JSON checks
# ========================================================================


def check_baseline_json(data: dict) -> list[str]:
    """Validate baseline_results.json structure."""
    issues = []
    if not data:
        return ["baseline_results.json: File missing or invalid JSON."]
    metrics = data.get("baseline_metrics", [])
    if not metrics:
        issues.append("baseline_results.json: baseline_metrics is empty.")
    required = [
        "model", "accuracy", "f1_score", "demographic_parity_diff",
        "equalized_odds_diff", "disparate_impact_ratio",
        "eu_ai_act_spd_violation", "eu_ai_act_eod_violation"
    ]
    for i, m in enumerate(metrics):
        for k in required:
            if k not in m:
                issues.append(f"baseline_results.json model {i}: Missing key '{k}'.")
    return issues


def check_mitigation_json(data: dict) -> list[str]:
    """Validate mitigation_results.json structure."""
    issues = []
    if not data:
        return ["mitigation_results.json: File missing or invalid JSON."]
    for key in ("baseline_metrics", "mitigation_metrics"):
        if key not in data:
            issues.append(f"mitigation_results.json: Missing key '{key}'.")
        elif not isinstance(data[key], list):
            issues.append(f"mitigation_results.json: '{key}' should be a list.")
    return issues


# ========================================================================
# LaTeX checks
# ========================================================================


def check_latex_basic(tex_path: str) -> list[str]:
    """Basic LaTeX syntax checks."""
    issues = []
    text = _read_file(tex_path)
    if not text:
        return [f"{tex_path}: File not found or empty."]
    # Unescaped special chars in table content
    if "&" in text and "\\&" not in text and "\\begin{tabular}" in text:
        # Could be fine if & is inside math mode
        pass
    if REPLACEMENT_CHAR in text:
        issues.append(f"{tex_path}: Contains replacement character.")
    # Table column count vs header
    tab_match = re.search(
        r"\\begin\{tabular\}\{[lrc]+\}\s*\\\\?\s*(.*?)\\\\",
        text,
        re.DOTALL
    )
    if tab_match:
        header = tab_match.group(1)
        n_cols = header.count("&") + 1
        # Rows should have same &
        row_pattern = re.compile(r"([^&]+&[^\\\\]+)\\\\")
        for m in row_pattern.finditer(text):
            row = m.group(1)
            if row.count("&") + 1 != n_cols:
                issues.append(f"{tex_path}: Table row column count mismatch.")
                break
    return issues


# ========================================================================
# Main API
# ========================================================================


def run_format_check(paper_only: bool = False, json_only: bool = False) -> dict:
    """
    Run all format checks. Returns {
        "passed": bool,
        "issues": list[str],
        "fixes_suggested": list[str],
    }
    """
    issues = []
    fixes = []

    if not json_only:
        # Paper / Markdown
        draft_path = os.path.join(OUTPUT_DIR, "paper_draft.md")
        draft = _read_file(draft_path)
        if draft:
            tables = _parse_markdown_table(draft)
            issues.extend(check_table_headers(tables))
            issues.extend(check_table_alignment(tables))
            issues.extend(check_threshold_footnote(draft))
            issues.extend(check_garbled_text(draft, "paper_draft.md"))
            issues.extend(check_markdown_syntax(draft, "paper_draft.md"))
            issues.extend(check_incomplete_content(draft, "paper_draft.md"))
            if any("SPD Viol" not in str(t.get("headers", [])) for t in tables):
                fixes.append("Rename table violation columns to 'SPD Viol' and 'EOD Viol'.")
        else:
            issues.append("paper_draft.md not found.")

        # Sections
        if os.path.isdir(SECTIONS_DIR):
            for f in os.listdir(SECTIONS_DIR):
                if f.endswith(".md"):
                    path = os.path.join(SECTIONS_DIR, f)
                    content = _read_file(path)
                    issues.extend(check_garbled_text(content, f))

        # LaTeX
        tex_path = os.path.join(OUTPUT_DIR, "paper", "paper.tex")
        if os.path.exists(tex_path):
            issues.extend(check_latex_basic(tex_path))
            tex_content = _read_file(tex_path)
            if tex_content:
                issues.extend(check_incomplete_content(tex_content, "paper.tex"))

    if not paper_only:
        # JSON
        baseline = _load_json(os.path.join(OUTPUT_DIR, "baseline_results.json"))
        mitigation = _load_json(os.path.join(OUTPUT_DIR, "mitigation_results.json"))
        issues.extend(check_baseline_json(baseline))
        issues.extend(check_mitigation_json(mitigation))

    passed = len(issues) == 0
    return {
        "passed": passed,
        "issues": issues,
        "fixes_suggested": fixes,
    }


def apply_format_fixes() -> bool:
    """
    Apply standard format fixes to paper outputs.
    Returns True if any fix was applied.
    """
    fixed = False
    draft_path = os.path.join(OUTPUT_DIR, "paper_draft.md")
    draft = _read_file(draft_path)
    if not draft:
        return False

    # Fix table headers: | SPD | EOD | -> | SPD Viol | EOD Viol |
    old_header = "| DPD     | EOD     | DI     | SPD | EOD |"
    new_header = "| DPD     | EOD     | DI     | SPD Viol | EOD Viol |"
    old_align = "|:--------|:--------|:-------|:----|:----|"
    new_align = "|:--------|:--------|:-------|:---------|:--------|"

    if old_header in draft:
        draft = draft.replace(old_header, new_header)
        draft = draft.replace(old_align, new_align)
        fixed = True

    # Add threshold footnote if table exists but footnote missing
    if "| Model " in draft and "*Thresholds: EU AI Act" not in draft:
        # Insert after each **Table N — ...** block followed by table
        draft = re.sub(
            r"(\*\*Table \d+[^*]+\*\*\n\n)(\| Model [^\n]+\n\|[^\n]+\n(?:\|[^\n]+\n)+)",
            r"\1\2\n\n*Thresholds: EU AI Act |SPD| ≤ 0.1, |EOD| ≤ 0.05, DI ≥ 0.8.*\n",
            draft,
            count=1,
        )
        if "*Thresholds: EU AI Act" in draft:
            fixed = True

    if fixed:
        with open(draft_path, "w", encoding="utf-8") as f:
            f.write(draft)
        # Also fix section files
        for fname in os.listdir(SECTIONS_DIR):
            if fname.endswith(".md"):
                path = os.path.join(SECTIONS_DIR, fname)
                content = _read_file(path)
                if old_header in content:
                    content = content.replace(old_header, new_header)
                    content = content.replace(old_align, new_align)
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(content)

    return fixed


def main():
    parser = argparse.ArgumentParser(description="Format Check Agent")
    parser.add_argument("--paper", action="store_true", help="Check paper outputs only")
    parser.add_argument("--json", action="store_true", help="Check JSON artifacts only")
    parser.add_argument("--fix", action="store_true", help="Apply format fixes automatically")
    args = parser.parse_args()

    paper_only = args.paper
    json_only = args.json
    if args.paper and args.json:
        paper_only = json_only = False

    print("=" * 64)
    print("  FORMAT CHECK AGENT — Output Structure Validation")
    print("=" * 64)

    if args.fix:
        print("\n  Applying format fixes...")
        if apply_format_fixes():
            print("  ✓ Fixes applied. Re-running format check.")
        else:
            print("  No fixes needed or no fixable content found.")

    result = run_format_check(paper_only=paper_only, json_only=json_only)

    if result["passed"]:
        print("\n  ✓ All format checks passed.")
    else:
        print("\n  ✗ Format issues found:")
        for issue in result["issues"]:
            print(f"    - {issue}")
        if result["fixes_suggested"]:
            print("\n  Suggested fixes:")
            for fix in result["fixes_suggested"]:
                print(f"    - {fix}")
        if not args.fix:
            print("\n  Run with --fix to apply standard fixes automatically.")

    return 0 if result["passed"] else 1


if __name__ == "__main__":
    exit(main())
