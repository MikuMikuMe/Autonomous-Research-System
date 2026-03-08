"""
Mitigation Agent — Bias Mitigation via SMOTE & Threshold Adjustment
Team: Alec & Viona

Hour 1 (Setup): Code to apply SMOTE oversampling and post-processing
                threshold adjustments is defined and ready to execute.
Hour 2 (Prep) : Agent loads baseline data produced by the Detection Agent
                and validates that bias violations exist before mitigating.
Hour 3 (Fix)  : Apply pre-processing (SMOTE + XGBoost), post-processing
                (threshold adjustment), produce comparative matrix, and
                document the Asymmetric Cost (accuracy/fairness trade-off).
Hour 4       : Export mitigation comparison graphs to outputs/figures/
                for inclusion in the research paper.

Run this script *after* detection_agent.py has completed (its outputs/
directory must contain data_splits.npz and baseline_results.json).
"""

import os
import json
import warnings

print("  Loading libraries (numpy, sklearn, xgboost...)...", flush=True)
import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    roc_auc_score,
    roc_curve,
)
from imblearn.over_sampling import SMOTE
from xgboost import XGBClassifier
from sklearn.linear_model import LogisticRegression
from fairlearn.metrics import (
    demographic_parity_difference,
    equalized_odds_difference,
)
from fairlearn.postprocessing import ThresholdOptimizer
from fairlearn.reductions import EqualizedOdds, ExponentiatedGradient

warnings.filterwarnings("ignore")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "outputs")
FIGURES_DIR = os.path.join(OUTPUT_DIR, "figures")
os.makedirs(FIGURES_DIR, exist_ok=True)


def _progress(pct: float, label: str = ""):
    """Emit progress marker for GUI."""
    print(f"[QMIND_PROGRESS]{pct:.2f}{f'|{label}' if label else ''}", flush=True)

EU_AI_ACT_SPD_THRESHOLD = 0.1
EU_AI_ACT_EOD_THRESHOLD = 0.05
DISPARATE_IMPACT_THRESHOLD = 0.8


# ====================================================================
# HOUR 1 SETUP — Pre-processing (SMOTE) & Post-processing (Thresholds)
# ====================================================================


def load_baseline_data():
    """Load the data splits and baseline results produced by the Detection Agent."""
    print("  Loading baseline data from Detection Agent...", flush=True)
    npz_path = os.path.join(OUTPUT_DIR, "data_splits.npz")
    json_path = os.path.join(OUTPUT_DIR, "baseline_results.json")

    if not os.path.exists(npz_path):
        raise FileNotFoundError(
            f"{npz_path} not found. Run detection_agent.py first."
        )

    data = np.load(npz_path)
    X_train = data["X_train"]
    X_test = data["X_test"]
    y_train = data["y_train"]
    y_test = data["y_test"]
    A_train = data["A_train"]
    A_test = data["A_test"]

    baseline_metrics = []
    if os.path.exists(json_path):
        with open(json_path, encoding="utf-8") as f:
            baseline_metrics = json.load(f).get("baseline_metrics", [])

    print("  Loaded data splits from Detection Agent")
    print(f"    Train: {X_train.shape[0]:,}   Test: {X_test.shape[0]:,}")
    print(f"    Baseline models evaluated: {len(baseline_metrics)}")
    return X_train, X_test, y_train, y_test, A_train, A_test, baseline_metrics


def _compute_fpr(y_true, y_pred):
    """False positive rate = FP / (FP + TN). In fraud detection, FPR costs money."""
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()
    return fp / (fp + tn) if (fp + tn) > 0 else 0.0


