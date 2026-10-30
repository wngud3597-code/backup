"""One-shot exact-question A/B verification; never repeats the four-question run.

Only --actual creates the existing GMS client. A persistent attempt marker rejects
another execution, including after a failed request. No chat, document embedding,
index writes, or production-cache writes occur here.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from movie_lab.config import resolve_index_path, resolve_movies_path
from movie_lab.data import load_movies
from movie_lab.discovery import discover_movies, filter_catalog, semantic_query
from movie_lab.document_pipeline import fingerprint
from movie_lab.embeddings import create_gms_embeddings, failure_details
from movie_lab.index import MetadataIndex, read_index_config
from movie_lab.services import valid_discovery_hits


QUESTION = "2014년 SF 영화 중 우주 탐험을 다룬 영화"
OLD_RECORD = PROJECT_ROOT / "artifacts/review_upgrade/discovery/ab_results.json"
SOURCES = ("movie_lab/discovery.py", "movie_lab/index.py", "movie_lab/services.py")


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def source_hashes():
    return {name: hashlib.sha256((PROJECT_ROOT / name).read_bytes()).hexdigest() for name in SOURCES}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--actual", action="store_true", help="Allow exactly one query-embedding attempt, SDK retries zero")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "artifacts/review_completion/discovery")
    options = parser.parse_args(argv)
    if not options.actual:
        print(json.dumps({"status": "not_run", "query": QUESTION, "query_embedding_requests": 0,
                          "note": "Use --actual only for the explicitly authorized one-shot check."}, ensure_ascii=False))
        return 0
    options.output_dir.mkdir(parents=True, exist_ok=True)
    marker = options.output_dir / "attempt_started.json"
    if marker.exists():
        print(json.dumps({"status": "refused_existing_attempt", "query_embedding_requests_this_execution": 0}, ensure_ascii=False))
        return 2
    report = {"query": QUESTION, "started_at": datetime.now(timezone.utc).isoformat(),
              "status": "not_completed", "query_embedding_request_limit": 1,
              "query_embedding_requests": 0, "chat_requests": 0, "document_embedding_requests": 0,
              "index_writes": 0, "production_cache_writes": 0, "sdk_max_retries": 0,
              "same_vector_reused_for_A_B": False, "semantic_k": 3, "final_limit": 10,
              "source_sha256_before": source_hashes()}
    store = embedder = None
    exit_code = 1
    try:
        previous = json.loads(OLD_RECORD.read_text(encoding="utf-8"))
        short = next(item for item in previous["comparisons"] if item["case_id"] == "C3")
        report["earlier_short_question"] = {
            "query": short["query"], "semantic_query": short["semantic_query"],
            "evidence": "artifacts/review_upgrade/discovery/ab_results.json#C3",
            "is_this_exact_question": short["query"] == QUESTION,
            "A_reference_rank": short["A"]["reference_rank"],
            "B_reference_rank": short["B"]["reference_rank"],
            "note": "Historical shortened-input observation; not the exact-question run and not re-executed.",
        }
        start = time.perf_counter()
        movies = load_movies(resolve_movies_path())
        eligibility = filter_catalog(QUESTION, movies)
        allowed = eligibility["eligible_ids"]
        expected = sorted(m.movie_id for m in movies.values() if m.year == 2014 and "SF" in m.genres)
        if allowed != expected or not allowed or eligibility["conditions"]["unsupported"]:
            raise ValueError("Independent metadata eligibility check failed")
        prepared = semantic_query(QUESTION, eligibility["conditions"]) or QUESTION
        config = read_index_config(resolve_index_path())
        if config.model_id != previous["model"] or config.dimension != previous["dimension"]:
            raise ValueError("Existing embedding settings changed")
        store = MetadataIndex(resolve_index_path(), config, create=False)
        verification = store.verify_movies(movies, check_vectors=False)
        if not verification["complete"]:
            raise ValueError("Current metadata records are missing or mismatched")
        report.update({"semantic_query": prepared, "conditions": eligibility["conditions"],
                       "eligible_count": len(allowed), "eligible_movie_ids": allowed,
                       "eligible_ids_hash": fingerprint(allowed), "independent_field_oracle_matches": True,
                       "same_conditions_as_previous_short_question": eligibility["conditions"] == short["conditions"],
                       "same_embedding_input_as_previous_short_question": prepared == short["semantic_query"],
                       "model": config.model_id, "dimension": config.dimension,
                       "collection": config.collection_name, "metadata_verification": verification,
                       "seconds": {"offline_preflight": time.perf_counter() - start}})
        write_json(options.output_dir / "preflight.json", report)
        # Exclusive creation prevents two concurrent invocations spending the budget.
        with marker.open("x", encoding="utf-8") as handle:
            json.dump({"query": QUESTION, "started_at": report["started_at"],
                       "embedding_request_limit": 1, "automatic_retry_allowed": False}, handle, ensure_ascii=False, indent=2)
        embedder = create_gms_embeddings(config.model_id, config.dimension)
        store._check_embedder(embedder)
        if embedder._client.max_retries != 0:
            raise ValueError("Client retries must be disabled")
        start = time.perf_counter()
        vector = embedder.embed_query(prepared)
        report["seconds"]["shared_query_embedding"] = time.perf_counter() - start
        report["query_embedding_requests"] = embedder.request_count
        if embedder.request_count != 1 or len(vector) != config.dimension:
            raise ValueError("One-shot query embedding budget or dimension check failed")
        report["reported_model"] = embedder.reported_model
        report["vector_sha256"] = fingerprint(vector)
        for label, scope in (("A", None), ("B", allowed)):
            start = time.perf_counter()
            hits = store.search_vector(vector, k=3, allowed_movie_ids=scope)
            query_seconds = time.perf_counter() - start
            if not valid_discovery_hits(hits, movies, movies if scope is None else allowed):
                raise ValueError("Candidate ID/document correspondence check failed")
            start = time.perf_counter()
            final = discover_movies(QUESTION, movies, semantic_hits=hits)
            final_seconds = time.perf_counter() - start
            report[label] = {
                "scope": "whole_metadata_collection" if scope is None else "eligible_movie_ids",
                "semantic_hits": hits, "results": final["results"],
                "reference_movie_id": "157336",
                "reference_is_relevance_example_not_complete_truth_label": True,
                "reference_semantic_rank": next((i for i, row in enumerate(hits, 1) if row["movie_id"] == "157336"), None),
                "reference_final_rank": next((i for i, row in enumerate(final["results"], 1) if row["movie_id"] == "157336"), None),
                "semantic_outside_conditions": sum(row["movie_id"] not in expected for row in hits),
                "final_condition_violations": sum(row["movie_id"] not in expected for row in final["results"]),
                "local_query_seconds": query_seconds, "fusion_and_final_check_seconds": final_seconds,
            }
        report["same_vector_reused_for_A_B"] = True
        if report["B"]["semantic_outside_conditions"] or any(report[label]["final_condition_violations"] for label in ("A", "B")):
            raise ValueError("Condition scope invariant failed")
        report["status"] = "success"
        exit_code = 0
    except Exception as error:
        report["status"] = "failure"
        report["failure"] = failure_details(error)
    finally:
        if embedder is not None:
            report["query_embedding_requests"] = embedder.request_count
        if store is not None:
            try:
                store.close()
            except Exception as error:
                report["store_close_failure"] = failure_details(error)
                report["status"] = "failure"
                exit_code = 1
        report["source_sha256_after"] = source_hashes()
        report["product_sources_unchanged"] = report["source_sha256_before"] == report["source_sha256_after"]
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        report["limitations"] = ["One exact question; no broad accuracy, average latency, or price claim.",
                                 "Vector was shared; per-scope local durations are not independent end-to-end API durations.",
                                 "Full metadata/external logical preservation audit is recorded separately by integration."]
        write_json(options.output_dir / "actual_case.json", report)
        print(json.dumps({key: report.get(key) for key in ("query", "status", "query_embedding_requests", "model", "reported_model", "dimension", "product_sources_unchanged", "failure")}, ensure_ascii=False))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
