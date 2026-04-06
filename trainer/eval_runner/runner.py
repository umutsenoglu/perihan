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
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
TRAINER = Path(__file__).resolve().parent.parent
ROOT = TRAINER.parent
load_dotenv(ROOT / ".env")

import requests

# ---------------------------------------------------------------------------
# Paths & Config
# ---------------------------------------------------------------------------

QA_OUTPUT_FILE = TRAINER / "qa_generator" / "output" / "qa_output.json"
EVAL_RESULTS_FILE = Path(__file__).parent / "output" / "eval_results.json"
COLLECTOR_OUTPUT_DIR = TRAINER / "collector" / "output"

PERIHAN_BASE = "http://localhost:8000"
PERIHAN_CHAT = f"{PERIHAN_BASE}/chat"

# ---------------------------------------------------------------------------
# Cost tracking
# ---------------------------------------------------------------------------

_GEMINI_PRICING = {  # (input_per_1M, output_per_1M)
    "gemini-3.0-flash": (0.50, 3.00),
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-2.0-flash": (0.15, 0.60),
}

total_requests = 0
total_input_tokens = 0
total_output_tokens = 0
total_cost = 0.0


def _calc_cost(model: str, usage) -> float:
    """Calculate cost in USD for a single LLM call. Returns 0 for local models."""
    if not usage:
        return 0.0
    inp = getattr(usage, "prompt_tokens", 0) or 0
    out = getattr(usage, "completion_tokens", 0) or 0
    pricing = _GEMINI_PRICING.get(model)
    if not pricing:
        return 0.0  # Ollama = free
    return (inp * pricing[0] + out * pricing[1]) / 1_000_000

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
    prefix = {"INFO": "->", "OK": "OK", "ERR": "!!", "SKIP": "--", "COST": "$$"}.get(level, "->")
    print(f"  {prefix} {msg}", flush=True)


def calc_tokens(usage) -> str:
    input_tokens = getattr(usage, "prompt_tokens", 0) or 0
    output_tokens = getattr(usage, "completion_tokens", 0) or 0
    return f"in={input_tokens} | out={output_tokens}"


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
# LLM API calls (configured via env vars from TheLoop UI)
# ---------------------------------------------------------------------------

sys.path.insert(0, str(TRAINER))
from model_helper import get_model_from_env

BENCHMARK_MODEL, BENCHMARK_PROVIDER, _benchmark_client = get_model_from_env("benchmark")
JUDGE_MODEL, JUDGE_PROVIDER, _judge_client = get_model_from_env("judge")


def _model_slug(name: str) -> str:
    """Sanitize model name for use as a JSON key fragment."""
    return name.replace(":", "-").replace("/", "-")


BENCHMARK_LABEL = f"benchmark-{_model_slug(BENCHMARK_MODEL)}"

log(f"Benchmark model: {BENCHMARK_MODEL} ({BENCHMARK_PROVIDER})", "INFO")
log(f"Benchmark label: {BENCHMARK_LABEL}", "INFO")
log(f"Judge model: {JUDGE_MODEL} ({JUDGE_PROVIDER})", "INFO")


async def call_llm(prompt: str, temperature: float = 0.3, role: str = "benchmark") -> tuple[str, object]:
    """Call the configured LLM and return (response_text, usage)."""
    global total_requests, total_input_tokens, total_output_tokens, total_cost
    client = _benchmark_client if role == "benchmark" else _judge_client
    model = BENCHMARK_MODEL if role == "benchmark" else JUDGE_MODEL

    resp = await asyncio.to_thread(
        client.chat.completions.create,
        model=model,
        temperature=temperature,
        messages=[{"role": "user", "content": prompt}],
    )

    usage = resp.usage
    total_requests += 1
    inp = getattr(usage, "prompt_tokens", 0) or 0 if usage else 0
    out = getattr(usage, "completion_tokens", 0) or 0 if usage else 0
    total_input_tokens += inp
    total_output_tokens += out
    cost = _calc_cost(model, usage)
    total_cost += cost
    cost_str = f" ${cost:.4f}" if cost > 0 else ""
    log(f"LLM #{total_requests} ({role}): in={inp} | out={out}{cost_str} [total: ${total_cost:.4f}]", "COST")
    # Structured cost line for UI parsing
    print(json.dumps({"__cost__": True, "total_cost": total_cost, "total_input_tokens": total_input_tokens, "total_output_tokens": total_output_tokens}), flush=True)

    return resp.choices[0].message.content.strip(), usage


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
    text, _ = await call_llm(prompt, temperature=0.1, role="benchmark")
    return text


# ---------------------------------------------------------------------------
# Perihan: ask via /chat
# ---------------------------------------------------------------------------

