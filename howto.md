


Writing and technically proving a research paper in a sprint requires parallelization. With a team (Mihailo, Kai Kim, Alec, Viona, Gopika, and Maya) and well-structured preliminary notes, you can parallelize the work. 

To prove your findings technically, avoid building algorithms from scratch. Instead, use standard datasets and existing fairness libraries (like IBM's `AIF360` or Microsoft's `fairlearn`). 

Here is the **research workflow** to write the paper and generate the technical proofs, based on the provided literature and team structure:

### Hour 1: Scope Definition, Setup & Delegation
**Goal:** Lock in the narrative and set up the technical environment.
*   **The Narrative:** Focus specifically on **Credit Card Fraud Detection or Credit Scoring**. Argue that traditional models (like Logistic Regression and Random Forest) inherit representational bias, and that complying with frameworks like the EU AI Act requires specific mitigation strategies. 
*   **Dataset:** Find a readily available financial dataset right now (e.g., the public *Kaggle's *Credit Card Fraud Detection* dataset). 
*   **Delegation:**
    *   **Detection Team (Mihailo & Kai Kim):** Write the Python script to load the dataset, inject/identify a protected attribute (e.g., age or gender), train a baseline Logistic Regression model, and output the bias metrics.
    *   **Mitigation Team (Alec & Viona):** Set up the code to apply SMOTE (oversampling) and threshold adjustments on the baseline models.
    *   **Auditing/Writing Team (Gopika & Maya):** Begin writing the "Introduction" and "Background" sections using the literature notes (e.g., defining Disparate Impact, Equalized Odds, and the EU AI Act).

    Use Machine Learning Group - ULB's dataset
    ```
    import kagglehub

    # Download latest version
    path = kagglehub.dataset_download("mlg-ulb/creditcardfraud")

    print("Path to dataset files:", path)
    ```

### Hour 2: Baseline Technical Proof (Detection)
**Goal:** Prove that bias *exists* in standard financial AI systems.
*   **Technical Action:** Mihailo and Kai Kim must train a standard Logistic Regression model and a Balanced Random Forest model. 
*   **Metrics to Calculate:** Use your notes to calculate:
    1.  **Disparate Impact (DI):** Prove that the proportion of positive outcomes between demographics is skewed.
    2.  **Equalized Odds (EO):** Prove that false positive/false negative rates disproportionately affect one demographic.
*   **Deliverable:** A baseline table showing high accuracy but severe violations of fairness thresholds (e.g., DELTA-SPD > 0.1 or DELTA-EOD > 0.05, referencing the EU AI Act limits).

### Hour 3: Implementing Mitigation (The "Fix")
**Goal:** Prove that bias can be technically mitigated and document the accuracy trade-offs.
*   **Technical Action:** Alec and Viona step in to apply the mitigation strategies referenced in your notes:
    1.  **Pre-processing (SMOTE):** Balance the dataset to fix representation bias. Test it using an XGBoost model (as your notes highlight that XGBoost responds better to SMOTE than Random Forests).
    2.  **Post-processing (Adjusting Thresholds):** Write a quick script to dynamically adjust the decision boundary for the disadvantaged group.
*   **Deliverable:** A comparative matrix (Accuracy vs. Fairness). You must technically prove the "Asymmetric Cost" mentioned in your notes—show that mitigating bias might slightly lower overall accuracy or increase false positives (which costs money in fraud detection), establishing the "trade-off."

### Hour 4: Drafting the Core Sections
**Goal:** Merge the technical findings into the paper structure.
*   **Gopika & Maya:** Write the **Bias Auditing** section. Use the framework from your notes to explain that technical mitigation isn't enough; organizations need a "lifecycle-based oversight process" (pre-deployment data checks, in-processing monitoring, post-deployment feedback loops). 
*   **Mihailo, Kai, Alec, Viona:** Export your Python graphs (ROC curves, Fairness Metric bar charts before/after mitigation). Write the **Methodology** and **Results** sections detailing exactly how you calculated Demographic Parity and Equalized Odds. 

### Hour 5: Synthesis and Discussion
**Goal:** Connect the technical proofs to the theoretical research.
*   **All Hands:** Write the **Discussion** section. 
*   **Key Talking Points from your notes:**
    *   *Model Selection matters:* Mention that reweighting logistic regression often produces no measurable change in fairness, whereas XGBoost with SMOTE satisfies EU AI Act thresholds (citing *Huang & Turetken, 2025*).
    *   *The Accuracy/Fairness Trade-off:* Discuss how adversarial debiasing can reduce DELTA-EOD by 58% but incurs an accuracy loss, forcing financial institutions to weigh compliance against operational costs (e.g., missed fraud).
    *   *Post-processing limits:* Mention that adjusting thresholds works well for latency (sub-200ms) but doesn't fix the root feature bias, and requires access to demographic data which may violate privacy laws.

### Hour 6: Review, Format, and Citations
**Goal:** Polish the paper for submission.
*   Format the paper according to the structure in your 3rd document: 
    1. Background & Taxonomy
    2. Use Case & Data 
    3. Detection Methods
    4. Mitigation Experiments
    5. Audit Framework
    6. Discussion
*   Insert your formulas (Demographic Parity, Disparate Impact, Equalized Odds, Accuracy, F1 Score) directly from your notes into the methodology section to add academic rigor.
*   Compile the bibliography using the references provided in your notes (e.g., *Pagano et al., 2023; Ntoutsi et al., 2020; Huang & Turetken, 2025*).

### Technical Cheat Sheet:
To save time on the code, tell your detection and mitigation teams to use the following Python snippet structure using `fairlearn`:

```python
from fairlearn.metrics import demographic_parity_difference, equalized_odds_difference
from imblearn.over_sampling import SMOTE
from xgboost import XGBClassifier

# 1. Baseline Bias Detection
baseline_model = XGBClassifier().fit(X_train, y_train)
y_pred = baseline_model.predict(X_test)
dp_diff = demographic_parity_difference(y_test, y_pred, sensitive_features=A_test)
eo_diff = equalized_odds_difference(y_test, y_pred, sensitive_features=A_test)
print(f"Baseline DP: {dp_diff}, Baseline EO: {eo_diff}") 
# (Compare these against the EU AI Act 0.1 / 0.05 thresholds)

# 2. Mitigation via Pre-processing (SMOTE)
smote = SMOTE()
X_res, y_res = smote.fit_resample(X_train, y_train)
mitigated_model = XGBClassifier().fit(X_res, y_res)
# Re-run metrics to prove mitigation success
```

By strictly keeping the team in their lanes (Detection, Mitigation, Auditing/Writing) and relying heavily on the pre-written literature reviews and equations in your notes, you can successfully output a technically verified paper.