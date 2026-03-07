"""
Paper Quality Guardrail — Prevents white chunks and incomplete content in the research PDF.

CRITICAL: The research paper must NEVER contain:
- Incomplete/truncated sentences
- Quotes or paragraphs ending mid-sentence
- Empty or near-empty sections
- Garbled or fragment text (e.g. "ial institutions", "nsufficient", "by 0.015" with no continuation)
- Duplicate incomplete fragments

This guardrail runs after LaTeX/PDF generation and FAILS the pipeline if issues are detected.
"""

import os
import re

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "outputs")
PAPER_DIR = os.path.join(OUTPUT_DIR, "paper")

# Patterns that indicate truncated/incomplete content (high-confidence only)
INCOMPLETE_ENDINGS = [
    r"by\s+0\.\d+\s*$",            # "by 0.015" with nothing after
    r"particularly\s*$",           # ends with "particularly"
    r"the\s+key\s*$",             # "the key" with nothing after
    r"far\s+exceeding\s+EU\s*$",   # "far exceeding EU" (missing "AI Act thresholds")
    r"---\s*$",                    # em-dash with nothing after (incomplete)
    r"–\s*$",                      # en-dash with nothing after (incomplete)
]

# Sentence fragments that indicate truncated start (e.g. "ial" from "Financial")
TRUNCATED_STARTS = [
    r"^\s*ial\s+",                # "ial institutions" (from "Financial")
    r"^\s*nsufficient",           # "nsufficient" (from "Insufficient")
    r"^\s*ictly\s+",              # "ictly prohibited" (from "Strictly")
]

# Minimum paragraph length (chars) — very short paragraphs may indicate truncation
MIN_PARAGRAPH_CHARS = 20

# Minimum section body length — sections should have substantial content
MIN_SECTION_BODY_CHARS = 50


def _read_file(path: str, default: str = "") -> str:
    if not os.path.exists(path):
        return default
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except (OSError, UnicodeDecodeError):
        return default


def _extract_paragraphs(text: str) -> list[str]:
    """Split text into paragraphs (blank-line separated blocks)."""
    blocks = re.split(r"\n\s*\n", text)
    return [b.strip() for b in blocks if b.strip()]


def _extract_quote_blocks(text: str) -> list[str]:
    """Extract content inside \\begin{quote}...\\end{quote} or markdown > blocks."""
    quotes = []
    # LaTeX quotes
    for m in re.finditer(r"\\begin\{quote\}\s*(.*?)\\end\{quote\}", text, re.DOTALL):
        quotes.append(m.group(1).strip())
    # Markdown blockquotes
    for m in re.finditer(r"^>\s*(.+)$", text, re.MULTILINE | re.DOTALL):
        block = m.group(1).replace("\n> ", "\n").strip()
        if len(block) > 100:
            quotes.append(block)
    return quotes


def check_incomplete_sentences(text: str, source: str = "") -> list[str]:
    """Detect paragraphs or quotes that end with incomplete sentence patterns."""
    issues = []
    paragraphs = _extract_paragraphs(text)
    for p in paragraphs:
        if len(p) < 30:
            continue
        # Skip reference/citation blocks (DOIs, URLs, "Cited in")
        if "[Cited in" in p or "doi.org" in p or "https://doi" in p:
            continue
        last_part = p.strip()[-100:]
        for pattern in INCOMPLETE_ENDINGS:
            if re.search(pattern, last_part):
                issues.append(
                    f"{source}: Incomplete sentence ending — '...{last_part[-70:]}'"
                )
                break
    # Also check quote blocks specifically
    for quote in _extract_quote_blocks(text):
        if len(quote) < 50:
            continue
        if "[Cited in" in quote or "doi.org" in quote:
            continue
        last_part = quote.strip()[-100:]
        for pattern in INCOMPLETE_ENDINGS:
            if re.search(pattern, last_part):
                issues.append(
                    f"{source}: Quote ends incompletely — '...{last_part[-70:]}'"
                )
                break
    return issues


def check_truncated_starts(text: str, source: str = "") -> list[str]:
    """Detect content that starts with fragment (truncated beginning)."""
    issues = []
    for pattern in TRUNCATED_STARTS:
        if re.search(pattern, text, re.MULTILINE | re.IGNORECASE):
            for m in re.finditer(rf"({pattern}.{{0,80}})", text, re.MULTILINE | re.IGNORECASE):
                issues.append(
                    f"{source}: Truncated start — '{m.group(1).strip()[:80]}...'"
                )
    return issues


