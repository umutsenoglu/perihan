"""
Perihan QA Runner
=================
Standalone script — run with: python tests/qa_runner.py

Flow:
  1. Parse notes/QA.md → extract questions, expected answers, categories, sources
  2. For each question: POST to http://localhost:8765/chat
  3. For each response: call Gemini judge → score 0/1/2 + one-line reason
  4. Save results to tests/results/run_YYYY-MM-DD_HH-MM.json
  5. Compare with previous run → generate diff
  6. Write tests/results/latest.md — human-readable report
"""

import os
import re
import json
import sys
from datetime import datetime
from pathlib import Path

import requests
from openai import OpenAI

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT = Path(__file__).parent.parent
QA_FILE = ROOT / "notes" / "QA.md"
RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

PERIHAN_BASE = "http://localhost:8000"
PERIHAN_URL = f"{PERIHAN_BASE}/chat"

JUDGE_MODEL = "gemini-2.5-flash"

JUDGE_PROMPT = """\
You are evaluating a RAG assistant called Perihan.

Question: {question}
Expected answer: {expected}
Perihan's response: {reply}

Score the response:
2 = Correct and complete
1 = Partially correct or correct but missing details
0 = Wrong, irrelevant, or hallucinated

For questions where the expected answer is "System should say it doesn't know", \
score 2 if Perihan appropriately says it doesn't have that information, \
score 0 if it fabricates an answer.

Reply in this exact format:
SCORE: <0|1|2>
REASON: <one sentence>"""


# ---------------------------------------------------------------------------
# Gemini judge client
# ---------------------------------------------------------------------------

def get_judge_client() -> OpenAI:
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        print("ERROR: GEMINI_API_KEY environment variable not set.", file=sys.stderr)
        sys.exit(1)
    return OpenAI(
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        api_key=api_key,
    )


# ---------------------------------------------------------------------------
# QA.md parser
# ---------------------------------------------------------------------------

def parse_qa_file(path: Path) -> list[dict]:
    """Parse QA.md and return list of question dicts."""
    text = path.read_text(encoding="utf-8")
    questions = []

    # Split text into category sections
    # Each section starts with "## Category N: ..."
    category_sections = re.split(r"(?=^## Category \d+:)", text, flags=re.MULTILINE)

    for section in category_sections:
        # Extract category name from heading
        cat_match = re.match(r"^## Category \d+:\s*(.+)", section.strip())
        category = cat_match.group(1).strip() if cat_match else "Uncategorized"

        # Find all question blocks in this section
        # A block starts with **QN:** and ends before the next **QN:** or end of section
        block_pattern = re.compile(
            r"\*\*(Q\d+):\*\*\s*(.*?)(?=\n\*\*Q\d+:\*\*|\Z)",
            re.DOTALL,
        )
        for m in block_pattern.finditer(section):
            q_id = m.group(1)
            block = m.group(2).strip()

            # Extract question text (first line of the block)
            lines = block.split("\n")
            question_text = lines[0].strip()

            # Extract Expected answer
            expected = ""
            exp_match = re.search(r"\*\*Expected:\*\*\s*(.+?)(?=\n-\s*\*\*|\Z)", block, re.DOTALL)
            if exp_match:
                expected = exp_match.group(1).strip()

            # Extract Source
            source = ""
            src_match = re.search(r"\*\*Source:\*\*\s*(.+)", block)
            if src_match:
                source = src_match.group(1).strip()

            questions.append({
                "id": q_id,
                "category": category,
                "question": question_text,
                "expected": expected,
                "source": source,
            })

    return questions


# ---------------------------------------------------------------------------
# Ask Perihan
# ---------------------------------------------------------------------------

