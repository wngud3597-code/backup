"""Explicit user actions connecting discovery and preparation to existing stores."""

from movie_lab.config import resolve_document_cache_path, resolve_index_path
from dataclasses import asdict

from movie_lab.discovery import discover_movies, filter_catalog, parse_conditions, semantic_query
from movie_lab.document_pipeline import SuccessCache, fingerprint
from movie_lab.embeddings import create_gms_embeddings
from movie_lab.index import IndexConfigurationError, MetadataIndex, read_index_config


DISCOVERY_CACHE_VERSION = "metadata-prefilter-v1"
SEMANTIC_PREPROCESS_VERSION = "catalog-semantic-query-v1"
SEMANTIC_TOP_K = 3


def discovery_cache_key(query, movies, config, eligibility):
    """Include every loaded Movie field used by filtering or ranking."""
    conditions = dict(eligibility["conditions"])
    for name, value in conditions.items():
        if isinstance(value, list):
            conditions[name] = sorted(value)
    allowed = sorted(eligibility["eligible_ids"])
    return "discovery:" + DISCOVERY_CACHE_VERSION + ":" + fingerprint({
        "query": query.strip(), "conditions": conditions,
        "eligible_ids_hash": fingerprint(allowed),
        "semantic_query": semantic_query(query, eligibility["conditions"]) or query,
        "preprocess_version": SEMANTIC_PREPROCESS_VERSION, "semantic_k": SEMANTIC_TOP_K,
        "config": asdict(config), "collection": config.collection_name,
        "catalog": [asdict(movies[mid]) for mid in sorted(movies)],
    })


def valid_discovery_hits(hits, movies, allowed_ids):
    """Reject corrupt/stale cache entries and out-of-scope backend responses."""
    if not isinstance(hits, list) or len(hits) > SEMANTIC_TOP_K:
        return False
    allowed = set(allowed_ids)
    seen = set()
    for hit in hits:
        if not isinstance(hit, dict):
            return False
        mid = hit.get("movie_id")
        if (not isinstance(mid, str) or mid not in allowed or mid not in movies or mid in seen
                or hit.get("document_id") != f"meta:{mid}"
                or hit.get("title") != movies[mid].title):
            return False
        seen.add(mid)
    return True


def search_catalog(query, movies):
    parsed = parse_conditions(query, movies)
    eligibility = filter_catalog(query, movies, conditions=parsed)
    # Exact title disambiguation needs no embedding call.
    if parsed.get("title_ids") or eligibility["state"] != "ready":
        result = discover_movies(query, movies)
        result.update({"semantic_cache_hit": False, "semantic_top_k": SEMANTIC_TOP_K,
                       "semantic_hits": [], "semantic_skipped": eligibility["state"]
                       if eligibility["state"] != "ready" else "exact_title"})
        return result
    path = resolve_index_path()
    config = read_index_config(path)
    cache = SuccessCache(resolve_document_cache_path())
    key = discovery_cache_key(query, movies, config, eligibility)
    hits = cache.get(key)
    rejected = bool(hits) and not valid_discovery_hits(hits, movies, eligibility["eligible_ids"])
    cached = bool(hits) and not rejected
    if rejected:
        hits = None
    store = None
    try:
        if not hits:
            store = MetadataIndex(path, config, create=False)
            selected = {mid: movies[mid] for mid in eligibility["eligible_ids"]}
            verification = store.verify_movies(selected, check_vectors=False)
            if verification["missing"] or verification["mismatched"]:
                raise IndexConfigurationError("조건에 맞는 영화의 저장 문서가 누락되거나 현재 데이터와 달라 제한 검색을 중단했습니다.")
            embedder = create_gms_embeddings(config.model_id, config.dimension)
            hits = store.search(semantic_query(query, parsed) or query, embedder,
                                k=SEMANTIC_TOP_K, allowed_movie_ids=eligibility["eligible_ids"])
            if not valid_discovery_hits(hits, movies, eligibility["eligible_ids"]):
                raise IndexConfigurationError("검색 응답이 현재 조건의 영화 ID와 대응하지 않습니다.")
            if hits:
                cache.put(key, hits)
        result = discover_movies(query, movies, semantic_hits=hits)
        result["semantic_cache_hit"] = cached
        result["semantic_cache_rejected"] = rejected
        result["semantic_top_k"] = SEMANTIC_TOP_K
        result["eligible_ids_hash"] = fingerprint(sorted(eligibility["eligible_ids"]))
        result["semantic_hits"] = hits
        return result
    finally:
        if store is not None:
            store.close()
