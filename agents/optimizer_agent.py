"""
Optimizer Agent — Propose prompt/solution updates from memory (Observe → Optimize).

Design: Review outputs/memory/ sessions and events. Use Gemini to propose prompt
refinements (e.g., "When accuracy_delta>0, always mention AUC/Recall") based on
recurring failures. Output proposals to outputs/optimizer_proposals.json for
manual or automated commit. Use --apply to apply proposals to configs/prompts/.
"""

import os
import json
import shutil
import sys
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "outputs")
CONFIGS_DIR = os.path.join(PROJECT_ROOT, "configs")
PROMPTS_DIR = os.path.join(CONFIGS_DIR, "prompts")
MEMORY_DIR = os.path.join(OUTPUT_DIR, "memory")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def run_optimizer() -> dict:
    """
    Load memory, ask Gemini to propose prompt updates based on failure patterns.
    Returns {proposals: [...], summary: str}.
    """
    try:
        from agents.memory_agent import load_recent_sessions, load_recent_events
        from utils.llm_client import generate, is_available
    except ImportError:
        return {"proposals": [], "summary": "Optimizer dependencies not available."}

    sessions = load_recent_sessions(limit=5)
    events = load_recent_events(limit=30)

    if not sessions and not events:
        return {"proposals": [], "summary": "No memory to analyze."}

    if not is_available():
        return {"proposals": [], "summary": "Gemini unavailable. Set GOOGLE_API_KEY."}

    # Build context for Gemini
    context = {
        "sessions": sessions,
        "events": events[:15],
    }
    context_str = json.dumps(context, indent=2)[:8000]

    prompt = f"""You are an optimizer for a research paper pipeline. Review the session and event memory below. Identify recurring failure patterns (e.g., "auditing fails when claim contradicts data", "accuracy_delta>0 but paper claims accuracy loss").

Propose 1-3 prompt refinements that would reduce these failures. Each proposal should:
1. Target a specific prompt (e.g., trade_off_summary, mitigation_claims)
2. Add a rule or instruction (e.g., "When accuracy_delta>0, NEVER claim accuracy loss; mention AUC/Recall instead")
3. Explain why (reference the failure pattern)

Memory:
{context_str}

Respond with a JSON array only:
[
  {{"prompt": "trade_off_summary", "rule": "string", "reason": "string"}},
  ...
]
If no actionable proposals, return [].
"""

    result = generate(prompt, max_output_tokens=1024)
    if not result or len(result.strip()) < 10:
        return {"proposals": [], "summary": "Gemini returned no proposals."}

    import re
    m = re.search(r"\[[\s\S]*\]", result)
    if not m:
        return {"proposals": [], "summary": "Could not parse proposals from Gemini."}

    try:
        proposals = json.loads(m.group(0))
    except json.JSONDecodeError:
        return {"proposals": [], "summary": "Invalid JSON from Gemini."}

    report = {
        "timestamp": datetime.now().isoformat(),
        "proposals": proposals,
        "summary": f"{len(proposals)} proposal(s) for prompt refinement.",
    }

    out_path = os.path.join(OUTPUT_DIR, "optimizer_proposals.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    return report


def apply_proposals(dry_run: bool = False) -> dict:
    """
    Apply proposals from optimizer_proposals.json to configs/prompts/.
    Creates backup before modifying. Returns {applied: int, backups: list}.
    """
    path = os.path.join(OUTPUT_DIR, "optimizer_proposals.json")
    if not os.path.exists(path):
        return {"applied": 0, "backups": [], "error": "optimizer_proposals.json not found"}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    proposals = data.get("proposals", [])
    if not proposals:
        return {"applied": 0, "backups": [], "message": "No proposals to apply"}

    backups = []
    applied = 0
    for p in proposals:
        prompt_name = p.get("prompt", "")
        rule = p.get("rule", "")
        if not prompt_name or not rule:
            continue
        prompt_path = os.path.join(PROMPTS_DIR, f"{prompt_name}.txt")
        if not os.path.exists(prompt_path):
            continue
        if dry_run:
            applied += 1
            continue
        backup_path = os.path.join(PROMPTS_DIR, f"{prompt_name}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
        shutil.copy(prompt_path, backup_path)
        backups.append(backup_path)
        with open(prompt_path, encoding="utf-8") as f:
            content = f.read()
        addition = f"\n\n**Optimizer addition ({datetime.now().strftime('%Y-%m-%d')}):** {rule}"
        if addition.strip() not in content:
            with open(prompt_path, "a", encoding="utf-8") as f:
                f.write(addition)
            applied += 1
    return {"applied": applied, "backups": backups}


def main():
    apply = "--apply" in sys.argv or "-a" in sys.argv
    dry_run = "--dry-run" in sys.argv

    print("=" * 64)
    print("  OPTIMIZER AGENT — Propose prompt updates from memory")
    print("=" * 64)
    report = run_optimizer()
    print(f"\n  {report['summary']}")
    for i, p in enumerate(report.get("proposals", []), 1):
        print(f"  [{i}] {p.get('prompt', '?')}: {p.get('rule', '')[:60]}...")
    print(f"\n  Saved: outputs/optimizer_proposals.json")

    if apply and report.get("proposals"):
        print("\n  Applying proposals to configs/prompts/...")
        result = apply_proposals(dry_run=dry_run)
        if dry_run:
            print(f"  [DRY RUN] Would apply {result['applied']} proposal(s)")
        else:
            print(f"  Applied {result['applied']} proposal(s). Backups: {result.get('backups', [])}")


if __name__ == "__main__":
    main()