def get_perihan_model() -> str:
    """Fetch the currently active model from Perihan's /current-model endpoint."""
    try:
        resp = requests.get(f"{PERIHAN_BASE}/current-model", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return data.get("model", "unknown")
    except Exception:
        return "unknown"


def ask_perihan(question: str) -> str:
    """POST to /chat and return the reply text."""
    try:
        resp = requests.post(
            PERIHAN_URL,
            params={"question": question, "use_drive": "false"},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        # Response format: {"reply": "...", ...}
        return data.get("reply") or data.get("answer") or str(data)
    except requests.exceptions.ConnectionError:
        return "[ERROR: Could not connect to Perihan server at localhost:8765]"
    except Exception as e:
        return f"[ERROR: {e}]"


# ---------------------------------------------------------------------------
# Gemini judge
# ---------------------------------------------------------------------------

def judge(client: OpenAI, question: str, expected: str, reply: str) -> tuple[int, str]:
    """Ask Gemini to score Perihan's reply. Returns (score, reason)."""
    prompt = JUDGE_PROMPT.format(question=question, expected=expected, reply=reply)
    try:
        resp = client.chat.completions.create(
            model=JUDGE_MODEL,
            temperature=0.0,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.choices[0].message.content.strip()
        score_match = re.search(r"SCORE:\s*([012])", text)
        reason_match = re.search(r"REASON:\s*(.+)", text)
        score = int(score_match.group(1)) if score_match else 0
        reason = reason_match.group(1).strip() if reason_match else text[:120]
        return score, reason
    except Exception as e:
        return 0, f"Judge error: {e}"


# ---------------------------------------------------------------------------
# Diff logic
# ---------------------------------------------------------------------------

def load_previous_run(current_path: Path) -> dict | None:
    """Return the second-most-recent run JSON, or None."""
    runs = sorted(RESULTS_DIR.glob("run_*.json"))
    # Exclude the file we just wrote
    others = [r for r in runs if r != current_path]
    if not others:
        return None
    try:
        return json.loads(others[-1].read_text(encoding="utf-8"))
    except Exception:
        return None


def compute_diff(current: dict, previous: dict) -> dict:
    """Compare per-question scores between two runs."""
    prev_by_id = {r["id"]: r for r in previous.get("results", [])}
    improvements = []
    regressions = []

    for r in current.get("results", []):
        qid = r["id"]
        new_score = r["score"]
        old = prev_by_id.get(qid)
        if old is None:
            continue
        old_score = old["score"]
        if new_score > old_score:
            improvements.append({
                "id": qid,
                "old": old_score,
                "new": new_score,
                "reason": r["reason"],
            })
        elif new_score < old_score:
            regressions.append({
                "id": qid,
                "old": old_score,
                "new": new_score,
                "reason": r["reason"],
            })

    return {"improvements": improvements, "regressions": regressions}


# ---------------------------------------------------------------------------
# Report generator
# ---------------------------------------------------------------------------

def build_report(run: dict, previous: dict | None, diff: dict | None) -> str:
    run_id = run["run_id"]
    total = run["total_score"]
    max_s = run["max_score"]
    pct = run["pct"]
    perihan_model = run.get("perihan_model", "unknown")
    judge_model = run.get("judge_model", JUDGE_MODEL)

    prev_line = ""
    change_line = ""
    if previous:
        p_total = previous["total_score"]
        p_max = previous["max_score"]
        p_pct = previous["pct"]
        p_model = previous.get("perihan_model", "unknown")
        delta = total - p_total
        sign = "+" if delta >= 0 else ""
        prev_line = f"  |  Previous: {p_total}/{p_max} ({p_pct:.1f}%) [{p_model}]"
        change_line = f"  |  Change: {sign}{delta}"

    lines = [
        f"# Perihan QA Report — {run_id.replace('_', ' ')}",
        f"Model: `{perihan_model}`  |  Judge: `{judge_model}`",
        f"Score: {total}/{max_s} ({pct:.1f}%){prev_line}{change_line}",
        "",
        "## Category Breakdown",
        "| Category | Score | Max | % |",
        "|----------|-------|-----|---|",
    ]

    for cat, data in run["categories"].items():
        c_pct = (data["score"] / data["max"] * 100) if data["max"] > 0 else 0
        lines.append(f"| {cat} | {data['score']} | {data['max']} | {c_pct:.0f}% |")

    lines.append("")

    # Regressions
    if diff and diff["regressions"]:
        lines.append("## Regressions ⚠️")
        for r in diff["regressions"]:
            lines.append(f"- {r['id']}: {r['old']}pts → {r['new']}pts — {r['reason']}")
        lines.append("")

    # Improvements
    if diff and diff["improvements"]:
        lines.append("## Improvements ✅")
        for r in diff["improvements"]:
            lines.append(f"- {r['id']}: {r['old']}pts → {r['new']}pts — {r['reason']}")
        lines.append("")

    # Full results table
    lines += [
        "## Full Results",
        "| ID | Category | Q | Score | Reason |",
        "|----|----------|---|-------|--------|",
    ]
    for r in run["results"]:
        short_q = r["question"][:60] + ("…" if len(r["question"]) > 60 else "")
        score_icon = {2: "✅", 1: "⚠️", 0: "❌"}.get(r["score"], "?")
        lines.append(
            f"| {r['id']} | {r['category']} | {short_q} | {score_icon} {r['score']} | {r['reason']} |"
        )

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print(f"Parsing {QA_FILE} …")
    questions = parse_qa_file(QA_FILE)
    if not questions:
        print("ERROR: No questions found in QA.md.", file=sys.stderr)
        sys.exit(1)
    print(f"Found {len(questions)} questions.")

    judge_client = get_judge_client()
    perihan_model = get_perihan_model()
    print(f"Perihan model: {perihan_model}  |  Judge model: {JUDGE_MODEL}")

    run_id = datetime.now().strftime("%Y-%m-%d_%H-%M")
    results = []

    # Accumulate category scores
    cat_scores: dict[str, dict] = {}

    for i, q in enumerate(questions, 1):
        print(f"  [{i}/{len(questions)}] {q['id']}: {q['question'][:60]}")

        # Ask Perihan
        reply = ask_perihan(q["question"])
        if reply.startswith("[ERROR"):
            print(f"    → {reply}")

        # Judge
        score, reason = judge(judge_client, q["question"], q["expected"], reply)
        print(f"    → Score: {score} | {reason}")

        cat = q["category"]
        if cat not in cat_scores:
            cat_scores[cat] = {"score": 0, "max": 0}
        cat_scores[cat]["score"] += score
        cat_scores[cat]["max"] += 2

        results.append({
            "id": q["id"],
            "category": cat,
            "question": q["question"],
            "expected": q["expected"],
            "source": q.get("source", ""),
            "reply": reply,
            "score": score,
            "reason": reason,
        })

    total_score = sum(r["score"] for r in results)
    max_score = len(results) * 2
    pct = (total_score / max_score * 100) if max_score > 0 else 0.0

    run_data = {
        "run_id": run_id,
        "perihan_model": perihan_model,
        "judge_model": JUDGE_MODEL,
        "total_score": total_score,
        "max_score": max_score,
        "pct": round(pct, 1),
        "categories": cat_scores,
        "results": results,
    }

    # Save JSON
    json_path = RESULTS_DIR / f"run_{run_id}.json"
    json_path.write_text(json.dumps(run_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved: {json_path}")

    # Diff vs previous run
    previous = load_previous_run(json_path)
    diff = compute_diff(run_data, previous) if previous else None

    # Write latest.md
    report = build_report(run_data, previous, diff)
    latest_md = RESULTS_DIR / "latest.md"
    latest_md.write_text(report, encoding="utf-8")
    print(f"Report: {latest_md}")

    # Summary
    print(f"\n{'='*50}")
    print(f"Score: {total_score}/{max_score} ({pct:.1f}%)")
    if diff:
        print(f"Regressions: {len(diff['regressions'])}  |  Improvements: {len(diff['improvements'])}")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