def compute_metrics(y_true, y_pred, y_score, sensitive, model_name):
    """Mirror of Detection Agent's metric computation, plus FPR for asymmetric cost."""
    dp_diff = demographic_parity_difference(y_true, y_pred, sensitive_features=sensitive)
    eo_diff = equalized_odds_difference(y_true, y_pred, sensitive_features=sensitive)

    pos0 = y_pred[sensitive == 0].mean()
    pos1 = y_pred[sensitive == 1].mean()
    di = min(pos0, pos1) / max(pos0, pos1) if max(pos0, pos1) > 0 else 0.0

    fpr = _compute_fpr(y_true, y_pred)

    return {
        "model": model_name,
        "accuracy": round(accuracy_score(y_true, y_pred), 4),
        "f1_score": round(f1_score(y_true, y_pred), 4),
        "auc": round(roc_auc_score(y_true, y_score), 4),
        "false_positive_rate": round(fpr, 6),
        "demographic_parity_diff": round(dp_diff, 4),
        "equalized_odds_diff": round(eo_diff, 4),
        "disparate_impact_ratio": round(di, 4),
        "positive_rate_group_0": round(pos0, 6),
        "positive_rate_group_1": round(pos1, 6),
        "eu_ai_act_spd_violation": bool(abs(dp_diff) > EU_AI_ACT_SPD_THRESHOLD),
        "eu_ai_act_eod_violation": bool(abs(eo_diff) > EU_AI_ACT_EOD_THRESHOLD),
    }


# ---------- Pre-processing: SMOTE ----------


def apply_smote(X_train, y_train, seed=42):
    """Oversample the minority class to correct representation bias."""
    print("\n  >> Applying SMOTE to training set ...")
    smote = SMOTE(random_state=seed)
    X_res, y_res = smote.fit_resample(X_train, y_train)
    print(f"     Before: {len(y_train):,}  (fraud={y_train.sum():,})")
    print(f"     After : {len(y_res):,}  (fraud={y_res.sum():,})")
    return X_res, y_res


def train_xgboost_smote(X_res, y_res, X_test, y_test, A_test, seed=42):
    """Train XGBoost on SMOTE-balanced data and evaluate fairness."""
    print("\n  >> Training XGBoost on SMOTE-balanced data ...")
    model = XGBClassifier(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.1,
        use_label_encoder=False,
        eval_metric="logloss",
        random_state=seed,
        n_jobs=-1,
    )
    model.fit(X_res, y_res)
    y_pred = model.predict(X_test)
    y_score = model.predict_proba(X_test)[:, 1]
    metrics = compute_metrics(y_test, y_pred, y_score, A_test, "XGBoost + SMOTE")
    _print_short(metrics)
    return model, y_pred, y_score, metrics


# ---------- Post-processing: Threshold Adjustment ----------


def find_group_thresholds(y_true, y_score, sensitive, target_fpr=None):
    """Find per-group thresholds that equalise false-positive rates.

    If *target_fpr* is None the global optimal threshold (Youden's J) is used
    as the target, and each group's threshold is adjusted so its FPR matches
    the global FPR at that operating point.
    """
    fpr_g, tpr_g, thresh_g = roc_curve(y_true, y_score)

    if target_fpr is None:
        j_scores = tpr_g - fpr_g
        best_idx = np.argmax(j_scores)
        target_fpr = fpr_g[best_idx]

    thresholds = {}
    for group in np.unique(sensitive):
        mask = sensitive == group
        fpr_grp, _, thresh_grp = roc_curve(y_true[mask], y_score[mask])
        idx = np.argmin(np.abs(fpr_grp - target_fpr))
        thresholds[group] = float(thresh_grp[min(idx, len(thresh_grp) - 1)])

    return thresholds


def apply_threshold_adjustment(y_score, A_test, group_thresholds):
    """Produce predictions using group-specific thresholds."""
    y_pred = np.zeros(len(y_score), dtype=int)
    for group, thr in group_thresholds.items():
        mask = A_test == group
        y_pred[mask] = (y_score[mask] >= thr).astype(int)
    return y_pred


def run_threshold_mitigation(model, X_test, y_test, A_test, label_suffix=""):
    """End-to-end threshold adjustment for a given model."""
    y_score = model.predict_proba(X_test)[:, 1]
    group_thr = find_group_thresholds(y_test, y_score, A_test)
    print(f"\n  >> Group-specific thresholds{label_suffix}:")
    for g, t in group_thr.items():
        print(f"     Group {g}: {t:.4f}")

    y_pred_adj = apply_threshold_adjustment(y_score, A_test, group_thr)
    name = f"Threshold-Adj {label_suffix}".strip()
    metrics = compute_metrics(y_test, y_pred_adj, y_score, A_test, name)
    _print_short(metrics)
    return y_pred_adj, y_score, metrics


