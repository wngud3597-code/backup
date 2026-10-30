"""Replay captured failure evidence with FIXED review relations, without APIs.

This tests code acceptance/rejection contracts, not model judgment accuracy.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from movie_lab.answering import (apply_verify_review, citation_numbers, materialize_citations,
                                prepare_verify_items, quotation_parts)


def replay(saved_case, output):
    saved = json.loads(saved_case.read_text(encoding="utf-8"))
    failed = next(row for row in saved["records"] if row["id"] == "contradiction_and_confirmation")
    canonical = next(row["draft"] for row in failed["validation"]["audit"] if row["stage"] == "mechanical")
    quotes = canonical["citations"]
    raw = {"checks": [{**row, "citations": [quote for quote in quotes if quote["source"] in citation_numbers(row["reason"])]}
                      for row in canonical["checks"]]}
    sources = failed["retrieval"]["sources"]
    passages = [quotation_parts(source["text"]) for source in sources]
    records = []
    for name, claim, proposed, relation, expected in (
        ("nolan_contradiction", "이 영화는 크리스토퍼 놀란이 감독했다.", "근거와 상충", "contradicts", True),
        ("nolan_confirmation", "이 영화는 크리스토퍼 놀란이 감독했다.", "확인됨", "contradicts", False),
        ("kim_confirmation", "이 영화는 김용화가 감독했다.", "확인됨", "supports", True),
        ("kim_contradiction", "이 영화는 김용화가 감독했다.", "근거와 상충", "supports", False),
    ):
        case = deepcopy(raw)
        case["checks"][0].update(claim=claim, verdict=proposed)
        result = materialize_citations(case, passages, "verify")
        items = result.pop("_assertions")
        result.pop("_pre_review_holds")
        result, items, mechanical_holds = prepare_verify_items(result, items, sources)
        review = {"items": [
            {"claim_id": "c1", "evidence_relation": relation, "service_reason_supported": True,
             "reason": "고정 대체 응답: 제공 감독 구절과 원래 명제의 관계"},
            {"claim_id": "c2", "evidence_relation": "supports", "service_reason_supported": True,
             "reason": "고정 대체 응답: 자연위성 구절이 사용자 명제를 지지"}]}
        final, decisions, protocol_errors = apply_verify_review(result, items, review, sources)
        passed = not mechanical_holds and decisions[0]["accepted"] == expected and decisions[1]["accepted"]
        records.append({"case": name, "expected_first_accepted": expected, "contract_passed": bool(passed),
                        "review_input": items, "fixed_review_output": review, "decisions": decisions,
                        "final_checks": final["checks"], "protocol_errors": protocol_errors})
    report = {"kind": "offline_contract_replay", "model_accuracy_verified": False, "api_calls": 0,
              "source_file": str(saved_case), "original_question": failed["question"],
              "original_failed_draft": canonical, "original_global_review": failed["validation"]["audit"][-1],
              "captured_sources": [{k: source.get(k) for k in ("document_id", "title", "url", "scope", "text")}
                                   for source in sources[:2]],
              "cases": records, "success": all(row["contract_passed"] for row in records)}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"success": report["success"], "api_calls": 0,
                      "cases": [{"case": row["case"], "accepted": [d["accepted"] for d in row["decisions"]]}
                                for row in records]}, ensure_ascii=False))
    return report["success"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--saved-case", type=Path, default=ROOT / "artifacts/review_stage4_fix/actual_cases.json")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/review_stage4_items/offline_contract.json")
    args = parser.parse_args()
    raise SystemExit(0 if replay(args.saved_case, args.output) else 1)
