"""Collector app — generates test content continuously and reports progress."""

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Load .env from parent directory (project root)
load_dotenv(Path(__file__).parent.parent / ".env")

from config import OUTPUT_DIR, CATEGORIES, BATCH_SIZE, BATCH_INTERVAL
from generators import knowledge, medical, messaging, legal, finance, personal, calendar, trello

# All generators
GENERATORS = {
    "knowledge": knowledge.generate,
    "medical": medical.generate,
    "messaging": messaging.generate,
    "legal": legal.generate,
    "finance": finance.generate,
    "personal": personal.generate,
    "calendar": calendar.generate,
    "trello": trello.generate,
}

# Stats tracking
stats = {
    "started_at": None,
    "total_generated": 0,
    "by_category": {cat: 0 for cat in CATEGORIES},
    "errors": 0,
    "last_files": [],
}


def log(msg: str, level: str = "INFO"):
    """Print a timestamped log message."""
    ts = datetime.now().strftime("%H:%M:%S")
    prefix = {"INFO": "→", "OK": "✓", "ERR": "✗", "STAT": "▸"}.get(level, "→")
    print(f"  [{ts}] {prefix} {msg}", flush=True)


def print_banner():
    """Print startup banner."""
    print()
    print("  ╔══════════════════════════════════════════════════╗")
    print("  ║           COLLECTOR — Test Content Generator     ║")
    print("  ╠══════════════════════════════════════════════════╣")
    print(f"  ║  Output:   {str(OUTPUT_DIR):<38} ║")
    print(f"  ║  Batch:    {BATCH_SIZE} files every {BATCH_INTERVAL}s{'':<24} ║")
    print(f"  ║  Categories: {', '.join(CATEGORIES.keys()):<36} ║")
    print("  ╚══════════════════════════════════════════════════╝")
    print()


def print_stats():
    """Print current statistics."""
    elapsed = (datetime.now() - stats["started_at"]).total_seconds()
    mins = int(elapsed // 60)
    secs = int(elapsed % 60)
    print()
    print(f"  ┌─ Stats ({mins}m {secs}s elapsed) ─────────────────────")
    print(f"  │ Total generated: {stats['total_generated']}")
    for cat, count in stats["by_category"].items():
        bar = "█" * count + "░" * max(0, 10 - count)
        print(f"  │   {cat:<12} {bar} {count}")
    print(f"  │ Errors: {stats['errors']}")
    if stats["last_files"]:
        print(f"  │ Recent:")
        for f in stats["last_files"][-3:]:
            print(f"  │   • {f}")
    print(f"  └──────────────────────────────────────────────────")
    print()


async def generate_one(category: str) -> dict | None:
    """Generate one file for the given category."""
    generator = GENERATORS[category]
    try:
        result = await generator()

        # Ensure output directory exists
        cat_dir = OUTPUT_DIR / category
        cat_dir.mkdir(parents=True, exist_ok=True)

        # Write file
        filepath = cat_dir / result["filename"]
        filepath.write_text(result["content"], encoding="utf-8")

        # Update stats
        stats["total_generated"] += 1
        stats["by_category"][category] += 1
        stats["last_files"].append(f"{category}/{result['filename']}")
        if len(stats["last_files"]) > 10:
            stats["last_files"] = stats["last_files"][-10:]

        log(f"{result['description']}", "OK")
        log(f"  Saved: {category}/{result['filename']}")

        return result

    except Exception as e:
        stats["errors"] += 1
        log(f"[{category}] Error: {e}", "ERR")
        return None


async def run_batch(batch_num: int):
    """Run one batch of content generation."""
    categories = list(GENERATORS.keys())

    # Pick BATCH_SIZE random categories for this batch
    picks = [categories[i % len(categories)] for i in range(batch_num * BATCH_SIZE, (batch_num + 1) * BATCH_SIZE)]

    print(f"  ── Batch {batch_num + 1} ──────────────────────────────────────")
    log(f"Generating {len(picks)} files: {', '.join(picks)}")

    # Generate concurrently
    tasks = [generate_one(cat) for cat in picks]
    await asyncio.gather(*tasks)

    print_stats()


async def main(category_filter: str = "all"):
    """Main loop — generate content continuously."""
    global GENERATORS

    # Wrap stdout for unicode support on Windows
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    # Filter to specific category if requested
    if category_filter != "all":
        if category_filter not in GENERATORS:
            print(f"  ✗ Unknown category: {category_filter}")
            print(f"  Available: {', '.join(GENERATORS.keys())}")
            sys.exit(1)
        GENERATORS = {category_filter: GENERATORS[category_filter]}

    print_banner()

    # Check GEMINI_API_KEY
    if not os.environ.get("GEMINI_API_KEY"):
        print("  ✗ GEMINI_API_KEY not set. Export it and try again.")
        sys.exit(1)

    log("Starting content generation...")
    stats["started_at"] = datetime.now()

    batch_num = 0
    try:
        while True:
            await run_batch(batch_num)
            batch_num += 1
            log(f"Sleeping {BATCH_INTERVAL}s until next batch... (Ctrl+C to stop)")
            await asyncio.sleep(BATCH_INTERVAL)
    except KeyboardInterrupt:
        print()
        log("Stopped by user.", "INFO")
        print_stats()
        log(f"All files saved in: {OUTPUT_DIR.resolve()}")


if __name__ == "__main__":
    category = "all"
    if len(sys.argv) > 1:
        category = sys.argv[1].lower()
    asyncio.run(main(category))
