"""
PipelineContext — Shared state object passed through the orchestrator.

Holds all inter-agent data in typed form. Agents receive inputs from the
context and write outputs back. Backward-compatible: save() writes the
same JSON files agents produce today; load() reconstructs from them.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from utils.schemas import (
    BaselineResults,
    MitigationResults,
    JudgeResult,
    AgentRunRecord,
    VerificationRecord,
)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "outputs")


@dataclass
class PipelineContext:
    seed: int = 42
    baseline: BaselineResults | None = None
    mitigation: MitigationResults | None = None
    paper_tex_path: str | None = None
    paper_pdf_path: str | None = None
    judge_results: dict[str, JudgeResult] = field(default_factory=dict)
    agent_runs: list[AgentRunRecord] = field(default_factory=list)
    verifications: list[VerificationRecord] = field(default_factory=list)
    paper_quality_issues: list[str] = field(default_factory=list)

    def save(self) -> None:
        """Persist to outputs/ as the same JSON files agents produce today."""
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        if self.baseline:
            self.baseline.to_json(os.path.join(OUTPUT_DIR, "baseline_results.json"))
        if self.mitigation:
            self.mitigation.to_json(os.path.join(OUTPUT_DIR, "mitigation_results.json"))

    @classmethod
    def load(cls, seed: int = 42) -> PipelineContext:
        """Reconstruct from existing outputs/ files (for standalone agent runs)."""
        ctx = cls(seed=seed)
        bl_path = os.path.join(OUTPUT_DIR, "baseline_results.json")
        if os.path.exists(bl_path):
            try:
                ctx.baseline = BaselineResults.from_json(bl_path)
            except (json.JSONDecodeError, KeyError, OSError):
                pass
        mit_path = os.path.join(OUTPUT_DIR, "mitigation_results.json")
        if os.path.exists(mit_path):
            try:
                ctx.mitigation = MitigationResults.from_json(mit_path)
            except (json.JSONDecodeError, KeyError, OSError):
                pass
        tex_path = os.path.join(OUTPUT_DIR, "paper", "paper.tex")
        if os.path.exists(tex_path):
            ctx.paper_tex_path = tex_path
        pdf_path = os.path.join(OUTPUT_DIR, "paper", "paper.pdf")
        if os.path.exists(pdf_path):
            ctx.paper_pdf_path = pdf_path
        return ctx

    def get_best_eod(self) -> float | None:
        """Extract the best (lowest) |EOD| from mitigation results."""
        if not self.mitigation:
            return None
        all_metrics = self.mitigation.baseline_metrics + self.mitigation.mitigation_metrics
        if not all_metrics:
            return None
        return min(abs(m.equalized_odds_diff) for m in all_metrics)

    def get_best_dpd(self) -> float | None:
        """Extract the best (lowest) |DPD| from mitigation results."""
        if not self.mitigation:
            return None
        all_metrics = self.mitigation.baseline_metrics + self.mitigation.mitigation_metrics
        if not all_metrics:
            return None
        return min(abs(m.demographic_parity_diff) for m in all_metrics)

    def get_eod_compliant_models(self) -> list[str]:
        """Return model names that achieve |EOD| <= 0.05."""
        if not self.mitigation:
            return []
        all_metrics = self.mitigation.baseline_metrics + self.mitigation.mitigation_metrics
        return [m.model for m in all_metrics if not m.eu_ai_act_eod_violation]
