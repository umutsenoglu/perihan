import os
import gc
import json
import shutil
import asyncio
from pathlib import Path

from openai import OpenAI
from fastapi import HTTPException

from config import (
    DEFAULT_MODEL,
    MODEL_FILE,
    VECTORDB_PATH,
    COLLECTION_NAME,
    GEMINI_MODELS,
    GOOGLE_TOKEN_FILE,
    GOOGLE_CREDENTIALS_FILE,
    GOOGLE_SCOPES,
)

# ---------------------------------------------------------------------------
# LLM clients
# ---------------------------------------------------------------------------

def get_ollama_host() -> str:
    from services.config_service import get_config
    return get_config().get("ollama_host", "") or os.environ.get("OLLAMA_HOST", "http://localhost:11434")


def get_gemini_api_key() -> str:
    from services.config_service import get_config
    return get_config().get("gemini_api_key", "") or os.environ.get("GEMINI_API_KEY", "")

# Mutable module-level state for current model
current_model: str = (
    json.loads(MODEL_FILE.read_text()).get("model", DEFAULT_MODEL)
    if MODEL_FILE.exists()
    else DEFAULT_MODEL
)


def get_llm_client() -> OpenAI:
    """Build a fresh client from current config — cheap, no network call at construction."""
    if current_model.startswith("gemini-"):
        api_key = get_gemini_api_key()
        if not api_key:
            raise HTTPException(status_code=400,
                detail="Gemini API key is not configured. Set it in Settings.")
        return OpenAI(base_url="https://generativelanguage.googleapis.com/v1beta/openai/", api_key=api_key)
    return OpenAI(base_url=f"{get_ollama_host()}/v1", api_key="ollama")


def get_current_model() -> str:
    """Return the currently active model name."""
    return current_model


def set_current_model(name: str) -> None:
    """Set the active model and persist to disk."""
    global current_model
    current_model = name
    MODEL_FILE.write_text(json.dumps({"model": name}))


# ---------------------------------------------------------------------------
# ChromaDB
# ---------------------------------------------------------------------------

_chroma_client = None
_collection = None


def _init_chroma():
    """Initialize ChromaDB client and collection."""
    global _chroma_client, _collection
    import chromadb

    _chroma_client = chromadb.PersistentClient(path=VECTORDB_PATH)
    _collection = _chroma_client.get_or_create_collection(COLLECTION_NAME)


def get_collection():
    """Return the ChromaDB collection, initializing if needed."""
    if _collection is None:
        _init_chroma()
    return _collection


def get_chroma():
    """Return the ChromaDB client, initializing if needed."""
    if _chroma_client is None:
        _init_chroma()
    return _chroma_client


async def reset_chroma() -> int:
    """Delete all documents, wipe the vectordb directory, and reinitialize.

    Returns the count of deleted documents.
    """
    global _chroma_client, _collection

    collection = get_collection()
    existing = collection.get()
    deleted_count = len(existing["ids"])

    # Delete all documents directly from the collection first
    if existing["ids"]:
        collection.delete(ids=existing["ids"])

    # Release all references so CPython closes the SQLite file handles
    _collection = None
    _chroma_client = None
    gc.collect()
    await asyncio.sleep(0.5)  # give OS time to release file locks on Windows

    # Wipe the entire directory — retry with increasing delays for Windows file locks
    for delay in (0, 1, 2, 3):
        await asyncio.sleep(delay)
        try:
            shutil.rmtree(VECTORDB_PATH)
            break
        except Exception:
            continue

    # Reinitialize fresh
    _init_chroma()
    return deleted_count


# ---------------------------------------------------------------------------
# Google Drive
# ---------------------------------------------------------------------------

_drive_service = None
_gmail_service = None


def load_drive_service():
    """Load/refresh Drive credentials and return API service, or None if not configured."""
    global _drive_service
    if not GOOGLE_TOKEN_FILE.exists():
        return None
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    creds = Credentials.from_authorized_user_file(str(GOOGLE_TOKEN_FILE), GOOGLE_SCOPES)
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            GOOGLE_TOKEN_FILE.write_text(creds.to_json())
        except Exception:
            _drive_service = None
            return None
    _drive_service = build("drive", "v3", credentials=creds)
    return _drive_service


def get_drive():
    """Return cached Drive service, refreshing if needed."""
    return load_drive_service()


def load_gmail_service():
    """Load/refresh Gmail credentials and return API service, or None if not configured."""
    global _gmail_service
    if not GOOGLE_TOKEN_FILE.exists():
        return None
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    creds = Credentials.from_authorized_user_file(str(GOOGLE_TOKEN_FILE), GOOGLE_SCOPES)
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            GOOGLE_TOKEN_FILE.write_text(creds.to_json())
        except Exception:
            _gmail_service = None
            return None
    # Check that the token actually has gmail scope
    if not creds.scopes or "https://www.googleapis.com/auth/gmail.readonly" not in creds.scopes:
        _gmail_service = None
        return None
    _gmail_service = build("gmail", "v1", credentials=creds)
    return _gmail_service


def get_gmail():
    """Return cached Gmail service, refreshing if needed."""
    return load_gmail_service()


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------


async def init_startup() -> None:
    """Initialize shared state on application startup."""
    # Init chroma eagerly (it's fast and needed immediately)
    _init_chroma()

    # Build vocab and warm up Drive in background threads to avoid blocking startup
    import asyncio as _asyncio

    def _build_vocab():
        # Lazy import to avoid circular deps
        from services.search_service import build_global_vocab
        build_global_vocab()

    _asyncio.create_task(_asyncio.to_thread(_build_vocab))
    _asyncio.create_task(_asyncio.to_thread(load_drive_service))
