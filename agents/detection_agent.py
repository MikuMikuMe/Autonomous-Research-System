"""
Detection Agent — Bias Detection in Credit Card Fraud Models
Team: Mihailo & Kai Kim

Hour 1: Load dataset, inject synthetic protected attribute, train baseline
        Logistic Regression, compute initial fairness metrics.
Hour 2: Train Balanced Random Forest, compute Disparate Impact & Equalized
        Odds for both models, produce baseline comparison table and plots.
Hour 4: Export ROC curves and Fairness Metric bar charts to outputs/figures/
        for inclusion in the research paper (Methodology & Results sections).
"""

import os
import json
import warnings

print("  Loading libraries (numpy, pandas, sklearn...)...", flush=True)
import numpy as np
import pandas as pd
import kagglehub
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    roc_auc_score,
    roc_curve,
)
from imblearn.ensemble import BalancedRandomForestClassifier
from fairlearn.metrics import (
    demographic_parity_difference,
    equalized_odds_difference,
)

warnings.filterwarnings("ignore")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "outputs")
FIGURES_DIR = os.path.join(OUTPUT_DIR, "figures")
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(FIGURES_DIR, exist_ok=True)

EU_AI_ACT_SPD_THRESHOLD = 0.1
EU_AI_ACT_EOD_THRESHOLD = 0.05
DISPARATE_IMPACT_THRESHOLD = 0.8


# ====================================================================
# HOUR 1 — Dataset, Protected Attribute, Baseline Logistic Regression
# ====================================================================


def _progress(pct: float, label: str = ""):
    """Emit progress marker for GUI (parsed by streaming orchestrator)."""
    print(f"[QMIND_PROGRESS]{pct:.2f}{f'|{label}' if label else ''}", flush=True)


def download_dataset():
    """Download the MLG-ULB Credit Card Fraud dataset via kagglehub."""
    print("  Downloading dataset (Kaggle)...", flush=True)
    _progress(0.02, "Starting dataset download")
    print("=" * 64)
    print("  Dataset Loading & Baseline Detection")
    print("=" * 64)

    path = kagglehub.dataset_download("mlg-ulb/creditcardfraud")
    _progress(0.08, "Dataset downloaded")
    csv_path = os.path.join(path, "creditcard.csv")
    df = pd.read_csv(csv_path)

    print(f"  Dataset shape        : {df.shape}")
    print(f"  Fraud cases          : {df['Class'].sum()}")
    print(f"  Fraud rate           : {df['Class'].mean():.4%}")
    return df


def inject_protected_attribute(df, seed=42):
    """Create a synthetic protected attribute to simulate demographic bias.

    The real dataset has no demographic columns (V1-V28 are PCA-anonymised).
    We split on V14 (one of the strongest fraud-discriminative features) so
    that the two groups have genuinely different feature distributions, which
    causes the model to produce systematically different prediction rates —
    exactly the kind of representational bias the paper needs to demonstrate.
    """
    np.random.seed(seed)
    median_v14 = df["V14"].median()
    noise = np.random.normal(0, 0.3, len(df))
    score = (df["V14"] - median_v14) / df["V14"].std() + noise
    df["protected_group"] = (score < 0).astype(int)  # 0 = disadvantaged

    g = df.groupby("protected_group")["Class"]
    print("\n  Protected attribute injected (simulated age_group via V14):")
    for gid, sub in g:
        label = "Disadvantaged (0)" if gid == 0 else "Advantaged   (1)"
        print(f"    {label}: n={len(sub):>6,}  fraud_rate={sub.mean():.4%}")
    return df


def prepare_data(df, seed=42):
    """Train/test split and standard-scale features."""
    feature_cols = [c for c in df.columns if c not in ("Class", "protected_group")]
    X = df[feature_cols].values
    y = df["Class"].values
    A = df["protected_group"].values

    X_train, X_test, y_train, y_test, A_train, A_test = train_test_split(
        X, y, A, test_size=0.3, random_state=seed, stratify=y
    )

    scaler = StandardScaler()
    X_train = scaler.fit_transform(X_train)
    X_test = scaler.transform(X_test)

    _progress(0.15, "Data prepared")
    print(f"\n  Train samples: {X_train.shape[0]:,}")
    print(f"  Test  samples: {X_test.shape[0]:,}")
    return X_train, X_test, y_train, y_test, A_train, A_test, scaler


