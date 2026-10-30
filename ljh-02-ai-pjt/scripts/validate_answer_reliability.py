"""Explicit three-question GMS validation; no retries of a whole pipeline.

Uses the real graph, preparation/cache, retrieval, and generator. The guard
checks the actual retrieved context BEFORE constructing a generation client.
No fake answer or substituted evidence is used. This script calls external
APIs only when explicitly executed; imports do not load credentials.
"""

import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from movie_lab.answering import create_answer_generator, quotation_parts
from movie_lab.config import resolve_gms_chat_model, resolve_movies_path
from movie_lab.data import load_movies
from movie_lab.document_llm import DocumentModelError
from movie_lab.document_pipeline import safe_error
from movie_lab.rag import create_rag_service
from movie_lab.state import append_assistant_message, append_user_message, get_thread


CASES = (
    {"id": "multiple_quotes", "movie_id": "157336", "mode": "general",
     "question": "이 영화의 감독과 상영 시간을 알려줘."},
    {"id": "insufficient", "movie_id": "753091", "mode": "verify",
     "question": "이 영화에는 달이 스스로 빛나는 별이라고 나와. 실제로도 달은 스스로 빛나는 별이야?"},
    {"id": "contradiction_and_confirmation", "movie_id": "753091", "mode": "verify",
     "question": "이 영화는 크리스토퍼 놀란이 감독했고, 실제 달은 지구의 자연위성이라는 말이 맞나요?"},
)


class EvidenceGuard:
    """Inspect real retrieval, then delegate without changing evidence/model."""
    def __init__(self, case):
        self.case, self.inner, self.preflight = case, None, []

    @property
    def request_count(self):
        return self.inner.request_count if self.inner else 0

    @property
    def metrics(self):
        return self.inner.metrics if self.inner else {}

    @property
    def audit(self):
        return [{"stage": "actual_retrieval_preflight", "checks": self.preflight}] + (self.inner.audit if self.inner else [])

    @property
    def model(self):
        return self.inner.model if self.inner else resolve_gms_chat_model()

    @property
    def reported_model(self):
        return self.inner.reported_model if self.inner else None

    @property
    def last_failure_stage(self):
        return self.inner.last_failure_stage if self.inner else "evidence_preflight"

    def generate(self, movie, question, history, sources, mode, warnings):
        requirements = [("movie_metadata", "감독: " + ", ".join(movie.director))]
        if self.case["id"] == "multiple_quotes":
            requirements.append(("movie_metadata", f"상영 시간(분): {movie.runtime}"))
        elif self.case["id"] == "contradiction_and_confirmation":
            requirements.append(("background_unverified", "달은 지구의 유일한 자연위성"))
        for scope, phrase in requirements:
            found = next(((n, source) for n, source in enumerate(sources, 1)
                          if source.get("scope") == scope and phrase in source["text"]), None)
            self.preflight.append({"scope": scope, "required_phrase": phrase, "present": found is not None,
                                   "source_number": found[0] if found else None})
        if not all(row["present"] for row in self.preflight):
            raise DocumentModelError("실제 검색 근거 사전 확인 실패: 생성 호출 생략")
        self.inner = create_answer_generator(max_attempts=1)
        return self.inner.generate(movie, question, history, sources, mode, warnings)


def run(snapshot_archive, output):
    movies = load_movies(resolve_movies_path())
    records, infrastructure_failures = [], 0
    for case in CASES:
        if infrastructure_failures >= 2:
            break
        # Each representative question is independent. Existing application
        # conversation data is neither loaded nor modified by this CLI.
        threads = {}
        append_user_message(threads, case["movie_id"], case["question"])
        guard = EvidenceGuard(case)
        service = create_rag_service(snapshot_archive, source_mode="snapshot", max_answer_attempts=1)
        service.generator_factory = lambda: guard
        started = time.perf_counter()
        result = service.answer(movies[case["movie_id"]], case["question"],
                                get_thread(threads, case["movie_id"]), mode=case["mode"])
        elapsed = time.perf_counter() - started
        # Keep explicit source/passage identifiers alongside the exact original
        # excerpt, so manual inspection can check the model's claim mapping.
        passages = [{"source_number": n, "document_id": source["document_id"],
                     "passages": [{"passage_id": f"s{n}p{i}", "text": part}
                                  for i, part in enumerate(quotation_parts(source["text"]))]}
                    for n, source in enumerate(result.get("retrieval", {}).get("sources", []), 1)]
        record = {**case, "elapsed_seconds": elapsed,
                  **{key: result.get(key) for key in ("trace", "preparation", "retrieval", "content", "sources", "checks",
                                                     "validation", "error", "calls", "timings", "stage_calls", "cache", "failure_stage")},
                  "evidence_preflight": guard.preflight, "provided_passages": passages}
        if result.get("content"):
            append_assistant_message(threads, case["movie_id"], result["content"], result["sources"])
        record["assistant_stored"] = bool(result.get("content"))
        records.append(record)
        category = (result.get("error") or {}).get("category", "")
        if any(term in category for term in ("타임아웃", "서버 오류", "네트워크")):
            infrastructure_failures += 1
        report = {"question_budget": 3, "whole_pipeline_retries": 0, "answer_attempts_per_question": 1,
                  "preparation_source": "snapshot or existing successful cache; no full reindex command",
                  "records": records, "unexecuted_cases": [row["id"] for row in CASES[len(records):]],
                  "success": len(records) == 3 and all(row["content"] for row in records)}
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({key: record.get(key) for key in ("id", "content", "timings", "stage_calls", "cache", "error", "failure_stage")},
                         ensure_ascii=False), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-archive")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/review_stage4_fix/actual_cases.json")
    args = parser.parse_args()
    try:
        report = run(args.snapshot_archive, args.output)
        return 0 if report["success"] else 1
    except Exception as error:
        print(json.dumps({"success": False, "error": safe_error(error)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
