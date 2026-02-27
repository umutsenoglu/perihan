import os
from pathlib import Path

SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf", ".docx", ".xml"}
COLLECTION_NAME = "perihan_docs"
DEFAULT_MODEL = "glm-4.7-flash"
GOOGLE_SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
GEMINI_MODELS = ["gemini-2.5-flash", "gemini-2.0-flash"]
CHUNK_SIZE = 500

# DATA_DIR allows all persistent state to live in a single mountable directory.
# Defaults to "." for local dev; set to "/app/data" inside Docker.
DATA_DIR = Path(os.environ.get("DATA_DIR", "."))

VECTORDB_PATH = str(DATA_DIR / "vectordb")
MODEL_FILE = DATA_DIR / "model.json"
GOOGLE_CREDENTIALS_FILE = DATA_DIR / "credentials.json"
GOOGLE_TOKEN_FILE = DATA_DIR / "token.json"
