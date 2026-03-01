Here's your updated `CLAUDE.md` with the additional shell rules:

```markdown
# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

RAG + Agentic (MCP) document assistant API built with FastAPI. Indexes documents (txt, md, pdf, docx, xml) and Google Drive files into a ChromaDB vector database. Answers questions using hybrid RAG with optional Deep Think fallback (MCP tool-calling). Supports Ollama (local) and Gemini (cloud) LLMs.

## Architecture

Layered structure — **not** a single-file app:

```
main.py                  ← entry point only, mounts routers
config.py                ← all constants (paths, model names, extensions)
dependencies.py          ← shared state: LLM clients, ChromaDB, Google Drive

routers/
  chat.py                ← /chat, /chat-folder, /chat-mcp, /current-model
  index.py               ← /index, /index-folder, /index-gdrive
  drive.py               ← /auth/google, /auth/google/callback, /drive/status
  settings.py            ← /documents, /document/{id}, /folders, /stats, /models, /model, /reset

services/
  chat_service.py        ← RAG pipeline, Deep Think fallback, Drive fallback search
  search_service.py      ← hybrid_search (keyword + vector), fuzzy expansion, global vocab
  index_service.py       ← file/GDrive indexing, LLM summary generation
  mcp_tools.py           ← MCP tool functions + schemas (TOOL_FUNCTIONS, MCP_TOOLS)

utils/
  file_reader.py         ← read_file_content() for txt/md/pdf/docx/xml
  drive_utils.py         ← drive_read_content(), drive_list_all_files()
```

## Key Design Decisions

- **Hybrid search**: keyword scoring (rare-term TF-IDF style) + vector search merged, with fuzzy typo correction via difflib
- **Deep Think**: RAG runs first; if LLM responds `[UNCERTAIN]`, automatically falls back to MCP tool-calling
- **GDrive indexing**: stores summary chunks only (LLM-generated); Drive native search used as RAG fallback
- **Local file indexing**: stores full content chunks + summary chunk per file
- **LLM switching**: Ollama (local) or Gemini (cloud) selectable at runtime via `/model` endpoint
- **Circular imports avoided**: services import from `dependencies` lazily (inside function bodies)

## Key Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/chat` | RAG query. Params: `use_drive`, `deep_think` |
| `POST` | `/chat-mcp` | Pure MCP tool-calling query |
| `POST` | `/index-folder` | Index local folder recursively |
| `POST` | `/index-gdrive` | Index Google Drive (summaries) |
| `GET`  | `/documents` | List all indexed chunks |
| `GET`  | `/document/{id}` | Get full content of one chunk |
| `POST` | `/reset` | Wipe vector database |
| `GET`  | `/auth/google` | Start Google OAuth flow |

## Commands

```bash
# Activate venv
source venv/Scripts/activate   # Windows/Git Bash

# Run the server
uvicorn main:app --reload

# Key packages
pip install fastapi uvicorn openai chromadb python-docx PyPDF2 \
    google-auth google-auth-oauthlib google-api-python-client httpx
```

## Prerequisites

- Python 3.12 (venv already set up)
- Ollama on port 11434 (optional — Gemini works without it)
- `GEMINI_API_KEY` env var set for Gemini models
- `credentials.json` in project root for Google Drive OAuth

## Shell Rules
- Never combine `cd` and `git` in a single command. Always `cd` first as a separate command, then run git commands separately.
- Never use quoted characters in flag names or arguments.
- When running multi-line Python, always write to a temporary .py file first and execute it. Never use inline `python -c` with complex strings or multi-line code.
- Keep shell commands simple and single-purpose. Avoid long compound commands chained with `&&`.
```

The key additions are the last three bullet points in Shell Rules. That should eliminate both the "quoted characters in flag names" and most of the compound command prompts.