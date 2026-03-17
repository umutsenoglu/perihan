"""Collector with web dashboard — run this instead of app.py for HTTP status endpoint."""

import asyncio
import json
import os
import sys
import random
from datetime import datetime
from pathlib import Path
from contextlib import asynccontextmanager
from dotenv import load_dotenv

# Load .env from parent directory (project root)
load_dotenv(Path(__file__).parent.parent / ".env")

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from config import OUTPUT_DIR, CATEGORIES, BATCH_SIZE, BATCH_INTERVAL
from generators import knowledge, medical, messaging, legal, finance, personal, calendar, trello


ALL_GENERATORS = {
    "knowledge": knowledge.generate,
    "medical": medical.generate,
    "messaging": messaging.generate,
    "legal": legal.generate,
    "finance": finance.generate,
    "personal": personal.generate,
    "calendar": calendar.generate,
    "trello": trello.generate,
}

# --category flag: "all" (default) or a specific category name
CATEGORY_FILTER = os.environ.get("COLLECTOR_CATEGORY", "all").lower()
if CATEGORY_FILTER == "all":
    GENERATORS = ALL_GENERATORS
elif CATEGORY_FILTER in ALL_GENERATORS:
    GENERATORS = {CATEGORY_FILTER: ALL_GENERATORS[CATEGORY_FILTER]}
else:
    print(f"  ✗ Unknown category: {CATEGORY_FILTER}. Available: {', '.join(ALL_GENERATORS.keys())}, all")
    sys.exit(1)

stats = {
    "started_at": None,
    "total_generated": 0,
    "by_category": {cat: 0 for cat in CATEGORIES},
    "by_source": {"internet": 0, "generated": 0},
    "errors": 0,
    "last_files": [],
    "running": False,
    "current_batch": 0,
    "log": [],
}


def log(msg: str, level: str = "INFO"):
    ts = datetime.now().strftime("%H:%M:%S")
    entry = f"[{ts}] {msg}"
    stats["log"].append(entry)
    if len(stats["log"]) > 100:
        stats["log"] = stats["log"][-100:]
    prefix = {"INFO": "→", "OK": "✓", "ERR": "✗"}.get(level, "→")
    print(f"  {prefix} {entry}", flush=True)


async def generate_one(category: str):
    generator = GENERATORS[category]
    try:
        result = await generator()
        cat_dir = OUTPUT_DIR / category
        cat_dir.mkdir(parents=True, exist_ok=True)
        filepath = cat_dir / result["filename"]
        filepath.write_text(result["content"], encoding="utf-8")

        source = result.get("source", "generated")
        stats["total_generated"] += 1
        stats["by_category"][category] += 1
        stats["by_source"][source] += 1
        stats["last_files"].append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "category": category,
            "file": result["filename"],
            "description": result["description"],
            "source": source,
        })
        if len(stats["last_files"]) > 20:
            stats["last_files"] = stats["last_files"][-20:]

        # Append to manifest.json
        manifest_path = OUTPUT_DIR / "manifest.json"
        manifest = []
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                manifest = []
        manifest.append({
            "filename": result["filename"],
            "category": category,
            "source": source,
            "description": result["description"],
            "storyline": result.get("storyline"),
            "generated_at": datetime.now().isoformat(),
            "path": f"{category}/{result['filename']}",
        })
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

        log(f"{result['description']}", "OK")
    except Exception as e:
        stats["errors"] += 1
        log(f"[{category}] Error: {e}", "ERR")


