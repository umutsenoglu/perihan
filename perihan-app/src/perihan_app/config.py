import os
from pathlib import Path

# Re-export all core constants so app code can import from one place
from perihan_core.config import *  # noqa: F401,F403

# App-specific paths — disk layout for persistent state
DATA_DIR = Path(os.environ.get("DATA_DIR", "."))

VECTORDB_PATH = str(DATA_DIR / "vectordb")
MODEL_FILE = DATA_DIR / "model.json"
GOOGLE_CREDENTIALS_FILE = DATA_DIR / "credentials.json"
GOOGLE_TOKEN_FILE = DATA_DIR / "token.json"