def ask_perihan(question: str, max_retries: int = 3) -> str:
    for attempt in range(max_retries):
        try:
            resp = requests.post(
                PERIHAN_CHAT,
                params={"question": question, "use_drive": "false", "deep_think": "true"},
                timeout=180,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("reply") or data.get("answer") or str(data)
        except requests.exceptions.ConnectionError:
            return "[ERROR: Could not connect to Perihan at localhost:8000]"
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else 0
            if status in (429, 500, 502, 503) and attempt < max_retries - 1:
                wait = 2 ** attempt * 5  # 5s, 10s, 20s
                time.sleep(wait)
                continue
            return f"[ERROR: HTTP {status} — {e}]"
        except Exception as e:
            return f"[ERROR: {e}]"
    return "[ERROR: max retries exceeded]"


# ---------------------------------------------------------------------------
# Judge
# ---------------------------------------------------------------------------

async def judge(question: str, expected: str, reply: str) -> tuple[int, str]:
    prompt = JUDGE_PROMPT.format(question=question, expected=expected, reply=reply)
    text, _ = await call_llm(prompt, temperature=0.0, role="judge")
    score_match = re.search(r"SCORE:\s*([012])", text)
    reason_match = re.search(r"REASON:\s*(.+)", text)
    score = int(score_match.group(1)) if score_match else 0
    reason = reason_match.group(1).strip() if reason_match else text[:120]
    return score, reason


# ---------------------------------------------------------------------------
# Run modes
# ---------------------------------------------------------------------------

async def run_benchmark(only_ids: list[str] | None = None):
    """Run benchmark: send each question + source docs to LLM, judge the answer.
    Skips questions that already have a benchmark score."""
    questions = load_questions()
    results = load_results()

    if only_ids:
        questions = [q for q in questions if q["id"] in only_ids]

    # Skip already benchmarked (for this specific model)
    pending = [q for q in questions if q["id"] not in results
               or BENCHMARK_LABEL not in results[q["id"]]]

    if not pending:
        log("All questions already benchmarked!", "OK")
        print_summary(results, BENCHMARK_LABEL)
        return

    log(f"Benchmark ({BENCHMARK_LABEL}): {len(pending)} questions to process ({len(questions) - len(pending)} already done)")

    sem = asyncio.Semaphore(1)
    lock = asyncio.Lock()

    async def process_one(q):
        qid = q["id"]
        short_q = q["question"][:60]

        async with sem:
            log(f"[{qid}] {short_q}")
            reply = await ask_benchmark(q["question"], q.get("source_documents", []))
            score, reason = await judge(q["question"], q["answer"], reply)
            log(f"[{qid}] Score: {score} | {reason}", "OK" if score == 2 else "INFO")

            async with lock:
                if qid not in results:
                    results[qid] = {
                        "question": q["question"],
                        "expected": q["answer"],
                        "difficulty": q.get("difficulty"),
                        "strategy": q.get("strategy"),
                        "source_documents": q.get("source_documents", []),
                    }
                results[qid][BENCHMARK_LABEL] = {
                    "reply": reply,
                    "score": score,
                    "reason": reason,
                    "model": BENCHMARK_MODEL,
                    "timestamp": datetime.now().isoformat(),
                }
                save_results(results)

    try:
        await asyncio.gather(*[process_one(q) for q in pending])
    except KeyboardInterrupt:
        log("Interrupted — progress saved.", "INFO")
        save_results(results)
        print_summary(results, BENCHMARK_LABEL)
        return

    print_summary(results, BENCHMARK_LABEL)


async def run_perihan(only_ids: list[str] | None = None, only_low_scores: bool = False):
    """Run Perihan eval: only questions that have benchmark scores.
    Always re-runs — overwrites previous perihan scores.
    Runs up to 5 questions concurrently."""
    questions = load_questions()
    results = load_results()

    if only_ids:
        questions = [q for q in questions if q["id"] in only_ids]

    # Only questions with at least one benchmark score
    benchmarked_ids = {qid for qid, r in results.items()
                       if any(k.startswith("benchmark-") for k in r)}
    questions = [q for q in questions if q["id"] in benchmarked_ids]

    # Filter to low-scoring (0 or 1) + unanswered questions
    if only_low_scores:
        needs_run = {qid for qid, r in results.items()
                     if "perihan" not in r or r["perihan"].get("score", 0) < 2}
        before = len(questions)
        questions = [q for q in questions if q["id"] in needs_run]
        log(f"Low-scores filter: {len(questions)} of {before} questions (low score + unanswered)")

    if not questions:
        log("No benchmarked questions found. Run 'benchmark' mode first.", "ERR")
        return

    log(f"Perihan: {len(questions)} questions to process (all will be re-evaluated)")

    sem = asyncio.Semaphore(3)
    completed = 0
    lock = asyncio.Lock()

    async def process_one(q):
        nonlocal completed
        qid = q["id"]
        short_q = q["question"][:60]

        async with sem:
            log(f"[{qid}] {short_q}")
            reply = await asyncio.to_thread(ask_perihan, q["question"])
            score, reason = await judge(q["question"], q["answer"], reply)
            log(f"[{qid}] Score: {score} | {reason}", "OK" if score == 2 else "INFO")

            async with lock:
                completed += 1
                results[qid]["perihan"] = {
                    "reply": reply,
                    "score": score,
                    "reason": reason,
                    "timestamp": datetime.now().isoformat(),
                }
                save_results(results)

    try:
        await asyncio.gather(*[process_one(q) for q in questions])
    except KeyboardInterrupt:
        log("Interrupted — progress saved.", "INFO")
        save_results(results)
        print_summary(results, "perihan")
        return

    print_summary(results, "perihan")


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def _find_benchmark_keys(results: dict) -> list[str]:
    """Find all unique benchmark-* keys across all questions."""
    keys = set()
    for r in results.values():
        for k in r:
            if k.startswith("benchmark-"):
                keys.add(k)
    return sorted(keys)


def print_summary(results: dict, mode: str | None = None):
    """Print score summary."""
    benchmark_keys = _find_benchmark_keys(results)
    perihan_scores = []

    for qid, r in sorted(results.items()):
        p = r.get("perihan", {}).get("score")
        if p is not None:
            perihan_scores.append(p)

    print()
    print("  " + "=" * 60)

    for bk in benchmark_keys:
        scores = [r.get(bk, {}).get("score") for r in results.values()]
        scores = [s for s in scores if s is not None]
        if scores:
            total = sum(scores)
            max_s = len(scores) * 2
            pct = total / max_s * 100 if max_s else 0
            model = bk.replace("benchmark-", "")
            print(f"  {bk}: {total}/{max_s} ({pct:.1f}%) — {len(scores)} questions")

    if perihan_scores:
        total = sum(perihan_scores)
        max_s = len(perihan_scores) * 2
        pct = total / max_s * 100 if max_s else 0
        print(f"  Perihan RAG: {total}/{max_s} ({pct:.1f}%) — {len(perihan_scores)} questions")

    # Side-by-side: compare perihan vs each benchmark
    for bk in benchmark_keys:
        both = []
        for qid, r in sorted(results.items()):
            b = r.get(bk, {}).get("score")
            p = r.get("perihan", {}).get("score")
            if b is not None and p is not None:
                both.append((qid, r, bk))
        if both:
            model = bk.replace("benchmark-", "")
            print()
            print(f"  vs {model} ({len(both)} questions):")
            print(f"  {'ID':<8} {'Bench':>5} {'Perihan':>7}  Question")
            print(f"  {'---':<8} {'---':>5} {'---':>7}  ---")
            wins = draws = losses = 0
            for qid, r, _ in both:
                b = r[bk]["score"]
                p = r["perihan"]["score"]
                marker = ""
                if p > b:
                    wins += 1
                    marker = " <-- RAG wins"
                elif p < b:
                    losses += 1
                    marker = f" <-- {model} wins"
                else:
                    draws += 1
                short_q = r["question"][:45]
                print(f"  {qid:<8} {b:>5} {p:>7}  {short_q}{marker}")
            print()
            print(f"  RAG wins: {wins} | Draws: {draws} | {model} wins: {losses}")

    cost_str = f" | Cost: ${total_cost:.4f}" if total_cost > 0 else ""
    print(f"  Total LLM requests: {total_requests} | Tokens: {total_input_tokens:,} in / {total_output_tokens:,} out{cost_str}")
    print("  " + "=" * 60)
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    args = [a for a in sys.argv[1:]]
    if not args:
        print("  Usage:")
        print(f"    python runner.py benchmark              # score {BENCHMARK_MODEL} with raw docs (skips done)")
        print("    python runner.py perihan                # score Perihan RAG (always re-runs)")
        print("    python runner.py perihan --low-scores   # re-run only questions scored 0 or 1")
        print("    python runner.py benchmark Q0001        # specific questions")
        print("    python runner.py report                 # side-by-side report")
        sys.exit(0)

    mode = args[0].lower()
    low_scores = "--low-scores" in args
    only_ids = [a.upper() for a in args[1:] if not a.startswith("--")] or None

    try:
        if mode == "benchmark":
            asyncio.run(run_benchmark(only_ids))
        elif mode == "perihan":
            asyncio.run(run_perihan(only_ids, only_low_scores=low_scores))
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
