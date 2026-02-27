import json
from pathlib import Path
from config import DATA_DIR, MODEL_FILE

CONFIG_FILE: Path = DATA_DIR / "perihan_config.json"

_DEFAULTS = {
    "gemini_api_key": "",
    "ollama_host": "http://localhost:11434",
    "setup_complete": False,
}


def get_config() -> dict:
    """Read perihan_config.json, falling back to defaults for missing keys.
    Migration: if file missing but model.json exists → existing user, skip wizard."""
    if not CONFIG_FILE.exists():
        if MODEL_FILE.exists():
            migrated = dict(_DEFAULTS) | {"setup_complete": True}
            CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            CONFIG_FILE.write_text(json.dumps(migrated, indent=2), encoding="utf-8")
            return migrated
        return dict(_DEFAULTS)
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return dict(_DEFAULTS)
    return dict(_DEFAULTS) | data


def save_config(data: dict) -> None:
    """Merge data into existing config and persist."""
    current = dict(_DEFAULTS) | (json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                                  if CONFIG_FILE.exists() else {})
    current.update(data)
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(current, indent=2, ensure_ascii=False), encoding="utf-8")


def is_setup_complete() -> bool:
    return get_config().get("setup_complete", False)
