"""
FastAPI server for Autonomous Research System GUI.

Supports two modes:
  - Goal-oriented: iterative research toward a quantifiable goal
  - Report: deep-dive research producing a comprehensive report

WebSocket streaming, REST API, static files.
"""

import asyncio
import json
import queue
import threading
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

SCRIPT_DIR = Path(__file__).resolve().parent.parent
OUTPUTS_DIR = SCRIPT_DIR / "outputs"
IDEA_UPLOADS_DIR = OUTPUTS_DIR / "idea_uploads"
IDEA_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Autonomous Research System")

# Static files — serve React build if it exists, otherwise fallback to legacy static
FRONTEND_BUILD = Path(__file__).resolve().parent / "frontend" / "dist"
STATIC_DIR = FRONTEND_BUILD if FRONTEND_BUILD.is_dir() else Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
# Serve favicon and /assets/* from the frontend dist directory at root
if FRONTEND_BUILD.is_dir():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_BUILD / "assets")), name="assets")

# Research state
_event_queue: queue.Queue = queue.Queue()
_research_thread = None
_ws_clients: list = []
_consumer_task = None

# Idea verification state
_idea_queue: queue.Queue = queue.Queue()
_idea_threads: dict[str, threading.Thread] = {}
_idea_consumer_task = None


def _run_research(mode: str = "goal", goal: str = "", claims_source: str | None = None,
                  max_iterations: int = 10, threshold: float = 0.9):
    """Run research loop in thread; events go to _event_queue."""
    try:
        from orchestration.continuous_research_loop import run_research_loop
        _event_queue.put({
            "type": "research_started",
            "mode": mode,
            "goal": goal,
        })
        report = run_research_loop(
            claims_source=claims_source,
            goal=goal or "Verify and refine research claims",
            max_iterations=max_iterations,
            converge_threshold=threshold,
            mode=mode,
        )
        _event_queue.put({
            "type": "research_finished",
            "converged": report.get("converged", False),
            "iterations": report.get("iterations_completed", 0),
            "report": report,
        })
    except Exception as e:
        _event_queue.put({
            "type": "research_error",
            "error": str(e),
        })
        _event_queue.put({
            "type": "research_finished",
            "converged": False,
            "iterations": 0,
            "report": {"error": str(e)},
        })


async def _event_consumer():
    """Consume events from queue and broadcast to WebSocket clients."""
    while True:
        try:
            event = await asyncio.to_thread(_event_queue.get)
            msg = json.dumps(event)
            for ws in list(_ws_clients):
                try:
                    await ws.send_text(msg)
                except Exception:
                    pass
            if event.get("type") in ("research_finished", "pipeline_finished"):
                break
        except Exception:
            break


async def _idea_consumer():
    """Consume idea verification events and broadcast to all WebSocket clients."""
    while True:
        try:
            event = await asyncio.to_thread(_idea_queue.get)
            msg = json.dumps(event)
            for ws in list(_ws_clients):
                try:
                    await ws.send_text(msg)
                except Exception:
                    pass
        except Exception:
            break


def _ensure_consumer_running():
    global _consumer_task
    if _consumer_task and not _consumer_task.done():
        return
    _consumer_task = asyncio.create_task(_event_consumer())


def _ensure_idea_consumer_running():
    global _idea_consumer_task
    if _idea_consumer_task and not _idea_consumer_task.done():
        return
    _idea_consumer_task = asyncio.create_task(_idea_consumer())


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    global _research_thread, _consumer_task
    await websocket.accept()
    _ws_clients.append(websocket)
    _ensure_idea_consumer_running()
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("action") == "start_research":
                    running = _research_thread and _research_thread.is_alive()
                    if not running:
                        _research_thread = threading.Thread(
                            target=_run_research,
                            kwargs={
                                "mode": msg.get("mode", "goal"),
                                "goal": msg.get("goal", ""),
                                "claims_source": msg.get("claims_source"),
                                "max_iterations": msg.get("max_iterations", 10),
                                "threshold": msg.get("threshold", 0.9),
                            },
                            daemon=True,
                        )
                        _research_thread.start()
                        _ensure_consumer_running()
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        if websocket in _ws_clients:
            _ws_clients.remove(websocket)