def _compute_fpr(y_true, y_pred):
    """False positive rate = FP / (FP + TN). In fraud detection, FPR costs money."""
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()
    return fp / (fp + tn) if (fp + tn) > 0 else 0.0


def compute_fairness_metrics(y_true, y_pred, y_score, sensitive, model_name):
    """Return a dict of accuracy and fairness metrics."""
    dp_diff = demographic_parity_difference(y_true, y_pred, sensitive_features=sensitive)
    eo_diff = equalized_odds_difference(y_true, y_pred, sensitive_features=sensitive)

    pos_rate_0 = y_pred[sensitive == 0].mean()
    pos_rate_1 = y_pred[sensitive == 1].mean()
    di_ratio = (
        min(pos_rate_0, pos_rate_1) / max(pos_rate_0, pos_rate_1)
        if max(pos_rate_0, pos_rate_1) > 0
        else 0.0
    )

    acc = accuracy_score(y_true, y_pred)
    f1 = f1_score(y_true, y_pred)
    auc = roc_auc_score(y_true, y_score)
    fpr = _compute_fpr(y_true, y_pred)

    m = {
        "model": model_name,
        "accuracy": round(acc, 4),
        "f1_score": round(f1, 4),
        "auc": round(auc, 4),
        "false_positive_rate": round(fpr, 6),
        "demographic_parity_diff": round(dp_diff, 4),
        "equalized_odds_diff": round(eo_diff, 4),
        "disparate_impact_ratio": round(di_ratio, 4),
        "positive_rate_group_0": round(pos_rate_0, 6),
        "positive_rate_group_1": round(pos_rate_1, 6),
        "eu_ai_act_spd_violation": bool(abs(dp_diff) > EU_AI_ACT_SPD_THRESHOLD),
        "eu_ai_act_eod_violation": bool(abs(eo_diff) > EU_AI_ACT_EOD_THRESHOLD),
    }

    _print_metrics(m)
    return m


def _print_metrics(m):
    spd_flag = "VIOLATION" if m["eu_ai_act_spd_violation"] else "OK"
    eod_flag = "VIOLATION" if m["eu_ai_act_eod_violation"] else "OK"
    di_flag = "VIOLATION" if m["disparate_impact_ratio"] < DISPARATE_IMPACT_THRESHOLD else "OK"

    print(f"\n  --- {m['model']} ---")
    print(f"  Accuracy            : {m['accuracy']:.4f}")
    print(f"  F1 Score            : {m['f1_score']:.4f}")
    print(f"  AUC                 : {m['auc']:.4f}")
    print(f"  False Positive Rate : {m.get('false_positive_rate', 0):.6f}")
    print(f"  Demographic Parity D: {m['demographic_parity_diff']:+.4f}  [{spd_flag}] (threshold +/-{EU_AI_ACT_SPD_THRESHOLD})")
    print(f"  Equalized Odds D    : {m['equalized_odds_diff']:+.4f}  [{eod_flag}] (threshold +/-{EU_AI_ACT_EOD_THRESHOLD})")
    print(f"  Disparate Impact    : {m['disparate_impact_ratio']:.4f}   [{di_flag}] (threshold >={DISPARATE_IMPACT_THRESHOLD})")
    print(f"  Pos-rate group 0    : {m['positive_rate_group_0']:.6f}")
    print(f"  Pos-rate group 1    : {m['positive_rate_group_1']:.6f}")


