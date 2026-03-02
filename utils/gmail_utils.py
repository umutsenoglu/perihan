import base64
import email.utils
from html import unescape
import re


def gmail_list_all_threads(svc, max_threads: int = 500) -> list:
    """Paginate through Gmail threads (skip SPAM/TRASH).

    Returns list of {"id": thread_id, "snippet": ...}.
    """
    threads = []
    page_token = None
    while True:
        kwargs = {
            "userId": "me",
            "q": "-in:spam -in:trash",
            "maxResults": min(100, max_threads - len(threads)),
        }
        if page_token:
            kwargs["pageToken"] = page_token
        result = svc.users().threads().list(**kwargs).execute()
        for t in result.get("threads", []):
            threads.append({"id": t["id"], "snippet": t.get("snippet", "")})
        page_token = result.get("nextPageToken")
        if not page_token or len(threads) >= max_threads:
            break
    return threads


def _extract_text_from_parts(parts) -> str:
    """Recursively extract plain text from MIME message parts."""
    texts = []
    for part in parts:
        mime = part.get("mimeType", "")
        if mime == "text/plain":
            data = part.get("body", {}).get("data", "")
            if data:
                texts.append(base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore"))
        elif mime == "text/html" and not texts:
            # Fallback: strip HTML tags if no plain text found
            data = part.get("body", {}).get("data", "")
            if data:
                html = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
                text = re.sub(r"<[^>]+>", " ", unescape(html))
                text = re.sub(r"\s+", " ", text).strip()
                texts.append(text)
        elif "parts" in part:
            texts.append(_extract_text_from_parts(part["parts"]))
    return "\n".join(t for t in texts if t)


def _get_header(headers: list, name: str) -> str:
    """Get a header value by name from a list of message headers."""
    for h in headers:
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def gmail_get_thread(svc, thread_id: str) -> dict:
    """Fetch full thread and return parsed content.

    Returns {"id", "subject", "messages": [{"from", "date", "body"}]}.
    """
    thread = svc.users().threads().get(userId="me", id=thread_id, format="full").execute()
    messages = []
    subject = ""
    for msg in thread.get("messages", []):
        headers = msg.get("payload", {}).get("headers", [])
        msg_subject = _get_header(headers, "Subject")
        if not subject and msg_subject:
            subject = msg_subject
        sender = _get_header(headers, "From")
        date_str = _get_header(headers, "Date")

        # Extract body
        payload = msg.get("payload", {})
        body = ""
        if "parts" in payload:
            body = _extract_text_from_parts(payload["parts"])
        else:
            data = payload.get("body", {}).get("data", "")
            if data:
                body = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")

        messages.append({
            "from": sender,
            "date": date_str,
            "body": body[:3000],  # cap per-message body
        })

    return {"id": thread_id, "subject": subject, "messages": messages}


def gmail_format_thread_text(thread_data: dict) -> str:
    """Format a parsed thread into readable text for indexing."""
    lines = [f"Subject: {thread_data['subject']}", ""]
    for msg in thread_data["messages"]:
        lines.append(f"From: {msg['from']}")
        lines.append(f"Date: {msg['date']}")
        lines.append(msg["body"])
        lines.append("---")
    return "\n".join(lines)


def gmail_search(svc, query: str, max_results: int = 10) -> list:
    """Search Gmail using native search. Returns list of thread dicts with content."""
    result = svc.users().threads().list(
        userId="me", q=query, maxResults=max_results
    ).execute()
    threads = []
    for t in result.get("threads", []):
        thread_data = gmail_get_thread(svc, t["id"])
        text = gmail_format_thread_text(thread_data)
        threads.append({
            "id": t["id"],
            "subject": thread_data["subject"],
            "content": text[:5000],
        })
    return threads
