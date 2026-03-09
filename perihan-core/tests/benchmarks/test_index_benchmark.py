"""Benchmark: measure indexing time (chunking + ChromaDB upsert) for files in tests/test-material/.

Uses an isolated ChromaDB in tests/_benchmark_db/ — does NOT touch the real vector database.
No LLM calls — measures only local processing speed.

Usage:
    python tests/test_index_benchmark.py
"""

import asyncio
import shutil
import sys
import time
from pathlib import Path

BENCH_DIR = Path(__file__).resolve().parent
ROOT = BENCH_DIR.parent.parent.parent
sys.path.insert(0, str(ROOT / "perihan-core" / "src"))
sys.path.insert(0, str(ROOT / "perihan-app" / "src"))

import chromadb
from perihan_core.config import COLLECTION_NAME
from perihan_core.services.index_service import index_local_folder

BENCHMARK_DB = BENCH_DIR / "_benchmark_db"


def create_test_collection():
    if BENCHMARK_DB.exists():
        shutil.rmtree(BENCHMARK_DB, ignore_errors=True)
    BENCHMARK_DB.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(BENCHMARK_DB))
    return client.get_or_create_collection(name=f"{COLLECTION_NAME}_benchmark")


async def run_benchmark():
    test_folder = BENCH_DIR / "test-material"
    if not test_folder.exists():
        print(f"ERROR: {test_folder} not found")
        return

    files = [f for f in test_folder.iterdir() if f.is_file()]
    total_bytes = sum(f.stat().st_size for f in files)
    print(f"Test folder: {test_folder}")
    print(f"Files: {len(files)}  Total size: {total_bytes:,} bytes")
    for f in files:
        print(f"  - {f.name} ({f.stat().st_size:,} bytes)")
    print("-" * 50)

    collection = create_test_collection()

    file_timings = {}
    t_start = time.perf_counter()

    async for event in index_local_folder(
        str(test_folder),
        collection=collection,
        llm_client=None,
        model=None,
    ):
        etype = event.get("type", "")
        step = event.get("step", "")
        fname = event.get("file", "")

        if etype == "start":
            print(f"\nIndexing {event['total']} file(s)...\n")

        elif etype == "progress" and step == "chunking":
            file_timings[fname] = {"start": time.perf_counter()}
            print(f"  [{fname}] Chunking + upserting...")

        elif etype == "progress" and step == "summarizing":
            file_timings[fname]["upsert_done"] = time.perf_counter()

        elif etype == "file_done":
            t = file_timings.get(fname, {})
            t["end"] = time.perf_counter()
            elapsed = t["end"] - t["start"]
            print(f"  [{fname}] Done: {event['chunks']} chunk(s) in {elapsed:.3f}s")

        elif etype == "file_error":
            # LLM summary error is expected (no client) — ignore
            if "llm_client" not in event.get("error", ""):
                print(f"  [{fname}] ERROR: {event.get('error')}")

        elif etype == "skip":
            print(f"  [{fname}] Skipped: {event.get('reason')}")

    t_total = time.perf_counter() - t_start

    print()
    print("=" * 50)
    print("BENCHMARK RESULTS")
    print("=" * 50)
    print(f"Total time:        {t_total:.3f}s")
    print()

    for fname, t in file_timings.items():
        upsert_t = t.get("upsert_done", t.get("end", 0)) - t["start"]
        print(f"  {fname}:")
        print(f"    Chunking + ChromaDB upsert:  {upsert_t:.3f}s")

    print()
    stored = collection.get()
    print(f"Chunks stored:     {len(stored['ids'])}")
    print(f"DB location:       {BENCHMARK_DB}")
    print()
    print("Stored document IDs:")
    for doc_id in sorted(stored["ids"]):
        print(f"  {doc_id}")
    print()
    print(f"Cleanup: delete {BENCHMARK_DB} when done")


if __name__ == "__main__":
    asyncio.run(run_benchmark())
