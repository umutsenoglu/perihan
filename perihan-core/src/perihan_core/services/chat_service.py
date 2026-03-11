import json
import time
import asyncio
from datetime import datetime


class LLMError(Exception):
    """Raised when an LLM operation fails. Carries a status_code for HTTP translation."""
    def __init__(self, message, status_code=400):
        self.status_code = status_code
        super().__init__(message)


def drive_fallback_search(
    question: str, existing_file_ids: set, max_files: int = 2, *, drive_svc=None
) -> tuple[list, list]:
    """Search Google Drive natively and read file content for RAG context."""
    from perihan_core.utils.drive_utils import drive_read_content

    if not drive_svc:
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
        results = drive_svc.files().list(
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
            content = drive_read_content(drive_svc, f["id"], f["name"], f["mimeType"])
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


def gmail_fallback_search(
    question: str, max_threads: int = 2, *, gmail_svc=None
) -> tuple[list, list]:
    """Search Gmail natively and return thread content for RAG context."""
    from perihan_core.utils.gmail_utils import gmail_search

    if not gmail_svc:
        return [], []
    try:
        terms = [
            w.strip("?.,!\"'():-")
            for w in question.split()
            if len(w.strip("?.,!\"'():-")) >= 4
        ]
        if not terms:
            return [], []
        query = " ".join(terms[:5])
        results = gmail_search(gmail_svc, query, max_results=max_threads + 3)
        docs, metas = [], []
        for t in results[:max_threads]:
            if t["content"] and len(t["content"].strip()) >= 10:
                docs.append(t["content"][:3000])
                metas.append({
                    "title": t["subject"] or "(no subject)",
                    "thread_id": t["id"],
                    "source": "gmail",
                    "folder": "gmail",
                })
        return docs, metas
    except Exception:
        return [], []


async def run_mcp_query(question: str, use_drive: bool = True, *, llm_client=None, model=None, collection=None, drive_svc=None) -> dict:
    """Run MCP tool-calling loop and return {reply, tool_calls}."""
    from perihan_core.services.mcp_tools import MCP_TOOLS, MCP_TOOLS_DRIVE, make_tool_functions

    if llm_client is None or model is None:
        raise ValueError("llm_client and model are required")
    if collection is None:
        raise ValueError("collection is required")

    tool_funcs = make_tool_functions(collection=collection, drive_svc=drive_svc)
    drive_tools = MCP_TOOLS_DRIVE if (use_drive and drive_svc) else []
    tools = MCP_TOOLS + drive_tools

    retry_instructions = """
CRITICAL RETRY RULES — you MUST follow these:
- You MUST search at least 3 times with DIFFERENT keywords before concluding you cannot find something.
- The user's query may contain typos. Try corrected spellings (e.g. "lastigi" → "lastik", "patlkasi" → "patlak").
- Try shorter keywords: extract the core noun/verb (e.g. "araba lastik patlak" → search "lastik", then "patlak", then "araba").
- Try synonyms and related terms in both Turkish and English.
- Try single-word searches — they often find what multi-word queries miss.
- NEVER give up after just 1 search. If your first search returns no results, that means you MUST try again with different terms.
- Only after 3+ failed searches with genuinely different keywords may you say you could not find the information."""

    if drive_tools:
        system_prompt = f"""You are Perihan, a helpful document assistant with access to an indexed document database and Google Drive.
Today's date is {datetime.now().strftime('%d %B %Y')}.

Follow these steps strictly:
1. FIRST use search_vectordb with a natural language query. It searches both local and Google Drive indexed documents.
2. You MUST call read_document (for source=local) or drive_read_file (for source=gdrive) for EVERY result returned. Reading files is mandatory — never skip a file.
3. Only after reading ALL returned files, provide your answer.
4. If search_vectordb finds nothing, try again with different keywords, then use drive_search_files as fallback.
5. NEVER answer "I could not find" without first reading every file from the search results.
6. Base your answer strictly on the actual file contents you have read.
{retry_instructions}"""
    else:
        system_prompt = f"""You are Perihan, a helpful document assistant with access to an indexed document database.
Today's date is {datetime.now().strftime('%d %B %Y')}.

Follow these steps strictly:
1. FIRST use search_vectordb with a natural language query based on the user's question.
2. You MUST call read_document(path=...) for EVERY file returned by search_vectordb. Reading is mandatory — the snippet alone is never enough.
3. Only after reading ALL returned files, provide your answer.
4. If search finds nothing OR after reading you still cannot answer, try search_vectordb again with completely different keywords (e.g. synonyms, related terms, or parts of the question).
5. NEVER answer "I could not find" without first reading every file from the search results.
6. Base your answer strictly on the actual file contents you have read. Quote or paraphrase directly when relevant.
{retry_instructions}"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": question},
    ]

    tool_call_log = []
    mcp_iterations = []
    search_count = 0  # Track how many searches have been done
    max_iterations = 8
    min_searches = 3  # Minimum searches before allowing "not found" answers

    for i in range(max_iterations):
        iteration_entry = {"iteration": i + 1, "prompt": [m if isinstance(m, dict) else m.model_dump() for m in messages]}
        try:
            response = llm_client.chat.completions.create(
                model=model,
                temperature=0.3,
                messages=messages,
                tools=tools,
            )
        except Exception as e:
            if "does not support tools" in str(e):
                raise LLMError(f"Model '{model}' does not support tool calling. Deep Think / MCP requires a model with tool support (e.g. Gemini).")
            raise
        choice = response.choices[0]

        if not choice.message.tool_calls:
            # If the LLM is giving up too early, nudge it to keep searching
            reply_text = choice.message.content or ""
            _negative = ["could not find", "cannot find", "can't find", "no information",
                         "no mention", "unable to find", "not found", "bulamıyorum",
                         "bulamadım", "bilgi yok", "bilgiye erişme"]
            is_giving_up = any(p in reply_text.lower() for p in _negative)

            if is_giving_up and search_count < min_searches:
                # Don't let it give up — force more searches
                messages.append(choice.message)
                nudge = (f"You have only searched {search_count} time(s). You MUST try at least {min_searches} searches with different keywords before giving up. "
                         f"Try shorter or simpler keywords, fix possible typos, or use synonyms. Search again now.")
                messages.append({"role": "user", "content": nudge})
                iteration_entry["response"] = reply_text
                iteration_entry["tool_calls"] = []
                iteration_entry["nudge"] = nudge
                mcp_iterations.append(iteration_entry)
                continue

            iteration_entry["response"] = reply_text
            iteration_entry["tool_calls"] = []
            mcp_iterations.append(iteration_entry)
            return {"reply": reply_text, "tool_calls": tool_call_log, "mcp_iterations": mcp_iterations}

        messages.append(choice.message)
        iteration_tool_calls = []

        for tc in choice.message.tool_calls:
            func_name = tc.function.name
            if func_name in ("search_vectordb", "drive_search_files", "search_files"):
                search_count += 1
            args = json.loads(tc.function.arguments)
            func = tool_funcs.get(func_name)
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
            iteration_tool_calls.append(log_entry)

            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

        iteration_entry["tool_calls"] = iteration_tool_calls
        mcp_iterations.append(iteration_entry)

    last_content = response.choices[0].message.content or "Max tool call iterations reached."
    return {"reply": last_content, "tool_calls": tool_call_log, "mcp_iterations": mcp_iterations}


async def rag_query(question: str, use_drive: bool = True, deep_think: bool = False, endpoint: str = "/chat",
                    *, collection=None, llm_client=None, model=None, drive_svc=None, gmail_svc=None, log_fn=None) -> dict:
    """Full RAG pipeline with optional deep-think MCP fallback."""
    from perihan_core.services.search_service import hybrid_search

    if llm_client is None or model is None or collection is None:
        raise ValueError("collection, llm_client, and model are required")

    start_time = time.perf_counter()
    rag_start = start_time
    where = None if use_drive else {"source": {"$ne": "gdrive"}}
    docs, metas, search_debug = hybrid_search(question, n_results=8, where=where, collection=collection)

    # Google Drive native search fallback — searches actual file content, not just indexed summaries
    if use_drive and drive_svc:
        existing_ids = {m.get("file_id") for m in metas if m.get("source") == "gdrive"}
        drive_docs, drive_metas = await asyncio.to_thread(
            drive_fallback_search, question, existing_ids, drive_svc=drive_svc
        )
        docs = docs + drive_docs
        metas = metas + drive_metas

    # Gmail native search fallback
    if gmail_svc:
        gmail_docs, gmail_metas = await asyncio.to_thread(
            gmail_fallback_search, question, gmail_svc=gmail_svc
        )
        docs = docs + gmail_docs
        metas = metas + gmail_metas

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
                    if len(stem) < 3:
                        break
                    if stem not in seen_st:
                        seen_st.add(stem)
                        raw_terms.append(stem)
        # Also include fuzzy-expanded terms (e.g. "dominik" corrected from "domonik")
        for expanded_kw in search_debug.get("expanded_terms", []):
            if len(expanded_kw) >= 3 and expanded_kw not in seen_st:
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

    # For group/chat listing queries, inject all named WhatsApp groups as context
    q_lower = question.lower()
    if any(w in q_lower for w in ("group", "groups", "grup", "grub", "gruplari", "gruplarda")):
        try:
            col = collection
            all_meta = col.get(include=["metadatas"])
            named_groups = set()
            for m in all_meta["metadatas"]:
                cn = m.get("chat_name", "")
                if cn and not cn.isdigit() and not cn.replace("+", "").isdigit():
                    named_groups.add(cn)
            if named_groups:
                group_list = ", ".join(sorted(named_groups))
                context += f"\n\n=== ALL WHATSAPP GROUPS ===\nYour named WhatsApp groups: {group_list}"
        except Exception:
            pass

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

    llm_messages = [
        {
            "role": "system",
            "content": f"""
You are Perihan, a helpful document assistant.
Today's date is {datetime.now().strftime('%d %B %Y')}.
If the documents below contain relevant information, use them to answer.
Do NOT mention, guess, or fabricate source file names or paths in your answer. Source attribution is handled separately.
If the question is general and not covered in the documents, answer from your own knowledge.
Always be clear about whether your answer comes from indexed documents or general knowledge.
In WhatsApp chat logs, "Me" is the user (Umut). Speakers labeled "Unknown" can often be identified from conversational context (e.g. if "Me" addresses someone by name and "Unknown" replies, that Unknown is the named person). Use this reasoning to extract information.
In MSN Messenger chat logs (from hatira/ folders), "umut" or "(li)umut(li)" is also the user. All indexed documents — WhatsApp chats, MSN logs, trainer files — belong to the same person.
WhatsApp chat names may be phone numbers (e.g. "905058540590"). These are system-generated identifiers, NOT personal contact information. Never reveal or infer someone's phone number from a chat identifier. If asked for a phone number, say you do not have that information.
The indexed data contains both English and Turkish content. Match concepts across languages (e.g. "Noel" = "Christmas", "yeni yıl" = "New Year"). When listing items (groups, people, events), scan ALL provided documents thoroughly — do not stop after finding a few matches.

IMPORTANT: Start your response with [CONFIDENT] if the documents contain specific, relevant information that answers the question. Start with [UNCERTAIN] if:
- The documents do not contain the answer, OR
- Your answer is essentially "I could not find this", "there is no mention of", "the documents do not discuss", or any similar negative finding.
When in doubt, use [UNCERTAIN] — do not guess or paraphrase absence of information as a confident answer.

Documents:
{context}
""",
        },
        {"role": "user", "content": question},
    ]

    llm_start = time.perf_counter()
    try:
        response = llm_client.chat.completions.create(
            model=model,
            temperature=0.3,
            messages=llm_messages,
        )
    except Exception as e:
        if log_fn:
            log_fn({
                "endpoint": endpoint,
                "model": model,
                "question": question,
                "use_drive": use_drive,
                "deep_think": deep_think,
                "rag_results": [{"title": m.get("title", ""), "source": m.get("source", ""), "content": d} for d, m in zip(docs, metas)],
                "llm_prompt": llm_messages,
                "llm_response": None,
                "deep_think_triggered": False,
                "mcp_iterations": [],
                "error": str(e),
                "duration_ms": round((time.perf_counter() - start_time) * 1000),
            })
        raise

    llm_time = time.perf_counter() - llm_start

    msg = response.choices[0].message if response.choices else None
    reply = (msg.content if msg and msg.content else "") or ""
    confident = "[UNCERTAIN]" not in reply.lstrip()[:15]

    # Secondary catch: LLM responded confidently but the answer is essentially "nothing found"
    # This handles cases where the LLM ignores [UNCERTAIN] instruction and just says "no info"
    if confident and docs:
        _negative_phrases = [
            "does not mention", "do not mention", "no mention of",
            "no information", "cannot find", "could not find", "can't find",
            "not found", "no specific", "not addressed", "not discussed",
            "not covered", "unable to find", "no details", "no record of",
            "none of the", "the documents do not", "sources do not",
        ]
        reply_lower = reply.lower()
        if any(phrase in reply_lower for phrase in _negative_phrases):
            confident = False

    reply_clean = reply.replace("[CONFIDENT]", "").replace("[UNCERTAIN]", "").strip()

    rag_results_log = [
        {"title": m.get("title", ""), "source": m.get("source", "local"), "content": d}
        for d, m in zip(docs, metas)
    ]

    # Deep Think fallback: RAG was uncertain, escalate to MCP
    if deep_think and not confident:
        mcp_result = await run_mcp_query(question, use_drive, llm_client=llm_client, model=model, collection=collection, drive_svc=drive_svc)
        if log_fn:
            log_fn({
                "endpoint": endpoint,
                "model": model,
                "question": question,
                "use_drive": use_drive,
                "deep_think": deep_think,
                "rag_results": rag_results_log,
                "llm_prompt": llm_messages,
                "llm_response": reply,
                "deep_think_triggered": True,
                "mcp_iterations": mcp_result.get("mcp_iterations", []),
                "error": None,
                "duration_ms": round((time.perf_counter() - start_time) * 1000),
            })
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

    if log_fn:
        log_fn({
            "endpoint": endpoint,
            "model": model,
            "question": question,
            "use_drive": use_drive,
            "deep_think": deep_think,
            "rag_results": rag_results_log,
            "llm_prompt": llm_messages,
            "llm_response": reply,
            "deep_think_triggered": False,
            "mcp_iterations": [],
            "error": None,
            "duration_ms": round((time.perf_counter() - start_time) * 1000),
        })

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
