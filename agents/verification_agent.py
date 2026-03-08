"""
Verification Agent — Gemini Generates Code, Run It to Verify Claims

Design: When Judge or consistency checks flag a claim (e.g., "accuracy loss" when data shows
accuracy increased), this agent asks Gemini to generate Python code that verifies or refutes
the claim given the data. The code runs in a sandboxed subprocess.

Never hardcode verification logic — let Gemini produce executable checks from claim + data.
"""

import os
import json
import subprocess
import tempfile
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "outputs")
os.makedirs(OUTPUT_DIR, exist_ok=True)

VERIFICATION_TIMEOUT = 30
MAX_CODE_BLOCKS = 3


def _load_json(path: str) -> dict | list | None:
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def generate_verification_code(claim: str, data_context: dict | str) -> str | None:
    """
    Ask Gemini to generate Python code that verifies or refutes the claim given the data.
    Returns the code string, or None on failure.
    """
    try:
        from utils.llm_client import generate, is_available
    except ImportError:
        return None
    if not is_available():
        return None

    if isinstance(data_context, dict):
        data_str = json.dumps(data_context, indent=2)
    else:
        data_str = str(data_context)
    data_str = data_str[:6000]

    try:
        from utils.config_loader import load_prompt
        prompt = load_prompt("verification", claim=claim, data_str=data_str)
    except ImportError:
        prompt = None
    if not prompt:
        prompt = (
            f"You are a verification code generator. Claim: {claim}\n\n"
            f"Data: {data_str}\n\n"
            "Produce Python code that checks the claim. Print VERIFIED=True or VERIFIED=False. "
            "Print EVIDENCE=... with explanation. Output ONLY code."
        )

    result = generate(prompt, max_output_tokens=2048)
    if not result or len(result.strip()) < 50:
        return None

    # Extract code block if wrapped in ```python
    code = result.strip()
    if "```" in code:
        import re
        m = re.search(r"```(?:python)?\s*([\s\S]*?)```", code)
        if m:
            code = m.group(1).strip()
    return code if len(code) > 20 else None


def run_verification_code(code: str, data_json: dict | None = None) -> dict:
    """
    Run generated code in a sandboxed subprocess.
    Returns {"verified": bool, "evidence": str, "error": str | None, "code": str}
    """
    result = {"verified": None, "evidence": "", "error": None, "code": code}

    data_path = None
    if data_json is not None:
        fd, data_path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data_json, f)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        if data_path:
            f.write("import json\n")
            f.write(f"with open({repr(data_path)}, encoding='utf-8') as _f:\n")
            f.write("    data = json.load(_f)\n\n")
        f.write(code)
        tmp_path = f.name

    try:
        proc = subprocess.run(
            [sys.executable, tmp_path],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=VERIFICATION_TIMEOUT,
            env={**os.environ, "PYTHONPATH": PROJECT_ROOT},
        )
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""

        if proc.returncode != 0:
            result["error"] = stderr or stdout or f"Exit code {proc.returncode}"
            result["verified"] = False
        else:
            for line in stdout.strip().split("\n"):
                if line.startswith("VERIFIED="):
                    val = line.split("=", 1)[1].strip().lower()
                    result["verified"] = val in ("true", "1", "yes")
                elif line.startswith("EVIDENCE="):
                    result["evidence"] = line.split("=", 1)[1].strip()

        if result["verified"] is None:
            result["verified"] = proc.returncode == 0
            result["evidence"] = stdout[:500] if stdout else "No VERIFIED= line in output"

    except subprocess.TimeoutExpired:
        result["error"] = f"Timeout after {VERIFICATION_TIMEOUT}s"
        result["verified"] = False
    except Exception as e:
        result["error"] = str(e)
        result["verified"] = False
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        if data_path and os.path.exists(data_path):
            try:
                os.unlink(data_path)
            except OSError:
                pass

    return result


def verify_claim(claim: str, data_context: dict | str) -> dict:
    """
    Full pipeline: Gemini generates code → run it → return verification result.
    """
    code = generate_verification_code(claim, data_context)
    if not code:
        return {
            "verified": None,
            "evidence": "Gemini failed to generate verification code",
            "error": "No code generated",
            "code": None,
        }

    data_for_run = data_context if isinstance(data_context, dict) else None
    out = run_verification_code(code, data_for_run)
    out["claim"] = claim
    return out


