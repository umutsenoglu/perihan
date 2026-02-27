import asyncio
from pathlib import Path

from config import SUPPORTED_EXTENSIONS, CHUNK_SIZE
from utils.file_reader import read_file_content


def generate_file_summary(filename: str, content: str) -> str | None:
    """Ask the LLM to describe a file's content in plain English for search indexing."""
    # Lazy imports to avoid circular deps
    from dependencies import get_llm_client, get_current_model

    try:
        sample = content[:3000]  # keep token cost low
        model = get_current_model()
        response = get_llm_client().chat.completions.create(
            model=model,
            temperature=0.1,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a document analysis assistant. "
                        "Your job is to describe documents so they can be found by search. "
                        "Be thorough with ALL names, entities, categories, and topics — "
                        "even if they seem minor. These keywords are used for search indexing."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Document name: {filename}\n\n"
                        f"Content:\n{sample}\n\n"
                        "Describe what this document contains in 3-5 sentences. "
                        "List ALL people, company names, product names, categories, "
                        "and topics mentioned. Be specific and complete."
                    ),
                },
            ],
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return None


async def index_local_folder(folder_path: str):
    """Index all supported documents from a local folder. Async generator yielding SSE progress events."""
    # Lazy imports to avoid circular deps
    from dependencies import get_collection
    from services.search_service import build_global_vocab

    collection = get_collection()
    base_path = Path(folder_path)
    if not base_path.exists():
        yield {"type": "error", "message": "Folder not found"}
        return

    all_files = [
        f for f in base_path.rglob("*")
        if not f.is_dir() and f.suffix.lower() in SUPPORTED_EXTENSIONS
    ]
    total = len(all_files)
    yield {"type": "start", "total": total}

    indexed = []
    errors = []

    for i, file in enumerate(all_files):
        try:
            content = read_file_content(file)
            if not content or len(content.strip()) < 10:
                yield {"type": "skip", "file": file.name, "reason": "empty", "done": i + 1, "total": total}
                continue

            yield {"type": "progress", "file": file.name, "step": "chunking", "done": i, "total": total}

            relative_path = file.relative_to(base_path)
            folder = (
                str(relative_path.parent)
                if str(relative_path.parent) != "."
                else "root"
            )
            folder_context = f"[Source: {folder}/{file.name}]\n"

            existing = collection.get(where={"full_path": str(file)})
            if existing["ids"]:
                collection.delete(ids=existing["ids"])

            words = content.split()
            chunks = []
            for j in range(0, len(words), CHUNK_SIZE):
                chunk = folder_context + " ".join(words[j : j + CHUNK_SIZE])
                chunks.append(chunk)

            for j, chunk in enumerate(chunks):
                doc_id = f"{relative_path}_{j}"
                collection.upsert(
                    ids=[doc_id],
                    documents=[chunk],
                    metadatas=[
                        {
                            "title": file.name,
                            "folder": folder,
                            "relative_path": str(relative_path),
                            "full_path": str(file),
                            "file_type": file.suffix.lower(),
                            "chunk": j,
                        }
                    ],
                )

            yield {"type": "progress", "file": file.name, "step": "summarizing", "done": i, "total": total}

            summary = await asyncio.to_thread(generate_file_summary, file.name, content)
            if summary:
                summary_text = f"[Summary of {file.name}]\n{summary}"
                collection.upsert(
                    ids=[f"{relative_path}_summary"],
                    documents=[summary_text],
                    metadatas=[
                        {
                            "title": file.name,
                            "folder": folder,
                            "relative_path": str(relative_path),
                            "full_path": str(file),
                            "file_type": file.suffix.lower(),
                            "chunk": -1,
                            "is_summary": "true",
                        }
                    ],
                )

            indexed.append(
                {
                    "file": str(relative_path),
                    "folder": folder,
                    "chunks": len(chunks),
                    "summary": bool(summary),
                }
            )
            yield {"type": "file_done", "file": file.name, "chunks": len(chunks), "done": i + 1, "total": total}

        except Exception as e:
            errors.append({"file": file.name, "error": str(e)})
            yield {"type": "file_error", "file": file.name, "error": str(e), "done": i + 1, "total": total}

    asyncio.create_task(asyncio.to_thread(build_global_vocab))
    yield {"type": "complete", "indexed": len(indexed), "files": indexed, "errors": errors}


async def index_gdrive_files(folder_id: str = "root"):
    """Index all Google Drive files into the local VectorDB (summaries only). Async generator yielding SSE progress events."""
    # Lazy imports to avoid circular deps
    from dependencies import get_collection, get_drive
    from services.search_service import build_global_vocab
    from utils.drive_utils import drive_list_all_files, drive_read_content

    svc = get_drive()
    if not svc:
        yield {"type": "error", "message": "Google Drive not connected. Visit Settings to connect."}
        return

    collection = get_collection()

    yield {"type": "progress", "file": "", "step": "listing files", "done": 0, "total": 0}
    all_files = await asyncio.to_thread(drive_list_all_files, svc, folder_id)
    total = len(all_files)
    yield {"type": "start", "total": total}

    indexed = []
    skipped = []
    errors = []

    for i, f in enumerate(all_files):
        file_id = f["id"]
        name = f["name"]
        mime = f["mimeType"]
        folder_path = f["folder_path"]

        try:
            yield {"type": "progress", "file": name, "step": "reading", "done": i, "total": total}
            content = await asyncio.to_thread(drive_read_content, svc, file_id, name, mime)
            if not content or len(content.strip()) < 10:
                skipped.append({"file": name, "reason": "unsupported or empty"})
                yield {"type": "skip", "file": name, "reason": "unsupported or empty", "done": i + 1, "total": total}
                continue

            existing = collection.get(where={"file_id": file_id})
            if existing["ids"]:
                collection.delete(ids=existing["ids"])

            yield {"type": "progress", "file": name, "step": "summarizing", "done": i, "total": total}
            summary = await asyncio.to_thread(generate_file_summary, name, content)
            if not summary:
                skipped.append({"file": name, "reason": "summary generation failed"})
                yield {"type": "skip", "file": name, "reason": "summary generation failed", "done": i + 1, "total": total}
                continue

            summary_text = f"[Google Drive Summary: {name}]\n{summary}"
            collection.upsert(
                ids=[f"gdrive_{file_id}_summary"],
                documents=[summary_text],
                metadatas=[
                    {
                        "title": name,
                        "file_id": file_id,
                        "source": "gdrive",
                        "mime_type": mime,
                        "folder": folder_path,
                        "is_summary": "true",
                        "chunk": -1,
                    }
                ],
            )
            indexed.append({"file": name, "folder": folder_path, "file_id": file_id})
            yield {"type": "file_done", "file": name, "done": i + 1, "total": total}

        except Exception as e:
            errors.append({"file": name, "error": str(e)})
            yield {"type": "file_error", "file": name, "error": str(e), "done": i + 1, "total": total}

    asyncio.create_task(asyncio.to_thread(build_global_vocab))
    yield {
        "type": "complete",
        "indexed": len(indexed),
        "skipped": len(skipped),
        "files": indexed,
        "skipped_files": skipped,
        "errors": errors,
    }
