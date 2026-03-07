"""
Reproducibility Agent — Runs detection and mitigation with multiple seeds to verify
that AI-generated claims in the paper can be reproduced.

Testable claims (from paper / RESEARCH_CHECKLIST):
- Baseline LR and Balanced RF violate EU AI Act thresholds (SPD, EOD)
- SMOTE + XGBoost improves fairness vs baseline
- Reweighting has minimal effect on LR
- Threshold adjustment reduces disparities

Runs 3 seeds (42, 43, 44), compares metrics, outputs reproducibility_report.json.
"""

import json
import os
import subprocess
import sys
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "outputs")
os.makedirs(OUTPUT_DIR, exist_ok=True)

SEEDS = [42, 43, 44]
EU_SPD = 0.1
EU_EOD = 0.05


def _run_agent(agent: str, seed: int) -> bool:
    """Run detection or mitigation agent. Returns True if success."""
    cmd = [sys.executable, "-m", agent, str(seed)]
    result = subprocess.run(cmd, cwd=SCRIPT_DIR, capture_output=True, text=True, timeout=300)
    return result.returncode == 0


def _save_baseline_copy(seed: int) -> None:
    """Copy baseline_results.json to seed-specific file before next run overwrites."""
    src = os.path.join(OUTPUT_DIR, "baseline_results.json")
    if not os.path.exists(src):
        return
    dst = os.path.join(OUTPUT_DIR, f"baseline_results_seed{seed}.json")
    with open(src, encoding="utf-8") as f:
        data = json.load(f)
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _load_baseline(seed: int) -> list | None:
    """Load baseline_results from seed-specific copy or main file."""
    for name in [f"baseline_results_seed{seed}.json", "baseline_results.json"]:
        path = os.path.join(OUTPUT_DIR, name)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            return data.get("baseline_metrics", [])
    return None


def _load_mitigation() -> list | None:
    path = os.path.join(OUTPUT_DIR, "mitigation_results.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("mitigation_metrics", [])


def run_reproducibility_tests() -> dict:
    """
    Run detection with seeds 42,43,44 (one at a time, overwrites outputs).
    Then run mitigation once (uses last detection output).
    Compare metrics across detection runs.
    """
    report = {
        "timestamp": datetime.now().isoformat(),
        "testable_claims": [
            "Baseline LR violates EU AI Act (|SPD|>0.1 or |EOD|>0.05)",
            "Baseline Balanced RF violates EU AI Act",
            "SMOTE + XGBoost improves fairness vs baseline",
            "Threshold adjustment reduces DPD/EOD",
        ],
        "detection_runs": [],
        "mitigation_run": None,
        "reproducibility": {},
        "summary": "",
    }

    # Run detection for each seed (each overwrites baseline_results.json)
    for seed in SEEDS:
        ok = _run_agent("detection_agent", seed)
        if ok:
            _save_baseline_copy(seed)  # Preserve before next run overwrites
        baseline = _load_baseline(seed) if ok else None
        report["detection_runs"].append({
            "seed": seed,
            "success": ok,
            "baseline_metrics": baseline,
        })
        if not ok:
            print(f"  Detection seed={seed} FAILED")
        else:
            print(f"  Detection seed={seed} OK")

    # Run mitigation once (uses last detection)
    if report["detection_runs"] and report["detection_runs"][-1]["success"]:
        ok = _run_agent("mitigation_agent", SEEDS[-1])
        report["mitigation_run"] = {
            "success": ok,
            "mitigation_metrics": _load_mitigation() if ok else None,
        }
        print(f"  Mitigation OK" if ok else "  Mitigation FAILED")
    else:
        report["mitigation_run"] = {"success": False, "reason": "Detection failed"}

    # Analyze reproducibility
    baseline_runs = [r for r in report["detection_runs"] if r["success"] and r.get("baseline_metrics")]
    if len(baseline_runs) >= 2:
        # Check if LR and BRF consistently violate
        lr_violations = []
        brf_violations = []
        for run in baseline_runs:
            for m in run["baseline_metrics"]:
                model_name = m.get("model", "")
                if "Logistic" in model_name:
                    spd = abs(m.get("demographic_parity_diff", 0))
                    eod = abs(m.get("equalized_odds_diff", 0))
                    lr_violations.append(spd > EU_SPD or eod > EU_EOD)
                if "Balanced" in model_name:
                    spd = abs(m.get("demographic_parity_diff", 0))
                    eod = abs(m.get("equalized_odds_diff", 0))
                    brf_violations.append(spd > EU_SPD or eod > EU_EOD)
        report["reproducibility"]["baseline_LR_violates"] = all(lr_violations) if lr_violations else None
        report["reproducibility"]["baseline_BRF_violates"] = all(brf_violations) if brf_violations else None

    # Mitigation: SMOTE improves fairness?
    mit = report.get("mitigation_run", {})
    if mit.get("success") and mit.get("mitigation_metrics"):
        smote_metrics = [m for m in mit["mitigation_metrics"] if "SMOTE" in m.get("model", "")]
        baseline_metrics = [m for r in baseline_runs for m in r["baseline_metrics"]]
        if smote_metrics and baseline_metrics:
            avg_baseline_dpd = sum(abs(m.get("demographic_parity_diff", 0)) for m in baseline_metrics) / len(baseline_metrics)
            avg_smote_dpd = sum(abs(m.get("demographic_parity_diff", 0)) for m in smote_metrics) / len(smote_metrics)
            report["reproducibility"]["SMOTE_improves_fairness"] = avg_smote_dpd < avg_baseline_dpd

    # Summary
    rep = report["reproducibility"]
    parts = []
    if rep.get("baseline_LR_violates") is not None:
        parts.append("LR violates" if rep["baseline_LR_violates"] else "LR does NOT consistently violate")
    if rep.get("baseline_BRF_violates") is not None:
        parts.append("BRF violates" if rep["baseline_BRF_violates"] else "BRF does NOT consistently violate")
    if rep.get("SMOTE_improves_fairness") is not None:
        parts.append("SMOTE improves fairness" if rep["SMOTE_improves_fairness"] else "SMOTE does NOT improve")
    report["summary"] = "; ".join(parts) if parts else "Insufficient data for reproducibility analysis"

    out_path = os.path.join(OUTPUT_DIR, "reproducibility_report.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n  Saved: {out_path}")
    return report


if __name__ == "__main__":
    print("=" * 60)
    print("  Reproducibility Agent")
    print("  Testing claims with seeds:", SEEDS)
    print("=" * 60)
    run_reproducibility_tests()