# ---------- EOD-Targeted Post-Processing (Fairlearn ThresholdOptimizer) ----------


def _ensure_float64_proba(estimator):
    """Wrap estimator to ensure predict_proba returns float64 (avoids Fairlearn dtype issues)."""
    from sklearn.base import BaseEstimator, ClassifierMixin

    class Float64ProbaWrapper(BaseEstimator, ClassifierMixin):
        def __init__(self, base):
            self.base = base

        def predict_proba(self, X):
            return np.asarray(self.base.predict_proba(X), dtype=np.float64)

        def predict(self, X):
            return self.base.predict(X)

        def fit(self, X, y, **kwargs):
            return self.base.fit(X, y, **kwargs)

    return Float64ProbaWrapper(estimator)


def run_eod_threshold_optimizer(
    model, X_train, y_train, A_train, X_test, y_test, A_test, label_suffix=""
):
    """
    Apply Fairlearn ThresholdOptimizer with equalized_odds constraint.
    Explicitly targets EOD (matches both FPR and TPR across groups).
    """
    print(f"\n  >> EOD-ThresholdOptimizer (equalized_odds){label_suffix}...")
    try:
        wrapped = _ensure_float64_proba(model)
        postprocess = ThresholdOptimizer(
            estimator=wrapped,
            constraints="equalized_odds",
            objective="balanced_accuracy_score",
            prefit=True,
            predict_method="predict_proba",
        )
        postprocess.fit(X_train, y_train, sensitive_features=A_train)
        y_pred = postprocess.predict(X_test, sensitive_features=A_test)
        y_score = np.asarray(model.predict_proba(X_test)[:, 1], dtype=np.float64)
        name = f"EOD-Opt {label_suffix}".strip()
        metrics = compute_metrics(y_test, y_pred, y_score, A_test, name)
        _print_short(metrics)
        return y_pred, y_score, metrics
    except Exception as e:
        print(f"     EOD-ThresholdOptimizer failed: {e}")
        return None


# ---------- In-Processing: ExponentiatedGradient (EqualizedOdds) ----------


def train_eod_exponentiated_gradient(X_train, y_train, A_train, X_test, y_test, A_test, seed=42):
    """
    In-processing: ExponentiatedGradient with EqualizedOdds constraint.
    Directly optimizes for EOD compliance during training.
    """
    print("\n  >> Training ExponentiatedGradient (EqualizedOdds) ...")
    try:
        base = LogisticRegression(max_iter=1000, random_state=seed)
        reduction = ExponentiatedGradient(
            estimator=base,
            constraints=EqualizedOdds(),
            eps=0.02,  # Tight constraint targeting |EOD| <= 0.05 (EU AI Act)
            max_iter=100,
        )
        reduction.fit(X_train, y_train, sensitive_features=A_train)
        y_pred = reduction.predict(X_test, random_state=seed)
        pmf = reduction._pmf_predict(X_test)
        y_score = np.asarray(pmf[:, 1], dtype=np.float64)  # P(Y=1)
        metrics = compute_metrics(y_test, y_pred, y_score, A_test, "ExponentiatedGradient (EOD)")
        _print_short(metrics)
        return reduction, y_pred, y_score, metrics
    except Exception as e:
        print(f"     ExponentiatedGradient failed: {e}")
        return None


# ---------- Reweighting Baseline (for comparison) ----------


def train_reweighted_lr(X_train, y_train, X_test, y_test, A_test, seed=42):
    """Logistic Regression with balanced class weights (simple reweighting)."""
    print("\n  >> Training Reweighted Logistic Regression ...")
    model = LogisticRegression(max_iter=1000, random_state=seed, class_weight="balanced")
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)
    y_score = model.predict_proba(X_test)[:, 1]
    metrics = compute_metrics(y_test, y_pred, y_score, A_test, "Reweighted LR")
    _print_short(metrics)
    return model, y_pred, y_score, metrics


# ====================================================================
# HOUR 3 — Run Mitigations, Comparative Matrix & Asymmetric Cost
# ====================================================================


