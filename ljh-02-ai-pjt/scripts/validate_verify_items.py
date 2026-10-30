"""One explicit live question, one draft, one batch review; no whole-flow retry.

The old three-question CLI is NOT executed. Only its existing evidence guard
is reused. Preparation must reuse a successful cache: new planner, wiki, or
document-embedding calls are blocked rather than producing substitute data.
"""

import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from movie_lab.config import resolve_movies_path
from movie_lab.data import load_movies
from movie_lab.document_llm import DocumentModelError
from movie_lab.document_pipeline import create_document_pipeline, safe_error
from movie_lab.rag import create_rag_service
from movie_lab.state import append_user_message, append_assistant_message, get_thread
from scripts.validate_answer_reliability import EvidenceGuard


QUESTION = "이 영화는 크리스토퍼 놀란이 감독했고, 실제 달은 지구의 자연위성이라는 말이 맞나요?"


def run(snapshot_archive, output):
    movie = load_movies(resolve_movies_path())["753091"]
    if movie.year != 2023:
        raise ValueError("선택 작품 연도 확인 실패")
    prepared = {}

    def deny_new_preparation(*args, **kwargs):
        raise DocumentModelError("이번 검증은 기존 성공 캐시만 사용합니다: 새 준비 호출 차단")

    def cached_pipeline_factory():
        pipeline = create_document_pipeline(snapshot_archive, source_mode="snapshot")
        pipeline.planner.extract = deny_new_preparation
        pipeline.planner.select = deny_new_preparation
        pipeline.embedder.embed_documents = deny_new_preparation
        if pipeline.wiki is not None:
            pipeline.wiki.search = deny_new_preparation
            pipeline.wiki.fetch_page = deny_new_preparation
        original_prepare = pipeline.prepare

        def require_cached(*args, **kwargs):
            result = original_prepare(*args, **kwargs)
            prepared.update(result)
            return result

        pipeline.prepare = require_cached
        return pipeline

    class CachedEvidenceGuard(EvidenceGuard):
        def generate(self, *args, **kwargs):
            if not prepared.get("cache_hit") or not prepared.get("complete"):
                raise DocumentModelError("기존 준비 캐시 확인 실패: 실제 생성 검증 중단")
            return super().generate(*args, **kwargs)

    guard = CachedEvidenceGuard({"id": "contradiction_and_confirmation"})
    service = create_rag_service(snapshot_archive, source_mode="snapshot", max_answer_attempts=1)
    service.pipeline_factory = cached_pipeline_factory
    service.generator_factory = lambda: guard
    threads = {}
    append_user_message(threads, movie.movie_id, QUESTION)
    started = time.perf_counter()
    result = service.answer(movie, QUESTION, get_thread(threads, movie.movie_id), mode="verify")
    elapsed = time.perf_counter() - started
    if result.get("content"):
        append_assistant_message(threads, movie.movie_id, result["content"], result["sources"])
    validation = result.get("validation", {})
    call_counts = result.get("stage_calls", {})
    verdicts = {row["scope"]: row["verdict"] for row in result.get("checks", [])}
    success = (validation.get("semantic_check") == "item_review_passed"
               and verdicts == {"작품 속 묘사": "근거와 상충", "현실 사실": "확인됨"}
               and validation.get("accepted_items") == 2
               and call_counts.get("answer_generation", {}).get("chat") == 1
               and call_counts.get("semantic_review", {}).get("chat") == 1
               and all(row["present"] for row in guard.preflight) and len(guard.preflight) == 2)
    report = {"question_budget": 1, "whole_pipeline_invocations": 1, "whole_pipeline_retries": 0,
              "answer_attempts": 1, "batch_review_limit": 1, "movie_id": movie.movie_id, "question": QUESTION,
              "elapsed_seconds": elapsed, "success": success,
              "assistant_stored": bool(result.get("content")), "evidence_preflight": guard.preflight,
              **{key: result.get(key) for key in ("trace", "preparation", "retrieval", "content", "sources", "checks",
                "validation", "error", "calls", "timings", "stage_calls", "cache", "failure_stage")}}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report.get(key) for key in ("success", "content", "checks", "validation", "timings",
                                                      "stage_calls", "cache", "error", "failure_stage")}, ensure_ascii=False))
    return success


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-archive")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/review_stage4_items/actual_case.json")
    args = parser.parse_args()
    try:
        return 0 if run(args.snapshot_archive, args.output) else 1
    except Exception as error:
        print(json.dumps({"success": False, "error": safe_error(error)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
