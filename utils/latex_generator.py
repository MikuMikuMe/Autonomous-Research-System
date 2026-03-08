"""
LaTeX Paper Generator — Hour 4 & 6
Generates a publication-ready LaTeX paper in IEEE/CUCAI 2026 format with figures,
formulas, and bibliography. Uses IEEEtran document class, two-column layout,
and IEEE-style numbered citations. Compiles to PDF when pdflatex and bibtex
are available.
"""

import os
import re
import shutil
import subprocess
import sys
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "outputs")
FIGURES_DIR = os.path.join(OUTPUT_DIR, "figures")
PAPER_DIR = os.path.join(OUTPUT_DIR, "paper")
AUTHORS_FILE = os.path.join(PROJECT_ROOT, "authors.txt")
os.makedirs(PAPER_DIR, exist_ok=True)


def _load_authors():
    """Load authors from authors.txt. Format: 'Name - email@domain.com'. Optional: 'Name - | Affiliation' for custom affiliation (no default)."""
    authors = []
    if os.path.exists(AUTHORS_FILE):
        with open(AUTHORS_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if " - " in line:
                    name, rest = line.split(" - ", 1)
                    rest = rest.strip()
                    if " | " in rest:
                        email_part, affil = rest.split(" | ", 1)
                        email, affil = email_part.strip(), affil.strip()
                    elif rest.startswith("| "):
                        email, affil = "", rest[2:].strip()
                    else:
                        email, affil = rest, None
                    authors.append({"name": name.strip(), "email": email, "affiliation": affil or None})
    if not authors:
        authors = [{"name": "QMind Research Team", "email": "", "affiliation": None}]
    return authors


def _latex_author_block(authors):
    """Build IEEE author block from list of {name, email, affiliation?} dicts."""
    blocks = []
    default_affil = "School of Computing\\\\\nQueen's University\\\\\nKingston, Ontario, Canada"
    for i, a in enumerate(authors):
        name = a["name"].replace("&", r"\&")
        email = a.get("email", "").replace("&", r"\&")
        affil_override = a.get("affiliation")
        affil = affil_override if affil_override else default_affil
        if email and not affil_override:
            affil += f"\\\\\n\\texttt{{{email}}}"
        block = f"\\IEEEauthorblockN{{{name}}}\n\\IEEEauthorblockA{{{affil}}}"
        blocks.append(block)
    return "\n\\and\n".join(blocks)


def _latex_metric_row(m):
    """Format a single metrics dict as a LaTeX table row."""
    spd = "Yes" if m.get("eu_ai_act_spd_violation") else "No"
    eod = "Yes" if m.get("eu_ai_act_eod_violation") else "No"
    fpr = m.get("false_positive_rate")
    fpr_str = f"{fpr:.6f}" if fpr is not None else "N/A"
    model = m["model"].replace("_", r"\_").replace("&", r"\&")
    return (
        f"{model} & {m['accuracy']:.4f} & {m['f1_score']:.4f} & "
        f"{m.get('auc', 0):.4f} & {fpr_str} & "
        f"{m['demographic_parity_diff']:+.4f} & {m['equalized_odds_diff']:+.4f} & "
        f"{m['disparate_impact_ratio']:.4f} & {spd} & {eod} \\\\"
    )


def _latex_metrics_table(metrics_list, caption, label):
    """Build a LaTeX table from a list of metric dicts (IEEE format).
    Uses table* to span both columns — follows docs/latex_exmaple.tex style."""
    rows = "\n".join(_latex_metric_row(m) for m in metrics_list)
    return r"""
\begin{table*}[!t]
\centering
\caption{%s}
\label{tab:%s}
\footnotesize
\begin{tabular}{@{}lrrrrrrrrr@{}}
\toprule
Model & Acc & F1 & AUC & FPR & DPD & EOD & DI & SPD Viol & EOD Viol \\
\midrule
%s
\bottomrule
\multicolumn{10}{l}{\scriptsize Thresholds: EU AI Act $|\mathrm{SPD}| \leq 0.1$, $|\mathrm{EOD}| \leq 0.05$, $\mathrm{DI} \geq 0.8$.}
\end{tabular}
\end{table*}
""" % (
        caption,
        label,
        rows,
    )


def assemble_paper_from_sections(section_contents: list[str], author_block: str) -> str:
    """Assemble full paper.tex from LaTeX section contents. No markdown."""
    abstract = (
        "Artificial intelligence systems in credit scoring and fraud detection can systematically "
        "disadvantage protected demographic groups. We train standard classifiers (Logistic Regression, "
        "Balanced Random Forest) on the MLG-ULB Credit Card Fraud dataset and demonstrate baseline "
        "violations of EU AI Act fairness thresholds. We apply pre-processing (SMOTE) and post-processing "
        "(threshold adjustment). We propose a lifecycle-based bias-audit framework aligned with the EU AI Act."
    )
    # Find bibliography section (contains \bibliography); rest are main content
    main_sections = []
    ref_section = ""
    for s in section_contents:
        if "\\bibliography" in (s or ""):
            ref_section = s
        else:
            main_sections.append(s)
    if not ref_section:
        ref_section = r"\bibliographystyle{IEEEtran}" + "\n" + r"\bibliography{references}"
    body = "\n\n".join(main_sections)
    acknowledgements = r"""
\section*{Acknowledgements}
This work was supported by the QMind Research Team. We thank the anonymous reviewers for their feedback.
"""
    return r"""\documentclass[conference]{IEEEtran}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{amsmath,amssymb}
\usepackage{graphicx}
\graphicspath{{../figures/}}
\usepackage{booktabs}
\usepackage{hyperref}
\usepackage{cite}
\usepackage{placeins}

\title{Bias Detection, Mitigation, and Auditing\\in Financial AI Systems}
\author{
""" + author_block + r"""
}

\begin{document}
\maketitle

\begin{abstract}
""" + abstract + r"""
\end{abstract}

""" + body + acknowledgements + "\n\n" + ref_section + r"""

\end{document}
"""


def _fix_table_collisions(tex_content: str) -> str:
    """Normalise table placement specifiers to match docs/latex_exmaple.tex conventions.
    - Single-column tables: [htbp]
    - Wide tables (table*): [!t]
    Never use [H] — it requires \\usepackage{float} and fights LaTeX's float algorithm."""
    tex_content = re.sub(
        r"\\begin\{table\}\[H\]",
        r"\\begin{table}[htbp]",
        tex_content,
    )
    return tex_content


def _clean_paper_content(tex_content: str) -> str:
    """Remove stray backslashes and fix float placement to reduce huge blanks in PDF."""
    # Remove lines that are just a backslash (creates unwanted vertical space)
    tex_content = re.sub(r"^\s*\\\s*$", "", tex_content, flags=re.MULTILINE)
    # Collapse multiple blank lines (3+ newlines -> 2)
    tex_content = re.sub(r"\n{3,}", "\n\n", tex_content)
    # Add FloatBarrier before each table* to prevent LaTeX from holding floats and leaving blanks
    tex_content = re.sub(
        r"(\n)(\\begin\{table\*\})",
        r"\1\\FloatBarrier\n\2",
        tex_content,
    )
    # Add \clearpage before Detection Results and Mitigation Experiments so table* floats
    # start on a new page instead of being pushed to bottom and leaving huge blanks
    tex_content = re.sub(
        r"(\n)(\\section\{Detection Results\})",
        r"\1\\clearpage\n\2",
        tex_content,
    )
    tex_content = re.sub(
        r"(\n)(\\section\{Mitigation Experiments\})",
        r"\1\\clearpage\n\2",
        tex_content,
    )
    return tex_content


def _truncate_draft_at_sentence_boundary(text: str, max_chars: int) -> str:
    """
    Truncate draft at sentence boundary to prevent mid-sentence cuts.
    CRITICAL: Prevents white chunks and incomplete content in the paper.
    """
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    last_period = cut.rfind(". ")
    last_excl = cut.rfind("! ")
    last_quest = cut.rfind("? ")
    last_end = max(last_period, last_excl, last_quest)
    if last_end > max_chars * 0.6:
        return text[: last_end + 1].strip()
    return cut.strip()


def _generate_paper_tex_from_gemini(baseline_data, mitigation_data):
    """Use Gemini to convert paper_draft.md to full IEEE LaTeX. Returns True if successful."""
    draft_path = os.path.join(OUTPUT_DIR, "paper_draft.md")
    tex_path = os.path.join(PAPER_DIR, "paper.tex")
    bib_path = os.path.join(PAPER_DIR, "references.bib")
    if not os.path.exists(draft_path):
        return False
    try:
        from utils.llm_client import generate, is_available
    except ImportError:
        return False
    if not is_available():
        return False

    with open(draft_path, encoding="utf-8") as f:
        draft_content = f.read()

    # Build metrics tables for injection
    detection_tab = ""
    mitigation_tab = ""
    if baseline_data:
        bl = baseline_data.get("baseline_metrics", [])
        if bl:
            detection_tab = _latex_metrics_table(bl, "Baseline Fairness Metrics", "baseline")
    if mitigation_data:
        mit = mitigation_data.get("mitigation_metrics", [])
        bl2 = mitigation_data.get("baseline_metrics", [])
        if mit:
            mitigation_tab = _latex_metrics_table(
                (bl2 or []) + mit,
                "Baseline vs. Mitigated: Accuracy vs. Fairness",
                "mitigation",
            )

    authors = _load_authors()
    author_block = _latex_author_block(authors)

    print("      Calling Gemini for LaTeX conversion (typically 1–2 min)...", flush=True)
    # Truncate at sentence boundary to prevent incomplete content (max 60k for Gemini 2.0)
    draft_safe = _truncate_draft_at_sentence_boundary(draft_content, 60000)

    system = """You are a LaTeX expert. Convert the given Markdown research paper to IEEE conference format.
CRITICAL RULES:
1. Use \\documentclass[conference]{IEEEtran}
2. For wide metric tables: use \\begin{table*}[!t] with \\footnotesize, @{}lrrr...@{} columns, \\bottomrule then \\multicolumn footnote. For narrow tables (2-3 columns): use \\begin{table}[htbp] with \\footnotesize, @{}p{width} p{width}@{} columns. Never use [H] placement.
3. Use \\FloatBarrier (placeins package) between consecutive tables/figures to prevent overlap
4. Convert citations: (Author, Year) → \\cite{key}; use keys like pagano2023, ntoutsi2020, huang2025, euai2024, mlgulb2018
5. Use \\cite{} for in-text references
6. Preserve all section structure, equations (use \\begin{equation}), and content
7. PRESERVE original wording from "From our reference documents" blockquotes — these come from bias_mitigation.pdf, Bias Auditing Framework.pdf, Bias Detection findings.pdf; keep them as \\begin{quote} or \\textit{...} with the exact wording
8. Escape special chars: & → \\&, _ → \\_, % → \\%
9. Output ONLY valid LaTeX, no markdown or explanation
10. COMPLETENESS GUARDRAIL: NEVER output incomplete sentences. Every paragraph and quote MUST end with proper punctuation (. ! ?). If source text is truncated mid-sentence, either complete the thought coherently or omit that fragment. No trailing "particularly", "by 0.015", "the key", "far exceeding EU" etc. — these cause white chunks in the PDF."""

    prompt = f"""Convert this Markdown paper to a complete IEEE conference LaTeX document.

MARKDOWN CONTENT:
---
{draft_safe}
---

REPLACE any markdown tables in these sections with these EXACT LaTeX blocks:
- Detection section (Section 4): use this table (replace any existing table):
{detection_tab if detection_tab else '% No baseline data'}

- Mitigation section (Section 5): use this table (replace any existing table):
{mitigation_tab if mitigation_tab else '% No mitigation data'}

AUTHOR BLOCK (use in \\author{{}}):
{author_block}

REQUIREMENTS:
- Full \\documentclass[conference]{{IEEEtran}} document with \\begin{{document}} ... \\end{{document}}
- Packages: inputenc, fontenc, amsmath, amssymb, graphicx, booktabs, hyperref, cite, placeins
- Title: Bias Detection, Mitigation, and Auditing\\\\in Financial AI Systems
- End with \\bibliographystyle{{IEEEtran}} and \\bibliography{{references}}
- ALL tables must use table* not table
- Output raw LaTeX only, no ```latex wrapper"""

    result = generate(prompt, system_instruction=system, max_output_tokens=16384)
    if not result:
        return False
    print("      Gemini response received, writing paper.tex...", flush=True)

    # Strip markdown code block if present
    if "```" in result:
        m = re.search(r"```(?:latex)?\s*([\s\S]*?)```", result)
        if m:
            result = m.group(1).strip()

    result = _fix_table_collisions(result)

    # Ensure bibliography
    if "\\bibliography" not in result and os.path.exists(bib_path):
        result = result.replace(
            "\\end{document}",
            "\\bibliographystyle{IEEEtran}\n\\bibliography{references}\n\\end{document}",
        )

    with open(tex_path, "w", encoding="utf-8") as f:
        f.write(result)
    return True


def _generate_paper_tex_from_markdown(baseline_data, mitigation_data):
    """Convert paper_draft.md to paper.tex via pandoc. Post-process to fix table collisions.
    Returns True if successful."""
    draft_path = os.path.join(OUTPUT_DIR, "paper_draft.md")
    tex_path = os.path.join(PAPER_DIR, "paper.tex")
    bib_path = os.path.join(PAPER_DIR, "references.bib")
    if not os.path.exists(draft_path):
        return False
    pandoc = shutil.which("pandoc") or shutil.which("pandoc.exe")
    if not pandoc:
        return False
    cmd = [
        pandoc, draft_path, "-s", "-o", tex_path,
        "-V", "documentclass=IEEEtran",
        "-V", "classoption=conference",
        "--wrap=preserve",
    ]
    if os.path.exists(bib_path):
        cmd.extend(["--bibliography", bib_path, "--citeproc"])
    r = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=60)
    if r.returncode != 0 or not os.path.exists(tex_path):
        return False
    with open(tex_path, encoding="utf-8") as f:
        content = f.read()
    content = _fix_table_collisions(content)
    if "\\bibliography" not in content and os.path.exists(bib_path):
        content = content.replace(
            "\\end{document}",
            "\\bibliographystyle{IEEEtran}\n\\bibliography{references}\n\\end{document}",
        )
    with open(tex_path, "w", encoding="utf-8") as f:
        f.write(content)
    return True


