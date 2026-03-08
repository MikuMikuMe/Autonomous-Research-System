"""
Revision Agent — Self-Evolution via Judge Feedback (Observe → Optimize)

Design principles:
- AI Court: Judge (司礼监) delegates corrective action to a specialist agent.
- Autogenesis: Judge feedback = Observe; this agent = Optimize; updated draft = Remember.

When the Judge finds semantic issues (e.g., intro contradicts Table 2, claim vs. data
mismatch), this agent immediately applies targeted fixes using the LLM instead of
retrying the full auditing pipeline.

Usage:
  python revision_agent.py                    # Reads JUDGE_FEEDBACK env or last judge result
  python revision_agent.py "feedback text"   # Explicit feedback
"""

import os
import json
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "outputs")
SECTIONS_DIR = os.path.join(OUTPUT_DIR, "paper_sections")


def _read_file(path, default=""):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return f.read()


def _write_file(path, content):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _load_json(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def run_revision(feedback: str) -> bool:
    """
    Apply targeted revisions to the paper based on Judge feedback.
    Returns True if revision was applied successfully.
    """
    try:
        from utils.llm_client import generate, is_available
        if not is_available():
            print("  [Revision] Gemini not available. Set GOOGLE_API_KEY.")
            return False
    except ImportError:
        print("  [Revision] llm_client not available.")
        return False

    # Prefer paper.tex (LaTeX-only pipeline)
    tex_path = os.path.join(OUTPUT_DIR, "paper", "paper.tex")
    draft_path = tex_path if os.path.exists(tex_path) else os.path.join(OUTPUT_DIR, "paper_draft.md")
    if not os.path.exists(draft_path):
        print("  [Revision] paper.tex / paper_draft.md not found. Run auditing_agent first.")
        return False

    draft = _read_file(draft_path)
    baseline = _load_json(os.path.join(OUTPUT_DIR, "baseline_results.json"))
    mitigation = _load_json(os.path.join(OUTPUT_DIR, "mitigation_results.json"))

    # Build context for the LLM — paper must fit testing, never the reverse
    data_summary = ""
    if mitigation:
        mit = mitigation.get("mitigation_metrics", [])
        for m in mit[:6]:
            model = m.get("model", "?")
            eod = m.get("equalized_odds_diff")
            di = m.get("disparate_impact_ratio")
            dpd = m.get("demographic_parity_diff")
            eod_s = f"{eod:+.4f}" if eod is not None else "N/A"
            di_s = f"{di:.4f}" if di is not None else "N/A"
            dpd_s = f"{dpd:+.4f}" if dpd is not None else "N/A"
            data_summary += f"  - {model}: EOD={eod_s}, DI={di_s}, DPD={dpd_s}\n"

    try:
        from utils.config_loader import load_prompt
        prompt = load_prompt(
            "revision",
            feedback=feedback,
            data_summary=data_summary or "(no data)",
            draft_excerpt=draft[:8000],
        )
    except ImportError:
        prompt = None
    if not prompt:
        prompt = (
            f"You are a research paper editor. Judge feedback: {feedback}\n\n"
            f"Data: {data_summary or '(no data)'}\n\n"
            f"Paper excerpt: {draft[:8000]}\n\n"
            "Produce JSON with 'sections' dict (01_introduction, 05_discussion, etc.). "
            "Modify paper to fit data. Never claim improvements data does not support."
        )

    out = generate(prompt)
    if not out:
        print("  [Revision] LLM returned no response.")
        return False

    # Parse JSON from response
    import re
    m = re.search(r'\{[\s\S]*\}', out)
    if not m:
        print("  [Revision] Could not parse JSON from LLM response.")
        return False

    try:
        result = json.loads(m.group(0))
    except json.JSONDecodeError:
        print("  [Revision] Invalid JSON from LLM.")
        return False

    sections = result.get("sections", result.get("sections_to_replace", []))
    if isinstance(sections, dict):
        sections = [{"section_name": k, "new_content": v} for k, v in sections.items()]
    if not sections:
        print("  [Revision] LLM returned no sections to replace.")
        return False

    applied = 0
    for item in sections:
        if isinstance(item, dict):
            section_name = item.get("section_name", item.get("section", ""))
            new_content = item.get("new_content", item.get("content", ""))
        else:
            continue
        if not section_name or not new_content:
            continue

        base = section_name.replace(".tex", "").replace(".md", "")
        fname = base + ".tex"
        path = os.path.join(SECTIONS_DIR, fname)
        if not os.path.exists(path):
            for f in os.listdir(SECTIONS_DIR):
                if f.endswith(".tex") and base in f:
                    path = os.path.join(SECTIONS_DIR, f)
                    break
        if os.path.exists(path):
            _write_file(path, new_content.strip() + "\n")
            print(f"  [Revision] Updated: {os.path.basename(path)}")
            applied += 1

    if applied == 0:
        print("  [Revision] No sections were updated (section names may not match).")
        return False

    # Reassemble paper.tex from sections
    sections_list = sorted(f for f in os.listdir(SECTIONS_DIR) if f.endswith(".tex"))
    if sections_list:
        try:
            from utils.latex_generator import assemble_paper_from_sections, _load_authors, _latex_author_block
            section_contents = [_read_file(os.path.join(SECTIONS_DIR, f)) for f in sections_list]
            authors = _load_authors()
            author_block = _latex_author_block(authors)
            full_tex = assemble_paper_from_sections(section_contents, author_block)
            _write_file(tex_path, full_tex)
            print(f"  [Revision] Reassembled paper.tex ({applied} sections revised).")
        except ImportError:
            print(f"  [Revision] Updated {applied} sections (run auditing_agent to reassemble paper.tex).")
    return True


def main():
    feedback = os.environ.get("JUDGE_FEEDBACK")
    if not feedback and len(sys.argv) > 1:
        feedback = " ".join(sys.argv[1:])
    if not feedback:
        # Try to read from last judge result (if stored)
        review_path = os.path.join(OUTPUT_DIR, "last_judge_feedback.txt")
        if os.path.exists(review_path):
            feedback = _read_file(review_path)
    if not feedback:
        print("Usage: python revision_agent.py 'Judge feedback text'")
        print("   or: JUDGE_FEEDBACK='...' python revision_agent.py")
        sys.exit(1)

    print("=" * 64)
    print("  REVISION AGENT — Applying Judge feedback (Observe → Optimize)")
    print("=" * 64)
    print(f"\n  Feedback: {feedback[:200]}...")
    ok = run_revision(feedback)
    print("\n  Revision complete." if ok else "\n  Revision failed.")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
