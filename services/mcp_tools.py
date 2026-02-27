import io
import json
from pathlib import Path

from config import SUPPORTED_EXTENSIONS
from utils.file_reader import read_file_content


# ---------------------------------------------------------------------------
# Local filesystem tools
# ---------------------------------------------------------------------------


def tool_list_files(folder_path: str) -> str:
    """List all supported document files in a folder recursively."""
    base = Path(folder_path)
    if not base.exists():
        return json.dumps({"error": f"Folder not found: {folder_path}"})
    files = []
    for f in base.rglob("*"):
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS:
            files.append({"path": str(f), "name": f.name, "size_bytes": f.stat().st_size})
    return json.dumps({"folder": folder_path, "file_count": len(files), "files": files})


def tool_read_document(file_path: str) -> str:
    """Read the full content of a document file."""
    p = Path(file_path)
    if not p.exists():
        return json.dumps({"error": f"File not found: {file_path}"})
    content = read_file_content(p)
    if content is None:
        return json.dumps({"error": f"Unsupported file type: {p.suffix}"})
    # Truncate very large files to avoid blowing up context
    if len(content) > 10000:
        content = content[:10000] + "\n... [truncated]"
    return json.dumps({"path": file_path, "content": content})


def tool_search_files(folder_path: str, keyword: str) -> str:
    """Search for a keyword in file names and contents within a folder."""
    base = Path(folder_path)
    if not base.exists():
        return json.dumps({"error": f"Folder not found: {folder_path}"})
    keyword_lower = keyword.lower()
    matches = []
    for f in base.rglob("*"):
        if not f.is_file() or f.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        # Check filename match
        name_match = keyword_lower in f.name.lower()
        # Check content match
        content_match = False
        snippet = ""
        try:
            content = read_file_content(f)
            if content:
                idx = content.lower().find(keyword_lower)
                if idx != -1:
                    content_match = True
                    start = max(0, idx - 50)
                    end = min(len(content), idx + len(keyword) + 50)
                    snippet = content[start:end]
        except Exception:
            pass
        if name_match or content_match:
            matches.append(
                {
                    "path": str(f),
                    "name": f.name,
                    "name_match": name_match,
                    "content_match": content_match,
                    "snippet": snippet,
                }
            )
    return json.dumps({"keyword": keyword, "match_count": len(matches), "matches": matches})


# ---------------------------------------------------------------------------
# Vector DB tool
# ---------------------------------------------------------------------------


def tool_search_vectordb(query: str) -> str:
    """Search the vector database for documents relevant to a query."""
    # Lazy import to avoid circular deps
    from services.search_service import hybrid_search

    docs, metas, _ = hybrid_search(query, n_results=4)
    if not docs:
        return json.dumps({"query": query, "results": []})

    # Build search terms for keyword-focused snippets
    terms = set()
    for w in query.split():
        cleaned = w.strip("?.,!\"'():-").lower()
        if len(cleaned) >= 4:
            terms.add(cleaned)

    def focused_snippet(doc: str, max_len: int = 300) -> str:
        doc_lower = doc.lower()
        for term in terms:
            idx = doc_lower.find(term)
            if idx != -1:
                start = max(0, idx - 100)
                end = min(len(doc), idx + max_len)
                snippet = doc[start:end].strip()
                return ("..." if start > 0 else "") + snippet + ("..." if end < len(doc) else "")
        return doc[:max_len]

    seen_keys = set()
    results = []
    for doc, meta in zip(docs, metas):
        source = meta.get("source", "local")
        key = meta.get("file_id", "") if source == "gdrive" else meta.get("full_path", "")
        if key in seen_keys:
            continue
        seen_keys.add(key)
        entry = {
            "title": meta.get("title", ""),
            "source": source,
            "folder": meta.get("folder", ""),
            "snippet": focused_snippet(doc),
        }
        if source == "gdrive":
            entry["file_id"] = meta.get("file_id", "")
        else:
            entry["path"] = meta.get("full_path", "")
        results.append(entry)
    return json.dumps({"query": query, "result_count": len(results), "results": results})


# ---------------------------------------------------------------------------
# Google Drive tools
# ---------------------------------------------------------------------------


