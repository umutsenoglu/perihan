import asyncio
from pathlib import Path

from perihan_core.config import SUPPORTED_EXTENSIONS, CHUNK_SIZE
from perihan_core.utils.file_reader import read_file_content


def generate_file_summary(filename: str, content: str, *, llm_client=None, model=None) -> str | None:
    """Ask the LLM to describe a file's content in plain English for search indexing."""
    if llm_client is None or model is None:
        raise ValueError("llm_client and model are required")

    try:
        sample = content[:6000]
        response = llm_client.chat.completions.create(
            model=model,
            temperature=0.1,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a search indexing assistant. "
                        "Your job is to extract and preserve every specific detail from a document "
                        "so it can be found later by any related search query. "
                        "Specific facts, names, and places are more valuable than general descriptions."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Document name: {filename}\n\n"
                        f"Content:\n{sample}\n\n"
                        "Create a search-optimized summary. Include ALL of the following:\n"
                        "1. A 2-3 sentence description of what this document is about\n"
                        "2. Every person's name mentioned, with their role or relationship if stated\n"
                        "3. Every specific place, city, country, or location mentioned\n"
                        "4. Every date, year, or time period mentioned\n"
                        "5. Every key fact, event, or specific detail a user might search for\n"
                        "6. Every company, organization, or product name\n"
                        "7. Topics and categories\n\n"
                        "Be exhaustive — include every specific detail, even minor ones. "
                        "A user might search for any fact in this document."
                    ),
                },
            ],
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return None


async def index_local_folder(folder_path: str, *, collection=None, llm_client=None, model=None):
    """Index all supported documents from a local folder. Async generator yielding SSE progress events."""
    from perihan_core.services.search_service import build_global_vocab

    if collection is None:
        raise ValueError("collection is required")
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
    skipped_unchanged = 0
    skipped_empty = []
    errors = []

    for i, file in enumerate(all_files):
        try:
            current_mtime = file.stat().st_mtime

            # Skip unchanged files — compare stored mtime with current
            existing = collection.get(where={"full_path": str(file)})
            if existing["ids"] and existing["metadatas"]:
                stored_mtime = existing["metadatas"][0].get("modified_at")
                if stored_mtime is not None and float(stored_mtime) == current_mtime:
                    skipped_unchanged += 1
                    yield {"type": "skip", "file": file.name, "reason": "unchanged", "done": i + 1, "total": total}
                    continue

            content = read_file_content(file)
            if not content or len(content.strip()) < 10:
                relative = file.relative_to(base_path)
                skipped_empty.append({"file": str(relative), "name": file.name})
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
                            "modified_at": current_mtime,
                        }
                    ],
                )

            yield {"type": "progress", "file": file.name, "step": "summarizing", "done": i, "total": total}

            summary = await asyncio.to_thread(generate_file_summary, file.name, content, llm_client=llm_client, model=model)
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
                            "modified_at": current_mtime,
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

    asyncio.create_task(asyncio.to_thread(build_global_vocab, collection))
    yield {"type": "complete", "indexed": len(indexed), "skipped_unchanged": skipped_unchanged, "skipped_empty": len(skipped_empty), "skipped_empty_files": skipped_empty, "files": indexed, "errors": errors}


async def index_gdrive_files(folder_id: str = "root", *, collection=None, drive_svc=None, llm_client=None, model=None):
    """Index all Google Drive files into the local VectorDB (summaries only). Async generator yielding SSE progress events."""
    from perihan_core.services.search_service import build_global_vocab
    from perihan_core.utils.drive_utils import drive_list_all_files, drive_read_content

    if drive_svc is None or not drive_svc:
        yield {"type": "error", "message": "Google Drive not connected. Visit Settings to connect."}
        return

    if collection is None:
        raise ValueError("collection is required")

    yield {"type": "progress", "file": "", "step": "listing files", "done": 0, "total": 0}
    all_files = await asyncio.to_thread(drive_list_all_files, drive_svc, folder_id)
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
            content = await asyncio.to_thread(drive_read_content, drive_svc, file_id, name, mime)
            if not content or len(content.strip()) < 10:
                skipped.append({"file": name, "reason": "unsupported or empty"})
                yield {"type": "skip", "file": name, "reason": "unsupported or empty", "done": i + 1, "total": total}
                continue

            existing = collection.get(where={"file_id": file_id})
            if existing["ids"]:
                collection.delete(ids=existing["ids"])

            yield {"type": "progress", "file": name, "step": "summarizing", "done": i, "total": total}
            summary = await asyncio.to_thread(generate_file_summary, name, content, llm_client=llm_client, model=model)
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

    asyncio.create_task(asyncio.to_thread(build_global_vocab, collection))
    yield {
        "type": "complete",
        "indexed": len(indexed),
        "skipped": len(skipped),
        "files": indexed,
        "skipped_files": skipped,
        "errors": errors,
    }


