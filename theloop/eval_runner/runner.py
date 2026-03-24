"""
QA Eval Runner
==============
Evaluates Perihan RAG vs Gemini benchmark (raw docs in prompt).

Usage:
  python runner.py benchmark          # score Gemini with raw source docs (skips already done)
  python runner.py perihan            # score Perihan RAG (re-runs every time, overwrites previous)
  python runner.py benchmark Q0001   # run specific questions
  python runner.py report             # print side-by-side report

Flow:
  benchmark mode: load source docs -> send question + docs to Gemini -> judge -> save
                  Skips questions that already have a benchmark score.
  perihan mode:   send question to Perihan /chat -> judge -> save
                  Only runs questions that have benchmark scores.
                  Always re-runs (overwrites previous perihan scores).
  CTRL+C saves progress immediately.
"""

import asyncio
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
THELOOP = Path(__file__).resolve().parent.parent
ROOT = THELOOP.parent
load_dotenv(ROOT / ".env")

import httpx
import requests

# ---------------------------------------------------------------------------
# Paths & Config
# ---------------------------------------------------------------------------

QA_OUTPUT_FILE = THELOOP / "qa_generator" / "output" / "qa_output.json"
EVAL_RESULTS_FILE = Path(__file__).parent / "output" / "eval_results.json"
COLLECTOR_OUTPUT_DIR = THELOOP / "collector" / "output"

PERIHAN_BASE = "http://localhost:8000"
PERIHAN_CHAT = f"{PERIHAN_BASE}/chat"

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"

JUDGE_MODEL = "gemini-2.5-flash"

# Pricing (Gemini 2.5 Flash)
PRICE_INPUT = 0.15 / 1_000_000
PRICE_OUTPUT = 0.60 / 1_000_000
PRICE_THINKING = 3.50 / 1_000_000

# Running totals
total_cost = 0.0
total_requests = 0

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

JUDGE_PROMPT = """\
You are evaluating a document assistant's answer.

Question: {question}
Expected answer: {expected}
Assistant's response: {reply}

Score the response:
2 = Correctly answers the question that was asked
1 = Partially correct, or contains a factual error alongside correct info
0 = Wrong, irrelevant, or hallucinated

Important rules:
- Judge based on what the question asked, not on every detail in the expected answer.
- Extra details in the expected answer that were NOT asked about do NOT lower the score.

Reply in this exact format:
SCORE: <0|1|2>
REASON: <one sentence>"""

BENCHMARK_PROMPT = """\
Answer the following question using ONLY the documents provided below.
If the answer is not in the documents, say "I don't have that information."

## Documents

{documents}

## Question

{question}"""

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def log(msg: str, level: str = "INFO"):
    ts = datetime.now().strftime("%H:%M:%S")
    prefix = {"INFO": "->", "OK": "OK", "ERR": "!!", "SKIP": "--", "COST": "$$"}.get(level, "->")
    print(f"  {prefix} [{ts}] {msg}", flush=True)


def calc_cost(usage: dict) -> tuple[float, str]:
    input_tokens = usage.get("promptTokenCount", 0)
    output_tokens = usage.get("candidatesTokenCount", 0)
    thinking_tokens = usage.get("thoughtsTokenCount", 0)
    cost = (input_tokens * PRICE_INPUT
            + output_tokens * PRICE_OUTPUT
            + thinking_tokens * PRICE_THINKING)
    parts = [f"in={input_tokens}"]
    if thinking_tokens:
        parts.append(f"think={thinking_tokens}")
    parts.append(f"out={output_tokens}")
    parts.append(f"${cost:.4f}")
    return cost, " | ".join(parts)


def load_questions() -> list[dict]:
    if not QA_OUTPUT_FILE.exists():
        return []
    return json.loads(QA_OUTPUT_FILE.read_text(encoding="utf-8"))


def load_results() -> dict:
    if not EVAL_RESULTS_FILE.exists():
        return {}
    try:
        return json.loads(EVAL_RESULTS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_results(results: dict):
    EVAL_RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    EVAL_RESULTS_FILE.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def read_source_document(path: str) -> str | None:
    full_path = COLLECTOR_OUTPUT_DIR / path
    if not full_path.exists():
        return None
    try:
        return full_path.read_text(encoding="utf-8")
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Gemini API calls
# ---------------------------------------------------------------------------

async def call_gemini(prompt: str, temperature: float = 0.3) -> tuple[str, dict]:
    """Call Gemini and return (response_text, usage_metadata)."""
    global total_cost, total_requests

    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.post(
            f"{GEMINI_URL}?key={GEMINI_API_KEY}",
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": temperature,
                    "maxOutputTokens": 8192,
                },
            },
        )
        resp.raise_for_status()
        data = resp.json()

    usage = data.get("usageMetadata", {})
    cost, summary = calc_cost(usage)
    total_requests += 1
    total_cost += cost
    log(f"Gemini #{total_requests}: {summary} (total: ${total_cost:.4f})", "COST")

    candidate = data["candidates"][0]
    text = candidate["content"]["parts"][0]["text"]
    return text, usage


