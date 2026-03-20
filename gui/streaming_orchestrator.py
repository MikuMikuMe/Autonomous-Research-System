from __future__ import annotations

import os
import queue
import subprocess
import sys
from pathlib import Path

from runtime.core import PipelineRuntime, RuntimeConfig
from utils.events import EventBus


PROJECT_ROOT = Path(__file__).resolve().parent.parent
os.chdir(PROJECT_ROOT)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

MODULE_MAP = {
    "detection": "agents.detection_agent",
    "mitigation": "agents.mitigation_agent",
    "auditing": "agents.auditing_agent",
}


def _classify_error(exc: Exception | None, stderr: str = "") -> str:
    message = str(exc) if exc else stderr
    if "LaTeX" in message or "pdflatex" in message:
        return "LaTeXCompileError"
    if "timeout" in message.lower():
        return "GeminiTimeout"
    if "schema" in message.lower() or "missing key" in message.lower():
        return "SchemaValidation"
    return "Unknown"


def _run_agent_subprocess(agent_name: str, seed: int, bus: EventBus) -> int:
    module = MODULE_MAP[agent_name]
    cmd = [sys.executable, "-u", "-m", module, str(seed)]
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=env,
        cwd=str(PROJECT_ROOT),
    )

    stdout = proc.stdout
    if stdout is not None:
        for line in iter(stdout.readline, ""):
            if not line:
                continue
            stripped = line.rstrip()
            if stripped.startswith("[QMIND_PROGRESS]"):
                try:
                    rest = stripped[len("[QMIND_PROGRESS]"):]
                    pct_str, _, label = rest.partition("|")
                    bus.progress(agent_name, float(pct_str), label)
                except ValueError:
                    pass
                continue
            bus.log(agent_name, stripped)

    proc.wait()
    return proc.returncode


def _run_research_module(module_name: str, bus: EventBus) -> int:
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
        cwd=str(PROJECT_ROOT),
    )

    stdout = proc.stdout
    if stdout is not None:
        for line in iter(stdout.readline, ""):
            if line:
                bus.log("research", line.rstrip())

    proc.wait()
    return proc.returncode


def _run_judge(agent_name: str):
    from agents.judge_agent import evaluate

    return evaluate(agent_name)


def build_runtime(bus: EventBus) -> PipelineRuntime:
    config = RuntimeConfig.from_project_root(PROJECT_ROOT)
    return PipelineRuntime(
        config=config,
        bus=bus,
        run_agent=_run_agent_subprocess,
        run_research_module=_run_research_module,
        run_judge=_run_judge,
        classify_error=_classify_error,
    )


def run_pipeline(event_queue: queue.Queue[dict[str, object]]) -> None:
    bus = EventBus()
    bus.connect_queue(event_queue)
    bus.log("", "Pipeline starting...")
    _ = build_runtime(bus).run()
