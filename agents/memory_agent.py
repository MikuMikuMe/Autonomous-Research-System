"""
Memory Agent — SQLite-backed self-evolution memory.

Persists full RunRecords (metric snapshots, error traces, timing, judge
feedback, verification results) to outputs/memory/memory.db.  Provides
SQL-powered query helpers for the optimizer: metric trends, failure
patterns, claim verification history, and per-model EOD history.

Legacy APIs (persist_event, persist_session, load_recent_sessions,
load_recent_events) are preserved for backward compatibility — they
wrap into MemoryStore calls.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime

from utils.schemas import (
    AgentRunRecord,
    ModelMetrics,
    RunRecord,
    VerificationRecord,
)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEMORY_DIR = os.path.join(PROJECT_ROOT, "outputs", "memory")
DB_PATH = os.path.join(MEMORY_DIR, "memory.db")

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT    NOT NULL,
    seed        INTEGER NOT NULL,
    all_passed  BOOLEAN NOT NULL,
    duration_s  REAL,
    best_eod    REAL,
    best_dpd    REAL,
    eod_compliant_models TEXT,
    paper_quality_issues TEXT
);

CREATE TABLE IF NOT EXISTS agent_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      INTEGER NOT NULL REFERENCES runs(id),
    agent       TEXT    NOT NULL,
    seed        INTEGER NOT NULL,
    attempt     INTEGER NOT NULL,
    passed      BOOLEAN NOT NULL,
    duration_s  REAL,
    error       TEXT,
    error_type  TEXT,
    judge_feedback TEXT,
    retry_hint  TEXT,
    metrics_snapshot TEXT
);

CREATE TABLE IF NOT EXISTS metrics (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      INTEGER NOT NULL REFERENCES runs(id),
    model       TEXT    NOT NULL,
    is_baseline BOOLEAN NOT NULL,
    accuracy    REAL,
    f1_score    REAL,
    auc         REAL,
    fpr         REAL,
    dpd         REAL,
    eod         REAL,
    di          REAL,
    spd_violation BOOLEAN,
    eod_violation BOOLEAN
);

CREATE TABLE IF NOT EXISTS verifications (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      INTEGER NOT NULL REFERENCES runs(id),
    claim       TEXT    NOT NULL,
    verified    BOOLEAN,
    evidence    TEXT,
    error       TEXT
);

CREATE TABLE IF NOT EXISTS idea_sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT    NOT NULL UNIQUE,
    timestamp       TEXT    NOT NULL,
    title           TEXT,
    domain          TEXT,
    keywords        TEXT,
    hypotheses      TEXT,
    proposed_methods TEXT,
    verdict         TEXT,
    novelty_score   REAL,
    flaws_count     INTEGER DEFAULT 0,
    iterations_done INTEGER DEFAULT 0,
    final_report    TEXT
);

CREATE TABLE IF NOT EXISTS idea_insights (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   TEXT    NOT NULL,
    domain       TEXT    NOT NULL,
    insight      TEXT    NOT NULL,
    insight_type TEXT,
    timestamp    TEXT    NOT NULL
);
"""