# ---------------------------------------------------------------------------
# Benchmark: ask Gemini with raw docs
# ---------------------------------------------------------------------------

async def ask_benchmark(question: str, source_docs: list[str]) -> str:
    """Send question + raw source documents to Gemini."""
    doc_texts = []
    for path in source_docs:
        content = read_source_document(path)
        if content:
            doc_texts.append(f"### {path}\n{content}")

    if not doc_texts:
        return "[ERROR: No source documents found]"

    documents = "\n\n---\n\n".join(doc_texts)
    prompt = BENCHMARK_PROMPT.format(documents=documents, question=question)
    text, _ = await call_gemini(prompt, temperature=0.1)
    return text


# ---------------------------------------------------------------------------
# Perihan: ask via /chat
# ---------------------------------------------------------------------------

def ask_perihan(question: str) -> str:
    try:
        resp = requests.post(
            PERIHAN_CHAT,
            params={"question": question, "use_drive": "false", "deep_think": "true"},
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("reply") or data.get("answer") or str(data)
    except requests.exceptions.ConnectionError:
        return "[ERROR: Could not connect to Perihan at localhost:8000]"
    except Exception as e:
        return f"[ERROR: {e}]"


# ---------------------------------------------------------------------------
# Judge
# ---------------------------------------------------------------------------

async def judge(question: str, expected: str, reply: str) -> tuple[int, str]:
    prompt = JUDGE_PROMPT.format(question=question, expected=expected, reply=reply)
    text, _ = await call_gemini(prompt, temperature=0.0)
    score_match = re.search(r"SCORE:\s*([012])", text)
    reason_match = re.search(r"REASON:\s*(.+)", text)
    score = int(score_match.group(1)) if score_match else 0
    reason = reason_match.group(1).strip() if reason_match else text[:120]
    return score, reason


# ---------------------------------------------------------------------------
# Run modes
# ---------------------------------------------------------------------------

async def run_benchmark(only_ids: list[str] | None = None):
    """Run benchmark: send each question + source docs to Gemini, judge the answer.
    Skips questions that already have a benchmark score."""
    questions = load_questions()
    results = load_results()

    if only_ids:
        questions = [q for q in questions if q["id"] in only_ids]

    # Skip already benchmarked
    pending = [q for q in questions if q["id"] not in results
               or "benchmark" not in results[q["id"]]]

    if not pending:
        log("All questions already benchmarked!", "OK")
        print_summary(results, "benchmark")
        return

    log(f"Benchmark: {len(pending)} questions to process ({len(questions) - len(pending)} already done)")

    try:
        for i, q in enumerate(pending, 1):
            qid = q["id"]
            short_q = q["question"][:60]
            log(f"[{i}/{len(pending)}] {qid}: {short_q}")

            reply = await ask_benchmark(q["question"], q.get("source_documents", []))
            score, reason = await judge(q["question"], q["answer"], reply)

            log(f"  Score: {score} | {reason}", "OK" if score == 2 else "INFO")

            if qid not in results:
                results[qid] = {
                    "question": q["question"],
                    "expected": q["answer"],
                    "difficulty": q.get("difficulty"),
                    "strategy": q.get("strategy"),
                    "source_documents": q.get("source_documents", []),
                }
            results[qid]["benchmark"] = {
                "reply": reply,
                "score": score,
                "reason": reason,
                "timestamp": datetime.now().isoformat(),
            }
            save_results(results)

    except KeyboardInterrupt:
        log("Interrupted — progress saved.", "INFO")
        save_results(results)
        print_summary(results, "benchmark")
        return

    print_summary(results, "benchmark")


async def run_perihan(only_ids: list[str] | None = None):
    """Run Perihan eval: only questions that have benchmark scores.
    Always re-runs — overwrites previous perihan scores."""
    questions = load_questions()
    results = load_results()

    if only_ids:
        questions = [q for q in questions if q["id"] in only_ids]

    # Only questions with benchmark scores
    benchmarked_ids = {qid for qid, r in results.items() if "benchmark" in r}
    questions = [q for q in questions if q["id"] in benchmarked_ids]

    if not questions:
        log("No benchmarked questions found. Run 'benchmark' mode first.", "ERR")
        return

    log(f"Perihan: {len(questions)} questions to process (all will be re-evaluated)")

    try:
        for i, q in enumerate(questions, 1):
            qid = q["id"]
            short_q = q["question"][:60]
            log(f"[{i}/{len(questions)}] {qid}: {short_q}")

            reply = ask_perihan(q["question"])
            score, reason = await judge(q["question"], q["answer"], reply)

            log(f"  Score: {score} | {reason}", "OK" if score == 2 else "INFO")

            results[qid]["perihan"] = {
                "reply": reply,
                "score": score,
                "reason": reason,
                "timestamp": datetime.now().isoformat(),
            }
            save_results(results)

    except KeyboardInterrupt:
        log("Interrupted — progress saved.", "INFO")
        save_results(results)
        print_summary(results, "perihan")
        return

    print_summary(results, "perihan")


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def print_summary(results: dict, mode: str | None = None):
    """Print score summary."""
    benchmark_scores = []
    perihan_scores = []
    both = []

    for qid, r in sorted(results.items()):
        b = r.get("benchmark", {}).get("score")
        p = r.get("perihan", {}).get("score")
        if b is not None:
            benchmark_scores.append(b)
        if p is not None:
            perihan_scores.append(p)
        if b is not None and p is not None:
            both.append((qid, r))

    print()
    print("  " + "=" * 60)

    if benchmark_scores:
        total = sum(benchmark_scores)
        max_s = len(benchmark_scores) * 2
        pct = total / max_s * 100 if max_s else 0
        print(f"  Gemini Benchmark: {total}/{max_s} ({pct:.1f}%) — {len(benchmark_scores)} questions")

    if perihan_scores:
        total = sum(perihan_scores)
        max_s = len(perihan_scores) * 2
        pct = total / max_s * 100 if max_s else 0
        print(f"  Perihan RAG:      {total}/{max_s} ({pct:.1f}%) — {len(perihan_scores)} questions")

    if both:
        print()
        print(f"  Side-by-side ({len(both)} questions):")
        print(f"  {'ID':<8} {'Bench':>5} {'Perihan':>7}  Question")
        print(f"  {'---':<8} {'---':>5} {'---':>7}  ---")
        wins = draws = losses = 0
        for qid, r in both:
            b = r["benchmark"]["score"]
            p = r["perihan"]["score"]
            marker = ""
            if p > b:
                wins += 1
                marker = " <-- RAG wins"
            elif p < b:
                losses += 1
                marker = " <-- Gemini wins"
            else:
                draws += 1
            short_q = r["question"][:45]
            print(f"  {qid:<8} {b:>5} {p:>7}  {short_q}{marker}")
        print()
        print(f"  RAG wins: {wins} | Draws: {draws} | Gemini wins: {losses}")

    print(f"  Total API cost this session: ${total_cost:.4f}")
    print("  " + "=" * 60)
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    if not GEMINI_API_KEY:
        print("  !! GEMINI_API_KEY not set.")
        sys.exit(1)

    args = [a for a in sys.argv[1:]]
    if not args:
        print("  Usage:")
        print("    python runner.py benchmark          # score Gemini with raw docs (skips done)")
        print("    python runner.py perihan            # score Perihan RAG (always re-runs)")
        print("    python runner.py benchmark Q0001    # specific questions")
        print("    python runner.py report             # side-by-side report")
        sys.exit(0)

    mode = args[0].lower()
    only_ids = [a.upper() for a in args[1:]] or None

    try:
        if mode == "benchmark":
            asyncio.run(run_benchmark(only_ids))
        elif mode == "perihan":
            asyncio.run(run_perihan(only_ids))
        elif mode == "report":
            results = load_results()
            if not results:
                print("  No results yet. Run benchmark first.")
            else:
                print_summary(results)
        else:
            print(f"  Unknown mode: {mode}. Use 'benchmark', 'perihan', or 'report'.")
            sys.exit(1)
    except KeyboardInterrupt:
        log("Interrupted — progress saved.", "INFO")
        results = load_results()
        if results:
            print_summary(results, mode)


if __name__ == "__main__":
    main()
