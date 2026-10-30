"""Search the persistent metadata collection with matching GMS query embeddings."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from movie_lab.config import resolve_index_path
from movie_lab.embeddings import create_gms_embeddings, failure_details
from movie_lab.index import IndexConfigurationError, MetadataIndex, read_index_config


def main() -> int:
    parser = argparse.ArgumentParser(description="실제 의미 검색 결과를 표시합니다. 조건 충족 판정은 수행하지 않습니다.")
    parser.add_argument("--index-dir")
    parser.add_argument("--query", action="append", required=True)
    parser.add_argument("--k", type=int, default=3)
    args = parser.parse_args()
    store = None
    try:
        path = resolve_index_path(args.index_dir)
        config = read_index_config(path)
        store = MetadataIndex(path, config, create=False)
        embedder = create_gms_embeddings(config.model_id, config.dimension)
        for query in args.query:
            hits = store.search(query, embedder, args.k)
            print(json.dumps({"query": query, "hits": hits, "collection": config.collection_name,
                              "embedding_model": config.model_id, "dimension": config.dimension,
                              "embedding_requests_so_far": embedder.request_count,
                              "result_type": "semantic_similarity_not_condition_verification"}, ensure_ascii=False), flush=True)
        store.close()
        store = None
        return 0
    except IndexConfigurationError:
        print(json.dumps({"status": "failure", "category": "메타데이터 색인 또는 검색 설정 확인 필요"}, ensure_ascii=False))
        return 2
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