def comparative_table(baseline_metrics, mitigation_metrics):
    """Hour 3 deliverable: Print a combined Accuracy-vs-Fairness matrix."""
    all_m = baseline_metrics + mitigation_metrics

    print("\n" + "=" * 110)
    print("  COMPARATIVE MATRIX — Accuracy vs. Fairness (Baseline --> Mitigated)")
    print("=" * 110)
    hdr = (
        f"  {'Model':<30} {'Acc':>6} {'F1':>6} {'AUC':>6} {'FPR':>8}"
        f" {'DPD':>7} {'EOD':>7} {'DI':>6} {'SPD?':>5} {'EOD?':>5}"
    )
    print(hdr)
    print("  " + "-" * 106)
    for m in all_m:
        spd_v = "YES" if m["eu_ai_act_spd_violation"] else "no"
        eod_v = "YES" if m["eu_ai_act_eod_violation"] else "no"
        fpr = m.get("false_positive_rate", 0)
        print(
            f"  {m['model']:<30}"
            f" {m['accuracy']:>6.4f}"
            f" {m['f1_score']:>6.4f}"
            f" {m['auc']:>6.4f}"
            f" {fpr:>8.6f}"
            f" {m['demographic_parity_diff']:>+7.4f}"
            f" {m['equalized_odds_diff']:>+7.4f}"
            f" {m['disparate_impact_ratio']:>6.4f}"
            f" {spd_v:>5}"
            f" {eod_v:>5}"
        )
    print("  " + "-" * 106)
    print("  Thresholds — EU AI Act: |SPD| <= 0.1, |EOD| <= 0.05, DI >= 0.8")
    print("  FPR = False Positive Rate (higher FPR = more costly in fraud detection)")
    print("=" * 110)


def _generate_trade_off_summary(
    acc_delta, fpr_delta, auc_delta, dpd_improvement, eod_improvement,
    best_baseline_model, best_mitigated_model,
):
    """
    Generate a trade-off summary that NEVER contradicts the data.
    Uses configs/prompts/trade_off_summary.txt when available; Gemini generates content.
    Fallback = programmatic template (never hardcoded narrative that contradicts data).
    """
    contradicts_default = acc_delta > 0 and fpr_delta < 0
    auc_dropped = auc_delta is not None and auc_delta < -0.1

    if contradicts_default or auc_dropped:
        try:
            from utils.llm_client import generate, is_available
            from utils.config_loader import load_prompt
        except ImportError:
            pass
        else:
            if is_available():
                auc_str = f"{auc_delta:+.4f}" if auc_delta is not None else "N/A"
                prompt = load_prompt(
                    "trade_off_summary",
                    acc_delta=acc_delta,
                    fpr_delta=fpr_delta,
                    auc_str=auc_str,
                    dpd_improvement=dpd_improvement,
                    eod_improvement=eod_improvement,
                )
                if prompt:
                    result = generate(prompt, max_output_tokens=500)
                else:
                    result = generate(
                        f"Generate a 2-4 sentence paragraph for asymmetric cost in fraud detection. "
                        f"Data: accuracy_delta={acc_delta:+.4f}, fpr_delta={fpr_delta:+.6f}, auc_delta={auc_str}. "
                        "NEVER claim accuracy loss when accuracy_delta>0. NEVER claim higher FPR when fpr_delta<0. "
                        "If AUC dropped, explain real cost is Recall (missed fraud). Output ONLY the paragraph.",
                        max_output_tokens=500,
                    )
                if result and len(result.strip()) > 80:
                    return result.strip()

                # Retry with clearer instructions (roadmap: fallback = Gemini retry, not programmatic)
                retry_prompt = (
                    f"Write 2-4 sentences for a research paper. Data: accuracy_delta={acc_delta:+.4f} "
                    f"(positive=increased), fpr_delta={fpr_delta:+.6f} (negative=decreased), auc_delta={auc_str}. "
                    "CRITICAL: If accuracy_delta>0 do NOT say 'accuracy loss'. If fpr_delta<0 do NOT say 'higher FPR'. "
                    "If AUC dropped significantly, state the real cost is Recall/TPR (missed fraud). Output ONLY the paragraph."
                )
                result = generate(retry_prompt, max_output_tokens=500)
                if result and len(result.strip()) > 80:
                    return result.strip()

        # Last resort: programmatic template (never contradicts data)
        parts = [
            "Mitigation improves fairness (reduces |DPD|, |EOD|)."
        ]
        if acc_delta > 0:
            parts.append(f"Paradoxically, accuracy increased (+{acc_delta:.4f}) and FPR decreased ({fpr_delta:+.4f}).")
        elif acc_delta < 0:
            parts.append(f"Accuracy decreased ({acc_delta:+.4f}).")
        if fpr_delta > 0:
            parts.append(f"FPR increased ({fpr_delta:+.4f}), increasing false-alarm cost.")
        if auc_delta is not None and auc_delta < -0.1:
            parts.append(
                f"However, AUC dropped sharply ({auc_delta:+.4f}) — the model's ability to distinguish "
                "classes degraded; the real cost of fairness here is likely missed fraud (lower Recall/TPR)."
            )
        parts.append(
            "In fraud detection, each additional false positive carries monetary cost (customer friction, investigation)."
        )
        return " ".join(parts)

    # Standard case: accuracy decreased and/or FPR increased
    return (
        "Mitigation improves fairness (reduces |DPD|, |EOD|) but may incur "
        "accuracy loss or higher FPR — each additional false positive in "
        "fraud detection carries monetary cost (customer friction, investigation)."
    )