def train_logistic_regression(X_train, y_train, X_test, y_test, A_test, seed=42):
    """Hour 1 — Baseline Logistic Regression."""
    _progress(0.20, "Training Logistic Regression")
    print("\n  >> Training Logistic Regression (baseline) ...")
    model = LogisticRegression(max_iter=1000, random_state=seed, class_weight="balanced")
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    y_score = model.predict_proba(X_test)[:, 1]

    _progress(0.35, "Logistic Regression complete")
    metrics = compute_fairness_metrics(y_test, y_pred, y_score, A_test, "Logistic Regression")
    return model, y_pred, y_score, metrics


# ====================================================================
# HOUR 2 — Balanced Random Forest, Full Baseline Table & Plots
# ====================================================================


def train_balanced_random_forest(X_train, y_train, X_test, y_test, A_test, seed=42):
    """Hour 2 — Balanced Random Forest baseline."""
    _progress(0.40, "Training Balanced Random Forest")
    print("\n  >> Training Balanced Random Forest ...")
    model = BalancedRandomForestClassifier(
        n_estimators=100, random_state=seed, n_jobs=-1
    )
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    y_score = model.predict_proba(X_test)[:, 1]

    _progress(0.65, "Balanced Random Forest complete")
    metrics = compute_fairness_metrics(y_test, y_pred, y_score, A_test, "Balanced Random Forest")
    return model, y_pred, y_score, metrics


def print_baseline_table(all_metrics):
    """Hour 2 deliverable — formatted comparison table."""
    print("\n" + "=" * 94)
    print("  Baseline Bias Detection Table")
    print("=" * 94)
    hdr = (
        f"  {'Model':<26} {'Acc':>6} {'F1':>6} {'AUC':>6}"
        f" {'DPD':>7} {'EOD':>7} {'DI':>6} {'SPD?':>5} {'EOD?':>5}"
    )
    print(hdr)
    print("  " + "-" * 90)
    for m in all_metrics:
        spd_v = "YES" if m["eu_ai_act_spd_violation"] else "no"
        eod_v = "YES" if m["eu_ai_act_eod_violation"] else "no"
        print(
            f"  {m['model']:<26}"
            f" {m['accuracy']:>6.4f}"
            f" {m['f1_score']:>6.4f}"
            f" {m['auc']:>6.4f}"
            f" {m['demographic_parity_diff']:>+7.4f}"
            f" {m['equalized_odds_diff']:>+7.4f}"
            f" {m['disparate_impact_ratio']:>6.4f}"
            f" {spd_v:>5}"
            f" {eod_v:>5}"
        )
    print("  " + "-" * 90)
    print("  Thresholds — EU AI Act: |SPD| <= 0.1, |EOD| <= 0.05, DI >= 0.8")
    print("=" * 94)
    _progress(0.75, "Generating plots")


