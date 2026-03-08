"""
Streaming Orchestrator — Runs the pipeline with real-time event emission.
Used by the GUI server; original orchestrator.py remains for CLI.
"""

import os
import sys
import subprocess
import threading
import queue

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)

MAX_RETRIES = 3
AGENTS = ["detection", "mitigation", "auditing"]
RESEARCH_MODULES = ["agents.research_agent", "agents.gap_check_agent", "agents.coverage_agent", "agents.reproducibility_agent"]

MODULE_MAP = {
    "detection": "agents.detection_agent",
    "mitigation": "agents.mitigation_agent",
    "auditing": "agents.auditing_agent",
}


def _run_agent_subprocess(agent_name: str, seed: int, event_queue: queue.Queue):
    """Run agent as subprocess, stream stdout lines to event_queue."""
    module = MODULE_MAP[agent_name]
    cmd = [sys.executable, "-u", "-m", module, str(seed)]  # -u = unbuffered stdout
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=env,
        cwd=SCRIPT_DIR,
    )

    for line in iter(proc.stdout.readline, ""):
        if line:
            s = line.rstrip()
            # Parse [QMIND_PROGRESS]0.42|label -> agent_progress event (skip from log)
            if s.startswith("[QMIND_PROGRESS]"):
                try:
                    rest = s[len("[QMIND_PROGRESS]"):]
                    pct_str, _, label = rest.partition("|")
                    pct = float(pct_str)
                    event_queue.put({
                        "type": "agent_progress",
                        "agent": agent_name,
                        "progress": pct,
                        "label": label or "",
                    })
                except ValueError:
                    pass
                continue
            event_queue.put({"type": "agent_log", "agent": agent_name, "line": s})

    proc.wait()
    return proc.returncode


def _run_research_module(module_name: str, event_queue: queue.Queue) -> int:
    """Run a research module (research_agent, gap_check_agent, etc.) as subprocess, stream stdout to event_queue."""
    cmd = [sys.executable, "-u", "-m", module_name]
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=env,
        cwd=SCRIPT_DIR,
    )

    for line in iter(proc.stdout.readline, ""):
        if line:
            s = line.rstrip()
            event_queue.put({"type": "agent_log", "agent": "research", "line": s})

    proc.wait()
    return proc.returncode


def _run_judge(agent_name: str):
    """Run judge evaluation. Returns (passed, feedback, retry_hint, actionable_feedback)."""
    from agents.judge_agent import evaluate
    r = evaluate(agent_name)
    return r["passed"], r["feedback"], r.get("retry_hint"), r.get("actionable_feedback")


