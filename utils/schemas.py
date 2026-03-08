"""
Formal I/O schemas for the Bias Audit Pipeline.

Dataclasses defining every data contract between agents. Replaces implicit
dict contracts with typed, validatable structures. All serialization is
backward-compatible with existing JSON files in outputs/.

No external dependencies — stdlib only (dataclasses, json).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Any


# ====================================================================
# Core metric schemas
# ====================================================================


@dataclass
class ModelMetrics:
    model: str
    accuracy: float
    f1_score: float
    auc: float
    false_positive_rate: float
    demographic_parity_diff: float
    equalized_odds_diff: float
    disparate_impact_ratio: float
    positive_rate_group_0: float
    positive_rate_group_1: float
    eu_ai_act_spd_violation: bool
    eu_ai_act_eod_violation: bool

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> ModelMetrics:
        return cls(
            model=d["model"],
            accuracy=d["accuracy"],
            f1_score=d["f1_score"],
            auc=d.get("auc", 0.0),
            false_positive_rate=d.get("false_positive_rate", 0.0),
            demographic_parity_diff=d["demographic_parity_diff"],
            equalized_odds_diff=d["equalized_odds_diff"],
            disparate_impact_ratio=d["disparate_impact_ratio"],
            positive_rate_group_0=d.get("positive_rate_group_0", 0.0),
            positive_rate_group_1=d.get("positive_rate_group_1", 0.0),
            eu_ai_act_spd_violation=d.get("eu_ai_act_spd_violation", False),
            eu_ai_act_eod_violation=d.get("eu_ai_act_eod_violation", False),
        )

    @classmethod
    def validate(cls, d: dict) -> list[str]:
        """Return list of validation errors (empty = valid)."""
        required = [
            "model", "accuracy", "f1_score", "auc",
            "demographic_parity_diff", "equalized_odds_diff",
            "disparate_impact_ratio", "eu_ai_act_spd_violation",
            "eu_ai_act_eod_violation",
        ]
        return [f"Missing key: {k}" for k in required if k not in d]


# ====================================================================
# Agent output schemas
# ====================================================================


@dataclass
class BaselineResults:
    baseline_metrics: list[ModelMetrics]

    def to_dict(self) -> dict:
        return {"baseline_metrics": [m.to_dict() for m in self.baseline_metrics]}

    def to_json(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def from_dict(cls, d: dict) -> BaselineResults:
        return cls(
            baseline_metrics=[ModelMetrics.from_dict(m) for m in d.get("baseline_metrics", [])]
        )

    @classmethod
    def from_json(cls, path: str) -> BaselineResults:
        with open(path, encoding="utf-8") as f:
            return cls.from_dict(json.load(f))

    @classmethod
    def validate(cls, d: dict) -> list[str]:
        errors = []
        metrics = d.get("baseline_metrics")
        if not metrics or not isinstance(metrics, list):
            errors.append("baseline_metrics missing or not a list")
            return errors
        if len(metrics) < 2:
            errors.append(f"Expected at least 2 baseline models, got {len(metrics)}")
        for i, m in enumerate(metrics):
            for e in ModelMetrics.validate(m):
                errors.append(f"baseline_metrics[{i}] ({m.get('model', '?')}): {e}")
        return errors


@dataclass
class AsymmetricCostAnalysis:
    best_baseline_model: str
    best_mitigated_model: str
    accuracy_delta: float
    fpr_delta: float
    auc_delta: float | None
    dpd_improvement: float
    eod_improvement: float
    trade_off_summary: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> AsymmetricCostAnalysis:
        return cls(
            best_baseline_model=d.get("best_baseline_model", "N/A"),
            best_mitigated_model=d.get("best_mitigated_model", "N/A"),
            accuracy_delta=d.get("accuracy_delta", 0.0),
            fpr_delta=d.get("fpr_delta", 0.0),
            auc_delta=d.get("auc_delta"),
            dpd_improvement=d.get("dpd_improvement", 0.0),
            eod_improvement=d.get("eod_improvement", 0.0),
            trade_off_summary=d.get("trade_off_summary", ""),
        )


@dataclass
class MitigationResults:
    baseline_metrics: list[ModelMetrics]
    mitigation_metrics: list[ModelMetrics]
    asymmetric_cost_analysis: AsymmetricCostAnalysis | None = None

    def to_dict(self) -> dict:
        d: dict[str, Any] = {
            "baseline_metrics": [m.to_dict() for m in self.baseline_metrics],
            "mitigation_metrics": [m.to_dict() for m in self.mitigation_metrics],
        }
        if self.asymmetric_cost_analysis:
            d["asymmetric_cost_analysis"] = self.asymmetric_cost_analysis.to_dict()
        return d

    def to_json(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def from_dict(cls, d: dict) -> MitigationResults:
        asym = d.get("asymmetric_cost_analysis")
        return cls(
            baseline_metrics=[ModelMetrics.from_dict(m) for m in d.get("baseline_metrics", [])],
            mitigation_metrics=[ModelMetrics.from_dict(m) for m in d.get("mitigation_metrics", [])],
            asymmetric_cost_analysis=AsymmetricCostAnalysis.from_dict(asym) if asym else None,
        )

    @classmethod
    def from_json(cls, path: str) -> MitigationResults:
        with open(path, encoding="utf-8") as f:
            return cls.from_dict(json.load(f))

    @classmethod
    def validate(cls, d: dict) -> list[str]:
        errors = []
        bl = d.get("baseline_metrics")
        mit = d.get("mitigation_metrics")
        if not bl or not isinstance(bl, list):
            errors.append("baseline_metrics missing or not a list")
        elif len(bl) < 2:
            errors.append(f"Expected at least 2 baseline models, got {len(bl)}")
        if not mit or not isinstance(mit, list):
            errors.append("mitigation_metrics missing or not a list")
        elif len(mit) < 2:
            errors.append(f"Expected at least 2 mitigation strategies, got {len(mit)}")
        return errors


@dataclass
class JudgeResult:
    passed: bool
    feedback: list[str] = field(default_factory=list)
    retry_hint: str | None = None
    actionable_feedback: str | None = None

    def to_dict(self) -> dict:
        d: dict[str, Any] = {"passed": self.passed, "feedback": self.feedback}
        if self.retry_hint is not None:
            d["retry_hint"] = self.retry_hint
        if self.actionable_feedback is not None:
            d["actionable_feedback"] = self.actionable_feedback
        return d

    @classmethod
    def from_dict(cls, d: dict) -> JudgeResult:
        return cls(
            passed=d["passed"],
            feedback=d.get("feedback", []),
            retry_hint=d.get("retry_hint"),
            actionable_feedback=d.get("actionable_feedback"),
        )


# ====================================================================
# Memory / self-evolution schemas
# ====================================================================


@dataclass
class AgentRunRecord:
    agent: str
    seed: int
    attempt: int
    passed: bool
    duration_seconds: float
    error: str | None = None
    error_type: str | None = None
    metrics_snapshot: dict | None = None
    judge_feedback: list[str] = field(default_factory=list)
    retry_hint: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> AgentRunRecord:
        return cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d})


@dataclass
class VerificationRecord:
    claim: str
    verified: bool | None
    evidence: str = ""
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> VerificationRecord:
        return cls(
            claim=d.get("claim", ""),
            verified=d.get("verified"),
            evidence=d.get("evidence", ""),
            error=d.get("error"),
        )


@dataclass
class RunRecord:
    timestamp: str
    seed: int
    all_passed: bool
    total_duration_seconds: float
    agents: list[AgentRunRecord] = field(default_factory=list)
    best_eod: float | None = None
    best_dpd: float | None = None
    eod_compliant_models: list[str] = field(default_factory=list)
    paper_quality_issues: list[str] = field(default_factory=list)
    verifications: list[VerificationRecord] = field(default_factory=list)
    metrics: list[ModelMetrics] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "seed": self.seed,
            "all_passed": self.all_passed,
            "total_duration_seconds": self.total_duration_seconds,
            "agents": [a.to_dict() for a in self.agents],
            "best_eod": self.best_eod,
            "best_dpd": self.best_dpd,
            "eod_compliant_models": self.eod_compliant_models,
            "paper_quality_issues": self.paper_quality_issues,
            "verifications": [v.to_dict() for v in self.verifications],
            "metrics": [m.to_dict() for m in self.metrics],
        }

    @classmethod
    def from_dict(cls, d: dict) -> RunRecord:
        return cls(
            timestamp=d["timestamp"],
            seed=d.get("seed", 42),
            all_passed=d.get("all_passed", False),
            total_duration_seconds=d.get("total_duration_seconds", 0.0),
            agents=[AgentRunRecord.from_dict(a) for a in d.get("agents", [])],
            best_eod=d.get("best_eod"),
            best_dpd=d.get("best_dpd"),
            eod_compliant_models=d.get("eod_compliant_models", []),
            paper_quality_issues=d.get("paper_quality_issues", []),
            verifications=[VerificationRecord.from_dict(v) for v in d.get("verifications", [])],
            metrics=[ModelMetrics.from_dict(m) for m in d.get("metrics", [])],
        )