def tool_drive_list_files(folder_id: str = "root") -> str:
    """List files in a Google Drive folder."""
    # Lazy import to avoid circular deps
    from dependencies import get_drive

    svc = get_drive()
    if not svc:
        return json.dumps({"error": "Google Drive not connected. Visit /auth/google first."})
    query = f"'{folder_id}' in parents and trashed=false"
    results = svc.files().list(q=query, fields="files(id,name,mimeType,size)").execute()
    return json.dumps({"folder_id": folder_id, "files": results.get("files", [])})


def tool_drive_search_files(keyword: str) -> str:
    """Full-text search across all Google Drive files."""
    # Lazy import to avoid circular deps
    from dependencies import get_drive

    svc = get_drive()
    if not svc:
        return json.dumps({"error": "Google Drive not connected. Visit /auth/google first."})
    query = f"fullText contains '{keyword}' and trashed=false"
    results = svc.files().list(
        q=query, fields="files(id,name,mimeType,size)", pageSize=10
    ).execute()
    return json.dumps({"keyword": keyword, "files": results.get("files", [])})


def tool_drive_read_file(file_id: str) -> str:
    """Read content of a Google Drive file. Auto-exports Docs as text, Sheets as CSV."""
    import io as _io
    from pathlib import Path as _Path

    # Lazy imports to avoid circular deps
    from dependencies import get_drive
    from googleapiclient.http import MediaIoBaseDownload

    svc = get_drive()
    if not svc:
        return json.dumps({"error": "Google Drive not connected. Visit /auth/google first."})
    meta = svc.files().get(fileId=file_id, fields="name,mimeType").execute()
    mime = meta.get("mimeType", "")
    name = meta.get("name", file_id)

    EXPORT_MAP = {
        "application/vnd.google-apps.document": "text/plain",
        "application/vnd.google-apps.spreadsheet": "text/csv",
    }
    try:
        if mime in EXPORT_MAP:
            content_bytes = svc.files().export(fileId=file_id, mimeType=EXPORT_MAP[mime]).execute()
            content = content_bytes.decode("utf-8", errors="ignore")
        else:
            buf = _io.BytesIO()
            downloader = MediaIoBaseDownload(buf, svc.files().get_media(fileId=file_id))
            done = False
            while not done:
                _, done = downloader.next_chunk()
            suffix = _Path(name).suffix.lower()
            tmp = _Path(f"/tmp/{name}")
            tmp.write_bytes(buf.getvalue())
            content = read_file_content(tmp) or ""
            tmp.unlink(missing_ok=True)
        if len(content) > 10000:
            content = content[:10000] + "\n... [truncated]"
        return json.dumps({"file_id": file_id, "name": name, "content": content})
    except Exception as e:
        return json.dumps({"error": str(e), "file_id": file_id})


# ---------------------------------------------------------------------------
# Tool registries
# ---------------------------------------------------------------------------

TOOL_FUNCTIONS: dict = {
    "search_vectordb": tool_search_vectordb,
    "list_files": tool_list_files,
    "read_document": tool_read_document,
    "search_files": tool_search_files,
    "drive_list_files": tool_drive_list_files,
    "drive_search_files": tool_drive_search_files,
    "drive_read_file": tool_drive_read_file,
}

MCP_TOOLS: list = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List all documents (txt, md, pdf, docx) in a folder recursively. Returns file paths and sizes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "folder_path": {"type": "string", "description": "Path to the folder to list"}
                },
                "required": ["folder_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_document",
            "description": "Read the full content of a document file (txt, md, pdf, docx).",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Path to the file to read"}
                },
                "required": ["file_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_vectordb",
            "description": "Search the indexed document database using a natural language query. Returns matching file paths and snippets. Use this first before reading files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language query to search for relevant documents",
                    }
                },
                "required": ["query"],
            },
        },
    },
]

MCP_TOOLS_DRIVE: list = [
    {
        "type": "function",
        "function": {
            "name": "drive_list_files",
            "description": "List files in a Google Drive folder. Returns file IDs, names, MIME types, and sizes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "folder_id": {
                        "type": "string",
                        "description": "Google Drive folder ID (default 'root' for My Drive)",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "drive_search_files",
            "description": "Full-text search across all Google Drive files. Returns up to 10 matching files with IDs and names.",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "Keyword to search for in Drive file contents and names",
                    }
                },
                "required": ["keyword"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "drive_read_file",
            "description": "Read the content of a Google Drive file by its ID. Google Docs are exported as plain text, Sheets as CSV.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_id": {
                        "type": "string",
                        "description": "Google Drive file ID",
                    }
                },
                "required": ["file_id"],
            },
        },
    },
]