@app.post("/api/research/start")
async def start_research(
    mode: str = "goal",
    goal: str = "",
    claims_source: str | None = None,
    max_iterations: int = 10,
    threshold: float = 0.9,
):
    """Start a research session."""
    global _research_thread
    if _research_thread and _research_thread.is_alive():
        return JSONResponse({"status": "already_running"})
    _research_thread = threading.Thread(
        target=_run_research,
        kwargs={
            "mode": mode,
            "goal": goal,
            "claims_source": claims_source,
            "max_iterations": max_iterations,
            "threshold": threshold,
        },
        daemon=True,
    )
    _research_thread.start()
    _ensure_consumer_running()
    return JSONResponse({"status": "started", "mode": mode})


@app.get("/api/outputs/research")
async def get_research_report():
    """Get the latest research loop report."""
    path = OUTPUTS_DIR / "research_loop_report.json"
    if not path.exists():
        return JSONResponse({"error": "not found"}, status_code=404)
    with open(path, encoding="utf-8") as f:
        return JSONResponse(json.load(f))


@app.get("/api/outputs/cross_validation")
async def get_cross_validation():
    """Get the latest cross-validation report."""
    path = OUTPUTS_DIR / "cross_validation_report.json"
    if not path.exists():
        return JSONResponse({"error": "not found"}, status_code=404)
    with open(path, encoding="utf-8") as f:
        return JSONResponse(json.load(f))


@app.get("/api/outputs/flaws")
async def get_flaws():
    """Get the latest flaw report."""
    path = OUTPUTS_DIR / "flaw_report.json"
    if not path.exists():
        return JSONResponse({"error": "not found"}, status_code=404)
    with open(path, encoding="utf-8") as f:
        return JSONResponse(json.load(f))


@app.get("/api/outputs/verification")
async def get_verification():
    """Get the latest verification report."""
    path = OUTPUTS_DIR / "verification_report.json"
    if not path.exists():
        return JSONResponse({"error": "not found"}, status_code=404)
    with open(path, encoding="utf-8") as f:
        return JSONResponse(json.load(f))


@app.get("/api/providers")
async def get_providers():
    """List available LLM providers."""
    try:
        from utils.llm_base import list_providers
        return JSONResponse({"providers": list_providers()})
    except Exception:
        return JSONResponse({"providers": []})


@app.get("/api/memory/journey")
async def get_memory_journey():
    try:
        from agents.memory_agent import MemoryStore
    except ImportError:
        return JSONResponse({"error": "memory unavailable"}, status_code=503)
    store = MemoryStore()
    try:
        return JSONResponse(store.research_journey_summary())
    except AttributeError:
        try:
            return JSONResponse(store.journey_summary())
        except Exception:
            return JSONResponse({"error": "no summary available"}, status_code=503)
    finally:
        store.close()


@app.get("/api/memory/knowledge")
async def get_memory_knowledge():
    """Get knowledge entries from memory."""
    try:
        from agents.memory_agent import MemoryStore
    except ImportError:
        return JSONResponse({"error": "memory unavailable"}, status_code=503)
    store = MemoryStore()
    try:
        knowledge = store.get_relevant_knowledge("", limit=50)
        return JSONResponse({"entries": knowledge})
    except Exception:
        return JSONResponse({"entries": []})
    finally:
        store.close()


@app.get("/api/memory/pitfalls")
async def get_memory_pitfalls():
    """Get known pitfalls from memory."""
    try:
        from agents.memory_agent import MemoryStore
    except ImportError:
        return JSONResponse({"error": "memory unavailable"}, status_code=503)
    store = MemoryStore()
    try:
        pitfalls = store.get_known_pitfalls(limit=50)
        return JSONResponse({"pitfalls": pitfalls})
    except Exception:
        return JSONResponse({"pitfalls": []})
    finally:
        store.close()


@app.get("/favicon.svg")
async def favicon():
    """Serve favicon from frontend dist."""
    path = FRONTEND_BUILD / "favicon.svg"
    if path.exists():
        return FileResponse(path, media_type="image/svg+xml")
    return PlainTextResponse("not found", status_code=404)


@app.get("/")
async def index():
    """Serve the frontend."""
    # Try React build first, fall back to legacy static
    for candidate in [FRONTEND_BUILD / "index.html", Path(__file__).resolve().parent / "static" / "index.html"]:
        if candidate.exists():
            return FileResponse(candidate)
    return PlainTextResponse("Frontend not found. Run: cd gui/frontend && npm install && npm run build", status_code=404)


