# Plan: Gmail Integration for Perihan

## Overview
Add Gmail thread indexing into ChromaDB, following the same pattern as Google Drive indexing (thread-level LLM summaries, manual "Index Gmail" button, Gmail search as RAG fallback).

## Current State
- OAuth scopes: `drive.readonly` only — **must add `gmail.readonly`**
- Token in `token.json` has only Drive scope — user will need to **re-authenticate** once to grant Gmail permission
- Drive pattern to follow: `index_gdrive_files()` in `services/index_service.py`, SSE streaming progress, summary-only chunks in ChromaDB

## Changes

### 1. `config.py` — Add Gmail scope
- Change `GOOGLE_SCOPES` from `["https://www.googleapis.com/auth/drive.readonly"]` to also include `"https://www.googleapis.com/auth/gmail.readonly"`
- This means existing token.json will need re-auth (scope mismatch triggers new consent)

### 2. `dependencies.py` — Add Gmail service loader
- Add `_gmail_service = None`
- Add `load_gmail_service()` — same pattern as `load_drive_service()` but builds `build("gmail", "v1", credentials=creds)`
- Add `get_gmail()` — returns cached Gmail service

### 3. `utils/gmail_utils.py` — New file: Gmail API helpers
- `gmail_list_all_threads(svc)` — paginate through all threads (skip SPAM/TRASH via `q="-in:spam -in:trash"`)
  - Returns list of `{"id": thread_id, "snippet": ...}`
  - Uses `threads().list()` with pagination
- `gmail_get_thread(svc, thread_id)` — fetch full thread with all messages
  - Returns parsed text: sender, date, subject, body for each message in the thread
  - Extracts plain text body from message parts (handles multipart/alternative)
- `gmail_search(svc, query, max_results=10)` — for RAG fallback
  - Uses Gmail's native search, returns thread snippets + message bodies

### 4. `services/index_service.py` — Add `index_gmail_threads()`
- Same async generator pattern as `index_gdrive_files()`
- Steps per thread:
  1. Fetch thread content via `gmail_get_thread()`
  2. Generate LLM summary (reuse `generate_file_summary()` or a gmail-specific variant)
  3. Upsert into ChromaDB with metadata: `source="gmail"`, `thread_id`, `subject`, `from`, `date`, `is_summary="true"`
- Delete existing gmail chunks before re-indexing (by `source="gmail"` metadata)
- SSE progress events: start → progress per thread → complete

### 5. `routers/index.py` — Add `/index-gmail` endpoint
- `POST /index-gmail` — same SSE streaming pattern as `/index-gdrive`
- Calls `index_service.index_gmail_threads()`

### 6. `routers/drive.py` — Add Gmail status endpoint
- Add `GET /gmail/status` — returns `{"connected": bool}` based on whether token has gmail scope
- Or: fold into existing `/drive/status` → return `{"drive_connected": ..., "gmail_connected": ...}`

### 7. `services/chat_service.py` — Add Gmail fallback search
- Add `gmail_fallback_search()` — same pattern as `drive_fallback_search()`
- Uses Gmail's native search API when ChromaDB results are weak
- Wire into the main RAG pipeline alongside Drive fallback

### 8. `static/index.html` — Frontend changes
- Add "Index Gmail" button in the Index tab (next to "Index Drive")
- Show Gmail connection status in Settings (next to Drive status)
- SSE progress handling — reuse same pattern as Drive indexing
- Add `use_gmail` toggle in Chat options (like `use_drive`)

## File Summary
| File | Action |
|------|--------|
| `config.py` | Add gmail.readonly scope |
| `dependencies.py` | Add Gmail service loader |
| `utils/gmail_utils.py` | **New** — Gmail API helpers |
| `services/index_service.py` | Add `index_gmail_threads()` |
| `routers/index.py` | Add `/index-gmail` endpoint |
| `routers/drive.py` | Add Gmail status check |
| `services/chat_service.py` | Add Gmail fallback search |
| `static/index.html` | Gmail UI (index button, status, chat toggle) |

## Key Considerations
- **Re-auth required**: Adding gmail.readonly scope means user must re-authenticate once. The OAuth flow already handles this — scope mismatch forces new consent.
- **Rate limits**: Gmail API has 250 quota units/second. `threads.list` = 5 units, `threads.get` = 10 units. For large mailboxes (10K+ threads), we should batch and add small delays.
- **Large mailboxes**: Some users have 50K+ threads. We should show clear progress and handle this gracefully. Consider indexing in batches of ~100 threads with progress updates.
- **Thread body extraction**: Gmail messages use multipart MIME. Need to handle text/plain and text/html parts, prefer plain text, strip HTML tags as fallback.
- **Summary generation**: Each thread gets one LLM summary call. For a mailbox with 5000 threads, that's 5000 LLM calls — could take hours. Should warn user in UI.
