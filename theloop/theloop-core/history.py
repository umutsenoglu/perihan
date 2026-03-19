"""Run history — stores and retrieves loop run data."""

import json
from datetime import datetime
from pathlib import Path

HISTORY_DIR = Path(__file__).parent.parent / "history"
RUNS_FILE = HISTORY_DIR / "runs.json"


def _ensure():
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    if not RUNS_FILE.exists():
        RUNS_FILE.write_text("[]", encoding="utf-8")


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
    """Create a new loop run and return it."""
    runs = load_runs()
    run_id = max((r["id"] for r in runs), default=0) + 1
    run = {
        "id": run_id,
        "started": datetime.now().isoformat(),
        "completed": None,
        "steps": {
            "collect": {"status": "pending"},
            "index": {"status": "pending"},
            "generate_qa": {"status": "pending"},
            "benchmark": {"status": "pending"},
            "perihan": {"status": "pending"},
            "report": {"status": "pending"},
            "improve": {"status": "pending"},
        },
        "total_cost": 0.0,
    }
    runs.append(run)
    save_runs(runs)
    return run


def update_step(run_id: int, step: str, data: dict):
    """Update a step in a run."""
    runs = load_runs()
    for run in runs:
        if run["id"] == run_id:
            run["steps"][step].update(data)
            # Recalculate total cost
            run["total_cost"] = round(sum(
                s.get("cost", 0) for s in run["steps"].values()
            ), 4)
            # Check if all steps are done
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
    """Get the latest incomplete run, or None."""
    runs = load_runs()
    for run in reversed(runs):
        if run.get("completed") is None:
            return run
    return None
