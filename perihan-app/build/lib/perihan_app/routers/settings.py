import os
import httpx
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from perihan_app.config import GEMINI_MODELS, VECTORDB_PATH, DATA_DIR
from perihan_app.dependencies import get_collection, get_gemini_api_key, get_ollama_host, reset_chroma, set_current_model

router = APIRouter()


@router.get("/documents")
async def list_documents():
    """List all indexed documents."""
    collection = get_collection()
    all_docs = collection.get()
    return {
        "count": len(all_docs["ids"]),
        "documents": [
            {"id": id_, "title": meta.get("title", ""), "source": meta.get("source", "local"), "preview": doc[:100]}
            for id_, doc, meta in zip(
                all_docs["ids"], all_docs["documents"], all_docs["metadatas"]
            )
        ],
    }


@router.get("/document/{doc_id}")
async def get_document(doc_id: str):
    """Get full content of a specific indexed document by ID."""
    collection = get_collection()
    result = collection.get(ids=[doc_id], include=["documents", "metadatas"])
    if not result["ids"]:
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found")
    return {
        "id": result["ids"][0],
        "title": result["metadatas"][0].get("title", ""),
        "content": result["documents"][0],
        "metadata": result["metadatas"][0],
    }


@router.get("/folders")
async def list_folders():
    """List all indexed folders and their files."""
    collection = get_collection()
    all_docs = collection.get()
    folders: dict = {}
    for meta in all_docs["metadatas"]:
        folder = meta.get("folder", "unknown")
        if folder not in folders:
            folders[folder] = []
        title = meta.get("title", "")
        if title and title not in folders[folder]:
            folders[folder].append(title)
    return {"folders": folders}


@router.get("/stats")
async def vectordb_stats():
    """Return summary statistics about the vector database."""
    collection = get_collection()
    all_docs = collection.get()
    chunk_count = len(all_docs["ids"])
    unique_files: set = set()
    unique_folders: set = set()
    for meta in all_docs["metadatas"]:
        if meta.get("title"):
            unique_files.add(meta["title"])
        if meta.get("folder"):
            unique_folders.add(meta["folder"])

    # Disk size of vectordb directory
    vectordb_path = Path(VECTORDB_PATH)
    disk_bytes = (
        sum(f.stat().st_size for f in vectordb_path.rglob("*") if f.is_file())
        if vectordb_path.exists()
        else 0
    )

    return {
        "chunks": chunk_count,
        "unique_files": len(unique_files),
        "unique_folders": len(unique_folders),
        "disk_size_kb": round(disk_bytes / 1024, 1),
    }


@router.get("/models")
async def list_models():
    """List all available models: local Ollama installs + Gemini (if API key is set)."""
    models = []

    # Ollama models
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{get_ollama_host()}/api/tags")
            resp.raise_for_status()
            data = resp.json()
        for m in data.get("models", []):
            models.append(
                {
                    "name": m["name"],
                    "provider": "ollama",
                    "size_gb": round(m.get("size", 0) / 1e9, 2),
                }
            )
    except Exception:
        pass  # Ollama not running — skip

    # Gemini models (only listed when API key is configured)
    if get_gemini_api_key():
        for name in GEMINI_MODELS:
            models.append({"name": name, "provider": "gemini", "size_gb": None})

    return {"models": models}


@router.post("/model")
async def set_model(model_name: str):
    """Set the active LLM model (Ollama or Gemini)."""
    if model_name.startswith("gemini-"):
        if not get_gemini_api_key():
            raise HTTPException(
                status_code=400,
                detail="Gemini API key is not configured. Set it in Settings.",
            )
        set_current_model(model_name)
        return {"message": f"Model set to '{model_name}' (Gemini)"}

    # Ollama: validate model is installed
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{get_ollama_host()}/api/tags")
        resp.raise_for_status()
        data = resp.json()
    installed = [m["name"] for m in data.get("models", [])]
    if model_name not in installed:
        raise HTTPException(
            status_code=400,
            detail=f"Model '{model_name}' not found in Ollama. Installed: {installed}",
        )
    set_current_model(model_name)
    return {"message": f"Model set to '{model_name}' (Ollama)"}


@router.post("/reset")
async def reset_vectordb():
    """Delete all indexed documents and reset the vector database."""
    deleted_count = await reset_chroma()
    return {"message": "Vector database reset.", "deleted_documents": deleted_count}


class GeminiKeyValidation(BaseModel):
    gemini_api_key: str


@router.post("/config/validate-gemini")
async def validate_gemini_key(body: GeminiKeyValidation):
    """Test a Gemini API key by listing models."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://generativelanguage.googleapis.com/v1beta/models",
                params={"key": body.gemini_api_key},
                timeout=10,
            )
        if resp.status_code == 200:
            return {"valid": True}
        data = resp.json()
        msg = data.get("error", {}).get("message", f"HTTP {resp.status_code}")
        return {"valid": False, "error": msg}
    except Exception as e:
        return {"valid": False, "error": str(e)}


class ConfigUpdate(BaseModel):
    gemini_api_key: Optional[str] = None
    ollama_host: Optional[str] = None
    setup_complete: Optional[bool] = None


@router.get("/setup-status")
async def setup_status():
    from perihan_app.services.config_service import is_setup_complete
    return {"setup_complete": is_setup_complete()}


@router.get("/config")
async def get_config_endpoint():
    from perihan_app.services.config_service import get_config
    cfg = get_config()
    config_key = cfg.get("gemini_api_key", "")
    env_key = os.environ.get("GEMINI_API_KEY", "")
    if config_key:
        key_source = "config"
    elif env_key:
        key_source = "env"
    else:
        key_source = None
    return {
        "gemini_api_key_set": bool(config_key or env_key),
        "gemini_api_key_source": key_source,
        "ollama_host": cfg.get("ollama_host", "http://localhost:11434"),
        "setup_complete": cfg.get("setup_complete", False),
    }


@router.post("/config")
async def update_config(body: ConfigUpdate):
    from perihan_app.services.config_service import save_config
    patch = {}
    if body.gemini_api_key is not None:
        patch["gemini_api_key"] = body.gemini_api_key
    if body.ollama_host is not None:
        patch["ollama_host"] = body.ollama_host.rstrip("/")
    if body.setup_complete is not None:
        patch["setup_complete"] = body.setup_complete
    save_config(patch)
    return {"ok": True}


@router.delete("/logs")
async def clear_logs():
    """Delete all log entries."""
    log_file = DATA_DIR / "logs" / "chat.jsonl"
    if log_file.exists():
        log_file.write_text("", encoding="utf-8")
    return {"ok": True}


@router.get("/logs")
async def get_logs(limit: int = 100, offset: int = 0):
    """Return log entries from chat.jsonl, newest first."""
    import json
    log_file = DATA_DIR / "logs" / "chat.jsonl"
    if not log_file.exists():
        return {"entries": [], "total": 0}
    lines = log_file.read_text(encoding="utf-8").splitlines()
    entries = []
    for line in reversed(lines):
        line = line.strip()
        if line:
            try:
                entries.append(json.loads(line))
            except Exception:
                pass
    total = len(entries)
    return {"entries": entries[offset: offset + limit], "total": total}
