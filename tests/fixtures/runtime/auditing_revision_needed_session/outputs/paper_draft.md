# Bias Detection and Mitigation in Credit Card Fraud Detection Models

## Introduction
Machine learning models used in financial decision-making can exhibit demographic bias, leading to discriminatory outcomes. This paper presents a systematic audit of bias in credit card fraud detection models.

## Background
Algorithmic fairness has become a critical concern in regulated domains. The EU AI Act establishes thresholds for acceptable bias levels in high-risk AI systems. Key fairness metrics include Demographic Parity Difference (DPD), Equalized Odds Difference (EOD), and Disparate Impact Ratio (DI).

## Use Case
Credit card fraud detection using the MLG-ULB dataset serves as our primary use case. We evaluate two baseline models — Logistic Regression and Balanced Random Forest — and assess their compliance with EU AI Act fairness thresholds.

## Detection Results
Baseline evaluation reveals that the Logistic Regression model violates both SPD (|DPD| > 0.1) and EOD (|EOD| > 0.05) thresholds. The Balanced Random Forest shows lower bias but still exhibits measurable disparities.

| Model | Accuracy | F1 | DPD | EOD | DI |
|-------|----------|-----|------|------|------|
| Logistic Regression | 0.961 | 0.823 | 0.125 | 0.062 | 0.765 |
| Balanced Random Forest | 0.959 | 0.816 | 0.089 | 0.043 | 0.812 |

## Audit Framework
Our audit framework evaluates models across three dimensions: predictive performance, fairness compliance, and the accuracy-fairness trade-off. We apply SMOTE pre-processing and threshold adjustment as mitigation strategies.

## Mitigation Experiments
XGBoost with SMOTE achieves DPD=0.046 and EOD=0.023, meeting EU AI Act thresholds. Threshold adjustment on Random Forest further reduces EOD to 0.015 with DI=0.910.

## Discussion
Mitigation introduces a modest accuracy trade-off (0.86% loss) while substantially improving fairness. However, XGBoost+SMOTE alone may not achieve full EOD compliance — threshold adjustment provides the additional calibration needed.

## References
1. Fairlearn documentation, Microsoft, 2024.
2. EU AI Act, European Commission, 2024.
3. MLG-ULB Credit Card Fraud Dataset, Kaggle.
