"""
Optimizer Agent — Propose prompt/solution updates from memory (Observe → Optimize).

Uses MemoryStore SQL queries to ground proposals in structured data instead of
truncated JSON blobs. Queries metric trends, failure patterns, verification
history, and per-model EOD history to propose prompt refinements.

Output proposals to outputs/optimizer_proposals.json for manual or automated
commit. Use --apply to apply proposals to configs/prompts/.
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
os.makedirs(OUTPUT_DIR, exist_ok=True)


def _build_memory_context() -> str:
    """Build a structured context string from MemoryStore SQL queries."""
    try:
        from agents.memory_agent import MemoryStore
        store = MemoryStore()
    except ImportError:
        return _build_legacy_context()

    sections = []

    # EOD trend
    eod_trend = store.metric_trend("best_eod", limit=10)
    if eod_trend:
        lines = [f"  {ts}: {val}" for ts, val in eod_trend if val is not None]
        if lines:
            sections.append("EOD TREND (best_eod across runs):\n" + "\n".join(lines))

    # Failure patterns
    failures = store.failure_patterns(limit=20)
    if failures:
        lines = [f"  {etype}: {count} occurrences" for etype, count in failures.items()]
        sections.append("FAILURE PATTERNS:\n" + "\n".join(lines))

    # Success rates
    for agent in ["detection", "mitigation", "auditing"]:
        rate = store.success_rate(agent)
        sections.append(f"SUCCESS RATE ({agent}): {rate:.1%}")

    # Unverified claims
    unverified = store.unverified_claims(limit=5)
    if unverified:
        lines = [f"  - {c.get('claim', '?')[:80]}" for c in unverified]
        sections.append("UNVERIFIED CLAIMS (keep failing verification):\n" + "\n".join(lines))

    # Recent failed agent runs with feedback
    for agent in ["auditing", "mitigation"]:
        failed = store.what_failed(agent, limit=3)
        if failed:
            lines = []
            for f in failed:
                fb = f.get("judge_feedback", "[]")
                try:
                    fb_list = json.loads(fb) if isinstance(fb, str) else fb
                except json.JSONDecodeError:
                    fb_list = [fb]
                lines.append(f"  attempt={f.get('attempt')}: {'; '.join(str(x)[:80] for x in fb_list[:2])}")
            sections.append(f"RECENT FAILURES ({agent}):\n" + "\n".join(lines))

    # Model-level metrics
    model_metrics = store.all_model_metrics(limit=30)
    if model_metrics:
        model_summary = {}
        for m in model_metrics:
            name = m.get("model", "?")
            if name not in model_summary:
                model_summary[name] = {"eod_values": [], "dpd_values": []}
            if m.get("eod") is not None:
                model_summary[name]["eod_values"].append(m["eod"])
            if m.get("dpd") is not None:
                model_summary[name]["dpd_values"].append(m["dpd"])
        lines = []
        for name, data in model_summary.items():
            eod_vals = data["eod_values"]
            if eod_vals:
                avg_eod = sum(abs(v) for v in eod_vals) / len(eod_vals)
                lines.append(f"  {name}: avg|EOD|={avg_eod:.4f} ({len(eod_vals)} runs)")
        if lines:
            sections.append("MODEL EOD SUMMARY:\n" + "\n".join(lines))

    store.close()

    if not sections:
        return _build_legacy_context()

    return "\n\n".join(sections)


def _build_legacy_context() -> str:
    """Fallback: build context from legacy JSON files."""
    try:
        from agents.memory_agent import load_recent_sessions, load_recent_events
    except ImportError:
        return ""
    sessions = load_recent_sessions(limit=5)
    events = load_recent_events(limit=30)
    context = {"sessions": sessions, "events": events[:15]}
    return json.dumps(context, indent=2)[:8000]


def run_optimizer() -> dict:
    """
    Load memory, ask Gemini to propose prompt updates based on failure patterns.
    Returns {proposals: [...], summary: str}.
    """
    try:
        from utils.llm_client import generate, is_available
    except ImportError:
        return {"proposals": [], "summary": "Optimizer dependencies not available."}

    if not is_available():
        return {"proposals": [], "summary": "Gemini unavailable. Set GOOGLE_API_KEY."}

    context_str = _build_memory_context()
    if not context_str:
        return {"proposals": [], "summary": "No memory to analyze."}

    prompt = f"""You are an optimizer for a bias audit research paper pipeline. Review the structured memory data below. Identify recurring failure patterns and propose targeted prompt refinements.

The data includes:
- EOD TREND: best Equalized Odds Difference across pipeline runs (lower = better, target <= 0.05)
- FAILURE PATTERNS: classified error types and their frequency
- UNVERIFIED CLAIMS: paper claims that code-based verification keeps refuting
- RECENT FAILURES: agent failures with judge feedback
- MODEL EOD SUMMARY: per-model average |EOD| across runs

Propose 1-3 prompt refinements that would reduce failures. Each proposal should:
1. Target a specific prompt file (e.g., trade_off_summary, mitigation_claims, verification)
2. Add a concrete rule or instruction
3. Reference the data pattern that motivates it

Memory data:
{context_str}

Respond with a JSON array only:
[
  {{"prompt": "target_prompt_name", "rule": "the new rule to add", "reason": "data-grounded reason"}},
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
