"""Diagnose stored/fresh vectors with one six-text request; never writes the index.

The three expected titles are diagnostic hypotheses, not automatic relevance
labels. Rankings use exact cosine as well as the existing Chroma search.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from movie_lab.config import resolve_index_path
from movie_lab.embeddings import create_gms_embeddings, failure_details
from movie_lab.index import IndexConfigurationError, MetadataIndex, read_index_config


EXPECTED_MOVIE_IDS = ("157336", "496243", "27205")


def cosine(left, right) -> float:
    if len(left) != len(right) or not len(left):
        raise IndexConfigurationError("검사 벡터 차원이 다릅니다.")
    denominator = math.sqrt(sum(float(value) ** 2 for value in left)) * math.sqrt(sum(float(value) ** 2 for value in right))
    if not denominator or not math.isfinite(denominator):
        raise IndexConfigurationError("검사 벡터의 크기가 유효하지 않습니다.")
    return sum(float(a) * float(b) for a, b in zip(left, right)) / denominator


def exact_hits(vector, identifiers, vectors, metadata) -> list[dict]:
    rows = [{"document_id": identifier, "movie_id": info["movie_id"], "title": info["title"],
             "cosine": cosine(vector, candidate)}
            for identifier, candidate, info in zip(identifiers, vectors, metadata)]
    return sorted(rows, key=lambda row: row["cosine"], reverse=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="저장 문서 3개와 대표 질의 3개를 한 번 재임베딩해 일관성을 검사합니다.")
    parser.add_argument("--index-dir")
    parser.add_argument("--queries-file", default="artifacts/review/semantic_search.jsonl")
    args = parser.parse_args()
    store = None
    try:
        query_path = Path(args.queries_file)
        if not query_path.is_absolute():
            query_path = PROJECT_ROOT / query_path
        lines = [json.loads(line) for line in query_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        queries = [line["query"] for line in lines]
        if len(queries) != 3 or any(not isinstance(query, str) or not query.strip() for query in queries):
            raise IndexConfigurationError("대표 질의 3개가 필요합니다.")
        path = resolve_index_path(args.index_dir)
        config = read_index_config(path)
        store = MetadataIndex(path, config, create=False)
        records = store.collection.get(include=["documents", "metadatas", "embeddings"])
        identifiers, all_vectors, metadatas = records["ids"], records["embeddings"], records["metadatas"]
        positions = {identifier: position for position, identifier in enumerate(identifiers)}
        if any(f"meta:{movie_id}" not in positions for movie_id in EXPECTED_MOVIE_IDS):
            raise IndexConfigurationError("검사할 대표 영화가 저장소에 없습니다.")
        chosen = [positions[f"meta:{movie_id}"] for movie_id in EXPECTED_MOVIE_IDS]
        texts = [records["documents"][position] for position in chosen]
        if any(not isinstance(text, str) or not text.strip() for text in texts):
            raise IndexConfigurationError("대표 영화 문서가 비어 있습니다.")
        embedder = create_gms_embeddings(config.model_id, config.dimension, batch_size=6)
        fresh = embedder.embed_documents(texts + queries)  # Exactly six texts, one API request.
        comparisons = []
        for ordinal, position in enumerate(chosen):
            stored, renewed = all_vectors[position], fresh[ordinal]
            ranked = exact_hits(renewed, identifiers, all_vectors, metadatas)
            comparisons.append({
                "movie_id": EXPECTED_MOVIE_IDS[ordinal], "title": metadatas[position]["title"],
                "stored_fresh_cosine": cosine(stored, renewed),
                "max_absolute_difference": max(abs(float(a) - float(b)) for a, b in zip(stored, renewed)),
                "fresh_document_expected_rank": next(index + 1 for index, hit in enumerate(ranked) if hit["movie_id"] == EXPECTED_MOVIE_IDS[ordinal]),
                "fresh_document_exact_top3": ranked[:3],
            })
        query_checks = []
        for ordinal, query in enumerate(queries):
            vector = fresh[3 + ordinal]
            ranked = exact_hits(vector, identifiers, all_vectors, metadatas)
            ann = store.collection.query(query_embeddings=[vector], n_results=3, include=["metadatas", "distances"])
            ann_hits = [{"document_id": identifier, "movie_id": info["movie_id"], "title": info["title"], "distance": float(distance)}
                        for identifier, info, distance in zip(ann["ids"][0], ann["metadatas"][0], ann["distances"][0])]
            query_checks.append({
                "query": query, "expected_movie_id": EXPECTED_MOVIE_IDS[ordinal],
                "expected_exact_rank": next(index + 1 for index, hit in enumerate(ranked) if hit["movie_id"] == EXPECTED_MOVIE_IDS[ordinal]),
                "exact_top3": ranked[:3], "chroma_top3": ann_hits,
                "cosine_to_same_batch_expected_document": cosine(vector, fresh[ordinal]),
                "cosine_to_stored_expected_document": cosine(vector, all_vectors[chosen[ordinal]]),
            })
        result = {
            "status": "success", "diagnostic_only": True,
            "model": embedder.model, "reported_model": embedder.reported_model,
            "dimensions": embedder.dimensions, "requested_dimensions": embedder.requested_dimensions,
            "request_count": embedder.request_count, "text_count": embedder.embedded_text_count,
            "same_batch_unique_vector_count": len({tuple(vector) for vector in fresh}),
            "stored_count": len(identifiers), "document_comparisons": comparisons,
            "stored_vs_fresh_document_cosine_matrix": [[cosine(all_vectors[position], vector) for vector in fresh[:3]] for position in chosen],
            "query_checks": query_checks,
        }
        store.close()
        store = None
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as error:
        print(json.dumps(failure_details(error), ensure_ascii=False))
        return 1
    finally:
        if store is not None:
            try:
                store.close()
            except Exception:
                print(json.dumps({"status": "failure", "category": "저장소 종료 확인 실패"}, ensure_ascii=False))


if __name__ == "__main__":
    raise SystemExit(main())