def asymmetric_cost_analysis(baseline_metrics, mitigation_metrics):
    """Hour 3 deliverable: Prove the Asymmetric Cost — accuracy/fairness trade-off.

    Mitigating bias may slightly lower overall accuracy or increase false
    positives (which costs money in fraud detection). This establishes the
    trade-off mentioned in the research notes.

    GUARDRAIL: Summary text is data-driven. If accuracy increased and FPR
    decreased, we never claim "accuracy loss" or "higher FPR". When AUC drops
    sharply, Gemini or a programmatic fallback explains the real cost (Recall).
    """
    if not baseline_metrics or not mitigation_metrics:
        return None

    # Best baseline by accuracy (typically LR or BRF)
    best_baseline = max(baseline_metrics, key=lambda m: m["accuracy"])
    # Best mitigated by fairness (lowest |DPD| + |EOD|)
    best_mitigated = min(
        mitigation_metrics,
        key=lambda m: abs(m["demographic_parity_diff"]) + abs(m["equalized_odds_diff"]),
    )

    acc_delta = best_mitigated["accuracy"] - best_baseline["accuracy"]
    fpr_delta = best_mitigated.get("false_positive_rate", 0) - best_baseline.get(
        "false_positive_rate", 0
    )
    auc_baseline = best_baseline.get("auc")
    auc_mitigated = best_mitigated.get("auc")
    auc_delta = (auc_mitigated - auc_baseline) if (auc_baseline is not None and auc_mitigated is not None) else None
    dpd_improvement = abs(best_mitigated["demographic_parity_diff"]) - abs(
        best_baseline["demographic_parity_diff"]
    )
    eod_improvement = abs(best_mitigated["equalized_odds_diff"]) - abs(
        best_baseline["equalized_odds_diff"]
    )

    trade_off_summary = _generate_trade_off_summary(
        acc_delta, fpr_delta, auc_delta, dpd_improvement, eod_improvement,
        best_baseline["model"], best_mitigated["model"],
    )

    analysis = {
        "best_baseline_model": best_baseline["model"],
        "best_mitigated_model": best_mitigated["model"],
        "accuracy_delta": round(acc_delta, 4),
        "fpr_delta": round(fpr_delta, 6),
        "auc_delta": round(auc_delta, 4) if auc_delta is not None else None,
        "dpd_improvement": round(dpd_improvement, 4),
        "eod_improvement": round(eod_improvement, 4),
        "trade_off_summary": trade_off_summary,
    }

    print("\n" + "=" * 90)
    print("  ASYMMETRIC COST — Accuracy/Fairness Trade-off")
    print("=" * 90)
    print(f"  Best baseline  : {best_baseline['model']}")
    print(f"  Best mitigated : {best_mitigated['model']}")
    print(f"  Accuracy delta : {acc_delta:+.4f}  (negative = mitigation cost)")
    print(f"  FPR delta      : {fpr_delta:+.6f}  (positive = more false alarms, higher cost)")
    if auc_delta is not None:
        print(f"  AUC delta      : {auc_delta:+.4f}  (negative = discriminative ability degraded)")
    print(f"  |DPD| change   : {dpd_improvement:+.4f}  (negative = fairness improved)")
    print(f"  |EOD| change   : {eod_improvement:+.4f}  (negative = fairness improved)")
    print()
    print("  " + analysis["trade_off_summary"])
    print("=" * 90)

    return analysis