def check_quote_blocks_complete(text: str, source: str = "") -> list[str]:
    """Ensure quote blocks end at sentence boundaries (., !, ?)."""
    issues = []
    for quote in _extract_quote_blocks(text):
        if len(quote) < 50:
            continue
        # LaTeX quotes end with \} - get last substantive char before closing brace
        content = quote.strip()
        if content.endswith("}"):
            content = content[:-1].strip()
        last_char = content[-1] if content else ""
        # Also accept ) for citations like "thresholds.)"
        if last_char not in ".!?\")\u201d":
            last_80 = quote.strip()[-100:]
            # Skip References/citation blocks (DOIs, URLs)
            if "[Cited in" in last_80 or "doi.org" in last_80 or "https://" in last_80:
                continue
            issues.append(
                f"{source}: Quote block does not end with complete sentence. "
                f"Ends with: '...{last_80}'"
            )
    return issues


def check_empty_sections(text: str, source: str = "") -> list[str]:
    """Detect sections with no or minimal body content (excluding those with subsections)."""
    issues = []
    # LaTeX sections: \section{...} followed by content until next \section
    section_pattern = re.compile(
        r"\\section\*?\{([^}]+)\}(.*?)(?=\\section|\Z)",
        re.DOTALL,
    )
    for m in section_pattern.finditer(text):
        title, body = m.group(1), m.group(2)
        # Skip if section has subsections (they contain the real content)
        if "\\subsection" in body[:500]:
            continue
        body_clean = re.sub(r"\\begin\{quote\}.*?\\end\{quote\}", "", body, flags=re.DOTALL)
        body_clean = re.sub(r"\\begin\{table.*?\}.*?\\end\{table.*?\}", "", body_clean, flags=re.DOTALL)
        body_clean = re.sub(r"\s+", " ", body_clean).strip()
        if len(body_clean) < MIN_SECTION_BODY_CHARS:
            issues.append(
                f"{source}: Section '{title[:40]}' has very little body content ({len(body_clean)} chars)."
            )
    return issues


def check_duplicate_incomplete_fragments(text: str, source: str = "") -> list[str]:
    """Detect the same incomplete fragment repeated (e.g. 'by 0.015' twice)."""
    issues = []
    frag = "reducing demographic parity difference by 0.015"
    if text.count(frag) > 1:
        issues.append(
            f"{source}: Duplicate incomplete fragment '{frag}' appears {text.count(frag)} times."
        )
    return issues


def run_paper_quality_guardrail(
    check_markdown: bool = True,
    check_latex: bool = True,
) -> dict:
    """
    Run all paper quality checks. Returns {
        "passed": bool,
        "issues": list[str],
        "blocking": bool,  # True = must fix before considering paper complete
    }
    """
    issues = []

    if check_markdown:
        draft_path = os.path.join(OUTPUT_DIR, "paper_draft.md")
        draft = _read_file(draft_path)
        if draft:
            issues.extend(check_incomplete_sentences(draft, "paper_draft.md"))
            issues.extend(check_truncated_starts(draft, "paper_draft.md"))
            issues.extend(check_quote_blocks_complete(draft, "paper_draft.md"))
            issues.extend(check_duplicate_incomplete_fragments(draft, "paper_draft.md"))

    if check_latex:
        tex_path = os.path.join(PAPER_DIR, "paper.tex")
        tex = _read_file(tex_path)
        if tex:
            issues.extend(check_incomplete_sentences(tex, "paper.tex"))
            issues.extend(check_truncated_starts(tex, "paper.tex"))
            issues.extend(check_quote_blocks_complete(tex, "paper.tex"))
            issues.extend(check_empty_sections(tex, "paper.tex"))
            issues.extend(check_duplicate_incomplete_fragments(tex, "paper.tex"))

    passed = len(issues) == 0
    return {
        "passed": passed,
        "issues": issues,
        "blocking": not passed,  # Any issue is blocking for paper completeness
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Paper Quality Guardrail")
    parser.add_argument("--md-only", action="store_true", help="Check paper_draft.md only")
    parser.add_argument("--tex-only", action="store_true", help="Check paper.tex only")
    args = parser.parse_args()

    check_md = not args.tex_only
    check_tex = not args.md_only

    print("=" * 64)
    print("  PAPER QUALITY GUARDRAIL — No White Chunks, No Incomplete Content")
    print("=" * 64)

    result = run_paper_quality_guardrail(check_markdown=check_md, check_latex=check_tex)

    if result["passed"]:
        print("\n  ✓ All paper quality checks passed. No incomplete content detected.")
        return 0

    print("\n  ✗ BLOCKING: Paper quality issues detected (would cause white chunks):")
    for issue in result["issues"]:
        print(f"    - {issue}")
    print("\n  Fix these before considering the paper complete. Re-run pipeline after fixes.")
    return 1


if __name__ == "__main__":
    exit(main())
