"""
FastAPI server for Bias Audit Pipeline GUI — WebSocket events, REST API, static files.
"""

import asyncio
import json
import queue
import threading
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

SCRIPT_DIR = Path(__file__).resolve().parent.parent
OUTPUTS_DIR = SCRIPT_DIR / "outputs"
FIGURES_DIR = OUTPUTS_DIR / "figures"
PAPER_DIR = OUTPUTS_DIR / "paper"

app = FastAPI(title="Bias Audit Pipeline")

# Static files
STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Pipeline state
_event_queue = queue.Queue()
_pipeline_thread = None
_ws_clients = []
_consumer_task = None


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


def _ensure_consumer_running():
    """Start consumer task if pipeline is running and consumer not active."""
    global _consumer_task
    if _consumer_task and not _consumer_task.done():
        return
    _consumer_task = asyncio.create_task(_event_consumer())


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    global _pipeline_thread, _consumer_task
    await websocket.accept()
    _ws_clients.append(websocket)
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
    path = OUTPUTS_DIR / "paper_draft.md"
    if not path.exists():
        return PlainTextResponse("Paper not yet generated.", status_code=404)
    with open(path, encoding="utf-8") as f:
        return PlainTextResponse(f.read(), media_type="text/markdown")


@app.get("/api/outputs/paper.pdf")
async def get_paper_pdf():
    path = PAPER_DIR / "paper.pdf"
    if not path.exists():
        return JSONResponse({"error": "PDF not found"}, status_code=404)
    return FileResponse(path, media_type="application/pdf", filename="paper.pdf")


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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