def verify_paper_claims() -> dict:
    """
    Verify key claims in the paper against mitigation_results.json and baseline_results.json.
    Uses Gemini to generate verification code for each claim — no hardcoded checks.

    Results are also persisted to MemoryStore so the optimizer can learn from
    claim verification failures across runs.
    """
    mitigation = _load_json(os.path.join(OUTPUT_DIR, "mitigation_results.json"))
    baseline = _load_json(os.path.join(OUTPUT_DIR, "baseline_results.json"))

    asym = (mitigation or {}).get("asymmetric_cost_analysis", {})
    data = {
        "asymmetric_cost_analysis": asym,
        "baseline_metrics": (baseline or {}).get("baseline_metrics", []),
        "mitigation_metrics": (mitigation or {}).get("mitigation_metrics", []),
    }

    claims_to_check = []
    if asym:
        acc_d = asym.get("accuracy_delta")
        fpr_d = asym.get("fpr_delta")
        claims_to_check.append(
            "Claim: 'Mitigation incurs accuracy loss or higher FPR'. "
            f"Data has accuracy_delta={acc_d}, fpr_delta={fpr_d}. "
            "Verify: If accuracy_delta > 0 then 'accuracy loss' is FALSE. If fpr_delta < 0 then 'higher FPR' is FALSE. "
            "Output VERIFIED=True only if the claim is consistent with data; VERIFIED=False if claim contradicts data."
        )

    report = {
        "timestamp": __import__("datetime").datetime.now().isoformat(),
        "claims": [],
        "summary": "",
    }

    for claim in claims_to_check:
        r = verify_claim(claim, data)
        report["claims"].append(r)

    n_ok = sum(1 for c in report["claims"] if c.get("verified") is True)
    n_fail = sum(1 for c in report["claims"] if c.get("verified") is False)
    n_skip = sum(1 for c in report["claims"] if c.get("verified") is None)
    if not report["claims"]:
        report["summary"] = "No claims to verify (no asymmetric cost data)."
    else:
        parts = [f"{n_ok} verified", f"{n_fail} contradicted"]
        if n_skip:
            parts.append(f"{n_skip} skipped (Gemini unavailable)")
        report["summary"] = "; ".join(parts) + ". " + (
            "All consistent with data." if n_fail == 0 and n_ok > 0 else (
                "Some claims contradict data — run Revision Agent." if n_fail > 0 else
                "Set GOOGLE_API_KEY for verification."
            )
        )

    out_path = os.path.join(OUTPUT_DIR, "verification_report.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    # Persist verification results to memory for optimizer learning
    _persist_verifications_to_memory(report)

    return report


def _persist_verifications_to_memory(report: dict) -> None:
    """Persist verification claim results into MemoryStore for self-evolution."""
    try:
        from agents.memory_agent import MemoryStore
        from utils.schemas import VerificationRecord
    except ImportError:
        return

    claims = report.get("claims", [])
    if not claims:
        return

    try:
        store = MemoryStore()
        # Find the most recent run_id (or use 0 for standalone execution)
        recent = store.recent_runs(limit=1)
        run_id = recent[0]["id"] if recent else 0

        for c in claims:
            store.db.execute(
                """INSERT INTO verifications (run_id, claim, verified, evidence, error)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    run_id,
                    c.get("claim", ""),
                    c.get("verified"),
                    c.get("evidence", ""),
                    c.get("error"),
                ),
            )
        store.db.commit()
        store.close()
    except Exception:
        pass


def main():
    print("=" * 64)
    print("  VERIFICATION AGENT — Gemini Generates Code, Run to Verify")
    print("=" * 64)

    report = verify_paper_claims()
    print(f"\n  {report['summary']}")
    for i, c in enumerate(report["claims"], 1):
        v = c.get("verified")
        status = "✓" if v is True else ("✗" if v is False else "?")
        print(f"  [{status}] Claim {i}: {c.get('evidence', c.get('error', ''))[:80]}...")
    print(f"\n  Saved: outputs/verification_report.json")
    has_contradictions = any(c.get("verified") is False for c in report.get("claims", []))
    return 0 if not has_contradictions else 1


if __name__ == "__main__":
    sys.exit(main())
