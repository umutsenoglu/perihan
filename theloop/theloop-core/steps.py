"""Step runners — each step wraps an existing script as an async subprocess."""

import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime

import httpx

THELOOP_DIR = Path(__file__).parent.parent
ROOT_DIR = THELOOP_DIR.parent
PYTHON = sys.executable

# Active subprocesses (so we can cancel)
_active_processes: dict[str, asyncio.subprocess.Process] = {}


async def _run_subprocess(step_name: str, cmd: list[str], cwd: str):
    """Run a command as subprocess, yielding stdout lines as events."""
    import os
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        cwd=cwd,
        env=env,
    )
    _active_processes[step_name] = proc

    try:
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace").rstrip()
            if text:
                yield {"type": "log", "text": text, "time": datetime.now().strftime("%H:%M:%S")}

        await proc.wait()
        yield {"type": "exit", "code": proc.returncode}
    finally:
        _active_processes.pop(step_name, None)


async def stop_step(step_name: str):
    """Stop a running step. On Windows, kills the entire process tree."""
    proc = _active_processes.get(step_name)
    if proc and proc.returncode is None:
        import platform
        if platform.system() == "Windows":
            # On Windows, terminate() doesn't kill child processes.
            # Use taskkill /T to kill the entire process tree.
            kill_proc = await asyncio.create_subprocess_exec(
                "taskkill", "/F", "/T", "/PID", str(proc.pid),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await kill_proc.wait()
        else:
            proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            proc.kill()


# ---------------------------------------------------------------------------
# Step 1: Collect
# ---------------------------------------------------------------------------

async def run_collect(category: str = "all"):
    """Run the collector."""
    cmd = [PYTHON, "app.py"]
    if category != "all":
        cmd.append(category)
    async for event in _run_subprocess("collect", cmd, str(THELOOP_DIR / "collector")):
        yield event


# ---------------------------------------------------------------------------
# Step 2: Index (calls Perihan API)
# ---------------------------------------------------------------------------

async def check_perihan() -> bool:
    """Check if Perihan server is running."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get("http://localhost:8000/current-model")
            return resp.status_code == 200
    except Exception:
        return False


async def run_index():
    """Index collector output via Perihan's /index-folder endpoint."""
    folder_path = str((THELOOP_DIR / "collector" / "output").resolve())

    if not await check_perihan():
        yield {"type": "error", "text": "Perihan server not running at localhost:8000"}
        return

    yield {"type": "log", "text": f"Indexing folder: {folder_path}", "time": datetime.now().strftime("%H:%M:%S")}

    try:
        async with httpx.AsyncClient(timeout=600) as client:
            async with client.stream(
                "POST",
                "http://localhost:8000/index-folder",
                params={"folder_path": folder_path},
            ) as resp:
                buffer = ""
                async for chunk in resp.aiter_text():
                    buffer += chunk
                    while "\n\n" in buffer:
                        part, buffer = buffer.split("\n\n", 1)
                        if part.startswith("data: "):
                            try:
                                event = json.loads(part[6:])
                                # Forward SSE events with cost info
                                text = ""
                                if event.get("type") == "start":
                                    text = f"Found {event['total']} files"
                                elif event.get("type") == "progress":
                                    text = f"[{event.get('done', 0)}/{event.get('total', 0)}] {event.get('file', '')} — {event.get('step', '')}"
                                elif event.get("type") == "file_done":
                                    text = f"Done: {event.get('file', '')}"
                                elif event.get("type") == "skip":
                                    text = f"Skip: {event.get('file', '')} ({event.get('reason', '')})"
                                elif event.get("type") == "file_error":
                                    text = f"Error: {event.get('file', '')} — {event.get('error', '')}"
                                elif event.get("type") == "complete":
                                    text = f"Complete: {event.get('indexed', 0)} indexed"
                                elif event.get("type") == "error":
                                    text = f"Error: {event.get('message', '')}"

                                out = {
                                    "type": event.get("type", "log"),
                                    "text": text,
                                    "time": datetime.now().strftime("%H:%M:%S"),
                                }
                                # Pass through cost info
                                if "total_cost" in event:
                                    out["total_cost"] = event["total_cost"]
                                    out["total_input_tokens"] = event.get("total_input_tokens", 0)
                                    out["total_output_tokens"] = event.get("total_output_tokens", 0)
                                # Pass through counts for complete event
                                if event.get("type") == "complete":
                                    out["indexed"] = event.get("indexed", 0)
                                    out["skipped_unchanged"] = event.get("skipped_unchanged", 0)

                                yield out
                            except json.JSONDecodeError:
                                pass
    except Exception as e:
        yield {"type": "error", "text": f"Index error: {e}"}


# ---------------------------------------------------------------------------
# Step 3: Generate QA
# ---------------------------------------------------------------------------

async def run_generate_qa(strategy: str = "all"):
    """Run the QA generator."""
    cmd = [PYTHON, "runner.py"]
    if strategy != "all":
        cmd.append(strategy)
    async for event in _run_subprocess("generate_qa", cmd, str(THELOOP_DIR / "qa_generator")):
        yield event


# ---------------------------------------------------------------------------
# Step 4: Benchmark
# ---------------------------------------------------------------------------

async def run_benchmark():
    """Run eval_runner benchmark mode."""
    cmd = [PYTHON, "runner.py", "benchmark"]
    async for event in _run_subprocess("benchmark", cmd, str(THELOOP_DIR / "eval_runner")):
        yield event


# ---------------------------------------------------------------------------
# Step 5: Evaluate Perihan
# ---------------------------------------------------------------------------

async def run_perihan_eval():
    """Run eval_runner perihan mode."""
    if not await check_perihan():
        yield {"type": "error", "text": "Perihan server not running at localhost:8000"}
        return

    cmd = [PYTHON, "runner.py", "perihan"]
    async for event in _run_subprocess("perihan", cmd, str(THELOOP_DIR / "eval_runner")):
        yield event


# ---------------------------------------------------------------------------
# Step 6: Report
# ---------------------------------------------------------------------------

async def run_report():
    """Generate the HTML report."""
    cmd = [PYTHON, "report.py"]
    async for event in _run_subprocess("report", cmd, str(THELOOP_DIR / "eval_runner")):
        yield event

    report_path = THELOOP_DIR / "eval_runner" / "output" / "report.html"
    if report_path.exists():
        yield {"type": "report_ready", "path": str(report_path)}


def get_report_html() -> str | None:
    """Return report HTML content if it exists."""
    report_path = THELOOP_DIR / "eval_runner" / "output" / "report.html"
    if report_path.exists():
        return report_path.read_text(encoding="utf-8")
    return None


# ---------------------------------------------------------------------------
# Step 7: Improve (manual)
# ---------------------------------------------------------------------------

# No runner — just status tracking via history.py


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def get_qa_count() -> int:
    """Get current number of generated QA questions."""
    qa_file = THELOOP_DIR / "qa_generator" / "output" / "qa_output.json"
    if not qa_file.exists():
        return 0
    try:
        data = json.loads(qa_file.read_text(encoding="utf-8"))
        return len(data)
    except Exception:
        return 0


def get_collector_file_count() -> int:
    """Get number of files in collector output."""
    manifest = THELOOP_DIR / "collector" / "output" / "manifest.json"
    if not manifest.exists():
        return 0
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        return len(data)
    except Exception:
        return 0


def get_eval_summary() -> dict | None:
    """Get summary from eval_results.json."""
    results_file = THELOOP_DIR / "eval_runner" / "output" / "eval_results.json"
    if not results_file.exists():
        return None
    try:
        results = json.loads(results_file.read_text(encoding="utf-8"))
        b_scores = []
        p_scores = []
        for r in results.values():
            b = r.get("benchmark", {}).get("score")
            p = r.get("perihan", {}).get("score")
            if b is not None:
                b_scores.append(b)
            if p is not None:
                p_scores.append(p)
        return {
            "benchmark_total": sum(b_scores),
            "benchmark_max": len(b_scores) * 2,
            "benchmark_count": len(b_scores),
            "perihan_total": sum(p_scores),
            "perihan_max": len(p_scores) * 2,
            "perihan_count": len(p_scores),
        }
    except Exception:
        return None
