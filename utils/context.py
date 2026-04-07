"""
ResearchContext — Shared state object for research pipeline modes.

Holds all inter-agent data in typed form. Agents receive inputs from the
context and write outputs back.

Two modes:
  - GOAL: Iterative goal-oriented research (converge on quantifiable results)
  - REPORT: Deep-dive research producing a comprehensive report on a topic
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "outputs")


class ResearchMode(Enum):
    GOAL = "goal"
    REPORT = "report"


@dataclass
class ClaimState:
    """Tracks the state of a single research claim through iterations."""
    text: str
    domain: str = ""
    verified: bool | None = None
    verdict: str = ""  # support | contradict | neutral
    confidence: float = 0.0
    evidence: str = ""
    supporting_papers: list[str] = field(default_factory=list)
    iteration_verified: int | None = None


@dataclass
class IterationResult:
    """Result of a single research loop iteration."""
    iteration: int
    claims_verified: int = 0
    claims_contradicted: int = 0
    papers_retrieved: int = 0
    flaws_detected: int = 0
    critical_flaws: int = 0
    verified_ratio: float = 0.0
    converged: bool = False
    evolved: bool = False
    duration_seconds: float = 0.0
    error: str | None = None


@dataclass
class ResearchContext:
    """Shared state for the research pipeline."""
    mode: ResearchMode = ResearchMode.GOAL
    goal: str = ""
    claims: list[ClaimState] = field(default_factory=list)
    iteration_results: list[IterationResult] = field(default_factory=list)
    research_findings: dict[str, Any] = field(default_factory=dict)
    flaw_reports: list[dict] = field(default_factory=list)
    cross_validation_results: list[dict] = field(default_factory=list)
    report_sections: dict[str, str] = field(default_factory=dict)
    converged: bool = False
    current_iteration: int = 0
    user_profile: dict[str, Any] = field(default_factory=dict)

    def add_claim(self, text: str, domain: str = "") -> ClaimState:
        """Add a new claim to track."""
        claim = ClaimState(text=text, domain=domain)
        self.claims.append(claim)
        return claim

    def verified_ratio(self) -> float:
        """Fraction of claims that have been verified."""
        if not self.claims:
            return 0.0
        verified = sum(1 for c in self.claims if c.verified is True)
        return verified / len(self.claims)

    def unverified_claims(self) -> list[ClaimState]:
        """Return claims not yet verified."""
        return [c for c in self.claims if c.verified is not True]

    def save(self, path: str | None = None) -> None:
        """Persist context to JSON."""
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        out_path = path or os.path.join(OUTPUT_DIR, "research_context.json")
        data = {
            "mode": self.mode.value,
            "goal": self.goal,
            "claims": [
                {
                    "text": c.text, "domain": c.domain, "verified": c.verified,
                    "verdict": c.verdict, "confidence": c.confidence,
                    "evidence": c.evidence, "supporting_papers": c.supporting_papers,
                }
                for c in self.claims
            ],
            "converged": self.converged,
            "current_iteration": self.current_iteration,
            "iteration_count": len(self.iteration_results),
        }
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load(cls, path: str | None = None) -> ResearchContext:
        """Load context from JSON."""
        in_path = path or os.path.join(OUTPUT_DIR, "research_context.json")
        if not os.path.exists(in_path):
            return cls()
        try:
            with open(in_path, encoding="utf-8") as f:
                data = json.load(f)
            ctx = cls(
                mode=ResearchMode(data.get("mode", "goal")),
                goal=data.get("goal", ""),
                converged=data.get("converged", False),
                current_iteration=data.get("current_iteration", 0),
            )
            for c in data.get("claims", []):
                claim = ClaimState(
                    text=c.get("text", ""),
                    domain=c.get("domain", ""),
                    verified=c.get("verified"),
                    verdict=c.get("verdict", ""),
                    confidence=c.get("confidence", 0.0),
                    evidence=c.get("evidence", ""),
                    supporting_papers=c.get("supporting_papers", []),
                )
                ctx.claims.append(claim)
            return ctx
        except (json.JSONDecodeError, KeyError, OSError):
            return cls()


# Backward-compat alias for legacy code
PipelineContext = ResearchContext

