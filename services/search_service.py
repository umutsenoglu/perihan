import re
import difflib

# Module-level vocabulary cache for robust fuzzy expansion
_global_vocab: set[str] = set()


def build_global_vocab() -> None:
    """Rebuild vocabulary from all indexed document content and metadata."""
    global _global_vocab
    # Lazy import to avoid circular deps
    from dependencies import get_collection

    try:
        collection = get_collection()
        all_data = collection.get(include=["documents", "metadatas"])
        vocab: set[str] = set()
        for doc in all_data["documents"]:
            for word in re.split(r'\W+', doc):
                if 3 <= len(word) <= 30:
                    vocab.add(word.lower())
        for meta in all_data["metadatas"]:
            for field in ("title", "relative_path"):
                for part in re.split(r'[\W_0-9]+', meta.get(field, "")):
                    if 3 <= len(part) <= 30:
                        vocab.add(part.lower())
        _global_vocab = vocab
    except Exception:
        pass


def hybrid_search(query: str, n_results: int = 5, where: dict = None):
    """Hybrid search: keyword matches first, then vector results."""
    # Lazy import to avoid circular deps
    from dependencies import get_collection

    collection = get_collection()

    # --- Keyword search ---
    # Only take words 5+ chars, strip punctuation, deduplicate
    # Common short words to exclude from keyword search
    _stopwords = {"the", "and", "for", "are", "but", "not", "you", "all",
                  "can", "has", "her", "his", "how", "its", "may", "our",
                  "was", "who", "did", "get", "got", "had", "him", "let",
                  "say", "she", "too", "use", "bir", "ben", "sen",
                  "ile", "var", "ama", "onu", "hem",
                  "what", "when", "where", "which", "does", "that",
                  "this", "from", "have", "been", "will", "with",
                  "about", "there", "their", "would", "could", "should",
                  "these", "those", "what's"}

    words = query.split()
    base_keywords = []
    seen_kw = set()
    for w in words:
        cleaned = w.strip("?.,!\"'():-")
        # Remove possessive 's suffix (e.g. "Seb's" → "Seb")
        if cleaned.endswith("'s") or cleaned.endswith("\u2019s"):
            cleaned = cleaned[:-2]
        if len(cleaned) < 3:
            continue
        cl = cleaned.lower()
        if cl in _stopwords:
            continue
        if cl not in seen_kw:
            seen_kw.add(cl)
            base_keywords.append(cleaned)

    # Build per-keyword stem groups and track keyword weight
    keyword_groups = {}  # base_kw -> [(stem, weight), ...]
    all_keywords = []    # [(keyword, weight), ...]
    for kw in base_keywords:
        weight = len(kw)
        # Boost proper nouns (capitalized words that aren't sentence starters)
        # Names like "Seb", "Ron", "Alp" are highly specific search terms
        if kw[0].isupper() and kw.lower() not in _stopwords:
            weight = max(weight, 8)
        group = [(kw, weight)]
        all_keywords.append((kw, weight))
        if len(kw) >= 7:
            for trim in range(1, 4):
                stem = kw[:-trim]
                if len(stem) < 4:
                    break
                stem_lower = stem.lower()
                if stem_lower not in seen_kw:
                    seen_kw.add(stem_lower)
                    stem_weight = len(stem)
                    group.append((stem, stem_weight))
                    all_keywords.append((stem, stem_weight))
        keyword_groups[kw] = group

    # --- Vector search (run early so its content powers fuzzy expansion) ---
    query_kwargs = {
        "query_texts": [query],
        "n_results": n_results,
        "include": ["documents", "metadatas"],
    }
    if where:
        query_kwargs["where"] = where
    vector_results = collection.query(**query_kwargs)
    v_docs = vector_results["documents"][0] if vector_results["documents"][0] else []
    v_metas = vector_results["metadatas"][0] if vector_results["metadatas"][0] else []
    v_ids = vector_results["ids"][0] if vector_results["ids"][0] else []

    # --- Fuzzy keyword expansion (typo tolerance) ---
    # Use the global vocab cache (all words from all indexed docs) so corrections
    # work regardless of what the vector search happens to return for a given query.
    try:
        vocab = set(_global_vocab)  # copy of global cache
        # Supplement with current vector result content (handles words indexed
        # after the last vocab rebuild, and query-specific context)
        for doc in v_docs:
            for word in re.split(r'\W+', doc):
                if len(word) >= 4:
                    vocab.add(word.lower())
        existing_lower = {kw.lower() for kw, _ in all_keywords}
        checked = set()
        for kw, weight in list(all_keywords):  # includes stems like "Domonik" from "Domonik's"
            kw_l = kw.lower()
            if kw_l in checked:
                continue
            checked.add(kw_l)
            if kw_l not in vocab:
                for match in difflib.get_close_matches(kw_l, vocab, n=2, cutoff=0.82):
                    if match not in existing_lower:
                        existing_lower.add(match)
                        all_keywords.append((match, len(match)))
    except Exception:
        pass  # fuzzy expansion is best-effort, never blocks the search

    # --- Keyword search: find candidate chunks ---
    chunk_data = {}  # id -> {doc, meta}
    errors = []

    searched_terms = set()
    for kw, _weight in all_keywords:
        for search_term in (kw, kw.lower(), kw.capitalize()):
            if search_term in searched_terms:
                continue
            searched_terms.add(search_term)
            try:
                get_kwargs = {
                    "where_document": {"$contains": search_term},
                    "include": ["documents", "metadatas"],
                    "limit": n_results * 2,
                }
                if where:
                    get_kwargs["where"] = where
                kw_results = collection.get(**get_kwargs)
                for id_, doc, meta in zip(
                    kw_results["ids"], kw_results["documents"], kw_results["metadatas"]
                ):
                    if id_ not in chunk_data:
                        chunk_data[id_] = {"doc": doc, "meta": meta}
            except Exception as e:
                errors.append(f"{search_term}: {e}")
                continue

    # --- Count how many candidate chunks contain each keyword ---
    total_candidates = len(chunk_data)
    kw_doc_freq = {}  # keyword_lower -> number of chunks containing it
    for kw, _w in all_keywords:
        kw_lower = kw.lower()
        if kw_lower not in kw_doc_freq:
            count = 0
            for data in chunk_data.values():
                if kw_lower in data["doc"].lower():
                    count += 1
            kw_doc_freq[kw_lower] = max(count, 1)

    # Only keep RARE keywords (appear in <10% of candidates) for scoring
    rare_threshold = max(total_candidates * 0.10, 3)
    rare_keywords = [
        (kw, w) for kw, w in all_keywords if kw_doc_freq.get(kw.lower(), 999) <= rare_threshold
    ]

    # Always include the original base keywords in scoring even when they are too
    # common to qualify as rare. A query like "Abdullah ile yazışma" should always
    # reward chunks that contain "Abdullah" — even if the user has many Abdullah
    # conversations that push it above the rare threshold.
    rare_kw_lower = {kw.lower() for kw, _ in rare_keywords}
    base_weights = {kw: w for kw, w in all_keywords if kw in base_keywords}
    forced_base = [(kw, base_weights.get(kw, len(kw))) for kw in base_keywords if kw.lower() not in rare_kw_lower]
    score_keywords = rare_keywords + forced_base

    # --- Re-score using rare keywords + forced base keywords ---
    scored = []
    for id_, data in chunk_data.items():
        doc_lower = data["doc"].lower()
        title_lower = data["meta"].get("title", "").lower()
        rel_path_lower = data["meta"].get("relative_path", "").lower()
        score = 0.0
        matched_rare = []
        for kw, weight in score_keywords:
            if kw.lower() in doc_lower:
                score += weight
                matched_rare.append(kw)
        # Bonus for matching multiple distinct base keywords — chunks that contain
        # more of the user's original terms are much more likely to be relevant.
        matched_base_count = sum(1 for kw in base_keywords if kw.lower() in doc_lower)
        if matched_base_count >= 2:
            # Quadratic bonus — matching 3 of 4 keywords is MUCH better than 2 of 4
            score += matched_base_count ** 2
        # Filename/title bonus:
        # - Short keywords (< 5 chars): word-split only  → "what" won't match "whatsapp"
        # - Longer keywords (≥ 5 chars): also substring  → "abdullah" matches "abdullahavci123.xml"
        title_words = set(re.split(r'[^a-z0-9]+', title_lower))
        path_words = set(re.split(r'[^a-z0-9]+', rel_path_lower))
        for kw, weight in all_keywords:
            kl = kw.lower()
            in_title = kl in title_words or (len(kl) >= 5 and kl in title_lower)
            in_path = kl in path_words or (len(kl) >= 5 and kl in rel_path_lower)
            if in_title or in_path:
                score += weight * 2
        scored.append((id_, data["doc"], data["meta"], round(score, 1), matched_rare))

    # Sort by score descending
    scored.sort(key=lambda x: x[3], reverse=True)
    ranked = [
        (id_, {"doc": doc, "meta": meta, "score": sc, "matched_rare": mr})
        for id_, doc, meta, sc, mr in scored
    ]

    keyword_ids = [id_ for id_, _ in ranked]
    keyword_docs = [d["doc"] for _, d in ranked]
    keyword_metas = [d["meta"] for _, d in ranked]

    # Take the top-n keyword results, then supplement with vector results.
    # seen_ids only covers what we're actually returning so that a chunk ranked
    # just below the keyword cutoff can still be promoted via vector search.
    out_docs = keyword_docs[:n_results]
    out_metas = keyword_metas[:n_results]
    seen_ids = set(keyword_ids[:n_results])

    # --- Merge: keyword results first (scored), then vector (deduplicated) ---
    for id_, doc, meta in zip(v_ids, v_docs, v_metas):
        if id_ not in seen_ids:
            seen_ids.add(id_)
            out_docs.append(doc)
            out_metas.append(meta)

    # Build debug info
    debug = {
        "rare_keywords": [
            f"{kw}(w={w}, freq={kw_doc_freq.get(kw.lower(), 0)})" for kw, w in rare_keywords
        ],
        "forced_base_keywords": [
            f"{kw}(w={w}, freq={kw_doc_freq.get(kw.lower(), 0)})" for kw, w in forced_base
        ],
        "rare_threshold": rare_threshold,
        "total_keywords": len(all_keywords),
        "errors": errors[:10],
        "keyword_chunks_found": len(chunk_data),
        "top_keyword_results": [
            {
                "id": id_,
                "score": d["score"],
                "title": d["meta"].get("title", ""),
                "matched_rare": d.get("matched_rare", []),
                "preview": d["doc"][:150],
            }
            for id_, d in ranked[:8]
        ],
        "vector_results": [
            {"id": id_, "title": meta.get("title", "")} for id_, meta in zip(v_ids, v_metas)
        ],
        "expanded_terms": [kw.lower() for kw, _ in all_keywords],
    }

    return out_docs, out_metas, debug
