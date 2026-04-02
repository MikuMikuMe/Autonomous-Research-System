"""
FastAPI server for Bias Audit Pipeline GUI — WebSocket events, REST API, static files.
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
FIGURES_DIR = OUTPUTS_DIR / "figures"
PAPER_DIR = OUTPUTS_DIR / "paper"
IDEA_UPLOADS_DIR = OUTPUTS_DIR / "idea_uploads"
IDEA_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Bias Audit Pipeline")

# Static files
STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Pipeline state
_event_queue: queue.Queue = queue.Queue()
_pipeline_thread = None
_ws_clients: list = []
_consumer_task = None

# Idea verification state (separate thread + queue, shared WS broadcast)
_idea_queue: queue.Queue = queue.Queue()
_idea_threads: dict[str, threading.Thread] = {}
_idea_consumer_task = None


def _run_pipeline():
    """Run pipeline in thread; events go to _event_queue."""
    try:
        from gui.streaming_orchestrator import run_pipeline
        run_pipeline(_event_queue)
    except Exception as e:
        try:
            _event_queue.put({
                "type": "agent_log",
                "agent": "",
                "line": f"[ERROR] Pipeline failed to start: {e}",
            })
            _event_queue.put({
                "type": "pipeline_finished",
                "all_passed": False,
                "results": {},
            })
        except Exception:
            pass


async def _event_consumer():
    """Consume events from queue and broadcast to WebSocket clients. Runs until pipeline_finished."""
    while True:
        try:
            event = await asyncio.to_thread(_event_queue.get)
            msg = json.dumps(event)
            for ws in list(_ws_clients):
                try:
                    await ws.send_text(msg)
                except Exception:
                    pass
            if event.get("type") == "pipeline_finished":
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
    """Start consumer task if pipeline is running and consumer not active."""
    global _consumer_task
    if _consumer_task and not _consumer_task.done():
        return
    _consumer_task = asyncio.create_task(_event_consumer())


def _ensure_idea_consumer_running():
    """Start the idea verification event consumer if not already running."""
    global _idea_consumer_task
    if _idea_consumer_task and not _idea_consumer_task.done():
        return
    _idea_consumer_task = asyncio.create_task(_idea_consumer())


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    global _pipeline_thread, _consumer_task
    await websocket.accept()
    _ws_clients.append(websocket)
    _ensure_idea_consumer_running()  # Keep idea consumer alive as long as clients are connected
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("action") == "run":
                    running = _pipeline_thread and _pipeline_thread.is_alive()
                    if not running:
                        _pipeline_thread = threading.Thread(target=_run_pipeline)
                        _pipeline_thread.start()
                        _ensure_consumer_running()
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        if websocket in _ws_clients:
            _ws_clients.remove(websocket)


@app.post("/run")
async def start_pipeline():
    """Start the pipeline. Events stream via WebSocket."""
    global _pipeline_thread
    if _pipeline_thread and _pipeline_thread.is_alive():
        return {"status": "already_running"}
    _pipeline_thread = threading.Thread(target=_run_pipeline)
    _pipeline_thread.start()
    _ensure_consumer_running()  # Must start consumer so events reach WebSocket clients
    return {"status": "started"}


@app.get("/api/outputs/baseline")
async def get_baseline():
    path = OUTPUTS_DIR / "baseline_results.json"
    if not path.exists():
        return JSONResponse({"error": "not found"}, status_code=404)
    with open(path, encoding="utf-8") as f:
        return JSONResponse(json.load(f))


@app.get("/api/outputs/mitigation")
async def get_mitigation():
    path = OUTPUTS_DIR / "mitigation_results.json"
    if not path.exists():
        return JSONResponse({"error": "not found"}, status_code=404)
    with open(path, encoding="utf-8") as f:
        return JSONResponse(json.load(f))


@app.get("/api/outputs/paper")
async def get_paper():
    path = OUTPUTS_DIR / "paper" / "paper.tex"
    if not path.exists():
        path = OUTPUTS_DIR / "paper_draft.md"
    if not path.exists():
        return PlainTextResponse("Paper not yet generated.", status_code=404)
    with open(path, encoding="utf-8") as f:
        media = "text/x-latex" if str(path).endswith(".tex") else "text/markdown"
        return PlainTextResponse(f.read(), media_type=media)


@app.get("/api/outputs/paper.pdf")
async def get_paper_pdf():
    path = PAPER_DIR / "paper.pdf"
    if not path.exists():
        return JSONResponse({"error": "PDF not found"}, status_code=404)
    return FileResponse(path, media_type="application/pdf", filename="paper.pdf")


@app.get("/api/memory/journey")
async def get_memory_journey():
    try:
        from agents.memory_agent import MemoryStore
    except ImportError:
        return JSONResponse({"error": "memory unavailable"}, status_code=503)

    store = MemoryStore()
    try:
        return JSONResponse(store.journey_summary())
    finally:
        store.close()


@app.get("/api/outputs/figures/{name}")
async def get_figure(name: str):
    # Sanitize: only allow alphanumeric and underscore
    safe = "".join(c for c in name if c.isalnum() or c in "._-")
    if safe != name:
        return JSONResponse({"error": "invalid name"}, status_code=400)
    for base, ext in [(FIGURES_DIR, ".png"), (FIGURES_DIR, ".pdf"), (OUTPUTS_DIR, ".png")]:
        path = base / f"{name}{ext}" if not name.endswith(ext) else base / name
        if path.exists():
            media = "image/png" if ".png" in str(path) else "application/pdf"
            return FileResponse(path, media_type=media)
    return JSONResponse({"error": "not found"}, status_code=404)


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


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