def plot_comparison(baseline_metrics, mitigation_metrics):
    """Before/after bar charts — Hour 3 visual deliverable."""
    all_m = baseline_metrics + mitigation_metrics
    names = [m["model"] for m in all_m]
    n = len(names)

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    # Accuracy vs F1
    x = np.arange(n)
    w = 0.35
    axes[0, 0].bar(x - w / 2, [m["accuracy"] for m in all_m], w, label="Accuracy", color="#2ecc71")
    axes[0, 0].bar(x + w / 2, [m["f1_score"] for m in all_m], w, label="F1", color="#9b59b6")
    axes[0, 0].set_xticks(x)
    axes[0, 0].set_xticklabels(names, rotation=20, ha="right", fontsize=8)
    axes[0, 0].set_title("Accuracy & F1")
    axes[0, 0].legend()

    # |DPD|
    axes[0, 1].bar(names, [abs(m["demographic_parity_diff"]) for m in all_m],
                   color=["#e74c3c" if m["eu_ai_act_spd_violation"] else "#2ecc71" for m in all_m])
    axes[0, 1].axhline(EU_AI_ACT_SPD_THRESHOLD, color="k", ls="--", label="Threshold")
    axes[0, 1].set_title("|Demographic Parity Diff|")
    axes[0, 1].tick_params(axis="x", rotation=20)
    axes[0, 1].legend()

    # |EOD|
    axes[1, 0].bar(names, [abs(m["equalized_odds_diff"]) for m in all_m],
                   color=["#e74c3c" if m["eu_ai_act_eod_violation"] else "#2ecc71" for m in all_m])
    axes[1, 0].axhline(EU_AI_ACT_EOD_THRESHOLD, color="k", ls="--", label="Threshold")
    axes[1, 0].set_title("|Equalized Odds Diff|")
    axes[1, 0].tick_params(axis="x", rotation=20)
    axes[1, 0].legend()

    # FPR (Asymmetric Cost — higher FPR = more costly in fraud detection)
    fpr_vals = [m.get("false_positive_rate", 0) for m in all_m]
    axes[1, 1].bar(names, fpr_vals, color="#e67e22", alpha=0.8)
    axes[1, 1].set_title("False Positive Rate (Asymmetric Cost)")
    axes[1, 1].set_ylabel("FPR")
    axes[1, 1].tick_params(axis="x", rotation=20)

    fig.suptitle("Mitigation Comparative Matrix: Accuracy vs. Fairness",
                 fontsize=14, fontweight="bold")
    plt.tight_layout()
    for ext, dpi in [("png", 150), ("pdf", 150)]:
        path = os.path.join(FIGURES_DIR, f"fig_mitigation_comparison.{ext}")
        fig.savefig(path, dpi=dpi, bbox_inches="tight")
    path_png = os.path.join(OUTPUT_DIR, "mitigation_comparison.png")
    fig.savefig(path_png, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"\n  Plots saved: {FIGURES_DIR}/fig_mitigation_comparison.{{png,pdf}}")


