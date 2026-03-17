"""Core QA generation — sends document packages to Gemini and parses QA responses."""

import json
import os
import re
import httpx

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"

MAX_RETRIES = 2


def _try_parse_json(raw: str) -> dict | None:
    """Try multiple strategies to parse JSON from LLM output."""
    raw = raw.strip()

    # Strip markdown code fences
    if raw.startswith("```"):
        raw = re.sub(r"^```\w*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)

    # Try direct parse
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Try fixing truncated JSON by closing brackets
    for suffix in ['}]}', '"}]}', '"}]}', '..."}]}']:
        try:
            return json.loads(raw + suffix)
        except json.JSONDecodeError:
            continue

    # Try extracting the first valid JSON object
    match = re.search(r'\{[\s\S]*"questions"\s*:\s*\[', raw)
    if match:
        # Find each complete question object
        questions = []
        for m in re.finditer(r'\{\s*"question"\s*:', raw):
            start = m.start()
            depth = 0
            i = start
            while i < len(raw):
                if raw[i] == '{':
                    depth += 1
                elif raw[i] == '}':
                    depth -= 1
                    if depth == 0:
                        try:
                            q = json.loads(raw[start:i+1])
                            questions.append(q)
                        except json.JSONDecodeError:
                            pass
                        break
                i += 1
        if questions:
            return {"questions": questions}

    return None


async def generate_qas(prompt: str) -> list[dict]:
    """Send a prompt to Gemini and parse the QA JSON response. Retries on failure."""
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY not set")

    last_error = None

    for attempt in range(1 + MAX_RETRIES):
        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(
                f"{GEMINI_URL}?key={GEMINI_API_KEY}",
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": 0.3,
                        "maxOutputTokens": 32768,
                        "responseMimeType": "application/json",
                    },
                },
            )
            resp.raise_for_status()
            data = resp.json()

            candidate = data["candidates"][0]
            raw_text = candidate["content"]["parts"][0]["text"]
            finish_reason = candidate.get("finishReason", "")

            parsed = _try_parse_json(raw_text)
            if parsed:
                return parsed.get("questions", [])

            last_error = f"JSON parse failed (finishReason={finish_reason}, len={len(raw_text)})"

    raise ValueError(last_error)
