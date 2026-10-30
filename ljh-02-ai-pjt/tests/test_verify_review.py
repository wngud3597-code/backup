"""Per-item protocol tests with fixed reviewer responses, not model-accuracy tests.

The short Moon excerpts mirror the previously captured failure's available
evidence. All SDK responses here are isolated fixtures; no service is called.
"""

from copy import deepcopy
import json
import unittest
from unittest.mock import MagicMock

from movie_lab import answering
from movie_lab.document_llm import DocumentModelError
from movie_lab.state import append_assistant_message, get_thread
from tests.test_answering import model_response
from tests.test_answering_reliability import selected_movie, separated_metadata
from tests.test_document_llm import sample_movie


def evidence():
    return [
        {"title": "격리된 영화 메타데이터", "url": "https://example.invalid/fixture/meta", "document_id": "meta:753091",
         "scope": "movie_metadata", "text": "제목: 더 문\n연도: 2023\n감독: 김용화"},
        {"title": "격리된 달 배경", "url": "https://example.invalid/fixture/moon", "document_id": "background:moon",
         "scope": "background_unverified", "text": "달은 지구의 유일한 자연위성이고, 태양계의 위성 중에서 5번째로 크다."},
        {"title": "가상의 상충 문서", "url": "https://example.invalid/fixture/conflict", "document_id": "background:conflict",
         "scope": "background_unverified", "text": "이 격리된 가상 문서는 달을 지구의 자연위성으로 분류하지 않는다."},
    ]


def check(scope, claim, verdict, reason, *passages):
    return {"scope": scope, "claim": claim, "verdict": verdict, "reason": reason,
            "citations": [{"passage_id": passage} for passage in passages]}


def draft():
    return {"checks": [
        check("작품 속 묘사", "이 영화는 크리스토퍼 놀란이 감독했다.", "근거와 상충", "제공 메타데이터의 감독은 김용화입니다.", "s1p0"),
        check("현실 사실", "실제 달은 지구의 자연위성이다.", "확인됨", "제공 문서는 달이 지구의 자연위성이라고 설명합니다.", "s2p0")
    ]}


def review_item(claim_id, relation="supports", supported=True):
    return {"claim_id": claim_id, "evidence_relation": relation,
            "service_reason_supported": supported, "reason": "격리된 검토 응답의 항목별 근거 관계 판정"}


