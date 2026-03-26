# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

RAG + Agentic (MCP) document assistant API built with FastAPI. Indexes documents (txt, md, pdf, docx, xml) and Google Drive files into a ChromaDB vector database. Answers questions using hybrid RAG with optional Deep Think fallback (MCP tool-calling). Supports Ollama (local) and Gemini (cloud) LLMs.

## Architecture

Two packages — `perihan-app` (FastAPI server + UI) and `perihan-core` (services + utils):

```
perihan-app/src/perihan_app/
  main.py                ← entry point, mounts routers
  config.py              ← all constants (paths, model names, extensions)
  dependencies.py        ← shared state: LLM clients, ChromaDB, Google Drive
  routers/
    chat.py              ← /chat, /chat-folder, /chat-mcp, /current-model
    index.py             ← /index, /index-folder, /index-gdrive, /index-gmail
    drive.py             ← /auth/google, /auth/google/callback, /drive/status
    settings.py          ← /documents, /document/{id}, /folders, /stats, /models, /model, /reset
    whatsapp.py          ← /whatsapp/start, /whatsapp/qr, /whatsapp/status

perihan-core/src/perihan_core/
  services/
    chat_service.py      ← RAG pipeline, Deep Think fallback, Drive/Gmail fallback search
    search_service.py    ← hybrid_search (keyword + vector), fuzzy expansion, global vocab
    index_service.py     ← file/GDrive/Gmail indexing, LLM summary generation
    mcp_tools.py         ← MCP tool functions + schemas
  utils/
    file_reader.py       ← read_file_content() for txt/md/pdf/docx/xml
    drive_utils.py       ← drive_read_content(), drive_list_all_files()
    gmail_utils.py       ← gmail_search(), gmail_list_all_threads()

theloop/                 ← Continuous improvement pipeline (eval + benchmarking)
  collector/             ← Collects source docs
  qa_generator/          ← Generates QA pairs from source docs
  eval_runner/           ← Runs Perihan vs Gemini benchmark, generates report.html
  theloop-core/          ← Step runners + history tracking
  theloop-ui/            ← Dashboard on port 8100
```

## Key Design Decisions

- **Hybrid search**: keyword scoring (rare-term TF-IDF style) + vector search merged, with fuzzy typo correction via difflib
- **Deep Think**: RAG runs first; if LLM responds `[UNCERTAIN]`, automatically falls back to MCP tool-calling
- **GDrive indexing**: stores summary chunks only (LLM-generated); Drive native search used as RAG fallback
- **Gmail indexing**: raw text chunks (NO LLM summary), saved to `DATA_DIR/gmail/`
- **Local file indexing**: stores full content chunks + summary chunk per file
- **LLM switching**: Ollama (local) or Gemini (cloud) selectable at runtime via `/model` endpoint
- **Circular imports avoided**: services import from `dependencies` lazily (inside function bodies)
- **Async with thread offloading**: all endpoints are `async def`, blocking calls (ChromaDB, file I/O, LLM API) wrapped in `asyncio.to_thread()`. Thread pool raised to 200 (default was 40).

## Search Algorithm — Hard-Won Lessons

These rules were discovered through extensive QA testing. Violating them causes regressions:

- **IDF only on base keywords, never stems** — stems like "yazi" (from "yazisma") match too broadly, IDF amplifies noise
- **Word-boundary matching for short keywords (<5 chars)** — prevents "seb" inflating via "seboistnet" substring matches
- **Never fuzzy-expand phrases** — "email address" → "mailaddress" false positive
- **Cross-folder diversity is critical** — same filename (e.g. abdullahavci) exists in 5+ hatira/ subfolders; round-robin 1 chunk per folder prevents one folder monopolizing results
- **$contains limit = n_results * 5** — this is the sweet spot; *10 changes IDF distribution and causes regressions
- **Vector search is weak for MSN/hatira files** — embeddings don't connect Turkish temporal queries to raw XML; keyword search carries these
- **Time-based queries fail in RAG** — query "19:30 da kim gelecekti" won't match "19:30 ?" because keywords don't overlap; Deep Think/MCP is the fallback

## RAG Performance Insights (from eval at 84%)

Failure patterns from 134-question eval (2026-03-19):
1. **Incomplete multi-doc retrieval** (biggest, ~16 questions): timeline/evolution questions need docs from many time periods. Increasing `n_results` helps.
2. **Narrow snippet windows** (~8 questions): keyword match windows too small, cutting off key facts.
3. **Wrong docs retrieved** (~5 questions): similar-but-wrong documents confuse the LLM. Recency preference in system prompt helps.
4. **Medical category weakest**: 73% vs 88% personal. Medical questions require cross-document synthesis across many clinical records.

## Commands

```bash
# Run the Perihan server
uvicorn perihan_app.main:app --reload --port 8000

# Run TheLoop dashboard
python theloop/theloop-ui/server.py    # port 8100

# Run eval (needs server running + GEMINI_API_KEY)
cd theloop/eval_runner
python runner.py benchmark             # score Gemini with raw docs
python runner.py perihan               # score Perihan RAG
python runner.py perihan --low-scores  # re-run only questions scored 0 or 1
python runner.py report                # print summary
```

## Prerequisites

- Python 3.12 (venv already set up)
- Ollama on port 11434 (optional — Gemini works without it)
- `GEMINI_API_KEY` env var set for Gemini models
- `credentials.json` in data/ folder for Google Drive/Gmail OAuth

## Shell Rules
- `cd` must ALWAYS be its own standalone command. Never combine `cd` with anything — not git, not redirection, not `&&` chains. Always `cd` first, then run the next command separately.
- Never use quoted characters in flag names or arguments.
- When running multi-line Python, always write to a temporary .py file first and execute it. Never use inline `python -c` with complex strings or multi-line code.
- Keep shell commands simple and single-purpose. One command per execution.