# ---------------------------------------------------------------------------
# Idea Verification API
# ---------------------------------------------------------------------------


def _run_idea_verification(
    session_id: str,
    text: str,
    image_paths: list[str],
    max_iterations: int,
) -> None:
    """Thread target: run idea verification and push events to _idea_queue."""
    try:
        from orchestration.idea_verification_orchestrator import run_idea_verification
        run_idea_verification(
            text,
            image_paths=image_paths,
            max_iterations=max_iterations,
            bus=_idea_queue,
            session_id=session_id,
        )
    except Exception as e:
        try:
            _idea_queue.put({
                "type": "idea_log",
                "session_id": session_id,
                "line": f"[ERROR] Verification failed: {e}",
            })
            _idea_queue.put({
                "type": "idea_finished",
                "session_id": session_id,
                "final_report": {"verdict": "error", "flaws": [str(e)], "recommendations": []},
                "iterations_completed": 0,
            })
        except Exception:
            pass


@app.post("/api/idea/verify")
async def submit_idea(
    text: str = Form(""),
    max_iterations: int = Form(3),
    files: list[UploadFile] = File(default=[]),
):
    """
    Submit a research idea (text + optional images) for iterative verification.
    Returns the session_id immediately; progress streams via WebSocket idea_* events.
    """
    import random
    from datetime import datetime as _dt

    if not text.strip():
        return JSONResponse({"error": "text is required"}, status_code=400)

    session_id = f"idea_{_dt.now().strftime('%Y%m%d_%H%M%S')}_{random.randint(1000, 9999)}"

    # Save uploaded files with randomized names to prevent path traversal
    import uuid as _uuid
    session_upload_dir = IDEA_UPLOADS_DIR / session_id
    session_upload_dir.mkdir(parents=True, exist_ok=True)
    saved_paths: list[str] = []
    for upload in files:
        if not upload.filename:
            continue
        # Preserve only the extension from the original filename; use a random stem
        original_ext = Path(upload.filename).suffix.lower()
        allowed_exts = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
        if original_ext not in allowed_exts:
            continue
        safe_name = f"{_uuid.uuid4().hex}{original_ext}"
        dest = session_upload_dir / safe_name
        content = await upload.read()
        with open(dest, "wb") as fh:
            fh.write(content)
        saved_paths.append(str(dest))

    # Clamp iterations
    max_iterations = max(1, min(max_iterations, 5))

    # Start verification thread
    thread = threading.Thread(
        target=_run_idea_verification,
        args=(session_id, text.strip(), saved_paths, max_iterations),
        daemon=True,
    )
    thread.start()
    _idea_threads[session_id] = thread
    _ensure_idea_consumer_running()

    return JSONResponse({"status": "started", "session_id": session_id})


@app.get("/api/idea/results/{session_id}")
async def get_idea_results(session_id: str):
    """Return the verification results for a completed session."""
    # Strict sanitization: only alphanumeric, underscore, hyphen (no path separators)
    safe = "".join(c for c in session_id if c.isalnum() or c in "_-")
    if safe != session_id or not safe:
        return JSONResponse({"error": "invalid session_id"}, status_code=400)
    # Enumerate server-side directory to decouple the path from user-controlled input
    idea_verification_dir = (OUTPUTS_DIR / "idea_verification").resolve()
    results_path = None
    if idea_verification_dir.is_dir():
        for candidate_dir in idea_verification_dir.iterdir():
            if candidate_dir.is_dir() and candidate_dir.name == safe:
                results_path = candidate_dir / "verification_results.json"
                break
    if results_path is None or not results_path.exists():
        running = _idea_threads.get(session_id)
        status = "running" if (running and running.is_alive()) else "pending"
        return JSONResponse({"status": status})
    with open(results_path, encoding="utf-8") as fh:
        return JSONResponse(json.load(fh))


@app.get("/api/idea/sessions")
async def list_idea_sessions():
    """Return a list of past idea verification sessions from memory."""
    try:
        from agents.memory_agent import MemoryStore
    except ImportError:
        return JSONResponse({"error": "memory unavailable"}, status_code=503)
    store = MemoryStore()
    try:
        return JSONResponse(store.get_idea_sessions(limit=20))
    finally:
        store.close()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
