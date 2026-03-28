import asyncio
from pathlib import Path

from perihan_core.config import SUPPORTED_EXTENSIONS, CHUNK_SIZE
from perihan_core.utils.file_reader import read_file_content


# Gemini pricing per million tokens: (input, output)
_GEMINI_PRICING = {
    "gemini-3.0-flash": (0.50, 3.00),
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-2.0-flash": (0.15, 0.60),
}
_DEFAULT_GEMINI_PRICE = (0.50, 3.00)  # fallback for unknown gemini models


def _calc_llm_cost(usage, model: str = "") -> dict:
    """Extract token counts and cost from an OpenAI-compatible usage object.
    Cost is only calculated for Gemini models; local models report $0."""
    if usage is None:
        return {"input_tokens": 0, "output_tokens": 0, "thinking_tokens": 0, "cost": 0.0}

    input_tokens = getattr(usage, "prompt_tokens", 0) or 0
    output_tokens = getattr(usage, "completion_tokens", 0) or 0

    # Check for thinking tokens in completion_tokens_details
    thinking_tokens = 0
    details = getattr(usage, "completion_tokens_details", None)
    if details:
        thinking_tokens = getattr(details, "reasoning_tokens", 0) or 0

    is_cloud = model.startswith("gemini-") if model else False
    cost = 0.0
    if is_cloud:
        price_in, price_out = _GEMINI_PRICING.get(model, _DEFAULT_GEMINI_PRICE)
        cost = (input_tokens * price_in / 1_000_000
                + (output_tokens + thinking_tokens) * price_out / 1_000_000)

    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "thinking_tokens": thinking_tokens,
        "cost": round(cost, 6),
    }


