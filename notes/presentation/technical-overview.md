# Perihan — Technical Overview

## System Architecture

Perihan is split into two packages:

- **perihan-core** — Reusable library containing search, chat, indexing, and file-reading logic. No web framework dependency.
- **perihan-app** — FastAPI web application that wires up HTTP endpoints, manages singletons (LLM clients, vector DB, Google APIs), and serves the UI.

This separation allows the core intelligence to be reused in future clients (mobile, CLI, desktop) without pulling in the web layer.

```
┌─────────────────────────────────────────────────────┐
│  Client (Browser / Mobile / API consumer)           │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│  perihan-app (FastAPI)                              │
│  ┌──────────┐ ┌──────────┐ ┌────────┐ ┌─────────┐  │
│  │ chat.py  │ │ index.py │ │drive.py│ │settings │  │
│  │ /chat    │ │ /index   │ │ /auth  │ │ /stats  │  │
│  │ /chat-mcp│ │ /index-  │ │ /drive │ │ /models │  │
│  └────┬─────┘ │  folder  │ └───┬────┘ └────┬────┘  │
│       │       │ /index-  │     │            │       │
│       │       │  gdrive  │     │            │       │
│       │       │ /index-  │     │            │       │
│       │       │  gmail   │     │            │       │
│       │       └────┬─────┘     │            │       │
│  dependencies.py (singletons: LLM, ChromaDB, Auth) │
└──────┬─────────────┬───────────┴────────────┘       │
       │             │                                 │
┌──────▼─────────────▼────────────────────────────────┐
│  perihan-core (library)                             │
│  ┌──────────────┐ ┌──────────────┐ ┌─────────────┐ │
│  │ chat_service │ │ index_service│ │ mcp_tools   │ │
│  │ RAG pipeline │ │ file/drive/  │ │ tool schemas│ │
│  │ Deep Think   │ │ gmail index  │ │ & functions │ │
│  └──────┬───────┘ └──────┬───────┘ └─────────────┘ │
│         │                │                          │
│  ┌──────▼───────┐ ┌──────▼───────┐                  │
│  │search_service│ │ utils/       │                  │
│  │hybrid search │ │ file_reader  │                  │
│  │keyword+vector│ │ drive_utils  │                  │
│  │fuzzy matching│ │ gmail_utils  │                  │
│  └──────────────┘ └──────────────┘                  │
└─────────────────────────────────────────────────────┘
       │             │             │
┌──────▼──┐  ┌──────▼──┐  ┌──────▼──────────────┐
│ChromaDB │  │Ollama / │  │Google Drive / Gmail │
│(vector) │  │Gemini   │  │(OAuth2)             │
└─────────┘  └─────────┘  └─────────────────────┘
```

## Core Pipeline: How a Question Gets Answered

```
1. User sends question via /chat
                │
2. Hybrid Search (search_service.py)
   ├── Keyword scoring: TF-IDF-style rare-term weighting
   ├── Vector search: ChromaDB embedding similarity
   ├── Fuzzy expansion: difflib typo correction against global vocab
   └── Merge & rank results, enforce cross-folder diversity
                │
3. LLM generates answer from top chunks
   ├── System prompt includes source citations requirement
   └── If LLM returns [UNCERTAIN] and deep_think=true...
                │
4. Deep Think fallback (agentic MCP tool-calling)
   ├── LLM gets access to tools: search_vectordb, read_document,
   │   list_files, search_by_folder, drive_search, gmail_search
   ├── Iterates up to 5 rounds of tool calls
   └── Returns answer with tool-call trace
                │
5. Drive/Gmail native search fallback (if enabled)
   └── Uses Google's own search API as last resort
```

## Data Indexing

### Local Files
Files are read by `file_reader.py` (supports txt, md, pdf, docx, xml), chunked into ~500-token segments, and stored in ChromaDB with full content. An LLM-generated summary chunk is also stored per file for semantic retrieval.

