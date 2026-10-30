"""Index supplied metadata, or verify the persisted records without any API."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from movie_lab.config import resolve_index_path, resolve_movies_path
from movie_lab.data import DataLoadError, load_movies
from movie_lab.embeddings import create_gms_embeddings, failure_details
from movie_lab.index import MANIFEST_NAME, IndexConfig, IndexConfigurationError, MetadataIndex, read_index_config


def main() -> int:
    parser = argparse.ArgumentParser(description="안정 ID와 내용 해시로 영화 메타데이터를 증분 색인합니다.")
    parser.add_argument("--movies", help="메타데이터 JSON 경로")
    parser.add_argument("--index-dir", help="로컬 Chroma 저장 경로")
    parser.add_argument("--model", help="실제로 확인한 GMS 임베딩 모델 ID")
    parser.add_argument("--dimensions", type=int, help="실제로 확인한 벡터 차원. 첫 색인에 필수")
    parser.add_argument("--movie-id", action="append", help="소량 검사할 영화 ID. 여러 번 지정 가능")
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--verify-only", action="store_true", help="키·임베딩 호출 없이 모든 ID와 저장 벡터를 검증")
    args = parser.parse_args()
    store = None
    try:
        movies = load_movies(resolve_movies_path(args.movies))
        if args.movie_id:
            if any(mid not in movies for mid in args.movie_id):
                raise IndexConfigurationError("검사 영화 ID가 데이터에 없습니다.")
            movies = {mid: movies[mid] for mid in dict.fromkeys(args.movie_id)}
        path = resolve_index_path(args.index_dir)
        config = read_index_config(path) if (path / MANIFEST_NAME).exists() else None
        if args.verify_only:
            if config is None:
                raise IndexConfigurationError("저장된 색인이 없습니다.")
            if (args.model and args.model != config.model_id) or (args.dimensions and args.dimensions != config.dimension):
                raise IndexConfigurationError("검증 요청 설정이 저장소와 다릅니다.")
            store = MetadataIndex(path, config, create=False)
            verified = store.verify_movies(movies)
            store.close()
            store = None
            print(json.dumps({"mode": "verify-only", **verified, "embedding_requests": 0,
                              "collection": config.collection_name}, ensure_ascii=False))
            return 0 if verified["complete"] else 1

        dimension = args.dimensions if args.dimensions is not None else (config.dimension if config else None)
        if dimension is None:
            raise IndexConfigurationError("첫 색인에는 실제 확인한 --dimensions가 필요합니다.")
        embedder = create_gms_embeddings(args.model, dimension, batch_size=args.batch_size)
        requested = IndexConfig(model_id=embedder.model, dimension=dimension)
        store = MetadataIndex(path, requested)
        before = store.collection.count()
        def progress(count, total):
            print(json.dumps({"event": "batch_saved", "stored_count": count, "requested_total": total}), flush=True)
        report = store.index_movies(movies, embedder, args.batch_size, on_progress=progress)
        store.close()
        store = None
        print(json.dumps({"mode": "index", "count_before": before, **report,
                          "embedding_requests": embedder.request_count,
                          "reported_model": embedder.reported_model}, ensure_ascii=False), flush=True)
        return 0 if report["complete"] else 1
    except (IndexConfigurationError, DataLoadError):
        print(json.dumps({"status": "failure", "category": "데이터 또는 색인 설정 확인 필요"}, ensure_ascii=False))
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
