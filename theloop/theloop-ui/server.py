"""TheLoop UI — single-page pipeline dashboard."""

import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent.parent / ".env")

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, str(Path(__file__).parent.parent / "theloop-core"))
from history import load_runs, create_run, update_step, get_run, get_current_run
from steps import (
    run_collect, run_index, run_generate_qa, run_benchmark, run_perihan_eval,
    run_report, get_report_html, stop_step, check_perihan,
    get_qa_count, get_collector_file_count, get_eval_summary,
)

app = FastAPI(title="TheLoop")

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ---------------------------------------------------------------------------
# SSE helper
# ---------------------------------------------------------------------------

async def sse_stream(step_name: str, generator, run_id: int):
    """Wrap a step generator as SSE, updating history along the way."""
    from fastapi.responses import StreamingResponse

    update_step(run_id, step_name, {"status": "running", "started": datetime.now().isoformat()})

    async def stream():
        last_cost = 0.0
        indexed = 0
        error_occurred = False
        try:
            async for event in generator:
                if event.get("total_cost"):
                    last_cost = event["total_cost"]
                if event.get("indexed"):
                    indexed = event["indexed"]
                if event.get("type") == "error":
                    error_occurred = True
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            error_occurred = True
            yield f"data: {json.dumps({'type': 'error', 'text': str(e)})}\n\n"

        status = "error" if error_occurred else "done"
        step_data = {
            "status": status,
            "finished": datetime.now().isoformat(),
            "cost": last_cost,
        }
        if indexed:
            step_data["indexed"] = indexed
        update_step(run_id, step_name, step_data)

        yield f"data: {json.dumps({'type': 'step_complete', 'step': step_name, 'status': status})}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


@app.get("/api/status")
async def status():
    """Get current loop status."""
    current = get_current_run()
    perihan_up = await check_perihan()
    return {
        "current_run": current,
        "perihan_up": perihan_up,
        "collector_files": get_collector_file_count(),
        "qa_count": get_qa_count(),
        "eval_summary": get_eval_summary(),
    }


@app.get("/api/history")
async def history():
    return load_runs()


@app.post("/api/new-run")
async def new_run():
    run = create_run()
    return run


@app.post("/api/run/{run_id}/{step}")
async def run_step(run_id: int, step: str, category: str = "all", strategy: str = "all"):
    """Start a step. Returns SSE stream."""
    run = get_run(run_id)
    if not run:
        return JSONResponse({"error": "Run not found"}, status_code=404)

    generators = {
        "collect": lambda: run_collect(category),
        "index": lambda: run_index(),
        "generate_qa": lambda: run_generate_qa(strategy),
        "benchmark": lambda: run_benchmark(),
        "perihan": lambda: run_perihan_eval(),
        "report": lambda: run_report(),
    }

    if step not in generators:
        return JSONResponse({"error": f"Unknown step: {step}"}, status_code=400)

    return await sse_stream(step, generators[step](), run_id)


@app.post("/api/stop/{step}")
async def stop(step: str):
    await stop_step(step)
    return {"message": f"Stopped {step}"}


@app.post("/api/run/{run_id}/improve")
async def complete_improve(run_id: int, notes: str = ""):
    """Mark the improve step as done."""
    update_step(run_id, "improve", {
        "status": "done",
        "finished": datetime.now().isoformat(),
        "notes": notes,
    })
    return {"message": "Improvement step completed"}


@app.post("/api/run/{run_id}/skip/{step}")
async def skip_step(run_id: int, step: str):
    """Skip a step."""
    update_step(run_id, step, {"status": "skipped", "finished": datetime.now().isoformat()})
    return {"message": f"Skipped {step}"}


@app.get("/api/report")
async def get_report():
    html = get_report_html()
    if html:
        return HTMLResponse(html)
    return JSONResponse({"error": "No report generated yet"}, status_code=404)


if __name__ == "__main__":
    import uvicorn
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
    uvicorn.run(app, host="0.0.0.0", port=8100)
