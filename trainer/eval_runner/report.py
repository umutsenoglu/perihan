"""
Eval Report Generator
=====================
Reads eval_results.json and generates an HTML report.
Supports multiple benchmark models side by side.

Usage:
  python report.py              # generates output/report.html
  python report.py --open       # generates and opens in browser
"""

import json
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


def find_benchmark_keys(results: dict) -> list[str]:
    """Find all unique benchmark-* keys across all questions."""
    keys = set()
    for r in results.values():
        for k in r:
            if k.startswith("benchmark-"):
                keys.add(k)
    # Also support legacy "benchmark" key
    for r in results.values():
        if "benchmark" in r and not any(k.startswith("benchmark-") for k in r):
            keys.add("benchmark")
            break
    return sorted(keys)


def extract_category(source_docs: list[str]) -> str:
    if not source_docs:
        return "unknown"
    first = source_docs[0]
    if "/" in first:
        return first.split("/")[0]
    return "unknown"


def build_report(results: dict) -> str:
    benchmark_keys = find_benchmark_keys(results)
    if not benchmark_keys:
        benchmark_keys = ["benchmark"]

    def bk_label(bk):
        return bk.replace("benchmark-", "") if bk != "benchmark" else "benchmark"

    # Gather data
    rows = []
    categories = {}
    difficulties = {}
    strategies = {}

    for qid, r in sorted(results.items()):
        cat = extract_category(r.get("source_documents", []))
        diff = r.get("difficulty", "unknown")
        strat = r.get("strategy", "unknown")
        p = r.get("perihan", {})

        row = {
            "id": qid,
            "question": r["question"],
            "expected": r.get("expected", ""),
            "category": cat,
            "difficulty": diff,
            "strategy": strat,
            "p_score": p.get("score"),
            "p_reply": p.get("reply", ""),
            "p_reason": p.get("reason", ""),
            "benchmarks": {},
        }
        for bk in benchmark_keys:
            b = r.get(bk, {})
            row["benchmarks"][bk] = {
                "score": b.get("score"),
                "reply": b.get("reply", ""),
                "reason": b.get("reason", ""),
            }

        rows.append(row)

        # Category stats
        if cat not in categories:
            categories[cat] = {"p_total": 0, "p_max": 0, "count": 0, "benchmarks": {bk: {"total": 0, "max": 0} for bk in benchmark_keys}}
        categories[cat]["count"] += 1
        if p.get("score") is not None:
            categories[cat]["p_total"] += p["score"]
            categories[cat]["p_max"] += 2
        for bk in benchmark_keys:
            bs = r.get(bk, {}).get("score")
            if bk not in categories[cat]["benchmarks"]:
                categories[cat]["benchmarks"][bk] = {"total": 0, "max": 0}
            if bs is not None:
                categories[cat]["benchmarks"][bk]["total"] += bs
                categories[cat]["benchmarks"][bk]["max"] += 2

        # Difficulty stats
        if diff not in difficulties:
            difficulties[diff] = {"p_total": 0, "p_max": 0, "count": 0, "benchmarks": {bk: {"total": 0, "max": 0} for bk in benchmark_keys}}
        difficulties[diff]["count"] += 1
        if p.get("score") is not None:
            difficulties[diff]["p_total"] += p["score"]
            difficulties[diff]["p_max"] += 2
        for bk in benchmark_keys:
            bs = r.get(bk, {}).get("score")
            if bk not in difficulties[diff]["benchmarks"]:
                difficulties[diff]["benchmarks"][bk] = {"total": 0, "max": 0}
            if bs is not None:
                difficulties[diff]["benchmarks"][bk]["total"] += bs
                difficulties[diff]["benchmarks"][bk]["max"] += 2

        # Strategy stats
        if strat not in strategies:
            strategies[strat] = {"p_total": 0, "p_max": 0, "count": 0, "benchmarks": {bk: {"total": 0, "max": 0} for bk in benchmark_keys}}
        strategies[strat]["count"] += 1
        if p.get("score") is not None:
            strategies[strat]["p_total"] += p["score"]
            strategies[strat]["p_max"] += 2
        for bk in benchmark_keys:
            bs = r.get(bk, {}).get("score")
            if bk not in strategies[strat]["benchmarks"]:
                strategies[strat]["benchmarks"][bk] = {"total": 0, "max": 0}
            if bs is not None:
                strategies[strat]["benchmarks"][bk]["total"] += bs
                strategies[strat]["benchmarks"][bk]["max"] += 2

    # Overall totals
    p_scores = [r["p_score"] for r in rows if r["p_score"] is not None]
    p_total = sum(p_scores) if p_scores else 0
    p_max = len(p_scores) * 2 if p_scores else 0

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

    # Colors for benchmarks
    bench_colors = ["#4fc3f7", "#ff8a65", "#ce93d8", "#fff176", "#80cbc4"]

    # Build stat cards for each benchmark
    bench_cards = ""
    for i, bk in enumerate(benchmark_keys):
        scores = [r["benchmarks"][bk]["score"] for r in rows if r["benchmarks"][bk]["score"] is not None]
        if not scores:
            continue
        total = sum(scores)
        mx = len(scores) * 2
        color = bench_colors[i % len(bench_colors)]
        label = bk_label(bk)
        bench_cards += f"""
        <div class="stat-card" style="border-top: 3px solid {color};">
            <h3>{label}</h3>
            <div class="score" style="color:{color};">{total}/{mx}</div>
            <div class="pct">{pct(total, mx)}</div>
            <div class="sub">{len(scores)} questions</div>
        </div>"""

    # Perihan card
    perihan_card = ""
    if p_scores:
        perihan_card = f"""
        <div class="stat-card perihan-card">
            <h3>Perihan RAG</h3>
            <div class="score">{p_total}/{p_max}</div>
            <div class="pct">{pct(p_total, p_max)}</div>
            <div class="sub">{len(p_scores)} questions</div>
        </div>"""

    # Head-to-head cards
    h2h_cards = ""
    for i, bk in enumerate(benchmark_keys):
        both = [r for r in rows if r["benchmarks"][bk]["score"] is not None and r["p_score"] is not None]
        if not both:
            continue
        wins = sum(1 for r in both if r["p_score"] > r["benchmarks"][bk]["score"])
        draws = sum(1 for r in both if r["p_score"] == r["benchmarks"][bk]["score"])
        losses = sum(1 for r in both if r["p_score"] < r["benchmarks"][bk]["score"])
        label = bk_label(bk)
        h2h_cards += f"""
        <div class="stat-card comparison-card">
            <h3>vs {label}</h3>
            <div class="h2h">
                <span class="h2h-item rag">RAG: {wins}</span>
                <span class="h2h-item draw">Draw: {draws}</span>
                <span class="h2h-item gemini">{label}: {losses}</span>
            </div>
            <div class="sub">{len(both)} compared</div>
        </div>"""

    # Category table
    cat_header_cols = ""
    for i, bk in enumerate(benchmark_keys):
        color = bench_colors[i % len(bench_colors)]
        cat_header_cols += f'<th style="color:{color}">{bk_label(bk)}</th>'
    cat_header_cols += '<th style="color:#81c784">Perihan</th>'

    cat_rows = ""
    for cat in sorted(categories.keys()):
        c = categories[cat]
        cols = ""
        for bk in benchmark_keys:
            bd = c["benchmarks"].get(bk, {"total": 0, "max": 0})
            cols += f'<td>{bd["total"]}/{bd["max"]} ({pct(bd["total"], bd["max"])})</td>'
        cols += f'<td>{c["p_total"]}/{c["p_max"]} ({pct(c["p_total"], c["p_max"])})</td>'
        cat_rows += f"<tr><td>{cat}</td><td>{c['count']}</td>{cols}</tr>"

    # Difficulty table
    diff_header_cols = ""
    for bk in benchmark_keys:
        diff_header_cols += f'<th>{bk_label(bk)}</th>'
    diff_header_cols += '<th>Perihan</th>'

    diff_rows = ""
    for diff in sorted(difficulties.keys()):
        d = difficulties[diff]
        cols = ""
        for bk in benchmark_keys:
            bd = d["benchmarks"].get(bk, {"total": 0, "max": 0})
            cols += f'<td>{bd["total"]}/{bd["max"]} ({pct(bd["total"], bd["max"])})</td>'
        cols += f'<td>{d["p_total"]}/{d["p_max"]} ({pct(d["p_total"], d["p_max"])})</td>'
        diff_rows += f"<tr><td>{diff}</td><td>{d['count']}</td>{cols}</tr>"

    # Strategy table
    strat_header_cols = ""
    for bk in benchmark_keys:
        strat_header_cols += f'<th>{bk_label(bk)}</th>'
    strat_header_cols += '<th>Perihan</th>'

    strat_rows = ""
    for strat in sorted(strategies.keys()):
        s = strategies[strat]
        cols = ""
        for bk in benchmark_keys:
            bd = s["benchmarks"].get(bk, {"total": 0, "max": 0})
            cols += f'<td>{bd["total"]}/{bd["max"]} ({pct(bd["total"], bd["max"])})</td>'
        cols += f'<td>{s["p_total"]}/{s["p_max"]} ({pct(s["p_total"], s["p_max"])})</td>'
        strat_rows += f"<tr><td>{strat}</td><td>{s['count']}</td>{cols}</tr>"

    # Detail table header
    detail_bench_headers = ""
    for bk in benchmark_keys:
        label = bk_label(bk)
        detail_bench_headers += f'<th>{label}</th><th>{label} Reason</th>'

    # Detail rows
    detail_rows = ""
    for r in rows:
        bench_cells = ""
        for bk in benchmark_keys:
            bd = r["benchmarks"][bk]
            bench_cells += f'<td class="{score_class(bd["score"])}">{score_icon(bd["score"])}</td>'
            bench_cells += f'<td class="reason-cell" title="{bd["reply"]}">{bd["reason"]}</td>'

        # Winner: compare perihan vs best benchmark
        winner = ""
        bench_scores = [r["benchmarks"][bk]["score"] for bk in benchmark_keys if r["benchmarks"][bk]["score"] is not None]
        best_bench = max(bench_scores) if bench_scores else None
        if best_bench is not None and r["p_score"] is not None:
            if r["p_score"] > best_bench:
                winner = '<span class="winner rag">RAG</span>'
            elif r["p_score"] < best_bench:
                winner = '<span class="winner bench">Bench</span>'

        detail_rows += f"""<tr>
            <td>{r['id']}</td>
            <td class="cat-cell">{r['category']}</td>
            <td class="q-cell" title="{r['expected']}">{r['question']}</td>
            {bench_cells}
            <td class="{score_class(r['p_score'])}">{score_icon(r['p_score'])}</td>
            <td class="reason-cell" title="{r['p_reply']}">{r['p_reason']}</td>
            <td>{winner}</td>
        </tr>"""

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
    .reason-cell {{ max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #999; font-size: 12px; }}

    .winner {{ padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 700; }}
    .winner.rag {{ background: #1b3a1b; color: #81c784; }}
    .winner.bench {{ background: #1a2a3a; color: #4fc3f7; }}

    .breakdown-table {{ table-layout: fixed; }}
    .breakdown-table th, .breakdown-table td {{ padding: 6px 12px; text-align: center; }}
    .breakdown-table td:first-child, .breakdown-table th:first-child {{ text-align: left; }}
    .breakdown-table td:nth-child(2), .breakdown-table th:nth-child(2) {{ text-align: center; width: 50px; }}

    .filter-bar {{ margin: 12px 0; display: flex; gap: 8px; flex-wrap: wrap; }}
    .filter-btn {{ background: #1a1b26; border: 1px solid #2a2a3a; color: #ccc; padding: 4px 12px;
                   border-radius: 4px; cursor: pointer; font-size: 12px; }}
    .filter-btn:hover {{ border-color: #4fc3f7; }}
    .filter-btn.active {{ border-color: #4fc3f7; color: #4fc3f7; }}
</style>
</head>
<body>

<h1>Eval Report</h1>
<div class="subtitle">Generated {now} &mdash; {len(rows)} questions, {len(benchmark_keys)} benchmark model(s)</div>

<div class="cards">
    {bench_cards}
    {perihan_card}
    {h2h_cards}
</div>

<h2>By Category</h2>
<table class="breakdown-table">
    <tr><th>Category</th><th>#</th>{cat_header_cols}</tr>
    {cat_rows}
</table>

<h2>By Difficulty</h2>
<table class="breakdown-table">
    <tr><th>Difficulty</th><th>#</th>{diff_header_cols}</tr>
    {diff_rows}
</table>

<h2>By Strategy</h2>
<table class="breakdown-table">
    <tr><th>Strategy</th><th>#</th>{strat_header_cols}</tr>
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
        {detail_bench_headers}
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
        if (cells.length < 5) return;
        // Check score cells (every other starting from index 3, and the perihan score)
        const scoreCells = [];
        for (let i = 3; i < cells.length - 2; i += 2) scoreCells.push(cells[i]);
        const perihanCell = cells[cells.length - 3];
        const allScores = [...scoreCells, perihanCell];

        if (mode === 'all') {{
            row.style.display = '';
        }} else if (mode === 'disagree') {{
            const vals = allScores.map(c => c.textContent.trim()).filter(v => v !== '-');
            const unique = new Set(vals);
            row.style.display = unique.size > 1 ? '' : 'none';
        }} else if (mode === 'fail') {{
            const hasFailure = allScores.some(c => c.textContent.trim() === '\\u274C');
            row.style.display = hasFailure ? '' : 'none';
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