class VerifyReviewTests(unittest.TestCase):
    def generate(self, raw=None, review=None, sources=None, movie=None):
        client = MagicMock()
        client.chat.completions.create.side_effect = [model_response(raw or draft()), model_response(review or {
            "items": [review_item("c1", "contradicts"), review_item("c2")]})]
        generator = answering.AnswerGenerator(client)
        result = generator.generate(movie or sample_movie(), "영화 감독과 달에 대한 주장을 확인해줘", [], sources or evidence(), "verify")
        self.assertEqual(client.chat.completions.create.call_count, 2)
        return result, client, generator

    def test_four_verdict_relations_use_original_claim_ids_and_separate_the_user_proposition(self):
        # Explicit proposition / proposed-verdict / evidence-relation matrix.
        # The Kim director excerpt is identical in all four cases; the mock
        # relation is fixed test input rather than a model-accuracy judgment.
        polarity_matrix = [
            ("크리스토퍼 놀란", "근거와 상충", "contradicts", True),
            ("크리스토퍼 놀란", "확인됨", "contradicts", False),
            ("김용화", "확인됨", "supports", True),
            ("김용화", "근거와 상충", "supports", False),
        ]
        for director, proposed, relation, accepted in polarity_matrix:
            with self.subTest(user_director=director, proposed=proposed, relation=relation):
                raw = draft()
                raw["checks"][0].update(claim=f"이 영화의 감독은 {director}다.", verdict=proposed)
                result, client, generator = self.generate(raw, {"items": [review_item("c1", relation), review_item("c2")]})
                self.assertEqual(result["checks"][0]["verdict"], proposed if accepted else "검토 보류")
                self.assertEqual(result["checks"][1]["verdict"], "확인됨")
                self.assertIn("[근거 2]", result["checks"][1]["reason"])
                self.assertEqual(result["validation"]["semantic_check"],
                                 "item_review_passed" if accepted else "item_review_partial")
                if not accepted:
                    self.assertNotIn("quote", result["sources"][0])
                    self.assertNotIn("[근거", result["checks"][0]["reason"])
        cases = []
        positive = draft()
        positive["checks"][0].update(claim="이 영화의 감독은 김용화다.", verdict="확인됨")
        cases.append((positive, [review_item("c1"), review_item("c2")]))
        cases.append((draft(), [review_item("c1", "contradicts"), review_item("c2")]))
        negative = draft()
        negative["checks"][0] = check("작품 속 묘사", "확인할 수 없는 장면", "근거 부족", "작품 근거 부족")
        negative["checks"][1] = check("현실 사실", "달은 지구의 위성이 아니다.", "근거와 상충", "문서는 달이 지구의 위성이라고 설명합니다.", "s2p0")
        cases.append((negative, [review_item("c2", "contradicts")]))
        conflicting = deepcopy(negative)
        conflicting["checks"][1] = check("현실 사실", "두 문서의 달 분류가 일치한다.", "출처 충돌", "격리된 두 문서의 위성 분류가 다릅니다.", "s2p0", "s3p0")
        cases.append((conflicting, [review_item("c2", "conflicting")]))
        for raw, items in cases:
            with self.subTest(verdicts=[row["verdict"] for row in raw["checks"]]):
                result, client, generator = self.generate(raw, {"items": items})
                self.assertEqual(result["validation"]["semantic_check"], "item_review_passed")
                self.assertEqual([row["verdict"] for row in result["checks"]], [row["verdict"] for row in raw["checks"]])
                payload = json.loads(client.chat.completions.create.call_args_list[1].kwargs["messages"][1]["content"])
                self.assertEqual([row["claim_id"] for row in payload["items"]], [row["claim_id"] for row in items])
                for item in payload["items"]:
                    original = raw["checks"][int(item["claim_id"][1:]) - 1]
                    self.assertEqual(item["user_proposition"], original["claim"])
                    self.assertEqual(item["service_reason"], original["reason"])
                    self.assertNotIn("proposed_verdict", item)
                    self.assertNotIn("verdict", item)
                    self.assertTrue(all({"source", "quote", "scope", "document_id"} <= set(citation)
                                        for citation in item["citations"]))

    def test_unrelated_terrain_holds_only_that_item_and_background_cannot_confirm_a_film_scene(self):
        sources = evidence()
        sources[1]["text"] = "달의 바다는 현무암과 용암 대지로 이루어진 상대적으로 어두운 지역이다."
        result, client, generator = self.generate(review={"items": [review_item("c1", "contradicts"),
            review_item("c2", "insufficient", False)]}, sources=sources)
        self.assertEqual(result["validation"]["semantic_check"], "item_review_partial")
        self.assertEqual(result["checks"][0]["verdict"], "근거와 상충")
        self.assertEqual(result["checks"][1]["verdict"], "검토 보류")
        self.assertNotIn("[근거", result["checks"][1]["reason"])
        self.assertNotIn("quote", result["sources"][1])
        unsafe = draft()
        unsafe["checks"][0] = check("작품 속 묘사", "영화에서 달이 스스로 빛난다.", "확인됨", "현실 설명을 영화 장면으로 확대했습니다.", "s2p0")
        checked, client, generator = self.generate(unsafe, {"items": [review_item("c2")]})
        self.assertEqual(checked["checks"][0]["verdict"], "검토 보류")
        self.assertEqual(checked["checks"][1]["verdict"], "확인됨")

    def test_missing_duplicate_invalid_known_and_unknown_ids_preserve_independent_accepted_items(self):
        normal = [review_item("c1", "contradicts"), review_item("c2")]
        malformed = {**normal[0], "service_reason_supported": "yes"}
        cases = [
            ({"items": [normal[0]]}, [True, False], None),
            ({"items": [normal[0], normal[0], normal[1]]}, [False, True], None),
            ({"items": [malformed, normal[1]]}, [False, True], None),
            ({"items": normal + [review_item("c99")]}, [True, True], True),
            ({"items": "broken"}, [False, False], True),
            ({"unexpected": []}, [False, False], True),
        ]
        passages = [answering.quotation_parts(source["text"]) for source in evidence()]
        for review, accepted, protocol_failure in cases:
            with self.subTest(review=review):
                canonical = answering.materialize_citations(draft(), passages, "verify")
                items = canonical.pop("_assertions")
                canonical.pop("_pre_review_holds", None)
                final, decisions, errors = answering.apply_verify_review(canonical, items, review, evidence())
                self.assertEqual([row["accepted"] for row in decisions], accepted)
                if protocol_failure is not None:
                    self.assertEqual(bool(errors), protocol_failure)
                for index, accept in enumerate(accepted):
                    self.assertEqual(final["checks"][index]["verdict"], draft()["checks"][index]["verdict"] if accept else "검토 보류")
                    if not accept:
                        self.assertNotIn("[근거", final["checks"][index]["reason"])
        partial, client, generator = self.generate(review={"items": normal + [review_item("c99")]})
        self.assertEqual(partial["validation"]["semantic_check"], "item_review_partial")
        self.assertEqual([row["verdict"] for row in partial["checks"]], ["근거와 상충", "확인됨"])

    def test_relation_disagreement_and_unsupported_service_reason_hold_each_affected_item_without_regeneration(self):
        for reviews in ([review_item("c1", "supports"), review_item("c2")],
                        [review_item("c1", "contradicts"), review_item("c2", supported=False)],
                        [review_item("c1", "supports"), review_item("c2", "contradicts")]):
            with self.subTest(reviews=reviews):
                result, client, generator = self.generate(review={"items": reviews})
                self.assertEqual(generator.request_count, 2)
                expected = "item_review_held" if all(row["verdict"] == "검토 보류" for row in result["checks"]) else "item_review_partial"
                self.assertEqual(result["validation"]["semantic_check"], expected)
                self.assertTrue(any(row["verdict"] == "검토 보류" for row in result["checks"]))

    def test_multiple_quotes_and_past_answer_snapshots_survive_partial_item_review(self):
        source, parts, director, runtime = separated_metadata()
        raw = {"checks": [
            check("작품 속 묘사", "감독은 크리스토퍼 놀란이다.", "확인됨", "메타데이터의 감독은 크리스토퍼 놀란입니다.", f"s1p{director}"),
            check("현실 사실", "기록된 상영 시간은 169분이다.", "확인됨", "메타데이터의 상영 시간은 169분입니다.", f"s1p{runtime}")]}
        first, client, generator = self.generate(raw, {"items": [review_item("c1"), review_item("c2")]}, [source], selected_movie())
        self.assertEqual(first["sources"][0]["quotes"], [parts[director], parts[runtime]])
        threads = {}
        append_assistant_message(threads, "157336", first["content"], first["sources"])
        old = deepcopy(get_thread(threads, "157336")[0])
        later, client, generator = self.generate(raw, {"items": [review_item("c1", "insufficient", False), review_item("c2")]}, [source], selected_movie())
        self.assertEqual(later["checks"][0]["verdict"], "검토 보류")
        self.assertEqual(later["sources"][0]["quote"], parts[runtime])
        self.assertNotIn("quotes", later["sources"][0])
        append_assistant_message(threads, "753091", later["content"], later["sources"])
        self.assertEqual(get_thread(threads, "157336")[0], old)

    def test_wrong_second_original_quote_is_rejected_before_item_review(self):
        raw = draft()
        raw["checks"][0]["citations"] = [{"source": 1, "quote": "감독: 김용화"},
                                            {"source": 1, "quote": "원문에 없는 두 번째 구절"}]
        result, client, generator = self.generate(raw, {"items": [review_item("c2")]})
        self.assertEqual(result["checks"][0]["verdict"], "검토 보류")
        self.assertEqual(result["checks"][1]["verdict"], "확인됨")
        self.assertNotIn("quote", result["sources"][0])


if __name__ == "__main__":
    unittest.main()
