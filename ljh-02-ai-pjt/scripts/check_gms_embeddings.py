"""One short embedding request. Prints only safe model/dimension evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from openai import APIConnectionError

from movie_lab.embeddings import TIMEOUT_SECONDS, create_gms_embeddings, failure_details


PROBE_TEXT = "영화 임베딩 연결 확인"


def run_check(model: str | None = None, dimensions: int | None = None) -> int:
    try:
        embeddings = create_gms_embeddings(model, dimensions)
        vectors = embeddings.embed_documents([PROBE_TEXT])
        print(json.dumps({
            "status": "success",
            "requested_model": embeddings.model,
            "reported_model": embeddings.reported_model,
            "dimensions": len(vectors[0]),
            "requested_dimensions": embeddings.requested_dimensions,
            "request_count": embeddings.request_count,
            "text_count": embeddings.embedded_text_count,
            "encoding_format": "float",
            "timeout_seconds": TIMEOUT_SECONDS,
            "max_retries": 0,
        }, ensure_ascii=False))
        return 0
    except Exception as error:
        print(json.dumps(failure_details(error), ensure_ascii=False))
        return 3 if isinstance(error, APIConnectionError) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="GMS 임베딩 후보 모델을 짧은 요청 1회로 확인합니다.")
    parser.add_argument("--model", help="GMS_EMBEDDING_MODEL보다 우선하는 임베딩 모델 ID")
    parser.add_argument("--dimensions", type=int, help="명시적 차원 옵션. 생략하면 실제 응답에서 확인")
    args = parser.parse_args()
    return run_check(args.model, args.dimensions)


if __name__ == "__main__":
    raise SystemExit(main())
