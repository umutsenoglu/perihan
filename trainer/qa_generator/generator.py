"""Core QA generation — sends document packages to LLM and parses QA responses."""

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from model_helper import get_model_from_env

LLM_MODEL, _LLM_PROVIDER, _llm_client = get_model_from_env("qa_generator")

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


# Running totals
total_requests = 0


async def generate_qas(prompt: str) -> list[dict]:
    """Send a prompt to the LLM and parse the QA JSON response. Retries on failure."""
    import asyncio
    global total_requests

    last_error = None

    for attempt in range(1 + MAX_RETRIES):
        resp = await asyncio.to_thread(
            _llm_client.chat.completions.create,
            model=LLM_MODEL,
            temperature=0.3,
            messages=[
                {"role": "system", "content": "You are a QA generator. Always respond with valid JSON."},
                {"role": "user", "content": prompt},
            ],
        )

        total_requests += 1
        usage = resp.usage
        in_t = getattr(usage, "prompt_tokens", 0) or 0
        out_t = getattr(usage, "completion_tokens", 0) or 0
        print(f"    LLM #{total_requests}: in={in_t} | out={out_t}")

        raw_text = resp.choices[0].message.content.strip()

        parsed = _try_parse_json(raw_text)
        if parsed:
            return parsed.get("questions", [])

        last_error = f"JSON parse failed (len={len(raw_text)})"

    raise ValueError(last_error)