def plot_fairness(all_metrics):
    """Bar charts comparing fairness metrics across baseline models."""
    models = [m["model"] for m in all_metrics]
    dp = [abs(m["demographic_parity_diff"]) for m in all_metrics]
    eo = [abs(m["equalized_odds_diff"]) for m in all_metrics]
    di = [m["disparate_impact_ratio"] for m in all_metrics]

    colours = ["#e74c3c", "#3498db"]
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))

    axes[0].bar(models, dp, color=colours)
    axes[0].axhline(EU_AI_ACT_SPD_THRESHOLD, color="k", ls="--", label=f"Threshold ({EU_AI_ACT_SPD_THRESHOLD})")
    axes[0].set_title("|Demographic Parity Diff|")
    axes[0].set_ylabel("|DPD|")
    axes[0].legend()
    axes[0].tick_params(axis="x", rotation=12)

    axes[1].bar(models, eo, color=colours)
    axes[1].axhline(EU_AI_ACT_EOD_THRESHOLD, color="k", ls="--", label=f"Threshold ({EU_AI_ACT_EOD_THRESHOLD})")
    axes[1].set_title("|Equalized Odds Diff|")
    axes[1].set_ylabel("|EOD|")
    axes[1].legend()
    axes[1].tick_params(axis="x", rotation=12)

    axes[2].bar(models, di, color=colours)
    axes[2].axhline(DISPARATE_IMPACT_THRESHOLD, color="k", ls="--", label=f"Threshold ({DISPARATE_IMPACT_THRESHOLD})")
    axes[2].set_title("Disparate Impact Ratio")
    axes[2].set_ylabel("DI")
    axes[2].legend()
    axes[2].tick_params(axis="x", rotation=12)

    fig.suptitle("Baseline Bias Detection — Fairness Metrics", fontsize=14, fontweight="bold")
    plt.tight_layout()
    for ext, dpi in [("png", 150), ("pdf", 150)]:
        path = os.path.join(FIGURES_DIR, f"fig_baseline_fairness.{ext}")
        fig.savefig(path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    _progress(0.85, "Fairness plots saved")
    print(f"\n  Plots saved: {FIGURES_DIR}/fig_baseline_fairness.{{png,pdf}}")


def plot_roc_curves(models_data):
    """ROC curves for each baseline model."""
    fig, ax = plt.subplots(figsize=(8, 6))
    for name, y_true, y_score in models_data:
        fpr, tpr, _ = roc_curve(y_true, y_score)
        auc_val = roc_auc_score(y_true, y_score)
        ax.plot(fpr, tpr, label=f"{name} (AUC={auc_val:.3f})")
    ax.plot([0, 1], [0, 1], "k--", alpha=0.4)
    ax.set_xlabel("False Positive Rate")
    ax.set_ylabel("True Positive Rate")
    ax.set_title("Baseline ROC Curves")
    ax.legend()
    plt.tight_layout()
    for ext, dpi in [("png", 150), ("pdf", 150)]:
        path = os.path.join(FIGURES_DIR, f"fig_baseline_roc.{ext}")
        fig.savefig(path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    _progress(0.92, "ROC plots saved")
    print(f"  Plots saved: {FIGURES_DIR}/fig_baseline_roc.{{png,pdf}}")


def save_results(all_metrics, X_train, X_test, y_train, y_test, A_train, A_test):
    """Persist results as JSON and data splits as .npz for the Mitigation Agent."""
    json_path = os.path.join(OUTPUT_DIR, "baseline_results.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"baseline_metrics": all_metrics}, f, indent=2)
    print(f"\n  Baseline metrics saved : {json_path}")

    npz_path = os.path.join(OUTPUT_DIR, "data_splits.npz")
    np.savez(
        npz_path,
        X_train=X_train, X_test=X_test,
        y_train=y_train, y_test=y_test,
        A_train=A_train, A_test=A_test,
    )
    print(f"  Data splits saved      : {npz_path}")
    _progress(1.0, "Detection complete")


# ====================================================================
# MAIN
# ====================================================================


def main(seed=42):
    """Run detection pipeline. seed can be varied for retries (e.g. if judge requests)."""
    # ---- HOUR 1 ----
    df = download_dataset()
    df = inject_protected_attribute(df, seed=seed)
    X_train, X_test, y_train, y_test, A_train, A_test, _scaler = prepare_data(df, seed=seed)

    lr_model, lr_pred, lr_score, lr_metrics = train_logistic_regression(
        X_train, y_train, X_test, y_test, A_test, seed=seed
    )

    # ---- HOUR 2 ----
    print("\n" + "=" * 64)
    print("  Balanced Random Forest + Full Baseline Table")
    print("=" * 64)

    brf_model, brf_pred, brf_score, brf_metrics = train_balanced_random_forest(
        X_train, y_train, X_test, y_test, A_test, seed=seed
    )

    all_metrics = [lr_metrics, brf_metrics]
    print_baseline_table(all_metrics)

    plot_fairness(all_metrics)
    plot_roc_curves([
        ("Logistic Regression", y_test, lr_score),
        ("Balanced Random Forest", y_test, brf_score),
    ])
    save_results(all_metrics, X_train, X_test, y_train, y_test, A_train, A_test)

    print("\n  Detection Agent complete. Baseline bias assessment ready.")
    print("  Hand off outputs/ directory to Mitigation Agent.\n")


if __name__ == "__main__":
    import sys
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 42
    main(seed=seed)
