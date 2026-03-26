"""
Eval Report Generator
=====================
Reads eval_results.json and generates an HTML report.

Usage:
  python report.py              # generates output/report.html
  python report.py --open       # generates and opens in browser
"""

import json
import os
import sys
import webbrowser
from datetime import datetime
from pathlib import Path

EVAL_RESULTS_FILE = Path(__file__).parent / "output" / "eval_results.json"
REPORT_FILE = Path(__file__).parent / "output" / "report.html"


def load_results() -> dict:
    if not EVAL_RESULTS_FILE.exists():
        print("  No eval_results.json found. Run benchmark first.")
        sys.exit(1)
    return json.loads(EVAL_RESULTS_FILE.read_text(encoding="utf-8"))


def extract_category(source_docs: list[str]) -> str:
    """Extract category from source document path (e.g. 'personal/file.txt' -> 'personal')."""
    if not source_docs:
        return "unknown"
    first = source_docs[0]
    if "/" in first:
        return first.split("/")[0]
    return "unknown"


def build_report(results: dict) -> str:
    # Gather data
    rows = []
    categories = {}
    difficulties = {}
    strategies = {}

    for qid, r in sorted(results.items()):
        cat = extract_category(r.get("source_documents", []))
        diff = r.get("difficulty", "unknown")
        strat = r.get("strategy", "unknown")
        b = r.get("benchmark", {})
        p = r.get("perihan", {})
        b_score = b.get("score")
        p_score = p.get("score")

        rows.append({
            "id": qid,
            "question": r["question"],
            "expected": r.get("expected", ""),
            "category": cat,
            "difficulty": diff,
            "strategy": strat,
            "b_score": b_score,
            "b_reply": b.get("reply", ""),
            "b_reason": b.get("reason", ""),
            "p_score": p_score,
            "p_reply": p.get("reply", ""),
            "p_reason": p.get("reason", ""),
        })

        # Category stats
        if cat not in categories:
            categories[cat] = {"b_total": 0, "b_max": 0, "p_total": 0, "p_max": 0, "count": 0}
        categories[cat]["count"] += 1
        if b_score is not None:
            categories[cat]["b_total"] += b_score
            categories[cat]["b_max"] += 2
        if p_score is not None:
            categories[cat]["p_total"] += p_score
            categories[cat]["p_max"] += 2

        # Difficulty stats
        if diff not in difficulties:
            difficulties[diff] = {"b_total": 0, "b_max": 0, "p_total": 0, "p_max": 0, "count": 0}
        difficulties[diff]["count"] += 1
        if b_score is not None:
            difficulties[diff]["b_total"] += b_score
            difficulties[diff]["b_max"] += 2
        if p_score is not None:
            difficulties[diff]["p_total"] += p_score
            difficulties[diff]["p_max"] += 2

        # Strategy stats
        if strat not in strategies:
            strategies[strat] = {"b_total": 0, "b_max": 0, "p_total": 0, "p_max": 0, "count": 0}
        strategies[strat]["count"] += 1
        if b_score is not None:
            strategies[strat]["b_total"] += b_score
            strategies[strat]["b_max"] += 2
        if p_score is not None:
            strategies[strat]["p_total"] += p_score
            strategies[strat]["p_max"] += 2

    # Overall totals
    b_scores = [r["b_score"] for r in rows if r["b_score"] is not None]
    p_scores = [r["p_score"] for r in rows if r["p_score"] is not None]
    both = [r for r in rows if r["b_score"] is not None and r["p_score"] is not None]

    b_total = sum(b_scores) if b_scores else 0
    b_max = len(b_scores) * 2 if b_scores else 0
    p_total = sum(p_scores) if p_scores else 0
    p_max = len(p_scores) * 2 if p_scores else 0

    wins = sum(1 for r in both if r["p_score"] > r["b_score"])
    draws = sum(1 for r in both if r["p_score"] == r["b_score"])
    losses = sum(1 for r in both if r["p_score"] < r["b_score"])

    def pct(total, mx):
        return f"{total/mx*100:.0f}%" if mx > 0 else "-"

    def score_icon(s):
        if s is None:
            return "-"
        return {2: "&#9989;", 1: "&#9888;&#65039;", 0: "&#10060;"}.get(s, str(s))

    def score_class(s):
        if s is None:
            return "na"
        return {2: "pass", 1: "partial", 0: "fail"}.get(s, "")

    def bar_width(total, mx):
        return f"{total/mx*100:.0f}" if mx > 0 else "0"

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Build category rows
    cat_rows = ""
    for cat in sorted(categories.keys()):
        c = categories[cat]
        cat_rows += f"""<tr>
            <td>{cat}</td><td>{c['count']}</td>
            <td><div class="bar-container"><div class="bar bench-bar" style="width:{bar_width(c['b_total'], c['b_max'])}%"></div></div></td>
            <td>{c['b_total']}/{c['b_max']} ({pct(c['b_total'], c['b_max'])})</td>
            <td><div class="bar-container"><div class="bar perihan-bar" style="width:{bar_width(c['p_total'], c['p_max'])}%"></div></div></td>
            <td>{c['p_total']}/{c['p_max']} ({pct(c['p_total'], c['p_max'])})</td>
        </tr>"""

    # Build difficulty rows
    diff_rows = ""
    for diff in sorted(difficulties.keys()):
        d = difficulties[diff]
        diff_rows += f"""<tr>
            <td>{diff}</td><td>{d['count']}</td>
            <td>{d['b_total']}/{d['b_max']} ({pct(d['b_total'], d['b_max'])})</td>
            <td>{d['p_total']}/{d['p_max']} ({pct(d['p_total'], d['p_max'])})</td>
        </tr>"""

    # Build strategy rows
    strat_rows = ""
    for strat in sorted(strategies.keys()):
        s = strategies[strat]
        strat_rows += f"""<tr>
            <td>{strat}</td><td>{s['count']}</td>
            <td>{s['b_total']}/{s['b_max']} ({pct(s['b_total'], s['b_max'])})</td>
            <td>{s['p_total']}/{s['p_max']} ({pct(s['p_total'], s['p_max'])})</td>
        </tr>"""

    # Build question detail rows
    detail_rows = ""
    for r in rows:
        winner = ""
        if r["b_score"] is not None and r["p_score"] is not None:
            if r["p_score"] > r["b_score"]:
                winner = '<span class="winner rag">RAG</span>'
            elif r["p_score"] < r["b_score"]:
                winner = '<span class="winner gemini">Gemini</span>'

        detail_rows += f"""<tr>
            <td>{r['id']}</td>
            <td class="cat-cell">{r['category']}</td>
            <td class="q-cell" title="{r['expected']}">{r['question']}</td>
            <td class="{score_class(r['b_score'])}">{score_icon(r['b_score'])}</td>
            <td class="reason-cell" title="{r['b_reply']}">{r['b_reason']}</td>
            <td class="{score_class(r['p_score'])}">{score_icon(r['p_score'])}</td>
            <td class="reason-cell" title="{r['p_reply']}">{r['p_reason']}</td>
            <td>{winner}</td>
        </tr>"""

    # Has perihan data?
    has_perihan = len(p_scores) > 0

    perihan_card = ""
    comparison_card = ""
    if has_perihan:
        perihan_card = f"""
        <div class="stat-card perihan-card">
            <h3>Perihan RAG</h3>
            <div class="score">{p_total}/{p_max}</div>
            <div class="pct">{pct(p_total, p_max)}</div>
            <div class="sub">{len(p_scores)} questions</div>
        </div>"""
        comparison_card = f"""
        <div class="stat-card comparison-card">
            <h3>Head to Head</h3>
            <div class="h2h">
                <span class="h2h-item rag">RAG wins: {wins}</span>
                <span class="h2h-item draw">Draws: {draws}</span>
                <span class="h2h-item gemini">Gemini wins: {losses}</span>
            </div>
            <div class="sub">{len(both)} compared</div>
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Eval Report — {now}</title>
<style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ font-family: 'Segoe UI', system-ui, sans-serif; background: #0f1117; color: #e0e0e0; padding: 24px; }}
    h1 {{ color: #fff; font-size: 22px; margin-bottom: 4px; }}
    .subtitle {{ color: #888; font-size: 13px; margin-bottom: 24px; }}
    h2 {{ color: #ccc; font-size: 16px; margin: 28px 0 12px 0; border-bottom: 1px solid #2a2a3a; padding-bottom: 6px; }}

    .cards {{ display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 8px; }}
    .stat-card {{ background: #1a1b26; border: 1px solid #2a2a3a; border-radius: 10px; padding: 20px 28px; min-width: 180px; }}
    .stat-card h3 {{ color: #888; font-size: 11px; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px; }}
    .stat-card .score {{ font-size: 32px; font-weight: 700; }}
    .stat-card .pct {{ font-size: 18px; color: #888; }}
    .stat-card .sub {{ font-size: 12px; color: #555; margin-top: 4px; }}
    .bench-card .score {{ color: #4fc3f7; }}
    .perihan-card .score {{ color: #81c784; }}
    .comparison-card {{ display: flex; flex-direction: column; justify-content: center; }}
    .h2h {{ display: flex; gap: 16px; margin: 8px 0; }}
    .h2h-item {{ font-size: 14px; font-weight: 600; }}
    .h2h-item.rag {{ color: #81c784; }}
    .h2h-item.draw {{ color: #888; }}
    .h2h-item.gemini {{ color: #4fc3f7; }}

    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th {{ background: #1a1b26; color: #888; text-align: left; padding: 8px 10px; font-weight: 600;
         text-transform: uppercase; font-size: 11px; letter-spacing: 0.5px; position: sticky; top: 0; }}
    td {{ padding: 7px 10px; border-bottom: 1px solid #1e1e2e; }}
    tr:hover {{ background: #1a1b26; }}

    .pass {{ color: #81c784; text-align: center; }}
    .partial {{ color: #ffb74d; text-align: center; }}
    .fail {{ color: #e57373; text-align: center; }}
    .na {{ color: #555; text-align: center; }}

    .q-cell {{ max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .cat-cell {{ color: #4fc3f7; }}
    .reason-cell {{ max-width: 250px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #999; font-size: 12px; }}

    .winner {{ padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 700; }}
    .winner.rag {{ background: #1b3a1b; color: #81c784; }}
    .winner.gemini {{ background: #1a2a3a; color: #4fc3f7; }}

    .bar-container {{ width: 100px; height: 14px; background: #1e1e2e; border-radius: 3px; overflow: hidden; }}
    .bar {{ height: 100%; border-radius: 3px; }}
    .bench-bar {{ background: #4fc3f7; }}
    .perihan-bar {{ background: #81c784; }}

    .breakdown-table th, .breakdown-table td {{ padding: 6px 12px; }}

    .filter-bar {{ margin: 12px 0; display: flex; gap: 8px; flex-wrap: wrap; }}
    .filter-btn {{ background: #1a1b26; border: 1px solid #2a2a3a; color: #ccc; padding: 4px 12px;
                   border-radius: 4px; cursor: pointer; font-size: 12px; }}
    .filter-btn:hover {{ border-color: #4fc3f7; }}
    .filter-btn.active {{ border-color: #4fc3f7; color: #4fc3f7; }}
</style>
</head>
<body>

<h1>Eval Report</h1>
<div class="subtitle">Generated {now} &mdash; {len(rows)} questions</div>

<div class="cards">
    <div class="stat-card bench-card">
        <h3>Gemini Benchmark</h3>
        <div class="score">{b_total}/{b_max}</div>
        <div class="pct">{pct(b_total, b_max)}</div>
        <div class="sub">{len(b_scores)} questions</div>
    </div>
    {perihan_card}
    {comparison_card}
</div>

<h2>By Category</h2>
<table class="breakdown-table">
    <tr><th>Category</th><th>#</th><th colspan="2">Benchmark</th><th colspan="2">Perihan</th></tr>
    {cat_rows}
</table>

<h2>By Difficulty</h2>
<table class="breakdown-table">
    <tr><th>Difficulty</th><th>#</th><th>Benchmark</th><th>Perihan</th></tr>
    {diff_rows}
</table>

<h2>By Strategy</h2>
<table class="breakdown-table">
    <tr><th>Strategy</th><th>#</th><th>Benchmark</th><th>Perihan</th></tr>
    {strat_rows}
</table>

<h2>All Questions</h2>
<div class="filter-bar">
    <button class="filter-btn active" onclick="filterRows('all')">All</button>
    <button class="filter-btn" onclick="filterRows('disagree')">Disagree Only</button>
    <button class="filter-btn" onclick="filterRows('fail')">Failures</button>
</div>
<table id="detail-table">
    <tr>
        <th>ID</th><th>Cat</th><th>Question</th>
        <th>Bench</th><th>Bench Reason</th>
        <th>Perihan</th><th>Perihan Reason</th>
        <th>Winner</th>
    </tr>
    {detail_rows}
</table>

<script>
function filterRows(mode) {{
    const rows = document.querySelectorAll('#detail-table tr:not(:first-child)');
    document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    event.target.classList.add('active');

    rows.forEach(row => {{
        const cells = row.querySelectorAll('td');
        if (cells.length < 7) return;
        const bench = cells[3].textContent.trim();
        const perihan = cells[5].textContent.trim();

        if (mode === 'all') {{
            row.style.display = '';
        }} else if (mode === 'disagree') {{
            row.style.display = (bench !== perihan && bench !== '-' && perihan !== '-') ? '' : 'none';
        }} else if (mode === 'fail') {{
            row.style.display = (bench === '\\u274C' || perihan === '\\u274C') ? '' : 'none';
        }}
    }});
}}
</script>

</body>
</html>"""

    return html


def main():
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    results = load_results()
    html = build_report(results)
    REPORT_FILE.write_text(html, encoding="utf-8")
    print(f"  Report saved: {REPORT_FILE.resolve()}")

    if "--open" in sys.argv:
        webbrowser.open(REPORT_FILE.resolve().as_uri())


if __name__ == "__main__":
    main()
