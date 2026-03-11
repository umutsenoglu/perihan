import json
from datetime import datetime
from perihan_app.config import DATA_DIR

LOG_FILE = DATA_DIR / "logs" / "chat.jsonl"


def append_log(entry: dict) -> None:
    """Append one JSON log entry to chat.jsonl. Creates the file/dirs if needed."""
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    entry.setdefault("timestamp", datetime.now().isoformat())
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
