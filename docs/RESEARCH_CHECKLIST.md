# Bias Audit Pipeline — Research Paper Coverage Checklist

This checklist ensures the paper addresses every point from the research outlines. Use it when generating or revising sections. When alphaXiv MCP is enabled, search for papers to support each claim.

## 1. Bias Detection (from how_biases_are_introduced.pdf, Bias Detection findings.pdf)

- [ ] **Bias types**: Data, algorithmic, user/interaction, measurement, selection, temporal, confounding (Chen, Pagano, Ntoutsi, González-Sendino, Mehrabi, Ferrara)
- [ ] **Fairness metrics**: Demographic parity, equal opportunity, equalized odds, predictive parity, disparate impact, calibration, subgroup metrics
- [ ] **Metric conflicts**: Note where metrics disagree; mapping trade-offs is a recognized gap
- [ ] **Detection pipeline**: Baseline models, group-wise performance, fairness over multiple sensitive attributes, intersectional analysis
- [ ] **Toolkits**: AI Fairness 360, Fairlearn, Aequitas for systematic comparison
- [ ] **EU AI Act thresholds**: |SPD| ≤ 0.1, |EOD| ≤ 0.05, DI ≥ 0.8

## 2. Bias Mitigation (from bias_mitigation.pdf)

### Pre-processing
- [ ] **Reweighting**: Assign weights to reflect real-world distribution; effectiveness depends on model (LR/KNN may show no change)
- [ ] **Data augmentation**: Expand training set; SMOTE, ADASYN, ROS
- [ ] **SMOTE**: Interpolation between minority instances; Huang & Turetken (2025) — SMOTE best balance for fraud detection
- [ ] **ADASYN vs ROS**: ADASYN adapts to harder instances; ROS can exacerbate temporal bias
- [ ] **Model selection matters**: XGBoost+SMOTE satisfies EU thresholds; Balanced RF violates (Huang & Turetken)
- [ ] **Asymmetric cost**: False positives in fraud = investigation costs; use FDE (Fraud Detection Efficiency)

### In-processing
- [ ] **Adversarial debiasing**: Secondary model predicts protected attr; reduces EOD up to 58% but 15% accuracy loss
- [ ] **Sequential approach**: SMOTE + adversarial debiasing reduces accuracy penalty
- [ ] **Fairness-constrained optimization**, loss regularization, causal methods

### Post-processing
- [ ] **Threshold adjustment**: Group-specific decision boundaries; sub-200ms latency (Huang & Turetken)
- [ ] **Human-in-the-loop**: EU AI Act Article 10; SHAP for high-risk decisions; escalation criteria
- [ ] **Limitations**: Requires demographic data at inference (GDPR); doesn't fix root bias

### Trade-offs
- [ ] **Accuracy–fairness trade-off**: Quantify (e.g., accuracy delta, FPR delta)
- [ ] **Mitigation matrix**: Methods × metrics on same dataset

## 3. Bias Auditing (from how_biases_are_introduced.pdf, Bias Auditing Framework.pdf)

- [ ] **Legal/compliance**: NYC Local Law 144, EU AI Act risk-based conformity
- [ ] **Audit components**: Data provenance, model documentation, stakeholder perspectives, cultural context
- [ ] **Pre-deployment**: Data bias assessment, value elicitation, model cards/datasheets
- [ ] **Deployment**: Continuous monitoring for drift, periodic re-audits
- [ ] **Socio-technical**: Stakeholder participation, documenting assumptions, diverse teams
- [ ] **Gaps**: Lack of intersectional analysis, one-shot technical audits, limited affected-community involvement

## 4. Paper Structure (required sections)

- [ ] Background & taxonomy (bias sources, fairness definitions, lifecycle)
- [ ] Use case & data (domain, protected groups, risks)
- [ ] Detection methods (metrics, tools, baseline disparities)
- [ ] Mitigation experiments (pre/in/post comparison, trade-offs)
- [ ] Audit framework (process, governance, documentation)
- [ ] Discussion (metric conflicts, ethics, open research gaps)

## 5. Key Citations to Include

- Pagano et al. (2023) — systematic review
- Ntoutsi et al. (2020) — bias in data-driven AI
- Huang & Turetken (2025) — fraud detection, SMOTE, threshold adjustment
- González-Sendino et al. (2023, 2024) — audit frameworks
- Mehrabi et al. (2019) — fairness metrics
- Murikah et al. (2024) — AI auditing
- EU AI Act (2024) — thresholds, Article 5, Article 10

## alphaXiv Search Queries (when MCP enabled)

Use these with `answer_research_query` or `find_papers_feed`:

- "How do baseline ML models in fraud detection violate EU AI Act fairness thresholds?"
- "SMOTE vs reweighting for fairness in credit scoring: recent comparative studies"
- "Accuracy-fairness trade-off in bias mitigation: post-processing threshold adjustment"
- "Adversarial debiasing effectiveness and accuracy penalty in financial AI"