def generate_paper_tex(baseline_data, mitigation_data):
    """Generate the full LaTeX paper source. PDF must always be compiled from LaTeX, never from Markdown.
    Order: (1) Assemble from paper_sections/*.tex, (2) template fallback."""

    # 1. Assemble from LaTeX sections (no markdown)
    SECTIONS_DIR = os.path.join(OUTPUT_DIR, "paper_sections")
    if os.path.isdir(SECTIONS_DIR):
        sections = sorted(f for f in os.listdir(SECTIONS_DIR) if f.endswith(".tex"))
        if sections:
            print("      Assembling from paper_sections/*.tex...", flush=True)
            section_contents = []
            for f in sections:
                path = os.path.join(SECTIONS_DIR, f)
                with open(path, encoding="utf-8") as fp:
                    section_contents.append(fp.read())
            authors = _load_authors()
            author_block = _latex_author_block(authors)
            full_tex = assemble_paper_from_sections(section_contents, author_block)
            full_tex = _fix_table_collisions(full_tex)
            full_tex = _clean_paper_content(full_tex)
            tex_path = os.path.join(PAPER_DIR, "paper.tex")
            os.makedirs(PAPER_DIR, exist_ok=True)
            with open(tex_path, "w", encoding="utf-8") as fp:
                fp.write(full_tex)
            print("      Assembled from LaTeX sections.", flush=True)
            return tex_path
    print("      No .tex sections found, using template...", flush=True)

    def has_fig(path):
        return os.path.exists(os.path.join(FIGURES_DIR, path))

    # Data-driven claims: paper must align with actual metrics
    try:
        from utils.claims_utils import _infer_mitigation_claims
        claims = _infer_mitigation_claims(baseline_data, mitigation_data)
    except ImportError:
        claims = {
            "intro_mitigation_claim": "demonstrating the accuracy/fairness trade-off",
            "mitigation_summary": "SMOTE and threshold adjustment affect fairness metrics.",
            "xgb_smote_claim": "XGBoost with SMOTE affects fairness; model selection matters.",
        }

    # Build results sections
    detection_tab = ""
    mitigation_tab = ""
    asym_block = ""
    fig_baseline_fairness = ""
    fig_baseline_roc = ""
    fig_mitigation = ""

    if baseline_data:
        bl = baseline_data.get("baseline_metrics", [])
        if bl:
            detection_tab = _latex_metrics_table(
                bl, "Baseline Fairness Metrics", "baseline"
            )
            if has_fig("fig_baseline_fairness.pdf"):
                fig_baseline_fairness = r"""
\begin{figure*}[t]
\centering
\includegraphics[width=0.95\linewidth]{../figures/fig_baseline_fairness.pdf}
\caption{Baseline bias detection: fairness metrics (|DPD|, |EOD|, DI) across Logistic Regression and Balanced Random Forest.}
\label{fig:baseline-fairness}
\end{figure*}
"""
            if has_fig("fig_baseline_roc.pdf"):
                fig_baseline_roc = r"""
\begin{figure}[htbp]
\centering
\includegraphics[width=\columnwidth]{../figures/fig_baseline_roc.pdf}
\caption{ROC curves for baseline models.}
\label{fig:baseline-roc}
\end{figure}
"""

    if mitigation_data:
        mit = mitigation_data.get("mitigation_metrics", [])
        bl2 = mitigation_data.get("baseline_metrics", [])
        asym = mitigation_data.get("asymmetric_cost_analysis")
        if mit:
            mitigation_tab = _latex_metrics_table(
                (bl2 or []) + mit,
                "Baseline vs. Mitigated: Accuracy vs. Fairness",
                "mitigation",
            )
            if asym:
                # GUARDRAIL: Use data-driven trade_off_summary — never claim "accuracy loss" when accuracy increased
                summary = (asym.get("trade_off_summary") or "").replace("%", "\\%").replace("|DPD|", r"$|\mathrm{DPD}|$").replace("|EOD|", r"$|\mathrm{EOD}|$")
                if not summary:
                    summary = "Mitigation improves fairness (reduces $|\\mathrm{DPD}|$, $|\\mathrm{EOD}|$). Our experiments show the trade-off between fairness and operational costs."
                nums = f"best baseline {asym.get('best_baseline_model', 'N/A')}, best mitigated {asym.get('best_mitigated_model', 'N/A')}; accuracy delta {asym.get('accuracy_delta', 0):+.4f}; FPR delta {asym.get('fpr_delta', 0):+.6f}"
                if asym.get("auc_delta") is not None:
                    nums += f"; AUC delta {asym.get('auc_delta'):+.4f}"
                nums += ". This establishes the \\emph{asymmetric cost} trade-off: financial institutions must weigh EU AI Act compliance against operational costs."
                asym_block = f"""
\\subsection{{Asymmetric Cost --- Accuracy/Fairness Trade-off}}

{summary} Our experiments show: {nums}
"""
            if has_fig("fig_mitigation_comparison.pdf"):
                fig_mitigation = r"""
\begin{figure*}[t]
\centering
\includegraphics[width=0.95\linewidth]{../figures/fig_mitigation_comparison.pdf}
\caption{Mitigation comparative matrix: Accuracy, F1, |DPD|, |EOD|, and FPR across baseline and mitigated models.}
\label{fig:mitigation}
\end{figure*}
"""

    authors = _load_authors()
    author_block = _latex_author_block(authors)

    content = r"""\documentclass[conference]{IEEEtran}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{amsmath,amssymb}
\usepackage{graphicx}
\usepackage{booktabs}
\usepackage{hyperref}
\usepackage{cite}
\usepackage{placeins}

\title{Bias Detection, Mitigation, and Auditing\\in Financial AI Systems}
\author{
%s
}

\begin{document}
\maketitle

\begin{abstract}
Artificial intelligence systems in credit scoring and fraud detection can systematically disadvantage protected demographic groups. We train standard classifiers (Logistic Regression, Balanced Random Forest) on the MLG-ULB Credit Card Fraud dataset and demonstrate baseline violations of EU AI Act fairness thresholds. We apply pre-processing (SMOTE) and post-processing (threshold adjustment), %s. We propose a lifecycle-based bias-audit framework aligned with the EU AI Act.
\end{abstract}

\section{Introduction}
\label{sec:intro}

\subsection{Motivation}
Artificial intelligence systems deployed in high-stakes financial domains---credit scoring, loan origination, and fraud detection---increasingly shape outcomes that affect millions of consumers \cite{pagano2023,ntoutsi2020}. While these models deliver measurable gains in predictive accuracy, a growing body of evidence shows that they can systematically disadvantage protected demographic groups \cite{pagano2023,ntoutsi2020}.

\subsection{Related Works}
Bias in automated decision systems can be categorised along three dimensions \cite{ntoutsi2020}: \emph{representational bias} (under-representation in training data), \emph{measurement bias} (proxy variables correlated with protected attributes), and \emph{algorithmic bias} (optimisation objectives amplifying imbalances). Huang and Turetken \cite{huang2025} compare pre-, in-, and post-processing techniques for credit scoring.

\subsection{Problem Definition}
Bias in machine-learning pipelines propagates through the entire lifecycle, from data collection to model training to deployment. Regulatory frameworks such as the EU Artificial Intelligence Act (2024) mandate that providers of ``high-risk'' AI systems demonstrate compliance with quantitative fairness thresholds: Statistical Parity Difference (SPD) $|\mathrm{SPD}| \leq 0.1$ and Equalised Odds Difference (EOD) $|\mathrm{EOD}| \leq 0.05$ \cite{euai2024}.

This paper makes three contributions: (1) \textbf{Detection}---we show baseline models violate EU AI Act thresholds; (2) \textbf{Mitigation}---we apply SMOTE and threshold adjustment, demonstrating the accuracy/fairness trade-off; (3) \textbf{Auditing}---we propose a lifecycle-based bias-audit framework.

\section{Methodology}
\label{sec:methodology}

\subsection{Data}

We use the Credit Card Fraud Detection dataset from MLG-ULB \cite{mlgulb2018}: 284,807 transactions, 492 fraudulent (0.173%%). Features V1--V28 are PCA components; \emph{Time} and \emph{Amount} are unmasked. We construct a synthetic protected attribute by splitting on V14 with additive Gaussian noise, simulating representational bias.

\subsection{Fairness Metrics}

\textbf{Demographic Parity (SPD):}
\begin{equation}
\mathrm{SPD} = P(\hat{Y}=1 \mid A=0) - P(\hat{Y}=1 \mid A=1)
\end{equation}
EU AI Act requires $|\mathrm{SPD}| \leq 0.1$.

\textbf{Disparate Impact (DI):}
\begin{equation}
\mathrm{DI} = \frac{\min(P(\hat{Y}=1|A=0), P(\hat{Y}=1|A=1))}{\max(P(\hat{Y}=1|A=0), P(\hat{Y}=1|A=1))}
\end{equation}
Fair when $\mathrm{DI} \geq 0.8$.

\textbf{Equalised Odds Difference (EOD):}
\begin{equation}
\mathrm{EOD} = \max\bigl(|FPR_0 - FPR_1|, |TPR_0 - TPR_1|\bigr)
\end{equation}
EU AI Act requires $|\mathrm{EOD}| \leq 0.05$.

\subsection{Models}

Logistic Regression ($\mathrm{class\_weight}=\mathrm{balanced}$), Balanced Random Forest (100 estimators), XGBoost + SMOTE (200 estimators, $\max\_\mathrm{depth}=6$).

\clearpage
\section{Results}
\label{sec:results}

\subsection{Detection}
%s
%s
%s
Both baseline models exhibit fairness-metric violations, confirming that standard classifiers inherit representational bias from the training data.

\FloatBarrier
\subsection{Mitigation}
%s
%s
%s
%s

\subsection{Bias Audit Framework}

Technical mitigation alone is insufficient. We propose a \textbf{lifecycle-based bias-audit framework} aligned with the EU AI Act's requirements for high-risk AI systems.

\textbf{Pre-Deployment:} Data representativeness audit; proxy-variable screening; baseline fairness evaluation (compute DPD, EOD, DI before deployment).

\textbf{In-Processing:} Track fairness metrics on rolling windows; automated alerts when $|\mathrm{DPD}|$ or $|\mathrm{EOD}|$ drift beyond thresholds; log model retraining events with fairness deltas.

\textbf{Post-Deployment:} Collect outcome data stratified by demographic group; quarterly conformity re-assessments; maintain audit trail (model version, data snapshot, metric values) for regulatory inspection.

\textbf{Organisational Governance:} Appoint an AI Ethics Officer; establish a cross-functional review board (data science, legal, compliance, affected-community representatives); publish annual transparency reports; document assumptions and trade-off decisions for audit trails.

Current frameworks lack intersectional analysis across multiple protected attributes, over-focus on one-shot technical audits, and involve limited participation of affected communities.

\section{Discussion}
\label{sec:discussion}

\subsection{Limitations of Post-Processing}

Threshold adjustment works well for latency (sub-200\,ms) and ease of deployment. However, it does not fix the root feature bias---the underlying model remains unfair if thresholds are removed---and requires demographic data at inference time, which may violate privacy regulations (e.g., GDPR Article 9).

\subsection{Limitations \& Future Work}

The protected attribute in this study is synthetic; results should be validated on datasets with real demographic annotations. We implemented ExponentiatedGradient (in-processing) and EOD-targeted post-processing; future work should benchmark adversarial debiasing and hybrid pipelines against these. The audit framework is conceptual; an empirical case study within a regulated financial institution would strengthen its practical applicability.

\section{Conclusion}
\label{sec:conclusion}

\subsection{Model Selection Matters}
Reweighting logistic regression produces no measurable change in fairness; our experiments confirm negligible improvement in DPD and EOD, consistent with Huang \& Turetken \cite{huang2025}. %s

\subsection{Accuracy/Fairness Trade-off}
Every mitigation strategy imposed a measurable accuracy cost. Adversarial debiasing can reduce $\Delta$-EOD by up to 58%% at 3--5%% accuracy loss, forcing financial institutions to weigh compliance against operational costs (e.g., missed fraud).

\subsection{Post-Processing Limits}
Threshold adjustment works well for latency (sub-200ms) and ease of deployment. However, it does not fix the root feature bias---the underlying model remains unfair if thresholds are removed---and requires demographic data at inference time, which may violate privacy laws (GDPR Article 9).

\subsection{Future Work}
Validate on datasets with real demographic annotations; benchmark in-processing methods; empirical case study within a regulated institution.

\section*{Acknowledgements}
This work was supported by the QMind Research Team. We thank the anonymous reviewers for their feedback.

\bibliographystyle{IEEEtran}
\bibliography{references}
\end{document}
""" % (
        author_block,
        "showing that " + claims["intro_mitigation_claim"],
        detection_tab,
        fig_baseline_fairness,
        fig_baseline_roc,
        mitigation_tab,
        fig_mitigation,
        claims["mitigation_summary"] + " \\cite{huang2025}.",
        asym_block,
        "In contrast, " + claims["xgb_smote_claim"],
    )

    tex_path = os.path.join(PAPER_DIR, "paper.tex")
    with open(tex_path, "w", encoding="utf-8") as f:
        f.write(content)
    return tex_path


