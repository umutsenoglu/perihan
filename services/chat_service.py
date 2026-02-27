import json
import time
import asyncio
from datetime import datetime


def drive_fallback_search(
    question: str, existing_file_ids: set, max_files: int = 2
) -> tuple[list, list]:
    """Search Google Drive natively and read file content for RAG context."""
    # Lazy imports to avoid circular deps
    from dependencies import get_drive
    from utils.drive_utils import drive_read_content

    svc = get_drive()
    if not svc:
        return [], []
    try:
        terms = [
            w.strip("?.,!\"'():-")
            for w in question.split()
            if len(w.strip("?.,!\"'():-")) >= 4
        ]
        if not terms:
            return [], []
        drive_query = " or ".join([f"fullText contains '{t}'" for t in terms[:5]])
        results = svc.files().list(
            q=f"({drive_query}) and trashed=false",
            fields="files(id,name,mimeType)",
            pageSize=5,
        ).execute()
        docs, metas = [], []
        for f in results.get("files", []):
            if f["id"] in existing_file_ids:
                continue
            if len(docs) >= max_files:
                break
            content = drive_read_content(svc, f["id"], f["name"], f["mimeType"])
            if content and len(content.strip()) >= 10:
                docs.append(content[:3000])
                metas.append(
                    {
                        "title": f["name"],
                        "file_id": f["id"],
                        "source": "gdrive",
                        "folder": "",
                    }
                )
        return docs, metas
    except Exception:
        return [], []


async def run_mcp_query(question: str, use_drive: bool = True) -> dict:
    """Run MCP tool-calling loop and return {reply, tool_calls}."""
    # Lazy imports to avoid circular deps
    from dependencies import get_llm_client, get_current_model, get_drive
    from services.mcp_tools import MCP_TOOLS, MCP_TOOLS_DRIVE, TOOL_FUNCTIONS

    drive_tools = MCP_TOOLS_DRIVE if (use_drive and get_drive()) else []
    tools = MCP_TOOLS + drive_tools

    if drive_tools:
        system_prompt = f"""You are Perihan, a helpful document assistant with access to an indexed document database and Google Drive.
Today's date is {datetime.now().strftime('%d %B %Y')}.

Follow these steps strictly:
1. FIRST use search_vectordb with a natural language query. It searches both local and Google Drive indexed documents.
2. For each result: if source=local use read_document(path=...), if source=gdrive use drive_read_file(file_id=...).
3. Read ALL returned files before answering.
4. If search_vectordb finds nothing, use drive_search_files and drive_list_files as fallback.
5. Only answer AFTER reading all relevant files.
6. Base your answer on the actual file contents."""
    else:
        system_prompt = f"""You are Perihan, a helpful document assistant with access to an indexed document database.
Today's date is {datetime.now().strftime('%d %B %Y')}.

Follow these steps strictly:
1. FIRST use search_vectordb with a natural language query based on the user's question.
2. ALWAYS read EVERY file returned by search_vectordb using read_document(path=...). Never skip a file — the snippet may not show the relevant part.
3. Read ALL returned files before answering (not just the first one).
4. If search finds nothing OR after reading files you still cannot answer, try search_vectordb again with different keywords.
5. Only answer AFTER reading all relevant files.
6. Base your answer on the actual file contents. Do NOT give generic answers if the files contain relevant information.
7. If a file directly answers the question, quote or paraphrase it accurately.
8. NEVER say you cannot find information after only one search — always try reading the returned files first."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": question},
    ]

    tool_call_log = []
    max_iterations = 5
    model = get_current_model()

    for _ in range(max_iterations):
        response = get_llm_client().chat.completions.create(
            model=model,
            temperature=0.3,
            messages=messages,
            tools=tools,
        )
        choice = response.choices[0]

        if not choice.message.tool_calls:
            return {"reply": choice.message.content, "tool_calls": tool_call_log}

        messages.append(choice.message)

        for tc in choice.message.tool_calls:
            func_name = tc.function.name
            args = json.loads(tc.function.arguments)
            func = TOOL_FUNCTIONS.get(func_name)
            result = (
                func(**args) if func else json.dumps({"error": f"Unknown tool: {func_name}"})
            )

            result_preview = result[:200] + "..." if len(result) > 200 else result
            log_entry = {"tool": func_name, "args": args, "result_preview": result_preview}
            try:
                parsed = json.loads(result)
                if "name" in parsed:
                    log_entry["file_name"] = parsed["name"]
                elif "files" in parsed:
                    log_entry["file_count"] = len(parsed["files"])
            except Exception:
                pass
            tool_call_log.append(log_entry)

            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

    last_content = response.choices[0].message.content or "Max tool call iterations reached."
    return {"reply": last_content, "tool_calls": tool_call_log}


async def rag_query(question: str, use_drive: bool = True, deep_think: bool = False) -> dict:
    """Full RAG pipeline with optional deep-think MCP fallback."""
    # Lazy imports to avoid circular deps
    from dependencies import get_llm_client, get_current_model, get_drive
    from services.search_service import hybrid_search

    rag_start = time.perf_counter()
    where = None if use_drive else {"source": {"$ne": "gdrive"}}
    docs, metas, search_debug = hybrid_search(question, n_results=8, where=where)

    # Google Drive native search fallback — searches actual file content, not just indexed summaries
    if use_drive and get_drive():
        existing_ids = {m.get("file_id") for m in metas if m.get("source") == "gdrive"}
        drive_docs, drive_metas = await asyncio.to_thread(
            drive_fallback_search, question, existing_ids
        )
        docs = docs + drive_docs
        metas = metas + drive_metas

    # Extract focused snippets around keyword matches instead of full chunks
    if docs:
        # Build search terms for snippet extraction
        q_words = question.split()
        raw_terms = []
        seen_st = set()
        for w in q_words:
            cleaned = w.strip("?.,!\"'():-").lower()
            if len(cleaned) < 3:
                continue
            if cleaned not in seen_st:
                seen_st.add(cleaned)
                raw_terms.append(cleaned)
            # Add stems (remove 1-3 chars) to handle suffixes/possessives
            if len(cleaned) >= 6:
                for trim in range(1, 4):
                    stem = cleaned[:-trim]
                    if len(stem) < 4:
                        break
                    if stem not in seen_st:
                        seen_st.add(stem)
                        raw_terms.append(stem)
        # Also include fuzzy-expanded terms (e.g. "dominik" corrected from "domonik")
        for expanded_kw in search_debug.get("expanded_terms", []):
            if len(expanded_kw) >= 4 and expanded_kw not in seen_st:
                seen_st.add(expanded_kw)
                raw_terms.append(expanded_kw)
        # For long queries, keep only 5+ char terms to avoid noise
        if len(raw_terms) > 10:
            search_terms = [t for t in raw_terms if len(t) >= 5]
        else:
            search_terms = raw_terms

        labeled_chunks = []
        for doc, meta in zip(docs, metas):
            title = meta.get("title", "unknown")
            is_summary = meta.get("is_summary") == "true"

            # Summaries and Drive fallback content are already concise — use in full
            if is_summary or (meta.get("source") == "gdrive" and not is_summary):
                focused = doc
            else:
                doc_lower = doc.lower()
                # Find all keyword match positions and extract windows around them
                match_positions = []
                for term in search_terms:
                    pos = 0
                    while True:
                        idx = doc_lower.find(term, pos)
                        if idx == -1:
                            break
                        match_positions.append(idx)
                        pos = idx + len(term)

                if match_positions:
                    # Merge overlapping windows (400 chars before and after each match)
                    match_positions.sort()
                    windows = []
                    for pos in match_positions:
                        start = max(0, pos - 400)
                        end = min(len(doc), pos + 400)
                        if windows and start <= windows[-1][1]:
                            windows[-1] = (windows[-1][0], max(windows[-1][1], end))
                        else:
                            windows.append((start, end))
                    snippets = []
                    for start, end in windows[:3]:  # max 3 windows
                        snippet = doc[start:end].strip()
                        if start > 0:
                            snippet = "..." + snippet
                        if end < len(doc):
                            snippet = snippet + "..."
                        snippets.append(snippet)
                    focused = "\n\n".join(snippets)
                else:
                    focused = doc[:600]

            labeled_chunks.append(f"=== SOURCE: {title} ===\n{focused}")
        context = "\n\n".join(labeled_chunks)
    else:
        context = "No documents found."

    # Build unique sources from metadata
    sources = []
    seen = set()
    for meta in metas:
        title = meta.get("title", "")
        path = meta.get("relative_path", "") or meta.get("full_path", "")
        key = f"{title}|{path}"
        if key not in seen:
            seen.add(key)
            sources.append({"title": title, "path": path})

    rag_time = time.perf_counter() - rag_start

    model = get_current_model()
    llm_start = time.perf_counter()
    response = get_llm_client().chat.completions.create(
        model=model,
        temperature=0.3,
        messages=[
            {
                "role": "system",
                "content": f"""