class MemoryStore:
    """SQLite-backed memory for the Bias Audit Pipeline self-evolution loop."""

    def __init__(self, db_path: str = DB_PATH) -> None:
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db = sqlite3.connect(db_path)
        self.db.row_factory = sqlite3.Row
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        self.db.executescript(_SCHEMA_SQL)
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    # ================================================================
    # Persist
    # ================================================================

    def persist_run(self, record: RunRecord) -> int:
        """Insert a full RunRecord (run + agent_runs + metrics + verifications)."""
        cur = self.db.execute(
            """INSERT INTO runs (timestamp, seed, all_passed, duration_s,
               best_eod, best_dpd, eod_compliant_models, paper_quality_issues)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record.timestamp,
                record.seed,
                record.all_passed,
                record.total_duration_seconds,
                record.best_eod,
                record.best_dpd,
                json.dumps(record.eod_compliant_models),
                json.dumps(record.paper_quality_issues),
            ),
        )
        run_id = cur.lastrowid
        if run_id is None:
            raise RuntimeError("Failed to insert run record")

        for ar in record.agents:
            self.db.execute(
                """INSERT INTO agent_runs (run_id, agent, seed, attempt, passed,
                   duration_s, error, error_type, judge_feedback, retry_hint,
                   metrics_snapshot) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    run_id, ar.agent, ar.seed, ar.attempt, ar.passed,
                    ar.duration_seconds, ar.error, ar.error_type,
                    json.dumps(ar.judge_feedback),
                    ar.retry_hint,
                    json.dumps(ar.metrics_snapshot) if ar.metrics_snapshot else None,
                ),
            )

        for m in record.metrics:
            is_baseline = m.model in {
                bm.model for bm in (record.metrics if not hasattr(record, '_baseline_model_names') else [])
            }
            self._insert_metric(run_id, m, is_baseline)

        for v in record.verifications:
            self.db.execute(
                """INSERT INTO verifications (run_id, claim, verified, evidence, error)
                   VALUES (?, ?, ?, ?, ?)""",
                (run_id, v.claim, v.verified, v.evidence, v.error),
            )

        self.db.commit()
        return run_id

    def persist_run_from_context(
        self,
        ctx,
        seed: int,
        all_passed: bool,
        total_duration: float,
        agent_runs: list[AgentRunRecord],
        verifications: list[VerificationRecord] | None = None,
    ) -> int:
        """Build a RunRecord from a PipelineContext and persist it."""
        all_metrics: list[ModelMetrics] = []
        baseline_names: set[str] = set()
        if ctx.mitigation:
            for m in ctx.mitigation.baseline_metrics:
                all_metrics.append(m)
                baseline_names.add(m.model)
            for m in ctx.mitigation.mitigation_metrics:
                all_metrics.append(m)
        elif ctx.baseline:
            for m in ctx.baseline.baseline_metrics:
                all_metrics.append(m)
                baseline_names.add(m.model)

        record = RunRecord(
            timestamp=datetime.now().isoformat(),
            seed=seed,
            all_passed=all_passed,
            total_duration_seconds=total_duration,
            agents=agent_runs,
            best_eod=ctx.get_best_eod(),
            best_dpd=ctx.get_best_dpd(),
            eod_compliant_models=ctx.get_eod_compliant_models(),
            paper_quality_issues=ctx.paper_quality_issues,
            verifications=verifications or ctx.verifications,
            metrics=all_metrics,
        )

        cur = self.db.execute(
            """INSERT INTO runs (timestamp, seed, all_passed, duration_s,
               best_eod, best_dpd, eod_compliant_models, paper_quality_issues)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record.timestamp, record.seed, record.all_passed,
                record.total_duration_seconds, record.best_eod, record.best_dpd,
                json.dumps(record.eod_compliant_models),
                json.dumps(record.paper_quality_issues),
            ),
        )
        run_id = cur.lastrowid
        if run_id is None:
            raise RuntimeError("Failed to insert run record")

        for ar in agent_runs:
            self.db.execute(
                """INSERT INTO agent_runs (run_id, agent, seed, attempt, passed,
                   duration_s, error, error_type, judge_feedback, retry_hint,
                   metrics_snapshot) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    run_id, ar.agent, ar.seed, ar.attempt, ar.passed,
                    ar.duration_seconds, ar.error, ar.error_type,
                    json.dumps(ar.judge_feedback), ar.retry_hint,
                    json.dumps(ar.metrics_snapshot) if ar.metrics_snapshot else None,
                ),
            )

        for m in all_metrics:
            is_baseline = m.model in baseline_names
            self._insert_metric(run_id, m, is_baseline)

        for v in (verifications or ctx.verifications):
            self.db.execute(
                """INSERT INTO verifications (run_id, claim, verified, evidence, error)
                   VALUES (?, ?, ?, ?, ?)""",
                (run_id, v.claim, v.verified, v.evidence, v.error),
            )

        self.db.commit()
        return run_id

    def _insert_metric(self, run_id: int, m: ModelMetrics, is_baseline: bool) -> None:
        self.db.execute(
            """INSERT INTO metrics (run_id, model, is_baseline, accuracy, f1_score,
               auc, fpr, dpd, eod, di, spd_violation, eod_violation)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run_id, m.model, is_baseline,
                m.accuracy, m.f1_score, m.auc, m.false_positive_rate,
                m.demographic_parity_diff, m.equalized_odds_diff,
                m.disparate_impact_ratio,
                m.eu_ai_act_spd_violation, m.eu_ai_act_eod_violation,
            ),
        )

    # ================================================================
    # Query helpers for optimizer
    # ================================================================

    def metric_trend(self, metric: str, limit: int = 20) -> list[tuple[str, float | None]]:
        """Return (timestamp, value) pairs for a run-level metric.

        Valid metrics: best_eod, best_dpd, duration_s, all_passed.
        """
        allowed = {"best_eod", "best_dpd", "duration_s", "all_passed"}
        if metric not in allowed:
            raise ValueError(f"metric must be one of {allowed}, got {metric!r}")
        rows = self.db.execute(
            f"SELECT timestamp, {metric} FROM runs ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [(r["timestamp"], r[metric]) for r in reversed(rows)]

    def model_eod_history(self, model: str, limit: int = 20) -> list[tuple[str, float]]:
        """Track a specific model's EOD across runs."""
        rows = self.db.execute(
            """SELECT r.timestamp, m.eod FROM metrics m
               JOIN runs r ON m.run_id = r.id
               WHERE m.model = ?
               ORDER BY r.id DESC LIMIT ?""",
            (model, limit),
        ).fetchall()
        return [(r["timestamp"], r["eod"]) for r in reversed(rows)]

    def failure_patterns(self, limit: int = 50) -> dict[str, int]:
        """Aggregate error_type counts from failed agent runs."""
        rows = self.db.execute(
            """SELECT error_type, COUNT(*) as cnt FROM agent_runs
               WHERE NOT passed AND error_type IS NOT NULL
               GROUP BY error_type ORDER BY cnt DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return {r["error_type"]: r["cnt"] for r in rows}

    def what_worked(self, agent: str, limit: int = 10) -> list[dict]:
        """Return recent successful runs for an agent with metrics context."""
        rows = self.db.execute(
            """SELECT ar.*, r.timestamp FROM agent_runs ar
               JOIN runs r ON ar.run_id = r.id
               WHERE ar.agent = ? AND ar.passed
               ORDER BY r.id DESC LIMIT ?""",
            (agent, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def what_failed(self, agent: str, limit: int = 10) -> list[dict]:
        """Return recent failed runs for an agent with error + feedback."""
        rows = self.db.execute(
            """SELECT ar.*, r.timestamp FROM agent_runs ar
               JOIN runs r ON ar.run_id = r.id
               WHERE ar.agent = ? AND NOT ar.passed
               ORDER BY r.id DESC LIMIT ?""",
            (agent, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def unverified_claims(self, limit: int = 10) -> list[dict]:
        """Claims that failed verification — optimizer should address these."""
        rows = self.db.execute(
            """SELECT v.*, r.timestamp FROM verifications v
               JOIN runs r ON v.run_id = r.id
               WHERE v.verified = 0
               ORDER BY r.id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def success_rate(self, agent: str | None = None) -> float:
        """Overall or per-agent success rate (0.0 to 1.0)."""
        if agent:
            row = self.db.execute(
                """SELECT CAST(SUM(passed) AS REAL) / COUNT(*) as rate
                   FROM agent_runs WHERE agent = ?""",
                (agent,),
            ).fetchone()
        else:
            row = self.db.execute(
                "SELECT CAST(SUM(passed) AS REAL) / COUNT(*) as rate FROM agent_runs"
            ).fetchone()
        return row["rate"] if row and row["rate"] is not None else 0.0

    def all_model_metrics(self, limit: int = 100) -> list[dict]:
        """Return recent metric rows with timestamps (for optimizer summaries)."""
        rows = self.db.execute(
            """SELECT m.*, r.timestamp FROM metrics m
               JOIN runs r ON m.run_id = r.id
               ORDER BY r.id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def recent_runs(self, limit: int = 10) -> list[dict]:
        """Return recent run summaries."""
        rows = self.db.execute(
            "SELECT * FROM runs ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def best_seed_for_agent(self, agent: str, default_seed: int = 42) -> tuple[int, str]:
        passed_rows = self.db.execute(
            """SELECT ar.seed, COUNT(*) as wins, MAX(r.id) as latest
               FROM agent_runs ar JOIN runs r ON ar.run_id = r.id
               WHERE ar.agent = ? AND ar.passed
               GROUP BY ar.seed ORDER BY wins DESC, latest DESC LIMIT 5""",
            (agent,),
        ).fetchall()
        if passed_rows:
            best = passed_rows[0]
            return (best["seed"], f"seed {best['seed']} passed {best['wins']}x for {agent}")

        failed_seeds = self.db.execute(
            """SELECT DISTINCT ar.seed FROM agent_runs ar
               WHERE ar.agent = ? AND NOT ar.passed
               ORDER BY ar.seed""",
            (agent,),
        ).fetchall()
        failed_set = {r["seed"] for r in failed_seeds}

        candidate = default_seed
        for _ in range(20):
            if candidate not in failed_set:
                return (candidate, f"seed {candidate} untried for {agent} (avoiding {len(failed_set)} failed seeds)")
            candidate += 1

        return (default_seed, "no history - using default seed")

    def recommend_seed_for_agent(self, agent: str, attempted_seeds: list[int], default_seed: int = 42) -> tuple[int, str]:
        attempted = set(attempted_seeds)
        passed_rows = self.db.execute(
            """SELECT ar.seed, COUNT(*) as wins, MAX(r.id) as latest
               FROM agent_runs ar JOIN runs r ON ar.run_id = r.id
               WHERE ar.agent = ? AND ar.passed
               GROUP BY ar.seed ORDER BY wins DESC, latest DESC""",
            (agent,),
        ).fetchall()
        for row in passed_rows:
            seed = row["seed"]
            if seed not in attempted:
                return (seed, f"using proven seed {seed} for {agent} ({row['wins']} prior wins)")

        failed_rows = self.db.execute(
            """SELECT DISTINCT ar.seed FROM agent_runs ar
               WHERE ar.agent = ? AND NOT ar.passed""",
            (agent,),
        ).fetchall()
        failed_set = {row["seed"] for row in failed_rows}

        candidate = default_seed
        for _ in range(50):
            if candidate not in attempted and candidate not in failed_set:
                return (
                    candidate,
                    f"using untried seed {candidate} for {agent} (avoiding {len(attempted)} attempted and {len(failed_set)} failed seeds)",
                )
            candidate += 1

        if passed_rows:
            best = passed_rows[0]
            return (best["seed"], f"reusing best historical seed {best['seed']} for {agent} after exhausting untried options")

        fallback = default_seed if default_seed not in attempted else max(attempted) + 1
        return (fallback, f"fallback seed {fallback} for {agent} after exhausting memory-guided options")

    def journey_summary(self) -> dict:
        summary: dict = {"total_runs": 0, "agents": {}, "metric_trends": {}, "unverified_claims": []}

        row = self.db.execute("SELECT COUNT(*) as cnt FROM runs").fetchone()
        summary["total_runs"] = row["cnt"] if row else 0

        if summary["total_runs"] == 0:
            return summary

        agents_in_db = self.db.execute("SELECT DISTINCT agent FROM agent_runs").fetchall()
        for agent_row in agents_in_db:
            agent = agent_row["agent"]
            info: dict = {}

            stats = self.db.execute(
                """SELECT COUNT(*) as total,
                          SUM(CASE WHEN passed THEN 1 ELSE 0 END) as wins,
                          SUM(CASE WHEN NOT passed THEN 1 ELSE 0 END) as losses
                   FROM agent_runs WHERE agent = ?""",
                (agent,),
            ).fetchone()
            info["total_attempts"] = stats["total"]
            info["successes"] = stats["wins"] or 0
            info["failures"] = stats["losses"] or 0
            info["success_rate"] = round(info["successes"] / info["total_attempts"], 3) if info["total_attempts"] else 0.0

            best = self.db.execute(
                """SELECT seed, COUNT(*) as wins FROM agent_runs
                   WHERE agent = ? AND passed GROUP BY seed ORDER BY wins DESC LIMIT 1""",
                (agent,),
            ).fetchone()
            info["best_seed"] = best["seed"] if best else None

            trials = self.db.execute(
                """SELECT ar.seed, ar.attempt, ar.passed, ar.error_type,
                          ar.judge_feedback, r.timestamp
                   FROM agent_runs ar JOIN runs r ON ar.run_id = r.id
                   WHERE ar.agent = ?
                   ORDER BY r.id DESC, ar.attempt DESC LIMIT 10""",
                (agent,),
            ).fetchall()
            info["recent_trials"] = []
            for t in trials:
                fb = t["judge_feedback"]
                try:
                    fb_list = json.loads(fb) if isinstance(fb, str) and fb else []
                except (json.JSONDecodeError, TypeError):
                    fb_list = [fb] if fb else []
                preview = "; ".join(str(f)[:80] for f in fb_list[:2]) if fb_list else ""
                info["recent_trials"].append(
                    {
                        "seed": t["seed"],
                        "attempt": t["attempt"],
                        "passed": bool(t["passed"]),
                        "error_type": t["error_type"],
                        "feedback_preview": preview,
                        "timestamp": t["timestamp"],
                    }
                )

            fail_reasons = self.db.execute(
                """SELECT error_type, COUNT(*) as cnt FROM agent_runs
                   WHERE agent = ? AND NOT passed AND error_type IS NOT NULL
                   GROUP BY error_type ORDER BY cnt DESC""",
                (agent,),
            ).fetchall()
            info["failure_reasons"] = {r["error_type"]: r["cnt"] for r in fail_reasons}

            directions: list[str] = []
            if info["failures"] > 0 and info["success_rate"] < 0.5:
                top_error = next(iter(info["failure_reasons"]), None)
                if top_error:
                    directions.append(f"Most common failure: {top_error} ({info['failure_reasons'][top_error]}x) - address this error type first")
            if info["successes"] > 0 and info["best_seed"] is not None:
                directions.append(f"Seed {info['best_seed']} has highest success rate - prefer it")
            if info["total_attempts"] > 5 and info["success_rate"] < 0.3:
                directions.append(f"Low success rate ({info['success_rate']:.0%}) - consider reviewing agent configuration or prompts")
            if not directions:
                if info["success_rate"] >= 0.8:
                    directions.append("Agent is performing well - no changes needed")
                else:
                    directions.append("Insufficient data for actionable recommendations")
            info["improvement_directions"] = directions

            summary["agents"][agent] = info

        for metric in ("best_eod", "best_dpd"):
            trend = self.metric_trend(metric, limit=10)
            if trend:
                summary["metric_trends"][metric] = [
                    {"timestamp": ts, "value": val}
                    for ts, val in trend if val is not None
                ]

        unverified = self.unverified_claims(limit=5)
        summary["unverified_claims"] = [
            {"claim": str(c.get("claim", ""))[:120], "evidence": str(c.get("evidence", ""))[:120]}
            for c in unverified
        ]

        return summary

    def prune_old_runs(self, keep_recent: int = 50) -> int:
        total = self.db.execute("SELECT COUNT(*) as cnt FROM runs").fetchone()["cnt"]
        keep_ids: set[int] = set()
        protected_ids: set[int] = set()
        recent = self.db.execute("SELECT id FROM runs ORDER BY id DESC LIMIT ?", (keep_recent,)).fetchall()
        keep_ids.update(r["id"] for r in recent)

        for metric in ("best_eod", "best_dpd"):
            best = self.db.execute(
                f"SELECT id FROM runs WHERE {metric} IS NOT NULL ORDER BY ABS({metric}) ASC LIMIT 3"
            ).fetchall()
            protected_ids.update(r["id"] for r in best)

        first = self.db.execute("SELECT id FROM runs ORDER BY id ASC LIMIT 1").fetchone()
        if first:
            keep_ids.add(first["id"])

        keep_ids.update(protected_ids)

        failed_runs = self.db.execute(
            """SELECT r.id,
                      GROUP_CONCAT(
                          ar.agent || '|' || COALESCE(ar.error_type, '') || '|' || COALESCE(ar.error, '') || '|' || COALESCE(ar.judge_feedback, ''),
                          '||'
                      ) AS signature,
                      SUM(CASE WHEN ar.passed THEN 1 ELSE 0 END) AS passed_count
               FROM runs r
               JOIN agent_runs ar ON ar.run_id = r.id
               GROUP BY r.id
               HAVING passed_count = 0
               ORDER BY r.id DESC"""
        ).fetchall()
        seen_signatures: set[str] = set()
        redundant_ids: set[int] = set()
        for row in failed_runs:
            signature = str(row["signature"] or "")
            run_id = int(row["id"])
            if not signature:
                continue
            if signature in seen_signatures and run_id not in protected_ids:
                redundant_ids.add(run_id)
            else:
                seen_signatures.add(signature)

        keep_ids.difference_update(redundant_ids)

        if total <= keep_recent and not redundant_ids:
            return 0

        if not keep_ids:
            return 0

        placeholders = ",".join("?" * len(keep_ids))
        ids_to_keep = list(keep_ids)

        for table in ("agent_runs", "metrics", "verifications"):
            self.db.execute(
                f"DELETE FROM {table} WHERE run_id NOT IN ({placeholders})",
                ids_to_keep,
            )
        deleted = self.db.execute(
            f"DELETE FROM runs WHERE id NOT IN ({placeholders})",
            ids_to_keep,
        ).rowcount
        self.db.commit()
        return deleted

    # ================================================================
    # Idea verification session API
    # ================================================================

    def store_idea_session(
        self,
        session_id: str,
        title: str,
        domain: str,
        hypotheses: list[str],
        methods: list[str],
        keywords: list[str],
        final_report: dict,
        iterations: list[dict],
    ) -> None:
        """Persist an idea verification session and extract insights into memory."""
        verdict = final_report.get("verdict", "")
        novelty_score = final_report.get("novelty_score")
        flaws = final_report.get("flaws", [])
        now = datetime.now().isoformat()

        self.db.execute(
            """INSERT OR REPLACE INTO idea_sessions
               (session_id, timestamp, title, domain, keywords, hypotheses,
                proposed_methods, verdict, novelty_score, flaws_count,
                iterations_done, final_report)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                session_id, now, title, domain,
                json.dumps(keywords),
                json.dumps(hypotheses),
                json.dumps(methods),
                verdict,
                novelty_score,
                len(flaws),
                len(iterations),
                json.dumps(final_report),
            ),
        )

        # Extract and store insights for future sessions in the same domain
        for flaw in flaws[:5]:
            if flaw and flaw.strip():
                self.db.execute(
                    """INSERT INTO idea_insights
                       (session_id, domain, insight, insight_type, timestamp)
                       VALUES (?, ?, ?, 'pitfall', ?)""",
                    (session_id, domain, flaw.strip()[:500], now),
                )

        for claim in final_report.get("supported_claims", [])[:3]:
            if claim and claim.strip():
                self.db.execute(
                    """INSERT INTO idea_insights
                       (session_id, domain, insight, insight_type, timestamp)
                       VALUES (?, ?, ?, 'supported_claim', ?)""",
                    (session_id, domain, claim.strip()[:500], now),
                )

        for method in methods[:3]:
            if method and method.strip():
                self.db.execute(
                    """INSERT INTO idea_insights
                       (session_id, domain, insight, insight_type, timestamp)
                       VALUES (?, ?, ?, 'effective_method', ?)""",
                    (session_id, domain, method.strip()[:500], now),
                )

        self.db.commit()

    def get_idea_insights(self, domain: str, limit: int = 10) -> list[str]:
        """Return previously accumulated insights for a given research domain."""
        rows = self.db.execute(
            """SELECT insight FROM idea_insights
               WHERE domain = ? OR domain LIKE ?
               ORDER BY id DESC LIMIT ?""",
            (domain, f"{domain}%", limit),
        ).fetchall()
        return [r["insight"] for r in rows]

    def get_idea_sessions(self, limit: int = 20) -> list[dict]:
        """Return a summary of recent idea verification sessions."""
        rows = self.db.execute(
            """SELECT session_id, timestamp, title, domain, verdict,
                      novelty_score, flaws_count, iterations_done
               FROM idea_sessions
               ORDER BY id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ================================================================
    # Legacy API wrappers (backward compat)
    # ================================================================

    def persist_event(
        self,
        agent: str,
        outcome: str,
        feedback: list | str | None = None,
        data_snapshot: dict | None = None,
    ) -> None:
        """Legacy API — wrap into a minimal AgentRunRecord row."""
        fb = feedback if isinstance(feedback, list) else ([feedback] if feedback else [])
        passed = outcome == "passed"
        self.db.execute(
            """INSERT INTO agent_runs (run_id, agent, seed, attempt, passed,
               duration_s, error, error_type, judge_feedback, retry_hint,
               metrics_snapshot) VALUES (0, ?, 42, 0, ?, 0, NULL, NULL, ?, NULL, ?)""",
            (
                agent, passed,
                json.dumps(fb),
                json.dumps(data_snapshot) if data_snapshot else None,
            ),
        )
        self.db.commit()

    def persist_session(
        self,
        results: dict,
        judge_failures: list | None = None,
    ) -> None:
        """Legacy API — wrap into a minimal run row."""
        all_passed = all(r.get("passed", False) for r in results.values())
        cur = self.db.execute(
            """INSERT INTO runs (timestamp, seed, all_passed, duration_s,
               best_eod, best_dpd, eod_compliant_models, paper_quality_issues)
               VALUES (?, 42, ?, 0, NULL, NULL, '[]', ?)""",
            (
                datetime.now().isoformat(),
                all_passed,
                json.dumps([f[1] for f in (judge_failures or [])] if judge_failures else []),
            ),
        )
        run_id = cur.lastrowid
        if run_id is None:
            raise RuntimeError("Failed to insert legacy run record")
        for agent_name, r in results.items():
            self.db.execute(
                """INSERT INTO agent_runs (run_id, agent, seed, attempt, passed,
                   duration_s, error, error_type, judge_feedback, retry_hint,
                   metrics_snapshot)
                   VALUES (?, ?, 42, ?, ?, 0, NULL, NULL, ?, NULL, NULL)""",
                (
                    run_id, agent_name,
                    r.get("attempts", 1),
                    r.get("passed", False),
                    json.dumps(r.get("feedback", [])),
                ),
            )
        self.db.commit()


# ====================================================================
# Module-level convenience functions (existing API contract)
# ====================================================================

_store: MemoryStore | None = None


def _get_store() -> MemoryStore:
    global _store
    if _store is None:
        _store = MemoryStore()
    return _store


def persist_event(
    agent: str,
    outcome: str,
    feedback: list | str | None = None,
    data_snapshot: dict | None = None,
) -> None:
    _get_store().persist_event(agent, outcome, feedback, data_snapshot)


def persist_session(results: dict, judge_failures: list | None = None) -> None:
    _get_store().persist_session(results, judge_failures)


def load_recent_sessions(limit: int = 10) -> list[dict]:
    return _get_store().recent_runs(limit)


def load_recent_events(agent: str | None = None, limit: int = 20) -> list[dict]:
    if agent:
        return _get_store().what_worked(agent, limit) + _get_store().what_failed(agent, limit)
    rows = _get_store().db.execute(
        "SELECT ar.*, r.timestamp FROM agent_runs ar JOIN runs r ON ar.run_id = r.id ORDER BY r.id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]