async def index_gmail_threads(max_threads: int = 500, *, collection=None, gmail_svc=None, raw_dir=None):
    """Index Gmail threads into ChromaDB (raw text chunks, no LLM). Async generator yielding SSE progress events."""
    from perihan_core.services.search_service import build_global_vocab
    from perihan_core.utils.gmail_utils import gmail_list_all_threads, gmail_get_thread, gmail_format_thread_text

    if gmail_svc is None or not gmail_svc:
        yield {"type": "error", "message": "Gmail not connected. Re-authenticate in Settings to grant Gmail access."}
        return

    if collection is None:
        raise ValueError("collection is required")

    if raw_dir is not None:
        raw_dir = Path(raw_dir)
        raw_dir.mkdir(parents=True, exist_ok=True)

    # Delete existing gmail chunks before re-indexing
    try:
        existing = collection.get(where={"source": "gmail"})
        if existing["ids"]:
            collection.delete(ids=existing["ids"])
    except Exception:
        pass

    yield {"type": "progress", "file": "", "step": "listing threads", "done": 0, "total": 0}
    all_threads = await asyncio.to_thread(gmail_list_all_threads, gmail_svc, max_threads)
    total = len(all_threads)
    yield {"type": "start", "total": total}

    indexed = []
    skipped = []
    errors = []

    for i, t in enumerate(all_threads):
        thread_id = t["id"]
        try:
            yield {"type": "progress", "file": t.get("snippet", "")[:60], "step": "reading", "done": i, "total": total}
            thread_data = await asyncio.to_thread(gmail_get_thread, gmail_svc, thread_id)
            subject = thread_data.get("subject", "(no subject)")
            text = gmail_format_thread_text(thread_data)

            if len(text.strip()) < 20:
                skipped.append({"file": subject, "reason": "empty thread"})
                yield {"type": "skip", "file": subject, "reason": "empty thread", "done": i + 1, "total": total}
                continue

            # Save raw file for development/debugging
            if raw_dir is not None:
                safe_subject = "".join(c if c.isascii() and c not in ' /\\:*?"<>|' else "_" for c in subject)[:80]
                raw_file = raw_dir / f"{thread_id}_{safe_subject}.txt"
                raw_file.write_text(text, encoding="utf-8")

            # Store raw text chunks directly (no LLM summary)
            folder_context = f"[Gmail: {subject}]\n"
            words = text.split()
            chunks = []
            for j in range(0, len(words), CHUNK_SIZE):
                chunk = folder_context + " ".join(words[j : j + CHUNK_SIZE])
                chunks.append(chunk)

            for j, chunk in enumerate(chunks):
                doc_id = f"gmail_{thread_id}_{j}"
                collection.upsert(
                    ids=[doc_id],
                    documents=[chunk],
                    metadatas=[{
                        "title": subject,
                        "thread_id": thread_id,
                        "source": "gmail",
                        "folder": "gmail",
                        "chunk": j,
                    }],
                )

            indexed.append({"file": subject, "thread_id": thread_id, "chunks": len(chunks)})
            yield {"type": "file_done", "file": subject[:60], "chunks": len(chunks), "done": i + 1, "total": total}

        except Exception as e:
            errors.append({"file": t.get("snippet", "")[:60], "error": str(e)})
            yield {"type": "file_error", "file": t.get("snippet", "")[:60], "error": str(e), "done": i + 1, "total": total}

    asyncio.create_task(asyncio.to_thread(build_global_vocab, collection))
    yield {
        "type": "complete",
        "indexed": len(indexed),
        "skipped": len(skipped),
        "files": indexed,
        "skipped_files": skipped,
        "errors": errors,
    }
