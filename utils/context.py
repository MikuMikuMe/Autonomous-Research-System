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
import uuid
from dataclasses import dataclass, field
from datetime import datetime
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
    category: str = "hypothesis"
    priority: str = "medium"
    verified: bool | None = None
    verdict: str = ""  # support | contradict | neutral | pending
    confidence: float = 0.0
    evidence: str = ""
    supporting_papers: list[str] = field(default_factory=list)
    iteration_verified: int | None = None


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
    """Shared state for the research pipeline.

    All agent nodes read from and write to this context.
    Replaces filesystem coupling with typed, in-memory data flow.
    """
    # Identity
    session_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    mode: ResearchMode = ResearchMode.GOAL
    goal: str = ""
    domain: str = "general"

    # Iteration control
    current_iteration: int = 0
    converged: bool = False

    # Claims & findings
    claims: list[ClaimState] = field(default_factory=list)
    iteration_results: list[IterationResult] = field(default_factory=list)
    research_findings: dict[str, Any] = field(default_factory=dict)
    flaw_reports: list[dict] = field(default_factory=list)
    cross_validation_results: list[dict] = field(default_factory=list)
    report_sections: dict[str, str] = field(default_factory=dict)

    # Enhanced state from v2.0
    discovered_techniques: list[Technique] = field(default_factory=list)
    flaws: list[Flaw] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)
    research_sources: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    user_profile: dict[str, Any] = field(default_factory=dict)

    # Timestamps
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    finished_at: str | None = None

    def add_claim(self, text: str, domain: str = "", category: str = "hypothesis",
                  priority: str = "medium") -> ClaimState:
        """Add a new claim to track."""
        claim = ClaimState(text=text, domain=domain, category=category, priority=priority)
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

    def verified_ratio(self) -> float:
        """Fraction of claims that have been verified."""
        if not self.claims:
            return 0.0
        verified = sum(1 for c in self.claims if c.verified is True)
        return verified / len(self.claims)

    def unverified_claims(self) -> list[ClaimState]:
        """Return claims not yet verified."""
        return [c for c in self.claims if c.verified is not True]

    def compute_metrics(self) -> None:
        """Recompute verified_ratio and flaw counts from current state."""
        ratio = self.verified_ratio()
        critical = sum(1 for f in self.flaws if f.severity == "critical")
        total_flaws = len(self.flaws)

        # Update iteration result if we have one
        if self.iteration_results:
            last = self.iteration_results[-1]
            last.verified_ratio = ratio
            last.critical_flaws = critical
            last.flaws_detected = total_flaws

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for JSON output or report generation."""
        return {
            "session_id": self.session_id,
            "mode": self.mode.value,
            "goal": self.goal,
            "domain": self.domain,
            "current_iteration": self.current_iteration,
            "converged": self.converged,
            "verified_ratio": self.verified_ratio(),
            "claims": [
                {
                    "text": c.text, "domain": c.domain, "category": c.category,
                    "verified": c.verified, "verdict": c.verdict,
                    "confidence": c.confidence, "evidence": c.evidence,
                    "supporting_papers": c.supporting_papers,
                }
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
        """Persist context to JSON."""
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        out_path = path or os.path.join(OUTPUT_DIR, "research_context.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, default=str)
        return out_path

    @classmethod
    def load(cls, path: str | None = None) -> ResearchContext:
        """Load context from JSON."""
        in_path = path or os.path.join(OUTPUT_DIR, "research_context.json")
        if not os.path.exists(in_path):
            return cls()
        try:
            with open(in_path, encoding="utf-8") as f:
                data = json.load(f)
            return cls.from_dict(data)
        except (json.JSONDecodeError, KeyError, OSError):
            return cls()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ResearchContext:
        """Reconstruct from a dict."""
        ctx = cls(
            session_id=data.get("session_id", str(uuid.uuid4())[:8]),
            mode=ResearchMode(data.get("mode", "goal")),
            goal=data.get("goal", ""),
            domain=data.get("domain", "general"),
            current_iteration=data.get("current_iteration", 0),
            converged=data.get("converged", False),
            errors=data.get("errors", []),
        )
        for c in data.get("claims", []):
            claim = ClaimState(
                text=c.get("text", ""),
                domain=c.get("domain", ""),
                category=c.get("category", "hypothesis"),
                verified=c.get("verified"),
                verdict=c.get("verdict", ""),
                confidence=c.get("confidence", 0.0),
                evidence=c.get("evidence", ""),
                supporting_papers=c.get("supporting_papers", []),
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
        for f_data in data.get("flaws", []):
            flaw = Flaw(
                description=f_data.get("description", ""),
                flaw_type=f_data.get("type", ""),
                severity=f_data.get("severity", "medium"),
                suggested_fix=f_data.get("suggested_fix", ""),
            )
            ctx.flaws.append(flaw)
        return ctx


# Backward-compat alias for legacy code
PipelineContext = ResearchContext