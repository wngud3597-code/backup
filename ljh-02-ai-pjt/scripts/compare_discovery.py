"""Inspect metadata read-only; --actual compares scopes with <=4 GMS vectors.

No chat calls, document embedding, index writes, or production cache writes.
Each question is embedded once and its exact vector is used for both scopes.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
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


QUESTIONS = (
    ("O1", "크리스토퍼 놀란 감독의 우주 탐사와 상대성 이론 영화", "157336"),
    ("O2", "가난한 가족이 부유한 집에 들어가 계층 갈등을 겪는 한국 영화", "496243"),
    ("O3", "꿈속으로 들어가 생각을 심는 영화", "27205"),
    ("C3", "2014년 SF 영화 우주 탐험", "157336"),
)


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def store_snapshot(store, movies):
    """Hash logical payloads, never publish embeddings or whole documents."""
    records = store._records(list(movies))
    digest = hashlib.sha256()
    schema = None
    for identifier in sorted(records):
        document, metadata, vector = records[identifier]
        value = [identifier, document, metadata, None if vector is None else [float(x) for x in vector]]
        digest.update(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        if schema is None:
            schema = {key: type(value).__name__ for key, value in metadata.items()}
    return {"count": store.collection.count(), "read_records": len(records),
            "logical_record_sha256": digest.hexdigest(), "collection": store.config.collection_name,
            "config": asdict(store.config), "metadata_schema": schema,
            "verification": store.verify_movies(movies), "network_requests": 0}


def oracle_ids(identifier, movies):
    # Independent field predicates; never call filter_catalog/_matches here.
    predicates = {
        "O1": lambda m: "크리스토퍼 놀란" in m.director,
        "O2": lambda m: "South Korea" in m.production_countries,
        "O3": lambda m: True,
        "C3": lambda m: m.year == 2014 and "SF" in m.genres,
    }
    return sorted(m.movie_id for m in movies.values() if predicates[identifier](m))


def rank_of(results, movie_id):
    return next((rank for rank, row in enumerate(results, 1) if row["movie_id"] == movie_id), None)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--actual", action="store_true", help="Explicitly allow at most four query embedding requests")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "artifacts/review_upgrade/discovery")
    options = parser.parse_args(argv)
    options.output_dir.mkdir(parents=True, exist_ok=True)
    report = {"started_at": datetime.now(timezone.utc).isoformat(), "mode": "actual" if options.actual else "inspection_only",
              "embedding_request_limit": 4, "chat_requests": 0, "document_embedding_requests": 0,
              "query_embedding_requests": 0, "comparisons": [], "success": False,
              "controls": {"semantic_k": 3, "final_limit": 10, "same_query_vector_for_A_B": True,
                           "same_preprocessing": True, "same_lexical_formula_and_normalization": True,
                           "search_cache_bypassed": True, "index_writes": 0}}
    store = embedder = None
    before = None
    exit_code = 0
    try:
        movies_path = resolve_movies_path()
        movies = load_movies(movies_path)
        config = read_index_config(resolve_index_path())
        store = MetadataIndex(resolve_index_path(), config, create=False)
        before = store_snapshot(store, movies)
        before["data_sha256"] = hashlib.sha256(movies_path.read_bytes()).hexdigest()
        before["captured_at"] = datetime.now(timezone.utc).isoformat()
        # Keep the earliest preflight evidence if this script was inspected first.
        baseline = options.output_dir / "store_before.json"
        if not baseline.exists():
            write_json(baseline, before)
        write_json(options.output_dir / "preflight_store.json", before)
        if not before["verification"]["complete"]:
            raise ValueError("Metadata preflight did not verify every current record")
        report["model"] = config.model_id
        report["dimension"] = config.dimension
        report["collection"] = config.collection_name
        if options.actual:
            embedder = create_gms_embeddings(config.model_id, config.dimension)
            store._check_embedder(embedder)
            for identifier, question, reference_id in QUESTIONS:
                if embedder.request_count >= 4:
                    raise ValueError("Query embedding budget exhausted")
                start = time.perf_counter()
                eligibility = filter_catalog(question, movies)
                allowed = eligibility["eligible_ids"]
                expected = oracle_ids(identifier, movies)
                if allowed != expected or not allowed:
                    raise ValueError("Independent field oracle or nonempty scope check failed")
                prepared = semantic_query(question, eligibility["conditions"]) or question
                filter_seconds = time.perf_counter() - start
                embed_start = time.perf_counter()
                previous_requests = embedder.request_count
                vector = embedder.embed_query(prepared)
                embed_seconds = time.perf_counter() - embed_start
                if embedder.request_count - previous_requests != 1:
                    raise ValueError("A question did not use exactly one embedding request")
                a_start = time.perf_counter()
                a_hits = store.search_vector(vector, k=3)
                a_query_seconds = time.perf_counter() - a_start
                b_start = time.perf_counter()
                b_hits = store.search_vector(vector, k=3, allowed_movie_ids=allowed)
                b_query_seconds = time.perf_counter() - b_start
                a_start = time.perf_counter()
                a = discover_movies(question, movies, semantic_hits=a_hits)
                a_fusion_seconds = time.perf_counter() - a_start
                b_start = time.perf_counter()
                b = discover_movies(question, movies, semantic_hits=b_hits)
                b_fusion_seconds = time.perf_counter() - b_start
                allowed_set = set(expected)
                def violations(rows):
                    return sum(row["movie_id"] not in allowed_set for row in rows)
                record = {"case_id": identifier, "query": question, "semantic_query": prepared,
                          "conditions": eligibility["conditions"], "eligible_count": len(allowed),
                          "eligible_ids_hash": fingerprint(allowed), "independent_field_oracle_matches": True,
                          "reference_movie_id": reference_id,
                          "reference_is_relevance_example_not_complete_truth_label": True,
                          "A": {"semantic_hits": a_hits, "results": a["results"],
                                "reference_rank": rank_of(a["results"], reference_id),
                                "semantic_outside_conditions": violations(a_hits), "final_condition_violations": violations(a["results"])},
                          "B": {"semantic_hits": b_hits, "results": b["results"],
                                "reference_rank": rank_of(b["results"], reference_id),
                                "semantic_outside_conditions": violations(b_hits), "final_condition_violations": violations(b["results"])},
                          "seconds": {"parse_and_filter": filter_seconds, "shared_query_embedding": embed_seconds,
                                      "A_local_query": a_query_seconds, "B_local_query": b_query_seconds,
                                      "A_fusion": a_fusion_seconds, "B_fusion": b_fusion_seconds},
                          "query_embedding_requests": embedder.request_count - previous_requests,
                          "vector_hash": fingerprint(vector), "same_vector_reused": True}
                report["comparisons"].append(record)
                report["query_embedding_requests"] = embedder.request_count
                write_json(options.output_dir / "ab_results.json", report)
                if record["B"]["semantic_outside_conditions"] or record["A"]["final_condition_violations"] or record["B"]["final_condition_violations"]:
                    raise ValueError("Scope invariant failed")
            report["reported_model"] = embedder.reported_model
            report["success"] = len(report["comparisons"]) == len(QUESTIONS)
        else:
            report["success"] = True
            report["note"] = "Read-only local store/schema verification only; no API calls or A/B search executed."
    except Exception as error:
        report["failure"] = failure_details(error)
        exit_code = 1
    finally:
        if embedder is not None:
            report["query_embedding_requests"] = embedder.request_count
        if store is not None:
            try:
                after = store_snapshot(store, movies)
                write_json(options.output_dir / "store_after.json", after)
                report["metadata_unchanged"] = before is not None and all(
                    before[key] == after[key] for key in ("count", "logical_record_sha256", "collection", "config"))
                if not report["metadata_unchanged"]:
                    report["success"] = False
                    exit_code = 1
            except Exception as error:
                report["store_recheck_failure"] = failure_details(error)
                report["success"] = False
                exit_code = 1
            finally:
                store.close()
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        name = "ab_results.json" if options.actual else "preflight_result.json"
        write_json(options.output_dir / name, report)
        print(json.dumps({key: report.get(key) for key in ("mode", "success", "query_embedding_requests", "dimension", "metadata_unchanged", "failure")}, ensure_ascii=False))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
