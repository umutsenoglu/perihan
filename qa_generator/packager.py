"""Package builder — groups documents into packages for QA generation."""

import hashlib
import json
import random
from pathlib import Path

from config import COLLECTOR_OUTPUT_DIR, MANIFEST_FILE, MAX_PACKAGE_BYTES


def load_manifest() -> list[dict]:
    """Load the collector manifest."""
    if not MANIFEST_FILE.exists():
        return []
    try:
        return json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def read_document(path: str) -> str | None:
    """Read a document from the collector output directory."""
    full_path = COLLECTOR_OUTPUT_DIR / path
    if not full_path.exists():
        return None
    try:
        return full_path.read_text(encoding="utf-8")
    except Exception:
        return None


def package_hash(file_paths: list[str]) -> str:
    """Create a deterministic hash for a set of file paths."""
    key = "|".join(sorted(file_paths))
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def estimate_size(file_paths: list[str]) -> int:
    """Estimate total byte size of a set of documents."""
    total = 0
    for p in file_paths:
        full_path = COLLECTOR_OUTPUT_DIR / p
        if full_path.exists():
            total += full_path.stat().st_size
    return total


def build_single_doc_packages(manifest: list[dict], done_hashes: set[str]) -> list[dict]:
    """Strategy 1: One document per package → search questions."""
    packages = []
    for entry in manifest:
        path = entry["path"]
        h = package_hash([path])
        if h in done_hashes:
            continue
        size = estimate_size([path])
        if size == 0 or size > MAX_PACKAGE_BYTES:
            continue
        packages.append({
            "hash": h,
            "strategy": "single_doc",
            "files": [path],
            "storyline": entry.get("storyline"),
            "category": entry.get("category"),
        })
    random.shuffle(packages)
    return packages


def build_same_category_packages(manifest: list[dict], done_hashes: set[str]) -> list[dict]:
    """Strategy 2: Group documents by category → reasoning questions."""
    # Group by category
    by_category: dict[str, list[dict]] = {}
    for entry in manifest:
        cat = entry.get("category", "unknown")
        by_category.setdefault(cat, []).append(entry)

    packages = []
    for cat, entries in by_category.items():
        if len(entries) < 3:
            continue
        # Build packages of 5-15 docs, respecting 3 MB limit
        random.shuffle(entries)
        batch = []
        batch_size = 0
        for entry in entries:
            path = entry["path"]
            file_size = estimate_size([path])
            if file_size == 0:
                continue
            if batch_size + file_size > MAX_PACKAGE_BYTES:
                # Flush current batch
                if len(batch) >= 3:
                    paths = [e["path"] for e in batch]
                    h = package_hash(paths)
                    if h not in done_hashes:
                        packages.append({
                            "hash": h,
                            "strategy": "same_category",
                            "files": paths,
                            "storyline": None,
                            "category": cat,
                        })
                batch = []
                batch_size = 0
            batch.append(entry)
            batch_size += file_size

            if len(batch) >= 15:
                paths = [e["path"] for e in batch]
                h = package_hash(paths)
                if h not in done_hashes:
                    packages.append({
                        "hash": h,
                        "strategy": "same_category",
                        "files": paths,
                        "storyline": None,
                        "category": cat,
                    })
                batch = []
                batch_size = 0

        # Remaining batch
        if len(batch) >= 3:
            paths = [e["path"] for e in batch]
            h = package_hash(paths)
            if h not in done_hashes:
                packages.append({
                    "hash": h,
                    "strategy": "same_category",
                    "files": paths,
                    "storyline": None,
                    "category": cat,
                })

    random.shuffle(packages)
    return packages


def build_cross_storyline_packages(manifest: list[dict], done_hashes: set[str]) -> list[dict]:
    """Strategy 3: Group documents by storyline across categories → multi-doc questions."""
    # Group by storyline (skip None)
    by_storyline: dict[str, list[dict]] = {}
    for entry in manifest:
        sl = entry.get("storyline")
        if sl:
            by_storyline.setdefault(sl, []).append(entry)

    packages = []
    for storyline_id, entries in by_storyline.items():
        if len(entries) < 2:
            continue

        # Ensure we have multiple categories
        categories = set(e.get("category") for e in entries)

        # Build a package with all docs from this storyline (up to 3 MB)
        random.shuffle(entries)
        batch = []
        batch_size = 0
        for entry in entries:
            path = entry["path"]
            file_size = estimate_size([path])
            if file_size == 0:
                continue
            if batch_size + file_size > MAX_PACKAGE_BYTES:
                break
            batch.append(entry)
            batch_size += file_size

        if len(batch) >= 2:
            paths = [e["path"] for e in batch]
            h = package_hash(paths)
            if h not in done_hashes:
                packages.append({
                    "hash": h,
                    "strategy": "cross_storyline",
                    "files": paths,
                    "storyline": storyline_id,
                    "category": None,
                    "categories": list(set(e.get("category") for e in batch)),
                })

    random.shuffle(packages)
    return packages


def build_all_packages(manifest: list[dict], done_hashes: set[str]) -> dict[str, list[dict]]:
    """Build all candidate packages grouped by strategy."""
    return {
        "single_doc": build_single_doc_packages(manifest, done_hashes),
        "same_category": build_same_category_packages(manifest, done_hashes),
        "cross_storyline": build_cross_storyline_packages(manifest, done_hashes),
    }


def load_package_contents(package: dict) -> list[dict]:
    """Load actual file contents for a package. Returns list of {path, content}."""
    docs = []
    for path in package["files"]:
        content = read_document(path)
        if content:
            docs.append({"path": path, "content": content})
    return docs
