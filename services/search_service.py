import re
import math
import difflib

# Module-level vocabulary cache for robust fuzzy expansion
_global_vocab: set[str] = set()


def build_global_vocab(collection=None) -> None:
    """Rebuild vocabulary from all indexed document content and metadata."""
    global _global_vocab

    if collection is None:
        from dependencies import get_collection
        collection = get_collection()

    try:
        all_data = collection.get(include=["documents", "metadatas"])
        vocab: set[str] = set()
        for doc in all_data["documents"]:
            for word in re.split(r'\W+', doc):
                if 3 <= len(word) <= 30:
                    vocab.add(word.lower())
        for meta in all_data["metadatas"]:
            for field in ("title", "relative_path", "chat_name"):
                for part in re.split(r'[\W_0-9]+', meta.get(field, "")):
                    if 3 <= len(part) <= 30:
                        vocab.add(part.lower())
        _global_vocab = vocab
    except Exception:
        pass


def hybrid_search(query: str, n_results: int = 5, where: dict = None, *, collection=None):
    """Hybrid search: keyword matches first, then vector results."""
    if collection is None:
        from dependencies import get_collection
        collection = get_collection()

    # --- Keyword search ---
    # Only take words 5+ chars, strip punctuation, deduplicate
    # Common short words to exclude from keyword search
    _stopwords = {"the", "and", "for", "are", "but", "not", "you", "all",
                  "can", "has", "her", "his", "how", "its", "may", "our",
                  "was", "who", "did", "get", "got", "had", "him", "let",
                  "say", "she", "too", "use",
                  "what", "when", "where", "which", "does", "that",
                  "this", "from", "have", "been", "will", "with",
                  "about", "there", "their", "would", "could", "should",
                  "these", "those", "what's",
                  # Turkish stopwords (conservative — only truly generic words)
                  "bir", "ben", "sen", "ile", "var", "ama", "onu", "hem",
                  "kim", "kime", "kimi", "nin", "nın", "dan", "den",
                  "için", "icin", "gibi", "daha", "kadar", "nasıl", "nasil",
                  "nedir", "neden", "nere", "nerede", "hangi",
                  "olan", "olarak", "bana", "sana", "ona",
                  "benim", "senin", "onun", "bizim", "bunun",
                  "etti", "eden", "etmek",
                  "söyledi", "soyledi", "gönderdi", "gonderdi",}

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

    # --- Bigram phrase search ---
    # Consecutive word pairs from the query are much more discriminative than
    # individual words (e.g. "new year" vs "new" + "year" separately).
    phrases = []
    cleaned_words = []
    for w in words:
        cw = w.strip("?.,!\"'():-")
        if len(cw) >= 3:
            cleaned_words.append(cw)
    for i in range(len(cleaned_words) - 1):
        a, b = cleaned_words[i], cleaned_words[i + 1]
        phrase = f"{a} {b}"
        phrase_lower = phrase.lower()
        # Skip if both words are stopwords
        if a.lower() in _stopwords and b.lower() in _stopwords:
            continue
        phrases.append(phrase)
        # Phrase weight: multi-word matches are far more discriminative than
        # individual words.  A doc matching "new year" is much more relevant
        # than one that coincidentally contains "new" and "year" separately.
        a_wt = max(len(a), 8) if a[0].isupper() else len(a)
        b_wt = max(len(b), 8) if b[0].isupper() else len(b)
        phrase_weight = (a_wt + b_wt) * 2 + 10
        all_keywords.append((phrase, phrase_weight))

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
            # Skip fuzzy expansion for phrases — they match concatenated
            # vocab words too aggressively (e.g. "email address" → "mailaddress")
            if " " in kw_l:
                continue
            if kw_l not in vocab:
                for match in difflib.get_close_matches(kw_l, vocab, n=2, cutoff=0.82):
                    if match not in existing_lower:
                        existing_lower.add(match)
                        all_keywords.append((match, len(match)))
    except Exception:
        pass  # fuzzy expansion is best-effort, never blocks the search

    # --- Cross-lingual keyword expansion ---
    # The indexed data mixes Turkish and English.  Add common translations
    # so a Turkish query can find English content and vice versa.
    _translations = {
        "noel": "christmas", "christmas": "noel",
        "yılbaşı": "new year", "yilbasi": "new year",
    }
    existing_lower = {kw.lower() for kw, _ in all_keywords}
    base_kw_lower = {kw.lower() for kw in base_keywords}
    for kw, weight in list(all_keywords):
        tr = _translations.get(kw.lower())
        if tr and tr not in existing_lower:
            existing_lower.add(tr)
            all_keywords.append((tr, weight))
            # Also add to base_keywords so it gets scored via forced_base
            if kw.lower() in base_kw_lower and tr not in base_kw_lower:
                base_kw_lower.add(tr)
                base_keywords.append(tr)

    # --- Keyword search: find candidate chunks ---
    chunk_data = {}  # id -> {doc, meta}
    errors = []

    searched_terms = set()
    searched_folders = set()
    for kw, _weight in all_keywords:
        for search_term in (kw, kw.lower(), kw.capitalize()):
            if search_term in searched_terms:
                continue
            searched_terms.add(search_term)
            try:
                get_kwargs = {
                    "where_document": {"$contains": search_term},
                    "include": ["documents", "metadatas"],
                    "limit": n_results * 5,
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

            # Also search by metadata (folder, chat_name) so group/folder
            # names in queries always surface the right chunks
            if search_term not in searched_folders:
                searched_folders.add(search_term)
                for meta_field in ("folder", "chat_name"):
                    try:
                        meta_filter = {meta_field: search_term}
                        if where:
                            meta_filter = {"$and": [where, meta_filter]}
                        meta_results = collection.get(
                            where=meta_filter,
                            include=["documents", "metadatas"],
                        )
                        for id_, doc, meta in zip(
                            meta_results["ids"],
                            meta_results["documents"],
                            meta_results["metadatas"],
                        ):
                            if id_ not in chunk_data:
                                chunk_data[id_] = {"doc": doc, "meta": meta}
                    except Exception:
                        pass

    # --- Count how many candidate chunks contain each keyword ---
    total_candidates = len(chunk_data)
    kw_doc_freq = {}  # keyword_lower -> number of chunks containing it
    # Pre-compile word-boundary patterns for short keywords to avoid
    # substring inflation (e.g. "seb" matching 200 "seboistnet" docs)
    _wb_patterns = {}
    for kw, _w in all_keywords:
        kl = kw.lower()
        if " " not in kl and len(kl) < 5 and kl not in _wb_patterns:
            _wb_patterns[kl] = re.compile(r'\b' + re.escape(kl) + r'\b')
    for kw, _w in all_keywords:
        kw_lower = kw.lower()
        if kw_lower not in kw_doc_freq:
            count = 0
            wb = _wb_patterns.get(kw_lower)
            for data in chunk_data.values():
                doc_lower = data["doc"].lower()
                if wb:
                    if wb.search(doc_lower):
                        count += 1
                else:
                    if kw_lower in doc_lower:
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
    # IDF base: use total candidates (floored at 20 to avoid extreme values)
    idf_base = max(total_candidates, 20)
    # Only exact base keywords get IDF boost — stems are fuzzy derivatives
    # and IDF-amplifying them inflates scores for chunks that happen to
    # contain a common substring (e.g. "yazi" stem matching many docs).
    base_kw_lower = {kw.lower() for kw in base_keywords}
    rare_base_set = {kw.lower() for kw, _ in rare_keywords if kw.lower() in base_kw_lower}
    # Phrases also get IDF (they're highly discriminative, not stems)
    for kw, _ in rare_keywords:
        if " " in kw:
            rare_base_set.add(kw.lower())

    scored = []
    for id_, data in chunk_data.items():
        doc_lower = data["doc"].lower()
        title_lower = data["meta"].get("title", "").lower()
        rel_path_lower = data["meta"].get("relative_path", "").lower()
        score = 0.0
        matched_rare = []
        for kw, weight in score_keywords:
            kl = kw.lower()
            # Short keywords: word-boundary match to avoid substring noise
            wb = _wb_patterns.get(kl)
            matched = wb.search(doc_lower) if wb else (kl in doc_lower)
            if matched:
                if kl in rare_base_set:
                    # Rare base keywords/phrases: IDF boost (capped)
                    freq = kw_doc_freq.get(kl, 1)
                    idf = min(math.log(idf_base / max(freq, 1)) + 1, 2.5)
                    score += weight * idf
                else:
                    # Forced base keywords: flat weight (already common, no IDF)
                    score += weight
                matched_rare.append(kw)
        # Bonus for matching multiple distinct base keywords — chunks that contain
        # more of the user's original terms are much more likely to be relevant.
        matched_base_count = sum(1 for kw in base_keywords if kw.lower() in doc_lower)
        if matched_base_count >= 2:
            # Quadratic bonus — matching 3 of 4 keywords is MUCH better than 2 of 4
            score += matched_base_count ** 2
        # Filename/title/chat_name bonus:
        # - Short keywords (< 5 chars): word-split only  → "what" won't match "whatsapp"
        # - Longer keywords (≥ 5 chars): also substring  → "abdullah" matches "abdullahavci123.xml"
        chat_name_lower = data["meta"].get("chat_name", "").lower()
        title_words = set(re.split(r'[^a-z0-9]+', title_lower))
        path_words = set(re.split(r'[^a-z0-9]+', rel_path_lower))
        chat_words = set(re.split(r'[^a-z0-9]+', chat_name_lower))
        for kw, weight in all_keywords:
            kl = kw.lower()
            in_title = kl in title_words or (len(kl) >= 5 and kl in title_lower)
            in_path = kl in path_words or (len(kl) >= 5 and kl in rel_path_lower)
            in_chat = kl in chat_words or (len(kl) >= 5 and kl in chat_name_lower)
            if in_title or in_path or in_chat:
                score += weight * 2
            # Extra bonus when keyword matches a chat/group name — the user is
            # asking about a specific conversation, so those chunks should rank
            # much higher than accidental Turkish-keyword matches elsewhere.
            if in_chat:
                score += weight * 2
        # Phrase match bonus: rare phrases get full bonus, common ones get less
        for phrase in phrases:
            if phrase.lower() in doc_lower:
                phrase_freq = kw_doc_freq.get(phrase.lower(), 1)
                if phrase_freq <= rare_threshold:
                    score += 20  # rare phrase — highly discriminative
                else:
                    score += 5   # common phrase — small bonus
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

    # --- Targeted vector search within dominant groups ---
    # When keyword search finds many entries from the same source (chat or file),
    # keyword scoring alone can't distinguish them.  Run a vector query scoped
    # to that group so the most *semantically* relevant entry surfaces.
    group_counts: dict[tuple[str, str], int] = {}  # (field, value) -> count
    for _, data in ranked:
        cn = data["meta"].get("chat_name", "")
        rp = data["meta"].get("relative_path", "")
        if cn:
            key = ("chat_name", cn)
        elif rp:
            key = ("relative_path", rp)
        else:
            continue
        group_counts[key] = group_counts.get(key, 0) + 1
    # Distilled query using only base keywords — removes stopwords and
    # common Turkish words that dilute the embedding for vector search
    distilled_query = " ".join(base_keywords) if base_keywords else query
    for (field, value), count in group_counts.items():
        if count > n_results:
            try:
                group_filter: dict = {field: value}
                if where:
                    group_filter = {"$and": [where, group_filter]}
                chat_vector = collection.query(
                    query_texts=[distilled_query],
                    where=group_filter,
                    n_results=min(n_results, 4),
                    include=["documents", "metadatas"],
                )
                # Boost scores of existing entries that the vector search deems
                # most relevant — the first result gets the biggest boost
                vector_ids = chat_vector["ids"][0]
                ranked_idx = {rid: i for i, (rid, _) in enumerate(ranked)}
                for rank_pos, vid in enumerate(vector_ids):
                    idx = ranked_idx.get(vid)
                    if idx is not None:
                        # Top vector result gets biggest boost (4→1 points)
                        boost = max(1, len(vector_ids) - rank_pos)
                        old = ranked[idx][1]["score"]
                        ranked[idx][1]["score"] = old + boost
                    else:
                        # New entry not yet in candidates
                        grp_scores = [d["score"] for _, d in ranked if d["meta"].get(field) == value]
                        top_score = max(grp_scores) if grp_scores else 0
                        doc = chat_vector["documents"][0][rank_pos]
                        meta = chat_vector["metadatas"][0][rank_pos]
                        ranked.append((vid, {"doc": doc, "meta": meta, "score": top_score + 1, "matched_rare": []}))
            except Exception:
                pass

    # Re-sort after injections
    ranked.sort(key=lambda x: x[1]["score"], reverse=True)

    # --- Source diversity ---
    # When many chunks share the same filename across folders (e.g. 50+
    # abdullahavci chunks in 5 folders), ensure we pick from different
    # relative_paths (folders) to cover different time periods.
    # First pass: count unique titles to identify duplicated filenames.
    title_total: dict[str, int] = {}
    for _, data in ranked:
        t = data["meta"].get("title", "")
        title_total[t] = title_total.get(t, 0) + 1
    max_per_title = max(n_results // 2, 3)
    # For titles with many chunks: round-robin across relative_paths
    diverse_ranked = []
    overflow = []
    title_rp_counts: dict[str, dict[str, int]] = {}  # title -> {rp -> count}
    title_counts: dict[str, int] = {}
    for item in ranked:
        title = item[1]["meta"].get("title", "")
        total = title_total.get(title, 0)
        if total <= max_per_title:
            # Not enough to hit the cap — keep as-is
            diverse_ranked.append(item)
            continue
        cnt = title_counts.get(title, 0)
        if cnt >= max_per_title:
            overflow.append(item)
            continue
        # Within the cap: limit 1 per relative_path for cross-folder diversity
        rp = item[1]["meta"].get("relative_path", "")
        rp_counts = title_rp_counts.setdefault(title, {})
        rp_cnt = rp_counts.get(rp, 0)
        if rp_cnt == 0:
            diverse_ranked.append(item)
            rp_counts[rp] = 1
            title_counts[title] = cnt + 1
        else:
            overflow.append(item)
    # If we didn't fill the cap (fewer unique paths than max_per_title),
    # take more from remaining overflow for those titles
    for item in list(overflow):
        title = item[1]["meta"].get("title", "")
        total = title_total.get(title, 0)
        if total <= max_per_title:
            continue
        cnt = title_counts.get(title, 0)
        if cnt < max_per_title:
            diverse_ranked.append(item)
            title_counts[title] = cnt + 1
            overflow.remove(item)
    diverse_ranked.extend(overflow)
    ranked = diverse_ranked

    keyword_ids = [id_ for id_, _ in ranked]
    keyword_docs = [d["doc"] for _, d in ranked]
    keyword_metas = [d["meta"] for _, d in ranked]

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
