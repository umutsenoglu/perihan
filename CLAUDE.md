# CLAUDE.md

## What Is This Repo

This repo contains **Perihan** — a personal document assistant that indexes your files, Google Drive, Gmail, and WhatsApp messages into a vector database, then answers questions about them using RAG (Retrieval-Augmented Generation) with optional agentic fallback.

There are **4 projects** in this repo:

| Project | What it does | Tech |
|---------|-------------|------|
| **perihan-app** | FastAPI server + web UI | Python, FastAPI, Jinja |
| **perihan-core** | RAG engine, search, indexing, MCP tools | Python, ChromaDB, OpenAI SDK |
| **theloop** | Eval & benchmarking pipeline with dashboard | Python, FastAPI, Gemini API |
| **whatsapp-sidecar** | Node.js bridge that imports WhatsApp chats | Node.js, whatsapp-web.js |

## How They Relate

```
                 perihan-app (server + UI on :8000)
                      |
                      | imports services from
                      v
                 perihan-core (RAG engine)
                      |
          +-----------+-----------+
          |           |           |
      ChromaDB   Ollama/Gemini  Google APIs
      (vectordb)  (LLM on :11434  (Drive, Gmail)
                   or cloud)

  whatsapp-sidecar ----HTTP----> perihan-app
  (node.js, spawned              (receives messages
   by perihan-app)                via internal API)

  theloop (eval dashboard on :8100)
      |
      +---HTTP---> perihan-app (/chat endpoint)
      +---HTTP---> Gemini API (benchmark + judging)
```

- **perihan-app** is the main server. It mounts routers, serves the web UI, and depends on **perihan-core** for all business logic.
- **perihan-core** is a pure library. It has no server, no endpoints. It provides search, chat, indexing, and MCP tool services.
- **theloop** is standalone. It talks to perihan-app over HTTP and to Gemini directly. It generates QA questions, benchmarks Gemini (with raw docs) vs Perihan (via RAG), and produces an eval report.
- **whatsapp-sidecar** is a Node.js process started by perihan-app. It connects to WhatsApp Web, fetches messages, and POSTs them back to perihan-app's internal API for indexing.

## Folder Structure

```
perihan-app/src/perihan_app/
  main.py              ← FastAPI app, mounts routers, startup event
  config.py            ← Constants: paths, model names, supported extensions
  dependencies.py      ← Shared state: LLM clients, ChromaDB collection, Drive/Gmail services
  routers/
    chat.py            ← /chat, /chat-folder, /chat-mcp, /current-model
    index.py           ← /index, /index-folder, /index-gdrive, /index-gmail
    drive.py           ← /auth/google, /auth/google/callback, /drive/status
    settings.py        ← /documents, /folders, /stats, /models, /model, /reset, /config, /logs
    whatsapp.py        ← /whatsapp/start, /whatsapp/qr, /whatsapp/status, internal message receiver
  services/
    config_service.py  ← Read/write perihan_config.json
    log_service.py     ← Chat log persistence
  static/
    index.html         ← Single-page web UI

perihan-core/src/perihan_core/
  config.py            ← Shared constants (chunk size, extensions, etc.)
  services/
    chat_service.py    ← RAG pipeline, Deep Think fallback, Drive/Gmail fallback search
    search_service.py  ← hybrid_search (keyword + vector), fuzzy expansion, global vocab
    index_service.py   ← File/GDrive/Gmail indexing, LLM summary generation
    mcp_tools.py       ← MCP tool functions + schemas for agentic mode
  utils/
    file_reader.py     ← read_file_content() for txt/md/pdf/docx/xml
    drive_utils.py     ← Google Drive: list files, read content
    gmail_utils.py     ← Gmail: search, list threads, format thread text

theloop/
  collector/           ← Step 1: Collects source documents for QA generation
  qa_generator/        ← Step 2: Generates question-answer pairs from source docs
  eval_runner/         ← Steps 3-5: Benchmark (Gemini) + Evaluate (Perihan) + Report
    runner.py          ← CLI: benchmark, perihan, perihan --low-scores, report
    report.py          ← Generates report.html with side-by-side comparison
    output/            ← eval_results.json, report.html
  theloop-core/        ← Step orchestration, history tracking
    steps.py           ← Subprocess runners for each pipeline step
    history.py         ← Run history persistence
  theloop-ui/          ← Dashboard web UI
    server.py          ← FastAPI app on port 8100
    static/index.html  ← Single-page dashboard

whatsapp-sidecar/
  index.js             ← Connects to WhatsApp Web, fetches chats, POSTs to Perihan

Data directories (not in git):
  vectordb/            ← ChromaDB persistent storage
  gmail/               ← Raw Gmail thread text files
  whatsapp/            ← Raw WhatsApp chat text files
  logs/                ← Chat interaction logs (chat.jsonl)
```

## Common Commands

```bash
# Run the Perihan server
uvicorn perihan_app.main:app --reload --port 8000

# Run TheLoop dashboard
python theloop/theloop-ui/server.py

# Run eval (needs Perihan server running + GEMINI_API_KEY)
cd theloop/eval_runner
python runner.py benchmark             # Score Gemini with raw docs (skips already done)
python runner.py perihan               # Score Perihan RAG (always re-runs all)
python runner.py perihan --low-scores  # Re-run only questions scored 0 or 1
python runner.py report                # Print summary to terminal
```

## Prerequisites

- Python 3.12
- `GEMINI_API_KEY` env var for Gemini models
- Ollama on port 11434 (optional — only needed for local models)
- `credentials.json` in data/ folder for Google Drive/Gmail OAuth
- Node.js (only needed for WhatsApp import)

## Shell Rules

- `cd` must ALWAYS be its own standalone command. Never combine with `&&` or anything else.
- Never use quoted characters in flag names or arguments.
- When running multi-line Python, write to a temp .py file first. Never use inline `python -c` with complex strings.
- Keep shell commands simple and single-purpose.
