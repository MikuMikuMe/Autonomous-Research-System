"""
Judge Agent — Quality Evaluation for Agent Outputs
Evaluates outputs from Detection, Mitigation, and Auditing agents.
Uses rule-based checks first; when GOOGLE_API_KEY is set, uses Gemini for
semantic evaluation: actual assessment of quality, consistency, and whether
claims are supported by the data.
"""

import os
import json
import re

from utils.schemas import JudgeResult

try:
    from utils.schemas import BaselineResults, MitigationResults, ModelMetrics  # type: ignore[attr-defined]
except ImportError:  # removed in research-system refactor
    BaselineResults = None  # type: ignore[assignment,misc]
    MitigationResults = None  # type: ignore[assignment,misc]
    ModelMetrics = None  # type: ignore[assignment,misc]

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "outputs")

MIN_DETECTION_MODELS = 2
MIN_MITIGATION_STRATEGIES = 2
REQUIRED_PAPER_SECTIONS = [
    "Introduction", "Background", "Use Case", "Audit Framework",
    "Discussion", "References",
]
MIN_PAPER_LENGTH = 2000


def _load_json(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _read_file(path, default=""):
    if not os.path.exists(path):
        return default
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return default


# ====================================================================
# Rule-based evaluation (always runs)
# ====================================================================


def _evaluate_detection_rules():
    """Rule-based detection checks. Uses BaselineResults schema validation."""
    result = {"passed": False, "feedback": []}

    json_path = os.path.join(OUTPUT_DIR, "baseline_results.json")
    npz_path = os.path.join(OUTPUT_DIR, "data_splits.npz")

    if not os.path.exists(npz_path):
        result["feedback"].append("data_splits.npz not found. Run detection_agent.py.")
        return result

    if not os.path.exists(json_path):
        result["feedback"].append("baseline_results.json not found.")
        return result

    data = _load_json(json_path)
    if not data:
        result["feedback"].append("baseline_results.json is invalid or empty.")
        return result

    schema_errors = BaselineResults.validate(data)
    if schema_errors:
        result["feedback"].extend(schema_errors)
        return result

    metrics = data.get("baseline_metrics", [])
    for i, m in enumerate(metrics):
        field_errors = ModelMetrics.validate(m)
        if field_errors:
            result["feedback"].extend(
                f"Model {i} ({m.get('model', '?')}): {e}" for e in field_errors
            )
            return result

    violations = sum(
        1 for m in metrics
        if m.get("eu_ai_act_eod_violation") or m.get("eu_ai_act_spd_violation")
    )
    if violations == 0:
        result["feedback"].append(
            "No fairness violations detected. Paper requires baseline models that violate EU AI Act thresholds."
        )
        return result

    result["passed"] = True
    result["feedback"].append(f"Detection OK: {len(metrics)} models, {violations} with violations.")
    return result


def _evaluate_mitigation_rules():
    """Rule-based mitigation checks. Uses MitigationResults schema validation."""
    result = {"passed": False, "feedback": []}

    json_path = os.path.join(OUTPUT_DIR, "mitigation_results.json")
    if not os.path.exists(json_path):
        result["feedback"].append(
            "mitigation_results.json not found. Run mitigation_agent.py after detection."
        )
        return result

    data = _load_json(json_path)
    if not data:
        result["feedback"].append("mitigation_results.json is invalid or empty.")
        return result

    schema_errors = MitigationResults.validate(data)
    if schema_errors:
        result["feedback"].extend(schema_errors)
        return result

    baseline = data.get("baseline_metrics", [])
    mitigation = data.get("mitigation_metrics", [])

    plot_path = os.path.join(OUTPUT_DIR, "mitigation_comparison.png")
    if not os.path.exists(plot_path):
        result["feedback"].append("mitigation_comparison.png not generated.")
        return result

    result["passed"] = True
    result["feedback"].append(
        f"Mitigation OK: {len(baseline)} baseline + {len(mitigation)} mitigated models."
    )
    return result


def _evaluate_auditing_rules():
    """Rule-based auditing checks with structural guardrails."""
    result = {"passed": False, "feedback": []}

    draft_path = os.path.join(OUTPUT_DIR, "paper", "paper.tex")
    if not os.path.exists(draft_path):
        draft_path = os.path.join(OUTPUT_DIR, "paper_draft.md")
    if not os.path.exists(draft_path):
        result["feedback"].append("paper.tex / paper_draft.md not found. Run auditing_agent.py.")
        return result

    draft = _read_file(draft_path)
    if len(draft) < MIN_PAPER_LENGTH:
        result["feedback"].append(
            f"Paper too short ({len(draft)} chars). Minimum {MIN_PAPER_LENGTH}."
        )
        return result

    # Structural guardrails: catch defects that waste Gemini calls
    abstract_count = draft.lower().count("\\begin{abstract}")
    if abstract_count > 1:
        result["feedback"].append(
            f"Duplicated abstract ({abstract_count} occurrences). Paper is structurally broken."
        )
        return result

    doc_begin_count = draft.count("\\begin{document}")
    if doc_begin_count > 1:
        result["feedback"].append(
            f"Multiple \\begin{{document}} ({doc_begin_count}). Section files contain document wrappers."
        )
        return result

    missing_sections = []
    for section in REQUIRED_PAPER_SECTIONS:
        if section.lower() not in draft.lower():
            missing_sections.append(section)
    if missing_sections:
        result["feedback"].append(f"Missing sections: {', '.join(missing_sections)}")
        return result

    if "\\begin{table" not in draft and "Model & Acc" not in draft and "| Model" not in draft:
        result["feedback"].append(
            "Paper should include detection/mitigation results tables."
        )
        return result

    # Check for truncation: paper should have content after the last required section
    last_section_pos = max(
        draft.lower().rfind(s.lower()) for s in REQUIRED_PAPER_SECTIONS
    )
    remaining_after_last = len(draft) - last_section_pos if last_section_pos > 0 else 0
    if remaining_after_last < 100:
        last_section_name = "unknown"
        for s in REQUIRED_PAPER_SECTIONS:
            if draft.lower().rfind(s.lower()) == last_section_pos:
                last_section_name = s
                break
        result["feedback"].append(
            f"Paper appears truncated: only {remaining_after_last} chars after last required section "
            f"('{last_section_name}' at position {last_section_pos}/{len(draft)}). "
            f"This usually means Gemini output was cut off during paper generation. "
            f"The auditing agent should be re-run — the LLM truncation guardrail will now retry automatically."
        )
        return result

    # Check for dangling incomplete content near the end
    end_doc_pos = draft.rfind("\\end{document}")
    check_region = draft[:end_doc_pos].rstrip() if end_doc_pos > 0 else draft.rstrip()
    if len(check_region) > 100:
        dangling = re.search(
            r"\s+(?:the|a|an|in|on|at|by|for|with|of|to|from|and|or|but|particularly)\s*$",
            check_region[-200:],
            re.IGNORECASE,
        )
        if dangling:
            result["feedback"].append(
                f"Paper content ends with incomplete sentence: '...{check_region[-60:].strip()}'. "
                f"Re-run auditing agent — the truncation guardrail should fix this."
            )
            return result

    result["passed"] = True
    msg = f"Auditing OK: draft {len(draft)} chars, all sections present."
    if os.path.exists(os.path.join(OUTPUT_DIR, "paper", "paper.tex")):
        msg += " LaTeX paper generated."
    if os.path.exists(os.path.join(OUTPUT_DIR, "paper", "paper.pdf")):
        msg += " PDF compiled."
    result["feedback"].append(msg)
    return result


# ====================================================================
# Gemini-based semantic evaluation (when API key is set)
# ====================================================================


def _gemini_evaluate_detection(baseline_data):
    """Use Gemini to evaluate detection quality and consistency."""
    try:
        from utils.llm_client import generate, is_available
        if not is_available():
            return None
    except ImportError:
        return None

    prompt = f"""You are a research quality evaluator for a paper on bias in financial AI (credit card fraud detection).

Evaluate the DETECTION AGENT output. The agent trained baseline models and computed fairness metrics.

**Baseline metrics (JSON):**
```json
{json.dumps(baseline_data.get("baseline_metrics", []), indent=2)}
```

**Your task:**
1. Are the metrics internally consistent? (e.g., DPD, EOD, DI align with positive rates)
2. Do the results support the paper's claim that "baseline models violate EU AI Act thresholds"?
3. Is the evidence sufficient for a research paper?

Respond in JSON only:
{{"passed": true/false, "reasoning": "2-3 sentence explanation", "suggestions": ["optional improvement"]}}
"""
    out = generate(prompt)
    if not out:
        return None
    # Extract JSON from response
    import re
    m = re.search(r'\{[^{}]*"passed"[^{}]*\}', out, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return None


def _gemini_evaluate_mitigation(baseline_data, mitigation_data):
    """Use Gemini to evaluate mitigation quality and trade-off analysis."""
    try:
        from utils.llm_client import generate, is_available
        if not is_available():
            return None
    except ImportError:
        return None

    prompt = f"""You are a research quality evaluator for a paper on bias mitigation in financial AI.

**Baseline metrics:** {json.dumps(baseline_data.get("baseline_metrics", [])[:2], indent=2)}

**Mitigation metrics:** {json.dumps(mitigation_data.get("mitigation_metrics", []), indent=2)}

**Asymmetric cost analysis:** {json.dumps(mitigation_data.get("asymmetric_cost_analysis", {}), indent=2)}

**Your task:**
1. Does the mitigation actually improve fairness (lower |DPD|, |EOD| or higher DI)?
2. Is the "asymmetric cost" (accuracy/fairness trade-off) correctly demonstrated?
3. Are the claims supported by the numbers?

Respond in JSON only:
{{"passed": true/false, "reasoning": "2-3 sentence explanation", "suggestions": []}}
"""
    out = generate(prompt)
    if not out:
        return None
    import re
    m = re.search(r'\{[^{}]*"passed"[^{}]*\}', out, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return None


def _gemini_evaluate_auditing(draft_text, baseline_data, mitigation_data):
    """Use Gemini to evaluate paper quality, consistency, and claim support."""
    try:
        from utils.llm_client import generate, is_available
        if not is_available():
            return None
    except ImportError:
        return None

    # Truncate draft if very long to fit context
    draft_preview = draft_text[:12000] + "..." if len(draft_text) > 12000 else draft_text

    mit_summary = ""
    if mitigation_data:
        for m in (mitigation_data.get("mitigation_metrics", []) or [])[:5]:
            model = m.get("model", "?")
            eod = m.get("equalized_odds_diff")
            di = m.get("disparate_impact_ratio")
            dpd = m.get("demographic_parity_diff")
            eod_s = f"{eod:+.4f}" if eod is not None else "N/A"
            di_s = f"{di:.4f}" if di is not None else "N/A"
            dpd_s = f"{dpd:+.4f}" if dpd is not None else "N/A"
            mit_summary += f"  {model}: EOD={eod_s}, DI={di_s}, DPD={dpd_s}\n"

    prompt = f"""You are a research paper reviewer. Evaluate this draft on bias detection/mitigation in financial AI.

**CRITICAL: The paper MUST fit the testing results.** If the paper claims "XGBoost + SMOTE substantially improves fairness" but the data shows EOD remains high (e.g. > 0.05) or Disparate Impact worsens, the paper is WRONG and must be revised to match the data.

**Paper draft (excerpt):**
{draft_preview}

**Detection results:** {json.dumps(baseline_data.get("baseline_metrics", []) if baseline_data else [], indent=2)[:800]}

**Mitigation results (key metrics — EU AI Act: |EOD| ≤ 0.05, DI ≥ 0.8, |DPD| ≤ 0.1):**
{mit_summary or json.dumps(mitigation_data.get("mitigation_metrics", [])[:4] if mitigation_data else [], indent=2)[:600]}

**Your task:**
1. Do the paper's claims EXACTLY match the experimental results? Check: Does it claim XGBoost+SMOTE "substantially improves fairness" when EOD is high or DI worsens? If so, FAIL.
2. Are key sections (Background, Use Case, Detection, Mitigation, Audit, Discussion) present and coherent?
3. Are formulas (Demographic Parity, Disparate Impact, Equalized Odds) mentioned?
4. If XGBoost+SMOTE has EOD > 0.05 or DI < 0.8, the paper must say post-processing (threshold adjustment) is required — not that it "substantially improves" or "achieves EU compliance" without it.
5. Provide actionable suggestions: e.g. "Change intro to state that XGBoost+SMOTE improves DPD but requires threshold adjustment for EOD/DI compliance; EOD=0.77, DI=0.04 in data."

Respond in JSON only:
{{"passed": true/false, "reasoning": "2-4 sentence explanation", "suggestions": ["max 2 concrete, actionable fixes to align paper with data"]}}
"""
    out = generate(prompt)
    if not out:
        return None
    import re
    m = re.search(r'\{[\s\S]*"passed"[\s\S]*\}', out)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            m2 = re.search(r'\{[^{}]*"passed"[^{}]*\}', m.group(0))
            if m2:
                try:
                    return json.loads(m2.group(0))
                except json.JSONDecodeError:
                    pass
    return None


# ====================================================================
# Public API
# ====================================================================


def _to_judge_result(d: dict) -> JudgeResult:
    """Convert internal dict to JudgeResult dataclass."""
    return JudgeResult(
        passed=d["passed"],
        feedback=d.get("feedback", []),
        retry_hint=d.get("retry_hint"),
        actionable_feedback=d.get("actionable_feedback"),
    )


def evaluate_detection() -> JudgeResult:
    """Evaluate Detection Agent outputs. Rule-based + optional Gemini."""
    rules = _evaluate_detection_rules()
    if not rules["passed"]:
        return JudgeResult(passed=False, feedback=rules["feedback"], retry_hint="detection")

    data = _load_json(os.path.join(OUTPUT_DIR, "baseline_results.json"))
    gemini_result = _gemini_evaluate_detection(data) if data else None
    if gemini_result and not gemini_result.get("passed", True):
        rules["feedback"].append(f"[Gemini] {gemini_result.get('reasoning', 'Quality concern')}")
        if gemini_result.get("suggestions"):
            rules["feedback"].extend(f"  - {s}" for s in gemini_result["suggestions"])
        return JudgeResult(passed=False, feedback=rules["feedback"], retry_hint="detection:try_different_seed")
    elif gemini_result and gemini_result.get("reasoning"):
        rules["feedback"].append(f"[Gemini] {gemini_result['reasoning']}")

    return JudgeResult(passed=True, feedback=rules["feedback"])


def evaluate_mitigation() -> JudgeResult:
    """Evaluate Mitigation Agent outputs. Rule-based + optional Gemini."""
    rules = _evaluate_mitigation_rules()
    if not rules["passed"]:
        return JudgeResult(passed=False, feedback=rules["feedback"], retry_hint="mitigation")

    baseline = _load_json(os.path.join(OUTPUT_DIR, "baseline_results.json"))
    mitigation = _load_json(os.path.join(OUTPUT_DIR, "mitigation_results.json"))
    gemini_result = _gemini_evaluate_mitigation(baseline or {}, mitigation or {})
    if gemini_result and not gemini_result.get("passed", True):
        rules["feedback"].append(f"[Gemini] {gemini_result.get('reasoning', 'Quality concern')}")
        return JudgeResult(passed=False, feedback=rules["feedback"], retry_hint="mitigation")
    elif gemini_result and gemini_result.get("reasoning"):
        rules["feedback"].append(f"[Gemini] {gemini_result['reasoning']}")

    return JudgeResult(passed=True, feedback=rules["feedback"])


def evaluate_auditing() -> JudgeResult:
    """Evaluate Auditing Agent outputs. Rule-based + optional Gemini."""
    rules = _evaluate_auditing_rules()
    if not rules["passed"]:
        return JudgeResult(passed=False, feedback=rules["feedback"], retry_hint="auditing")

    tex_path = os.path.join(OUTPUT_DIR, "paper", "paper.tex")
    draft = _read_file(tex_path) or _read_file(os.path.join(OUTPUT_DIR, "paper_draft.md"))
    baseline = _load_json(os.path.join(OUTPUT_DIR, "baseline_results.json"))
    mitigation = _load_json(os.path.join(OUTPUT_DIR, "mitigation_results.json"))
    gemini_result = _gemini_evaluate_auditing(draft, baseline or {}, mitigation or {})
    if gemini_result and not gemini_result.get("passed", True):
        reasoning = gemini_result.get("reasoning", "Quality concern")
        rules["feedback"].append(f"[Gemini] {reasoning}")
        suggestions = gemini_result.get("suggestions") or []
        if suggestions:
            rules["feedback"].extend(f"  - {s}" for s in suggestions)
        actionable = reasoning
        if suggestions:
            actionable += "\n\nSuggestions:\n" + "\n".join(f"- {s}" for s in suggestions)
        return JudgeResult(
            passed=False, feedback=rules["feedback"],
            retry_hint="revise_claims", actionable_feedback=actionable,
        )
    elif gemini_result and gemini_result.get("reasoning"):
        rules["feedback"].append(f"[Gemini] {gemini_result['reasoning']}")

    return JudgeResult(passed=True, feedback=rules["feedback"])


def evaluate(agent_name: str) -> JudgeResult:
    """Evaluate a specific agent's output. Returns a JudgeResult dataclass."""
    evaluators = {
        "detection": evaluate_detection,
        "mitigation": evaluate_mitigation,
        "auditing": evaluate_auditing,
    }
    fn = evaluators.get(agent_name)
    if not fn:
        return JudgeResult(passed=False, feedback=[f"Unknown agent: {agent_name}"])
    return fn()


def evaluate_all() -> dict[str, JudgeResult]:
    """Evaluate all agent outputs in pipeline order."""
    return {
        "detection": evaluate_detection(),
        "mitigation": evaluate_mitigation(),
        "auditing": evaluate_auditing(),
    }


if __name__ == "__main__":
    import sys
    agent = sys.argv[1] if len(sys.argv) > 1 else None
    if agent:
        r = evaluate(agent)
        print(f"Agent: {agent} | Passed: {r.passed}")
        for msg in r.feedback:
            print(f"  - {msg}")
        if r.retry_hint:
            print(f"  Retry hint: {r.retry_hint}")
    else:
        for name, r in evaluate_all().items():
            status = "PASS" if r.passed else "FAIL"
            print(f"[{status}] {name}: {r.feedback[0] if r.feedback else 'OK'}")
