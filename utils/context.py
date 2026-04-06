"""
PipelineContext — Shared state object passed through the orchestrator.

Holds all inter-agent data in typed form. Agents receive inputs from the
context and write outputs back. Backward-compatible: save() writes the
same JSON files agents produce today; load() reconstructs from them.

ResearchContext — In-process state for the generalized research pipeline.
Replaces filesystem coupling with typed, in-memory data flow.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from utils.schemas import (
    BaselineResults,
    MitigationResults,
    JudgeResult,
    AgentRunRecord,
    VerificationRecord,
)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "outputs")


# ---------------------------------------------------------------------------
# Legacy bias-pipeline context (backward-compatible)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Generalized research context (in-process state, no filesystem coupling)
# ---------------------------------------------------------------------------

@dataclass
class Claim:
    """A single testable research claim."""
    text: str
    category: str = "hypothesis"
    priority: str = "medium"
    verified: bool | None = None
    evidence: str = ""
    verdict: str = "pending"
    confidence: float = 0.0


@dataclass
class Technique:
    """A discovered research technique/method."""
    name: str
    description: str = ""
    category: str = ""
    relevance: float = 0.5
    libraries: list[str] = field(default_factory=list)
    key_papers: list[str] = field(default_factory=list)


@dataclass
class Flaw:
    """A detected flaw in the research."""
    claim: str = ""
    flaw_type: str = ""
    severity: str = "medium"
    description: str = ""
    suggested_fix: str = ""


@dataclass
class ResearchContext:
    """In-process state object for the generalized research pipeline.

    Replaces filesystem coupling (JSON files) with typed, in-memory state.
    All agent nodes read from and write to this context.
    """
    # Identity
    session_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    research_idea: str = ""
    goal: str = ""
    domain: str = "general"

    # Iteration control
    iteration: int = 0
    max_iterations: int = 5
    converge_threshold: float = 0.85
    flaw_halt_severity: str = "critical"
    converged: bool = False

    # Typed state objects (in-process, no JSON files)
    claims: list[Claim] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)
    discovered_techniques: list[Technique] = field(default_factory=list)
    flaws: list[Flaw] = field(default_factory=list)

    # Results
    verified_ratio: float = 0.0
    critical_flaws: int = 0
    total_flaws: int = 0
    research_sources: list[dict[str, Any]] = field(default_factory=list)
    cross_validation_results: list[dict[str, Any]] = field(default_factory=list)
    report: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    # Timestamps
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    finished_at: str | None = None

    def add_claim(self, text: str, category: str = "hypothesis", priority: str = "medium") -> Claim:
        """Add a testable claim to the context."""
        claim = Claim(text=text, category=category, priority=priority)
        self.claims.append(claim)
        return claim

    def add_technique(self, name: str, **kwargs: Any) -> Technique:
        """Register a discovered technique."""
        tech = Technique(name=name, **kwargs)
        self.discovered_techniques.append(tech)
        return tech

    def add_flaw(self, description: str, **kwargs: Any) -> Flaw:
        """Record a detected flaw."""
        flaw = Flaw(description=description, **kwargs)
        self.flaws.append(flaw)
        return flaw

    def compute_metrics(self) -> None:
        """Recompute verified_ratio, critical_flaws, etc. from current state."""
        total = len(self.claims) or 1
        verified = sum(1 for c in self.claims if c.verified is True)
        self.verified_ratio = round(verified / total, 3)
        self.critical_flaws = sum(1 for f in self.flaws if f.severity == "critical")
        self.total_flaws = len(self.flaws)

        blocking = self.critical_flaws > 0 if self.flaw_halt_severity == "critical" else self.total_flaws > 0
        self.converged = self.verified_ratio >= self.converge_threshold and not blocking

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for JSON output or report generation."""
        return {
            "session_id": self.session_id,
            "research_idea": self.research_idea,
            "goal": self.goal,
            "domain": self.domain,
            "iteration": self.iteration,
            "converged": self.converged,
            "verified_ratio": self.verified_ratio,
            "total_flaws": self.total_flaws,
            "critical_flaws": self.critical_flaws,
            "claims": [
                {"text": c.text, "category": c.category, "verified": c.verified,
                 "verdict": c.verdict, "confidence": c.confidence}
                for c in self.claims
            ],
            "techniques": [
                {"name": t.name, "description": t.description, "category": t.category,
                 "relevance": t.relevance}
                for t in self.discovered_techniques
            ],
            "flaws": [
                {"description": f.description, "type": f.flaw_type, "severity": f.severity,
                 "suggested_fix": f.suggested_fix}
                for f in self.flaws
            ],
            "errors": self.errors,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }

    def save(self, path: str | None = None) -> str:
        """Persist context to JSON (optional, for debugging/checkpointing)."""
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        out_path = path or os.path.join(OUTPUT_DIR, "research_context.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, default=str)
        return out_path

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ResearchContext:
        """Reconstruct from a dict."""
        ctx = cls(
            session_id=data.get("session_id", str(uuid.uuid4())[:8]),
            research_idea=data.get("research_idea", ""),
            goal=data.get("goal", ""),
            domain=data.get("domain", "general"),
            iteration=data.get("iteration", 0),
            converged=data.get("converged", False),
            verified_ratio=data.get("verified_ratio", 0.0),
            total_flaws=data.get("total_flaws", 0),
            critical_flaws=data.get("critical_flaws", 0),
            errors=data.get("errors", []),
        )
        for c in data.get("claims", []):
            claim = Claim(
                text=c.get("text", ""),
                category=c.get("category", "hypothesis"),
                verified=c.get("verified"),
                verdict=c.get("verdict", "pending"),
                confidence=c.get("confidence", 0.0),
            )
            ctx.claims.append(claim)
        for t in data.get("techniques", []):
            tech = Technique(
                name=t.get("name", ""),
                description=t.get("description", ""),
                category=t.get("category", ""),
                relevance=t.get("relevance", 0.5),
            )
            ctx.discovered_techniques.append(tech)
        for f in data.get("flaws", []):
            flaw = Flaw(
                description=f.get("description", ""),
                flaw_type=f.get("type", ""),
                severity=f.get("severity", "medium"),
                suggested_fix=f.get("suggested_fix", ""),
            )
            ctx.flaws.append(flaw)
        return ctx