async def generation_loop():
    stats["started_at"] = datetime.now().isoformat()
    stats["running"] = True
    categories = list(GENERATORS.keys())

    batch_num = 0
    while True:
        stats["current_batch"] = batch_num + 1
        picks = [categories[i % len(categories)] for i in range(batch_num * BATCH_SIZE, (batch_num + 1) * BATCH_SIZE)]
        log(f"Batch {batch_num + 1}: generating {', '.join(picks)}")

        tasks = [generate_one(cat) for cat in picks]
        await asyncio.gather(*tasks)

        batch_num += 1
        await asyncio.sleep(BATCH_INTERVAL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    if not os.environ.get("GEMINI_API_KEY"):
        print("  ✗ GEMINI_API_KEY not set!")
        sys.exit(1)

    task = asyncio.create_task(generation_loop())
    log("Collector started — generating content in background")
    yield
    task.cancel()


app = FastAPI(title="Collector", lifespan=lifespan)


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return """<!DOCTYPE html>
<html><head><title>Collector Dashboard</title>
<style>
  body { font-family: 'Segoe UI', monospace; background: #1a1a2e; color: #e0e0e0; margin: 0; padding: 20px; }
  h1 { color: #00d4ff; }
  .stats { display: flex; gap: 20px; flex-wrap: wrap; margin: 20px 0; }
  .stat-card { background: #16213e; padding: 15px 25px; border-radius: 8px; border: 1px solid #0f3460; }
  .stat-card h3 { margin: 0; color: #888; font-size: 12px; text-transform: uppercase; }
  .stat-card .value { font-size: 28px; color: #00d4ff; margin: 5px 0; }
  .category-bar { display: flex; align-items: center; gap: 10px; margin: 5px 0; }
  .category-bar .bar { height: 20px; background: #00d4ff; border-radius: 3px; min-width: 2px; transition: width 0.5s; }
  .category-bar .label { width: 100px; text-align: right; }
  .log-box { background: #0a0a1a; padding: 15px; border-radius: 8px; max-height: 400px; overflow-y: auto; font-size: 13px; }
  .log-box div { padding: 2px 0; border-bottom: 1px solid #111; }
  .files-list { background: #16213e; padding: 15px; border-radius: 8px; }
  .files-list .file { padding: 5px 0; border-bottom: 1px solid #0f3460; font-size: 13px; }
  .file .time { color: #666; }
  .file .cat { color: #00d4ff; font-weight: bold; }
  .file .src-internet { color: #4caf50; font-weight: bold; }
  .file .src-generated { color: #ff9800; font-weight: bold; }
</style>
</head><body>
<h1>Collector Dashboard</h1>
<div id="content">Loading...</div>
<script>
async function refresh() {
  const r = await fetch('/status');
  const d = await r.json();
  let html = '<div class="stats">';
  html += `<div class="stat-card"><h3>Total Generated</h3><div class="value">${d.total_generated}</div></div>`;
  html += `<div class="stat-card"><h3>Current Batch</h3><div class="value">#${d.current_batch}</div></div>`;
  html += `<div class="stat-card"><h3>Errors</h3><div class="value">${d.errors}</div></div>`;
  const bs = d.by_source || {};
  html += `<div class="stat-card"><h3>From Internet</h3><div class="value" style="color:#4caf50">${bs.internet || 0}</div></div>`;
  html += `<div class="stat-card"><h3>AI Generated</h3><div class="value" style="color:#ff9800">${bs.generated || 0}</div></div>`;
  html += '</div>';

  html += '<h2>Categories</h2>';
  const max = Math.max(1, ...Object.values(d.by_category));
  for (const [cat, count] of Object.entries(d.by_category)) {
    const w = Math.max(2, (count / max) * 300);
    html += `<div class="category-bar"><span class="label">${cat}</span><div class="bar" style="width:${w}px"></div><span>${count}</span></div>`;
  }

  html += '<h2>Recent Files</h2><div class="files-list">';
  for (const f of [...d.last_files].reverse()) {
    const srcClass = f.source === 'internet' ? 'src-internet' : 'src-generated';
    const srcLabel = f.source === 'internet' ? 'WEB' : 'AI';
    html += `<div class="file"><span class="time">${f.time}</span> <span class="cat">[${f.category}]</span> <span class="${srcClass}">[${srcLabel}]</span> ${f.description}</div>`;
  }
  html += '</div>';

  html += '<h2>Log</h2><div class="log-box">';
  for (const line of [...d.log].reverse()) {
    html += `<div>${line}</div>`;
  }
  html += '</div>';

  document.getElementById('content').innerHTML = html;
}
refresh();
setInterval(refresh, 5000);
</script>
</body></html>"""


@app.get("/status")
async def status():
    return JSONResponse(stats)


@app.post("/stop")
async def stop():
    stats["running"] = False
    return {"message": "Stopping after current batch"}