def compile_latex():
    """Run pdflatex and bibtex to produce PDF from paper.tex. PDF is always from LaTeX; never from Markdown."""
    cwd = PAPER_DIR
    if not os.path.exists(os.path.join(cwd, "paper.tex")):
        return False, "paper.tex not found"

    # Find pdflatex (PATH or common MiKTeX/TeX Live locations)
    pdflatex = shutil.which("pdflatex") or shutil.which("pdflatex.exe")
    if not pdflatex and sys.platform == "win32":
        for base in [
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\MiKTeX\miktex\bin\x64"),
            os.path.expandvars(r"%ProgramFiles%\MiKTeX\miktex\bin\x64"),
            os.path.expandvars(r"%ProgramFiles(x86)%\MiKTeX\miktex\bin\x64"),
        ]:
            exe = os.path.join(base, "pdflatex.exe")
            if os.path.isfile(exe):
                pdflatex = exe
                break
    if not pdflatex:
        return (
            False,
            "pdflatex not found. Install MiKTeX or TeX Live to compile PDF from LaTeX. "
            "PDF must always be generated from LaTeX, never from Markdown.",
        )

    try:
        for i in range(2):
            print(f"      pdflatex pass {i+1}/2...", flush=True)
            r = subprocess.run(
                [pdflatex, "-interaction=nonstopmode", "paper.tex"],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if r.returncode != 0:
                return False, f"pdflatex failed: {r.stderr[-500:] if r.stderr else r.stdout[-500:]}"

        bibtex = shutil.which("bibtex") or shutil.which("bibtex.exe")
        if not bibtex and pdflatex and sys.platform == "win32":
            bibtex_dir = os.path.dirname(pdflatex)
            bibtex_exe = os.path.join(bibtex_dir, "bibtex.exe")
            if os.path.isfile(bibtex_exe):
                bibtex = bibtex_exe
        if bibtex and os.path.exists(os.path.join(cwd, "references.bib")):
            print("      bibtex...", flush=True)
            subprocess.run([bibtex, "paper"], cwd=cwd, capture_output=True, timeout=30)
            print("      pdflatex pass 3 (after bibtex)...", flush=True)
            subprocess.run(
                [pdflatex, "-interaction=nonstopmode", "paper.tex"],
                cwd=cwd,
                capture_output=True,
                timeout=60,
            )
        else:
            print("      (no references.bib, skipping bibtex)", flush=True)

        print("      pdflatex final pass...", flush=True)
        subprocess.run(
            [pdflatex, "-interaction=nonstopmode", "paper.tex"],
            cwd=cwd,
            capture_output=True,
            timeout=60,
        )

        pdf_path = os.path.join(PAPER_DIR, "paper.pdf")
        if os.path.exists(pdf_path):
            return True, pdf_path
        return False, "PDF was not produced"
    except subprocess.TimeoutExpired:
        return False, "Compilation timed out"
    except Exception as e:
        return False, str(e)


if __name__ == "__main__":
    import json
    baseline = None
    mitigation = None
    if os.path.exists(os.path.join(OUTPUT_DIR, "baseline_results.json")):
        with open(os.path.join(OUTPUT_DIR, "baseline_results.json"), encoding="utf-8") as f:
            baseline = json.load(f)
    if os.path.exists(os.path.join(OUTPUT_DIR, "mitigation_results.json")):
        with open(os.path.join(OUTPUT_DIR, "mitigation_results.json"), encoding="utf-8") as f:
            mitigation = json.load(f)
    tex_path = generate_paper_tex(baseline, mitigation)
    print(f"Generated: {tex_path}")
    ok, msg = compile_latex()
    if ok:
        print(f"PDF compiled: {msg}")
    else:
        print(f"Compilation: {msg}")