def run_pipeline(event_queue: queue.Queue):
    """
    Run the full pipeline, putting events into event_queue.
    Events: agent_started, agent_log, agent_finished, judge_result, outputs_updated, pipeline_finished
    """
    try:
        event_queue.put({
            "type": "agent_log",
            "agent": "",
            "line": "Pipeline starting...",
        })
    except Exception:
        pass

    results = {}
    seed = 42

    for agent_name in AGENTS:
        event_queue.put({"type": "agent_started", "agent": agent_name})
        event_queue.put({
            "type": "agent_log",
            "agent": agent_name,
            "line": f"  Starting {agent_name} agent (loading libraries & data — may take 10–30s)...",
        })

        for attempt in range(1, MAX_RETRIES + 1):
            if attempt > 1:
                seed = 42 + attempt
                event_queue.put({
                    "type": "agent_log",
                    "agent": agent_name,
                    "line": f"\n  [RETRY {attempt}/{MAX_RETRIES}] seed={seed}",
                })

            returncode = _run_agent_subprocess(agent_name, seed, event_queue)
            event_queue.put({"type": "agent_finished", "agent": agent_name, "returncode": returncode})

            if returncode != 0:
                event_queue.put({
                    "type": "agent_log",
                    "agent": agent_name,
                    "line": f"\n  [FAILED] Agent exited with error (returncode {returncode}). Retrying...",
                })
                event_queue.put({
                    "type": "judge_result",
                    "agent": agent_name,
                    "passed": False,
                    "feedback": ["Agent exited with error. Retrying..."],
                    "attempt": attempt,
                })
                continue

            event_queue.put({
                "type": "agent_log",
                "agent": agent_name,
                "line": f"  Running Judge evaluation for {agent_name}...",
            })
            passed, feedback, retry_hint, actionable_feedback = _run_judge(agent_name)
            event_queue.put({
                "type": "agent_log",
                "agent": agent_name,
                "line": f"\n  [Judge] {'PASSED' if passed else 'FAILED'}" + ("" if passed else f": {'; '.join(feedback[:3])}"),
            })
            event_queue.put({
                "type": "judge_result",
                "agent": agent_name,
                "passed": passed,
                "feedback": feedback,
                "retry_hint": retry_hint,
                "attempt": attempt,
            })

            if passed:
                results[agent_name] = {"passed": True, "attempts": attempt}
                event_queue.put({"type": "outputs_updated", "agent": agent_name})
                break
            else:
                # AI Court / Autogenesis: Judge delegates fix → Revision Agent
                if retry_hint == "revise_claims" and actionable_feedback:
                    event_queue.put({
                        "type": "agent_log",
                        "agent": agent_name,
                        "line": "\n  [REVISION] Invoking Revision Agent to fix claim contradictions...",
                    })
                    env = os.environ.copy()
                    env["JUDGE_FEEDBACK"] = actionable_feedback
                    rev = subprocess.run(
                        [sys.executable, "-m", "agents.revision_agent"],
                        env=env,
                        capture_output=True,
                        text=True,
                        cwd=SCRIPT_DIR,
                    )
                    if rev.returncode == 0:
                        event_queue.put({
                            "type": "agent_log",
                            "agent": agent_name,
                            "line": "  [REVISION] Applied. Re-running Judge...",
                        })
                        passed2, feedback2, _, _ = _run_judge(agent_name)
                        event_queue.put({
                            "type": "agent_log",
                            "agent": agent_name,
                            "line": f"  [Judge] {'PASSED' if passed2 else 'FAILED'} after revision" + ("" if passed2 else f": {'; '.join(feedback2[:3])}"),
                        })
                        event_queue.put({
                            "type": "judge_result",
                            "agent": agent_name,
                            "passed": passed2,
                            "feedback": feedback2,
                            "retry_hint": None,
                            "attempt": attempt,
                        })
                        if passed2:
                            results[agent_name] = {"passed": True, "attempts": attempt}
                            event_queue.put({"type": "outputs_updated", "agent": agent_name})
                            break
                    else:
                        event_queue.put({
                            "type": "agent_log",
                            "agent": agent_name,
                            "line": f"  [REVISION] FAILED: {rev.stderr or rev.stdout or 'unknown'}",
                        })

                if attempt == MAX_RETRIES:
                    event_queue.put({
                        "type": "agent_log",
                        "agent": agent_name,
                        "line": f"\n  [FAILED] {agent_name} failed after {MAX_RETRIES} attempts. Stopping pipeline.",
                    })
                    results[agent_name] = {"passed": False, "attempts": attempt, "feedback": feedback}
                    break

        if not results.get(agent_name, {}).get("passed"):
            break

    all_passed = all(r["passed"] for r in results.values())

    # Research phase (alphaXiv, gap check, coverage, reproducibility) — stream to live log
    if all_passed:
        event_queue.put({
            "type": "agent_log",
            "agent": "research",
            "line": f"\n{'─'*50}\n  RESEARCH PHASE — alphaXiv, Gap Check, Coverage, Reproducibility\n{'─'*50}",
        })
        for module in RESEARCH_MODULES:
            event_queue.put({
                "type": "agent_log",
                "agent": "research",
                "line": f"\n  >> {module}",
            })
            _run_research_module(module, event_queue)

    event_queue.put({
        "type": "agent_log",
        "agent": "",
        "line": f"\n{'='*50}\n  Pipeline {'PASSED' if all_passed else 'FAILED'}. " + (
            "All agents passed." if all_passed else f"Failed at: {', '.join(a for a, r in results.items() if not r.get('passed'))}"
        ),
    })
    event_queue.put({
        "type": "pipeline_finished",
        "all_passed": all_passed,
        "results": results,
    })