### Google Drive
Files are read via Drive API, summarised by LLM, and only the summary chunks are stored in ChromaDB. For retrieval fallback, Drive's native search is used to find content not captured in summaries.

### Gmail
Messages are fetched via Gmail API, stored as raw text chunks (no LLM summary) in ChromaDB and saved locally. Gmail search is available as a fallback tool in Deep Think mode.

### WhatsApp
Exported chat files (txt or xml format) are indexed as local files. The system handles both plain-text exports and MSN/Hatira XML formats.

## Search Algorithm

The hybrid search is Perihan's core differentiator. It combines three signals:

**Keyword scoring** — Extracts keywords from the query, scores documents by term frequency weighted by inverse document frequency (IDF). Only base keywords get IDF weighting (never stems), and short keywords (<5 chars) use word-boundary matching to avoid false positives.

**Vector search** — ChromaDB's built-in embedding similarity finds semantically related chunks even when keywords don't overlap.

**Fuzzy matching** — A global vocabulary is built at startup from all indexed content. Query terms are expanded using `difflib.get_close_matches` to handle typos, missing diacritics, and partial matches (e.g., "hedgehg" → "hedgehogs", "suleyman" → "SÜLEYMAN").

Results are merged, deduplicated, and diversity-enforced (round-robin across folders to prevent one source from dominating).

## LLM Integration

Perihan is LLM-agnostic. Two providers are supported, switchable at runtime via the `/model` endpoint:

| Provider | Models | Use Case |
|---|---|---|
| **Ollama** (local) | Any model the user runs (Llama, Mistral, etc.) | Full privacy, no internet, free |
| **Gemini** (cloud) | gemini-2.5-flash, gemini-2.0-flash | Better quality, requires API key |

Both are accessed via OpenAI-compatible API clients. The chat service constructs prompts identically regardless of provider — only the base URL and API key change.

## MCP Tool-Calling (Deep Think)

When standard RAG returns `[UNCERTAIN]`, Perihan switches to agentic mode. The LLM receives a set of tool schemas and autonomously decides which tools to call:

| Tool | Function |
|---|---|
| `search_vectordb` | Search ChromaDB with a custom query |
| `read_document` | Read full content of a specific chunk |
| `list_all_files` | List all indexed files |
| `search_by_folder` | Search within a specific folder |
| `drive_search` | Search Google Drive natively |
| `gmail_search` | Search Gmail natively |

The system iterates up to 5 tool-call rounds, accumulating context until the LLM produces a final answer.

## Data Storage

**ChromaDB** — Single collection (`perihan_docs`) stores all document chunks with embeddings. Metadata includes source file path, folder, chunk index, and content type. ChromaDB runs embedded (no separate server).

**Local filesystem** — Gmail messages and configuration are persisted to `DATA_DIR`. Google OAuth tokens are stored locally.

**No external database** — Everything runs from the local machine. No cloud storage, no account creation, no data leaves the device (unless using Gemini as LLM provider).

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12 |
| Web framework | FastAPI (async, SSE streaming for long operations) |
| Vector database | ChromaDB (embedded) |
| LLM clients | OpenAI Python SDK (compatible with Ollama & Gemini) |
| File parsing | PyPDF2, python-docx, xml.etree |
| Google APIs | google-auth, google-api-python-client |
| Distribution | Standalone Windows installer with embedded Python + pre-built wheels |

## Key Design Principles

1. **Privacy first** — All data stays local. Cloud LLM is optional, not required.
2. **LLM-agnostic** — No vendor lock-in. Swap models at runtime.
3. **Layered architecture** — Core logic has zero web framework dependency.
4. **Lazy initialisation** — Services import dependencies inside function bodies to avoid circular imports and speed up startup.
5. **Graceful degradation** — RAG → Deep Think → Drive/Gmail fallback. Each layer catches what the previous one missed.
6. **Cost awareness** — Expensive operations (map-reduce, multi-round tool calls) require explicit opt-in.