You are Perihan, a helpful document assistant.
Today's date is {datetime.now().strftime('%d %B %Y')}.
If the documents below contain relevant information, use them to answer.
Do NOT mention, guess, or fabricate source file names or paths in your answer. Source attribution is handled separately.
If the question is general and not covered in the documents, answer from your own knowledge.
Always be clear about whether your answer comes from indexed documents or general knowledge.

IMPORTANT: Start your response with [CONFIDENT] if the documents contain specific information to answer the question, or [UNCERTAIN] if you could not find relevant information.

Documents:
{context}
""",
            },
            {"role": "user", "content": question},
        ],
    )

    llm_time = time.perf_counter() - llm_start

    reply = response.choices[0].message.content or ""
    confident = "[UNCERTAIN]" not in reply.lstrip()[:15]
    reply_clean = reply.replace("[CONFIDENT]", "").replace("[UNCERTAIN]", "").strip()

    # Deep Think fallback: RAG was uncertain, escalate to MCP
    if deep_think and not confident:
        mcp_result = await run_mcp_query(question, use_drive)
        return {
            "reply": mcp_result["reply"],
            "sources": [],
            "tool_calls": mcp_result["tool_calls"],
            "deep_think_used": True,
            "timing": {
                "rag_seconds": round(rag_time, 3),
                "llm_seconds": round(llm_time, 3),
            },
        }

    return {
        "reply": reply_clean,
        "sources": sources,
        "tool_calls": [],
        "deep_think_used": False,
        "timing": {
            "rag_seconds": round(rag_time, 3),
            "llm_seconds": round(llm_time, 3),
        },
        "search_debug": search_debug,
    }
