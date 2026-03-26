"""Run history — stores and retrieves loop run data.

Benchmark steps (collect, generate_qa, benchmark) are standalone — no run tracking.
Improve cycles (index, perihan, report, improve) are tracked as numbered runs.
"""

import json
from datetime import datetime
from pathlib import Path

HISTORY_DIR = Path(__file__).parent.parent.parent / "history"
RUNS_FILE = HISTORY_DIR / "runs.json"
BENCHMARK_FILE = HISTORY_DIR / "benchmark.json"

IMPROVE_STEPS = ["index", "perihan", "report", "improve"]


def _ensure():
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    if not RUNS_FILE.exists():
        RUNS_FILE.write_text("[]", encoding="utf-8")


# ---------------------------------------------------------------------------
# Benchmark state (standalone, no run tracking)
# ---------------------------------------------------------------------------

def load_benchmark() -> dict:
    """Load benchmark step states."""
    _ensure()
    if not BENCHMARK_FILE.exists():
        return {
            "collect": {"status": "pending"},
            "generate_qa": {"status": "pending"},
            "benchmark": {"status": "pending"},
            "total_cost": 0.0,
        }
    try:
        return json.loads(BENCHMARK_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {
            "collect": {"status": "pending"},
            "generate_qa": {"status": "pending"},
            "benchmark": {"status": "pending"},
            "total_cost": 0.0,
        }


def save_benchmark(data: dict):
    _ensure()
    BENCHMARK_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def update_benchmark_step(step: str, data: dict):
    """Update a benchmark step."""
    bench = load_benchmark()
    if step not in bench:
        bench[step] = {}
    bench[step].update(data)
    bench["total_cost"] = round(sum(
        bench[s].get("cost", 0) for s in ["collect", "generate_qa", "benchmark"]
        if isinstance(bench.get(s), dict)
    ), 4)
    save_benchmark(bench)


# ---------------------------------------------------------------------------
# Improve cycles (tracked runs)
# ---------------------------------------------------------------------------

def load_runs() -> list[dict]:
    _ensure()
    try:
        return json.loads(RUNS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def save_runs(runs: list[dict]):
    _ensure()
    RUNS_FILE.write_text(json.dumps(runs, ensure_ascii=False, indent=2), encoding="utf-8")


def create_run() -> dict:
    """Create a new improve cycle and return it."""
    runs = load_runs()
    run_id = max((r["id"] for r in runs), default=0) + 1
    run = {
        "id": run_id,
        "started": datetime.now().isoformat(),
        "completed": None,
        "steps": {s: {"status": "pending"} for s in IMPROVE_STEPS},
        "total_cost": 0.0,
    }
    runs.append(run)
    save_runs(runs)
    return run


def update_step(run_id: int, step: str, data: dict):
    """Update a step in an improve cycle."""
    runs = load_runs()
    for run in runs:
        if run["id"] == run_id:
            run["steps"][step].update(data)
            run["total_cost"] = round(sum(
                s.get("cost", 0) for s in run["steps"].values()
            ), 4)
            if all(s.get("status") in ("done", "skipped") for s in run["steps"].values()):
                run["completed"] = datetime.now().isoformat()
            break
    save_runs(runs)


def get_run(run_id: int) -> dict | None:
    for run in load_runs():
        if run["id"] == run_id:
            return run
    return None


def get_current_run() -> dict | None:
    """Get the latest incomplete improve cycle, or None."""
    runs = load_runs()
    for run in reversed(runs):
        if run.get("completed") is None:
            return run
    return None
