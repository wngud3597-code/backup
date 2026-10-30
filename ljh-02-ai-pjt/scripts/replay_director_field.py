"""Replay the captured browser failure with fixed responses and no API calls."""

from copy import deepcopy
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from movie_lab.answering import AnswerGenerator, citation_numbers
from movie_lab.config import resolve_movies_path
from movie_lab.data import load_movies


def response(value):
    return SimpleNamespace(model="fixture-not-live", choices=[SimpleNamespace(
        message=SimpleNamespace(content=json.dumps(value, ensure_ascii=False)))])


def run():
    source_file = ROOT / "artifacts/review_browser_demo/api_events.jsonl"
    events = [json.loads(line) for line in source_file.read_text(encoding="utf-8").splitlines() if line]
    captured = next(row for row in events if row["event"] == "answer_result" and row["mode"] == "verify")
    catalog = load_movies(resolve_movies_path())
    movie = catalog[captured["movie_id"]]
    names = {name for item in catalog.values() for name in item.director}
    old = captured["result"]
    canonical = next(row["draft"] for row in old["validation"]["audit"] if row["stage"] == "mechanical")
    raw = {"checks": [{**check, "citations": [deepcopy(citation) for citation in canonical["citations"]
                   if citation["source"] in citation_numbers(check["reason"])]} for check in canonical["checks"]]}
    sources = old["retrieval"]["sources"]
    originals = deepcopy((raw, sources))
    claimed = [name for name in names if name in captured["question"] and name in raw["checks"][0]["claim"]]
    if len(claimed) != 1 or len(movie.director) != 1:
        raise ValueError("저장 사례의 감독 대조 입력을 명확히 식별하지 못했습니다.")
    cases = []
    for case_id, same_director, review_relation in (
        ("stored_other_director", False, "contradicts"),
        ("same_director", True, "supports"),
        ("review_rejects_proposal", False, "supports"),
    ):
        draft, question = deepcopy(raw), captured["question"]
        if same_director:
            question = question.replace(claimed[0], movie.director[0])
            draft["checks"][0]["claim"] = draft["checks"][0]["claim"].replace(claimed[0], movie.director[0])
            last = movie.director[0][-1]
            if "가" <= last <= "힣" and (ord(last) - ord("가")) % 28 == 0:
                question = question.replace(movie.director[0] + "이 감독", movie.director[0] + "가 감독")
                draft["checks"][0]["claim"] = draft["checks"][0]["claim"].replace(
                    movie.director[0] + "이 감독", movie.director[0] + "가 감독")
        review = {"items": [
            {"claim_id": "c1", "evidence_relation": review_relation,
             "service_reason_supported": True, "reason": "고정 대체 검토 응답: 감독 표기 대조"},
            {"claim_id": "c2", "evidence_relation": "supports",
             "service_reason_supported": True, "reason": "고정 대체 검토 응답: 저장된 자연위성 구절"},
        ]}
        client = MagicMock()
        client.chat.completions.create.side_effect = [response(draft), response(review)]
        generator = AnswerGenerator(client, max_attempts=1, canonical_directors=names)
        result = generator.generate(movie, question, [], sources, "verify")
        expected = "확인됨" if same_director else "검토 보류" if case_id == "review_rejects_proposal" else "근거와 상충"
        passed = (result["checks"][0]["verdict"] == expected
                  and result["checks"][1]["verdict"] == "확인됨"
                  and result["sources"][1]["quote"] == old["sources"][1]["quote"]
                  and client.chat.completions.create.call_count == 2)
        cases.append({"case": case_id, "question": question, "expected_director_verdict": expected,
                      "contract_passed": passed, "result": result, "audit": generator.audit})
    assert (raw, sources) == originals, "Captured sources or raw checks were mutated"
    report = {"kind": "offline captured failure replay with fixed model responses", "api_calls": 0,
              "model_accuracy_verified": False, "source_file": source_file.relative_to(ROOT).as_posix(),
              "movie_id": movie.movie_id, "original_question": captured["question"],
              "before": {"checks": old["checks"], "semantic_check": old["validation"]["semantic_check"],
                         "reviewed_items": old["validation"]["reviewed_items"]},
              "captured_sources": sources[:2], "cases": cases,
              "success": all(case["contract_passed"] for case in cases)}
    target = ROOT / "artifacts/review_director_field/offline_cases.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"success": report["success"], "api_calls": 0,
                      "cases": [{"case": c["case"], "passed": c["contract_passed"]} for c in cases]}))
    return report["success"]


if __name__ == "__main__":
    with patch("socket.socket.connect", side_effect=AssertionError("Offline failure replay")):
        raise SystemExit(0 if run() else 1)
