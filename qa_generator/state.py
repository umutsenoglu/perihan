"""QA Generator state tracking — survives restarts, prevents duplicate work."""

import json
from pathlib import Path

from config import QA_STATE_FILE, QA_OUTPUT_FILE, QA_OUTPUT_DIR


def _ensure_dir():
    QA_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def load_state() -> dict:
    """Load QA generator state from disk."""
    _ensure_dir()
    if not QA_STATE_FILE.exists():
        return {"package_hashes": {}, "in_progress": None}
    try:
        return json.loads(QA_STATE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"package_hashes": {}, "in_progress": None}


def save_state(state: dict):
    """Save QA generator state to disk."""
    _ensure_dir()
    QA_STATE_FILE.write_text(
        json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def get_done_hashes(state: dict) -> set[str]:
    """Get set of already-completed package hashes."""
    return set(state.get("package_hashes", {}).keys())


def mark_in_progress(state: dict, package_hash: str, package_info: dict):
    """Mark a package as in-progress (before sending to LLM)."""
    state["in_progress"] = {"hash": package_hash, **package_info}
    save_state(state)


def mark_completed(state: dict, package_hash: str, package_info: dict, qa_count: int):
    """Mark a package as completed."""
    from datetime import datetime
    state["package_hashes"][package_hash] = {
        "files": package_info["files"],
        "strategy": package_info["strategy"],
        "storyline": package_info.get("storyline"),
        "category": package_info.get("category"),
        "qa_count": qa_count,
        "completed_at": datetime.now().isoformat(),
    }
    state["in_progress"] = None
    save_state(state)


def load_qa_output() -> list[dict]:
    """Load existing QA output."""
    _ensure_dir()
    if not QA_OUTPUT_FILE.exists():
        return []
    try:
        return json.loads(QA_OUTPUT_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def save_qa_output(qas: list[dict]):
    """Save QA output to disk."""
    _ensure_dir()
    QA_OUTPUT_FILE.write_text(
        json.dumps(qas, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def append_qas(new_qas: list[dict]):
    """Append new QAs to the output file."""
    existing = load_qa_output()
    # Assign IDs
    next_id = len(existing) + 1
    for qa in new_qas:
        qa["id"] = f"Q{next_id:04d}"
        next_id += 1
    existing.extend(new_qas)
    save_qa_output(existing)
    return new_qas
