"""QA Generator runner — main entry point."""

import asyncio
import json
import os
import random
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent.parent / ".env")

from config import (
    QA_PER_SINGLE_DOC, QA_PER_SAME_CATEGORY, QA_PER_CROSS_STORYLINE,
    STRATEGY_WEIGHTS, BATCH_INTERVAL,
)
from packager import (
    load_manifest, build_all_packages, load_package_contents,
)
from state import (
    load_state, save_state, get_done_hashes,
    mark_in_progress, mark_completed, append_qas,
)
from generator import generate_qas
from prompts import (
    single_doc_prompt, same_category_prompt, cross_storyline_prompt,
)


def log(msg: str, level: str = "INFO"):
    ts = datetime.now().strftime("%H:%M:%S")
    prefix = {"INFO": "→", "OK": "✓", "ERR": "✗", "SKIP": "⊘"}.get(level, "→")
    print(f"  {prefix} [{ts}] {msg}", flush=True)


def pick_strategy(available: dict[str, list]) -> str | None:
    """Pick a strategy weighted by config, but only from those with packages."""
    candidates = []
    weights = []
    for strategy, pkgs in available.items():
        if pkgs:
            candidates.append(strategy)
            weights.append(STRATEGY_WEIGHTS.get(strategy, 1))
    if not candidates:
        return None
    return random.choices(candidates, weights=weights, k=1)[0]


def build_prompt(package: dict, docs: list[dict]) -> str:
    """Build the appropriate prompt for a package's strategy."""
    strategy = package["strategy"]
    if strategy == "single_doc":
        return single_doc_prompt(docs[0]["path"], docs[0]["content"], QA_PER_SINGLE_DOC)
    elif strategy == "same_category":
        return same_category_prompt(docs, package.get("category", "unknown"), QA_PER_SAME_CATEGORY)
    elif strategy == "cross_storyline":
        return cross_storyline_prompt(docs, package.get("storyline", "unknown"), QA_PER_CROSS_STORYLINE)
    else:
        raise ValueError(f"Unknown strategy: {strategy}")


def expected_qa_count(strategy: str) -> int:
    return {
        "single_doc": QA_PER_SINGLE_DOC,
        "same_category": QA_PER_SAME_CATEGORY,
        "cross_storyline": QA_PER_CROSS_STORYLINE,
    }.get(strategy, 5)


async def process_package(package: dict, state: dict) -> int:
    """Process a single package: load docs, generate QAs, save results. Returns QA count."""
    docs = load_package_contents(package)
    if not docs:
        log(f"No readable documents in package {package['hash']}", "SKIP")
        return 0

    # Calculate actual package size
    total_bytes = sum(len(d["content"].encode("utf-8")) for d in docs)
    size_mb = total_bytes / (1024 * 1024)

    strategy = package["strategy"]
    file_count = len(docs)
    storyline = package.get("storyline", "")
    category = package.get("category", "")
    context = storyline or category or "mixed"

    log(f"[{strategy}] {file_count} files, {size_mb:.1f} MB — {context}")

    mark_in_progress(state, package["hash"], package)

    prompt = build_prompt(package, docs)

    try:
        questions = await generate_qas(prompt)
    except Exception as e:
        log(f"LLM error: {e}", "ERR")
        state["in_progress"] = None
        save_state(state)
        return 0

    if not questions:
        log("LLM returned no questions", "ERR")
        state["in_progress"] = None
        save_state(state)
        return 0

    # Enrich QAs with metadata
    difficulty_map = {
        "single_doc": "search",
        "same_category": "reasoning",
        "cross_storyline": "multi-doc",
    }
    for q in questions:
        q["difficulty"] = difficulty_map.get(strategy, "search")
        q["strategy"] = strategy
        q["source_documents"] = package["files"]
        q["storyline"] = package.get("storyline")
        q["package_hash"] = package["hash"]

    saved = append_qas(questions)
    mark_completed(state, package["hash"], package, len(saved))

    log(f"Generated {len(saved)} QAs ({strategy}, {context})", "OK")
    return len(saved)


async def run(strategy_filter: str = "all"):
    """Main run loop — builds packages and processes them."""
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    print("\n  QA Generator")
    print("  " + "=" * 50)

    # Load state and manifest
    state = load_state()
    manifest = load_manifest()

    if not manifest:
        log("No manifest found — run the collector first", "ERR")
        return

    log(f"Manifest: {len(manifest)} documents")

    done_hashes = get_done_hashes(state)
    log(f"Already completed: {len(done_hashes)} packages")

    # Handle interrupted package
    if state.get("in_progress"):
        ip = state["in_progress"]
        log(f"Found interrupted package {ip['hash']} — skipping it", "INFO")
        done_hashes.add(ip["hash"])
        state["in_progress"] = None
        save_state(state)

    # Build all candidate packages
    all_packages = build_all_packages(manifest, done_hashes)

    total_available = sum(len(pkgs) for pkgs in all_packages.values())
    for strategy, pkgs in all_packages.items():
        log(f"  {strategy}: {len(pkgs)} packages available")

    if total_available == 0:
        log("No new packages to process — all done!", "OK")
        return

    # Filter by strategy if specified
    if strategy_filter != "all":
        if strategy_filter in all_packages:
            filtered = {strategy_filter: all_packages[strategy_filter]}
            all_packages = filtered
        else:
            log(f"Unknown strategy: {strategy_filter}", "ERR")
            return

    # Process packages
    total_qas = 0
    processed = 0

    while True:
        strategy = pick_strategy(all_packages)
        if strategy is None:
            break

        package = all_packages[strategy].pop(0)
        qa_count = await process_package(package, state)
        total_qas += qa_count
        processed += 1

        remaining = sum(len(pkgs) for pkgs in all_packages.values())
        if remaining == 0:
            break

        await asyncio.sleep(BATCH_INTERVAL)

    print(f"\n  Done! Processed {processed} packages, generated {total_qas} QAs total.")


def main():
    """CLI entry point."""
    strategy = "all"
    if len(sys.argv) > 1:
        strategy = sys.argv[1].lower()

    asyncio.run(run(strategy))


if __name__ == "__main__":
    main()