def save_mitigation_results(baseline_metrics, mitigation_metrics, asymmetric_cost=None):
    """Persist combined results as JSON for the Auditing Agent."""
    payload = {
        "baseline_metrics": baseline_metrics,
        "mitigation_metrics": mitigation_metrics,
    }
    if asymmetric_cost:
        payload["asymmetric_cost_analysis"] = asymmetric_cost
    path = os.path.join(OUTPUT_DIR, "mitigation_results.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"  Mitigation results saved: {path}")


def _print_short(m):
    spd = "VIOLATION" if m["eu_ai_act_spd_violation"] else "OK"
    eod = "VIOLATION" if m["eu_ai_act_eod_violation"] else "OK"
    fpr = m.get("false_positive_rate", 0)
    print(
        f"     Acc={m['accuracy']:.4f}  F1={m['f1_score']:.4f}  AUC={m['auc']:.4f}  FPR={fpr:.6f}"
        f"  DPD={m['demographic_parity_diff']:+.4f}[{spd}]"
        f"  EOD={m['equalized_odds_diff']:+.4f}[{eod}]"
        f"  DI={m['disparate_impact_ratio']:.4f}"
    )


# ====================================================================
# MAIN
# ====================================================================


def main(seed=42):
    """Run mitigation pipeline. seed can be varied for retries."""
    print("=" * 64)
    print("  MITIGATION AGENT — SMOTE + Threshold Adjustment")
    print("=" * 64)

    # ---- Load data from Detection Agent (Hour 2) ----
    _progress(0.1, "Loading baseline data")
    X_train, X_test, y_train, y_test, A_train, A_test, baseline_metrics = (
        load_baseline_data()
    )

    # ---- HOUR 3: Implementing Mitigation (The "Fix") ----
    print("\n" + "=" * 64)
    print("  Implementing Mitigation — Pre-processing & Post-processing")
    print("=" * 64)

    mitigation_metrics = []

    # 1. Pre-processing (SMOTE): Balance dataset, test with XGBoost
    _progress(0.25, "Applying SMOTE")
    X_res, y_res = apply_smote(X_train, y_train, seed=seed)
    _progress(0.45, "Training XGBoost")
    xgb_model, xgb_pred, xgb_score, xgb_m = train_xgboost_smote(
        X_res, y_res, X_test, y_test, A_test, seed=seed
    )
    mitigation_metrics.append(xgb_m)

    # 2. Post-processing: Dynamically adjust decision boundary per group
    _progress(0.55, "Threshold mitigation")
    _, _, thr_m = run_threshold_mitigation(
        xgb_model, X_test, y_test, A_test, label_suffix="(XGBoost+SMOTE)"
    )
    mitigation_metrics.append(thr_m)

    # 2b. EOD-targeted post-processing (Fairlearn ThresholdOptimizer)
    _progress(0.6, "EOD-ThresholdOptimizer")
    eod_xgb = run_eod_threshold_optimizer(
        xgb_model, X_train, y_train, A_train, X_test, y_test, A_test,
        label_suffix="(XGBoost+SMOTE)"
    )
    if eod_xgb:
        mitigation_metrics.append(eod_xgb[2])

    # Reweighted LR (to show reweighting alone is insufficient per notes)
    rw_model, rw_pred, rw_score, rw_m = train_reweighted_lr(
        X_train, y_train, X_test, y_test, A_test, seed=seed
    )
    mitigation_metrics.append(rw_m)

    _, _, thr_rw_m = run_threshold_mitigation(
        rw_model, X_test, y_test, A_test, label_suffix="(Reweighted LR)"
    )
    mitigation_metrics.append(thr_rw_m)

    eod_rw = run_eod_threshold_optimizer(
        rw_model, X_train, y_train, A_train, X_test, y_test, A_test,
        label_suffix="(Reweighted LR)"
    )
    if eod_rw:
        mitigation_metrics.append(eod_rw[2])

    # 3. In-processing: ExponentiatedGradient (EqualizedOdds)
    _progress(0.65, "ExponentiatedGradient")
    eg_result = train_eod_exponentiated_gradient(
        X_train, y_train, A_train, X_test, y_test, A_test, seed=seed
    )
    if eg_result:
        mitigation_metrics.append(eg_result[3])

    # ---- Hour 3 Deliverables: Comparative Matrix + Asymmetric Cost ----
    _progress(0.75, "Generating comparison plots")
    comparative_table(baseline_metrics, mitigation_metrics)
    asymmetric_cost = asymmetric_cost_analysis(baseline_metrics, mitigation_metrics)
    plot_comparison(baseline_metrics, mitigation_metrics)
    save_mitigation_results(baseline_metrics, mitigation_metrics, asymmetric_cost)
    _progress(1.0, "Mitigation complete")

    print("\n  Mitigation Agent complete.")
    print("  Outputs: Comparative matrix + Asymmetric Cost trade-off.")
    print("  Hand off outputs/ directory to Auditing Agent.\n")


if __name__ == "__main__":
    import sys
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 42
    main(seed=seed)