def generate_file_summary(filename: str, content: str, *, llm_client=None, model=None) -> tuple[str | None, dict]:
    """Ask the LLM to describe a file's content in plain English for search indexing.
    Returns (summary_text, cost_info)."""
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
        cost_info = _calc_llm_cost(getattr(response, "usage", None), model=model)
        return response.choices[0].message.content.strip(), cost_info
    except Exception:
        return None, {"input_tokens": 0, "output_tokens": 0, "thinking_tokens": 0, "cost": 0.0}


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
    done_count = 0
    total_cost = 0.0
    total_input_tokens = 0
    total_output_tokens = 0

    # Queue for events produced by background summary tasks
    event_queue = asyncio.Queue()
    running_summaries = set()
    MAX_CONCURRENT_SUMMARIES = 5

    async def _summarize_and_enqueue(file, content, relative_path, folder, num_chunks, current_mtime, task_id):
        """Run LLM summary in background and push result events to the queue."""
        try:
            summary, cost_info = await asyncio.to_thread(
                generate_file_summary, file.name, content,
                llm_client=llm_client, model=model
            )
            if summary:
                summary_text = f"[Summary of {file.name}]\n{summary}"
                await asyncio.to_thread(
                    collection.upsert,
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
                            "source": "local",
                        }
                    ],
                )
            await event_queue.put({
                "event": {"type": "file_done", "file": file.name, "chunks": num_chunks},
                "indexed": {"file": str(relative_path), "folder": folder, "chunks": num_chunks, "summary": bool(summary)},
                "cost_info": cost_info,
                "task_id": task_id,
            })
        except Exception as e:
            await event_queue.put({
                "event": {"type": "file_error", "file": file.name, "error": str(e)},
                "error": {"file": file.name, "error": str(e)},
                "task_id": task_id,
            })

    def _accumulate_cost(item):
        """Add cost from a completed item to running totals."""
        nonlocal total_cost, total_input_tokens, total_output_tokens
        ci = item.get("cost_info")
        if ci:
            total_cost += ci.get("cost", 0)
            total_input_tokens += ci.get("input_tokens", 0)
            total_output_tokens += ci.get("output_tokens", 0)

    def _add_cost_to_event(ev):
        """Attach current cost totals to an event dict."""
        ev["total_cost"] = round(total_cost, 4)
        ev["total_input_tokens"] = total_input_tokens
        ev["total_output_tokens"] = total_output_tokens

    async def _drain_completed():
        """Drain all completed summary events from the queue."""
        nonlocal done_count
        events = []
        while not event_queue.empty():
            item = event_queue.get_nowait()
            running_summaries.discard(item["task_id"])
            done_count += 1
            _accumulate_cost(item)
            ev = item["event"]
            ev["done"] = done_count
            ev["total"] = total
            _add_cost_to_event(ev)
            events.append(item)
        return events

    async def _wait_for_slot():
        """Wait until a summary slot opens up, yielding completed events."""
        nonlocal done_count
        while len(running_summaries) >= MAX_CONCURRENT_SUMMARIES:
            item = await event_queue.get()
            running_summaries.discard(item["task_id"])
            done_count += 1
            _accumulate_cost(item)
            ev = item["event"]
            ev["done"] = done_count
            ev["total"] = total
            _add_cost_to_event(ev)
            yield item

    task_counter = 0

    for i, file in enumerate(all_files):
        # Drain any completed summaries before processing next file
        for item in await _drain_completed():
            if "indexed" in item:
                indexed.append(item["indexed"])
            if "error" in item:
                errors.append(item["error"])
            yield item["event"]

        try:
            current_mtime = file.stat().st_mtime

            # Skip unchanged files (also skip if already indexed but no mtime stored — old data)
            existing = await asyncio.to_thread(collection.get, where={"full_path": str(file)})
            if existing["ids"] and existing["metadatas"]:
                stored_mtime = existing["metadatas"][0].get("modified_at")
                if stored_mtime is None or abs(float(stored_mtime) - current_mtime) < 1:
                    skipped_unchanged += 1
                    yield {"type": "skip", "file": file.name, "reason": "unchanged", "done": done_count, "total": total}
                    continue

            content = await asyncio.to_thread(read_file_content, file)
            if not content or len(content.strip()) < 10:
                relative = file.relative_to(base_path)
                skipped_empty.append({"file": str(relative), "name": file.name})
                # Store a marker so we skip this file on next run
                await asyncio.to_thread(
                    collection.upsert,
                    ids=[f"{relative}_empty"],
                    documents=["[empty file]"],
                    metadatas=[{
                        "title": file.name,
                        "full_path": str(file),
                        "file_type": file.suffix.lower(),
                        "modified_at": current_mtime,
                        "is_empty": "true",
                        "source": "local",
                    }],
                )
                yield {"type": "skip", "file": file.name, "reason": "empty", "done": done_count, "total": total}
                continue

            yield {"type": "progress", "file": file.name, "step": "chunking", "done": done_count, "total": total}

            relative_path = file.relative_to(base_path)
            folder = (
                str(relative_path.parent)
                if str(relative_path.parent) != "."
                else "root"
            )
            folder_context = f"[Source: {folder}/{file.name}]\n"

            if existing["ids"]:
                await asyncio.to_thread(collection.delete, ids=existing["ids"])

            words = content.split()
            chunks = []
            for j in range(0, len(words), CHUNK_SIZE):
                chunk = folder_context + " ".join(words[j : j + CHUNK_SIZE])
                chunks.append(chunk)

            for j, chunk in enumerate(chunks):
                doc_id = f"{relative_path}_{j}"
                await asyncio.to_thread(
                    collection.upsert,
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
                            "source": "local",
                        }
                    ],
                )

            # Wait for a slot if all summary slots are busy
            async for item in _wait_for_slot():
                if "indexed" in item:
                    indexed.append(item["indexed"])
                if "error" in item:
                    errors.append(item["error"])
                yield item["event"]

            # Fire off LLM summary in background
            task_counter += 1
            tid = task_counter
            running_summaries.add(tid)
            yield {"type": "progress", "file": file.name, "step": "summarizing", "done": done_count, "total": total}
            asyncio.create_task(_summarize_and_enqueue(
                file, content, relative_path, folder, len(chunks), current_mtime, tid
            ))

        except Exception as e:
            errors.append({"file": file.name, "error": str(e)})
            yield {"type": "file_error", "file": file.name, "error": str(e), "done": done_count, "total": total}

    # Wait for all remaining summaries to finish
    while running_summaries:
        item = await event_queue.get()
        running_summaries.discard(item["task_id"])
        done_count += 1
        _accumulate_cost(item)
        ev = item["event"]
        ev["done"] = done_count
        ev["total"] = total
        _add_cost_to_event(ev)
        if "indexed" in item:
            indexed.append(item["indexed"])
        if "error" in item:
            errors.append(item["error"])
        yield ev

    asyncio.create_task(asyncio.to_thread(build_global_vocab, collection))
    yield {"type": "complete", "indexed": len(indexed), "skipped_unchanged": skipped_unchanged, "skipped_empty": len(skipped_empty), "skipped_empty_files": skipped_empty, "files": indexed, "errors": errors, "total_cost": round(total_cost, 4), "total_input_tokens": total_input_tokens, "total_output_tokens": total_output_tokens}


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
    skipped_existing = 0
    errors = []
    total_cost = 0.0
    total_input_tokens = 0
    total_output_tokens = 0

    # Concurrent processing queue
    event_queue = asyncio.Queue()
    running_tasks = set()
    MAX_CONCURRENT = 5
    done_count = 0

    async def _process_file(f, task_id):
        """Read + summarize + upsert a single Drive file in background."""
        file_id = f["id"]
        name = f["name"]
        mime = f["mimeType"]
        folder_path = f["folder_path"]
        try:
            # Skip files already indexed (resume support)
            existing = await asyncio.to_thread(collection.get, where={"file_id": file_id})
            if existing["ids"]:
                await event_queue.put({"type": "skip_existing", "file": name, "task_id": task_id})
                return

            content = await asyncio.to_thread(drive_read_content, drive_svc, file_id, name, mime)
            if not content or len(content.strip()) < 10:
                await event_queue.put({"type": "skip_empty", "file": name, "task_id": task_id})
                return

            summary, cost_info = await asyncio.to_thread(
                generate_file_summary, name, content, llm_client=llm_client, model=model
            )

            if not summary:
                await event_queue.put({"type": "skip_no_summary", "file": name, "task_id": task_id})
                return

            summary_text = f"[Google Drive Summary: {name}]\n{summary}"
            await asyncio.to_thread(
                collection.upsert,
                ids=[f"gdrive_{file_id}_summary"],
                documents=[summary_text],
                metadatas=[{
                    "title": name,
                    "file_id": file_id,
                    "source": "gdrive",
                    "mime_type": mime,
                    "folder": folder_path,
                    "is_summary": "true",
                    "chunk": -1,
                }],
            )
            await event_queue.put({
                "type": "done", "file": name, "folder": folder_path, "file_id": file_id,
                "cost_info": cost_info, "task_id": task_id,
            })
        except Exception as e:
            await event_queue.put({"type": "error", "file": name, "error": str(e), "task_id": task_id})

    async def _drain_completed():
        """Drain all completed events from the queue."""
        nonlocal done_count, total_cost, total_input_tokens, total_output_tokens, skipped_existing
        events = []
        while not event_queue.empty():
            item = event_queue.get_nowait()
            running_tasks.discard(item["task_id"])
            done_count += 1
            events.append(item)
        return events

    def _handle_item(item):
        """Process a queue item and return an SSE event."""
        nonlocal total_cost, total_input_tokens, total_output_tokens, skipped_existing
        name = item.get("file", "")
        if item["type"] == "skip_existing":
            skipped_existing += 1
            return {"type": "skip", "file": name, "reason": "already indexed", "done": done_count, "total": total}
        elif item["type"] == "skip_empty":
            skipped.append({"file": name, "reason": "unsupported or empty"})
            return {"type": "skip", "file": name, "reason": "unsupported or empty", "done": done_count, "total": total}
        elif item["type"] == "skip_no_summary":
            skipped.append({"file": name, "reason": "summary generation failed"})
            return {"type": "skip", "file": name, "reason": "summary generation failed", "done": done_count, "total": total}
        elif item["type"] == "done":
            ci = item.get("cost_info", {})
            total_cost += ci.get("cost", 0)
            total_input_tokens += ci.get("input_tokens", 0)
            total_output_tokens += ci.get("output_tokens", 0)
            indexed.append({"file": name, "folder": item["folder"], "file_id": item["file_id"]})
            return {"type": "file_done", "file": name, "done": done_count, "total": total,
                    "total_cost": round(total_cost, 4), "total_input_tokens": total_input_tokens, "total_output_tokens": total_output_tokens}
        elif item["type"] == "error":
            errors.append({"file": name, "error": item["error"]})
            return {"type": "file_error", "file": name, "error": item["error"], "done": done_count, "total": total}

    task_counter = 0

    for f in all_files:
        # Drain completed tasks
        for item in await _drain_completed():
            ev = _handle_item(item)
            if ev:
                yield ev

        # Wait for a slot if all slots are busy
        while len(running_tasks) >= MAX_CONCURRENT:
            item = await event_queue.get()
            running_tasks.discard(item["task_id"])
            done_count += 1
            ev = _handle_item(item)
            if ev:
                yield ev

        # Launch file processing in background
        task_counter += 1
        tid = task_counter
        running_tasks.add(tid)
        yield {"type": "progress", "file": f["name"], "step": "queued", "done": done_count, "total": total}
        asyncio.create_task(_process_file(f, tid))

    # Wait for all remaining tasks
    while running_tasks:
        item = await event_queue.get()
        running_tasks.discard(item["task_id"])
        done_count += 1
        ev = _handle_item(item)
        if ev:
            yield ev

    asyncio.create_task(asyncio.to_thread(build_global_vocab, collection))
    yield {
        "type": "complete",
        "indexed": len(indexed),
        "skipped_existing": skipped_existing,
        "skipped": len(skipped),
        "files": indexed,
        "skipped_files": skipped,
        "errors": errors,
        "total_cost": round(total_cost, 4),
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
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
        existing = await asyncio.to_thread(collection.get, where={"source": "gmail"})
        if existing["ids"]:
            await asyncio.to_thread(collection.delete, ids=existing["ids"])
    except Exception:
        pass

    yield {"type": "progress", "file": "", "step": "listing threads", "done": 0, "total": 0}
    all_threads = await asyncio.to_thread(gmail_list_all_threads, gmail_svc, max_threads)
    total = len(all_threads)
    yield {"type": "start", "total": total}

    indexed = []
    skipped = []
    errors = []

    event_queue = asyncio.Queue()
    running_tasks = set()
    MAX_CONCURRENT = 10  # Gmail has no LLM calls, can go higher
    done_count = 0

    async def _process_thread(t, task_id):
        thread_id = t["id"]
        try:
            thread_data = await asyncio.to_thread(gmail_get_thread, gmail_svc, thread_id)
            subject = thread_data.get("subject", "(no subject)")
            text = gmail_format_thread_text(thread_data)

            if len(text.strip()) < 20:
                await event_queue.put({"type": "skip", "file": subject, "reason": "empty thread", "task_id": task_id})
                return

            # Save raw file for development/debugging
            if raw_dir is not None:
                safe_subject = "".join(c if c.isascii() and c not in ' /\\:*?"<>|' else "_" for c in subject)[:80]
                raw_file = raw_dir / f"{thread_id}_{safe_subject}.txt"
                await asyncio.to_thread(raw_file.write_text, text, encoding="utf-8")

            # Store raw text chunks directly (no LLM summary)
            folder_context = f"[Gmail: {subject}]\n"
            words = text.split()
            chunks = []
            for j in range(0, len(words), CHUNK_SIZE):
                chunk = folder_context + " ".join(words[j : j + CHUNK_SIZE])
                chunks.append(chunk)

            for j, chunk in enumerate(chunks):
                doc_id = f"gmail_{thread_id}_{j}"
                await asyncio.to_thread(
                    collection.upsert,
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

            await event_queue.put({
                "type": "done", "file": subject, "thread_id": thread_id,
                "chunks": len(chunks), "task_id": task_id,
            })
        except Exception as e:
            await event_queue.put({
                "type": "error", "file": t.get("snippet", "")[:60],
                "error": str(e), "task_id": task_id,
            })

    task_counter = 0

    for t in all_threads:
        # Drain completed tasks
        while not event_queue.empty():
            item = event_queue.get_nowait()
            running_tasks.discard(item["task_id"])
            done_count += 1
            name = item.get("file", "")
            if item["type"] == "skip":
                skipped.append({"file": name, "reason": item["reason"]})
                yield {"type": "skip", "file": name, "reason": item["reason"], "done": done_count, "total": total}
            elif item["type"] == "done":
                indexed.append({"file": name, "thread_id": item["thread_id"], "chunks": item["chunks"]})
                yield {"type": "file_done", "file": name[:60], "chunks": item["chunks"], "done": done_count, "total": total}
            elif item["type"] == "error":
                errors.append({"file": name, "error": item["error"]})
                yield {"type": "file_error", "file": name, "error": item["error"], "done": done_count, "total": total}

        # Wait for a slot
        while len(running_tasks) >= MAX_CONCURRENT:
            item = await event_queue.get()
            running_tasks.discard(item["task_id"])
            done_count += 1
            name = item.get("file", "")
            if item["type"] == "skip":
                skipped.append({"file": name, "reason": item["reason"]})
                yield {"type": "skip", "file": name, "reason": item["reason"], "done": done_count, "total": total}
            elif item["type"] == "done":
                indexed.append({"file": name, "thread_id": item["thread_id"], "chunks": item["chunks"]})
                yield {"type": "file_done", "file": name[:60], "chunks": item["chunks"], "done": done_count, "total": total}
            elif item["type"] == "error":
                errors.append({"file": name, "error": item["error"]})
                yield {"type": "file_error", "file": name, "error": item["error"], "done": done_count, "total": total}

        task_counter += 1
        tid = task_counter
        running_tasks.add(tid)
        asyncio.create_task(_process_thread(t, tid))

    # Wait for remaining tasks
    while running_tasks:
        item = await event_queue.get()
        running_tasks.discard(item["task_id"])
        done_count += 1
        name = item.get("file", "")
        if item["type"] == "skip":
            skipped.append({"file": name, "reason": item["reason"]})
            yield {"type": "skip", "file": name, "reason": item["reason"], "done": done_count, "total": total}
        elif item["type"] == "done":
            indexed.append({"file": name, "thread_id": item["thread_id"], "chunks": item["chunks"]})
            yield {"type": "file_done", "file": name[:60], "chunks": item["chunks"], "done": done_count, "total": total}
        elif item["type"] == "error":
            errors.append({"file": name, "error": item["error"]})
            yield {"type": "file_error", "file": name, "error": item["error"], "done": done_count, "total": total}

    asyncio.create_task(asyncio.to_thread(build_global_vocab, collection))
    yield {
        "type": "complete",
        "indexed": len(indexed),
        "skipped": len(skipped),
        "files": indexed,
        "skipped_files": skipped,
        "errors": errors,
    }
