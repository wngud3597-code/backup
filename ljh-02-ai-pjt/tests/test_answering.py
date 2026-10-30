"""Grounded generation boundaries with an injected client; no API or key reads."""

from copy import deepcopy
import json
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock

import httpx
from openai import AuthenticationError

from movie_lab.answering import AnswerGenerator, quotation_parts, validate_answer
from movie_lab.document_llm import DocumentModelError
from tests.test_document_llm import sample_movie


def model_response(content):
    return SimpleNamespace(model="gpt-4o-mini-2024-07-18", choices=[SimpleNamespace(
        message=SimpleNamespace(content=content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)))])


def source(**changes):
    return {"title": "실제 검색 문서", "url": "https://example.invalid/verified-source",
            "document_id": "science-a", "text": "중력이 강한 곳에서는 시간이 느리게 흐른다.",
            "scope": "background_unverified", "identity": "확인 필요",
            "details": {"labels": ["원본"]}, **changes}


def draft(**changes):
    return {"answer": "제공 문서는 강한 중력에서 시간이 느리게 흐른다고 설명합니다. [근거 1]",
            "citations": [{"source": 1, "quote": "중력이 강한 곳에서는 시간이 느리게 흐른다."}],
            "checks": [], **changes}


def fact_result(text="제공 문서는 강한 중력에서 시간이 느리게 흐른다고 설명합니다.", *,
                number=1, index=0, unconfirmed=""):
    return {"facts": [{"text": text, "citations": [{"passage_id": f"s{number}p{index}"}]}],
            "unconfirmed": unconfirmed}


def review_result(supported=True, reason="선택 원문 구절이 제시한 사실 주장을 뒷받침합니다."):
    return {"reason": reason, "supported": supported}


def verify_review_result(*items):
    """Fixed protocol fixtures, not measurements of model judgment accuracy."""
    return {"items": [{"claim_id": claim_id, "evidence_relation": relation,
                       "service_reason_supported": supported, "reason": "격리된 항목 검토 fixture"}
                      for claim_id, relation, supported in items]}


class AnsweringTests(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.create = self.client.chat.completions.create
        self.generator = AnswerGenerator(self.client, "gpt-4o-mini")

    def generate(self, sources=None, **kwargs):
        return self.generator.generate(sample_movie(), "시간이 흐르는 현상을 설명해줘", [],
                                       [source()] if sources is None else sources, **kwargs)

    def test_success_separates_mechanical_and_model_review_and_preserves_source_snapshot(self):
        sources = [source(text="관측 과정의 배경을 설명하는 문장입니다. " * 20
                               + "중력이 강한 곳에서는 시간이 느리게 흐른다.")]
        before = deepcopy(sources)
        excerpts = quotation_parts(sources[0]["text"])
        index = len(excerpts) - 1
        self.assertGreater(index, 0)
        general = fact_result(index=index, unconfirmed="보류된 질문의 전제는 검증하지 못했습니다.")
        self.create.side_effect = [model_response(general), model_response(review_result())]
        result = self.generate(sources, warnings=["작품 묘사로 확인되지 않은 배경 문서"])
        self.assertEqual(self.create.call_count, 2)
        actual_schema = self.create.call_args_list[0].kwargs["response_format"]["json_schema"]["schema"]
        generation_payload = json.loads(self.create.call_args_list[0].kwargs["messages"][1]["content"])
        self.assertEqual(set(actual_schema["properties"]), {"facts", "unconfirmed"})
        self.assertEqual(set(actual_schema["required"]), {"facts", "unconfirmed"})
        self.assertEqual(actual_schema["properties"]["facts"]["minItems"], 0)
        self.assertEqual(result["checks"], [])
        review_payload = json.loads(self.create.call_args_list[1].kwargs["messages"][1]["content"])
        self.assertNotIn("question", review_payload)  # Coverage is not a factual assertion.
        self.assertNotIn("unconfirmed", review_payload)
        citations_schema = actual_schema["properties"]["facts"]["items"]["properties"]["citations"]
        self.assertEqual(citations_schema["minItems"], 1)
        self.assertEqual(set(citations_schema["items"]["properties"]), {"passage_id"})
        self.assertEqual(citations_schema["items"]["required"], ["passage_id"])
        passage_ids = [f"s1p{i}" for i in range(len(excerpts))]
        self.assertEqual(citations_schema["items"]["properties"]["passage_id"]["enum"], passage_ids)
        self.assertEqual([part["passage_id"] for part in generation_payload["evidence"][0]["passages"]], passage_ids)
        self.assertEqual(generation_payload["evidence"][0]["passages"][index]["text"], excerpts[index])
        self.assertEqual(review_payload["selected_movie"]["movie_id"], sample_movie().movie_id)
        self.assertEqual(len(review_payload["assertions"]), 1)
        self.assertEqual(review_payload["assertions"][0]["claim"], general["facts"][0]["text"])
        self.assertNotIn(general["unconfirmed"], json.dumps(review_payload, ensure_ascii=False))
        self.assertEqual(review_payload["assertions"][0]["citations"][0]["quote"], excerpts[index])
        review_schema = self.create.call_args_list[1].kwargs["response_format"]["json_schema"]["schema"]
        self.assertEqual(set(review_schema["properties"]), {"reason", "supported"})
        self.assertEqual(review_schema["properties"]["supported"]["type"], "boolean")
        self.assertEqual(review_schema["required"], ["reason", "supported"])
        self.assertTrue(result["validation"]["number_range"])
        self.assertTrue(result["validation"]["quotes_in_original"])
        self.assertEqual(result["validation"]["semantic_check"], "model_review_passed")
        self.assertEqual([row["stage"] for row in self.generator.audit],
                         ["mechanical", "semantic_model_review"])
        self.assertEqual(result["sources"][0]["title"], before[0]["title"])
        self.assertEqual(result["sources"][0]["url"], before[0]["url"])
        self.assertEqual(result["sources"][0]["quote"], excerpts[index])
        self.assertIn(result["sources"][0]["quote"], sources[0]["text"])
        self.assertIn("[근거 1]", result["content"])
        self.assertNotIn("text", result["sources"][0])
        self.assertEqual(sources, before)
        sources[0]["title"] = "나중에 바뀐 제목"
        result["sources"][0]["details"]["labels"].append("반환본 변경")
        self.assertEqual(result["sources"][0]["title"], before[0]["title"])
        self.assertEqual(sources[0]["details"], before[0]["details"])

    def test_invalid_json_number_and_missing_original_quote_have_bounded_repair(self):
        cases = ["synthetic-private-invalid-json", draft(answer="설명 [근거 9]"),
                 draft(citations=[{"source": 1, "quote": "원문에는 없는 인용 구절"}]),
                 fact_result(number=0), fact_result(number=2), fact_result(index=-1),
                 fact_result(index=1), fact_result(index=True)]
        for malformed in ({}, "잘못된 인용 문자열", {"source": 1},
                          {"source": "1", "quote_index": 0},
                          {"source": 1, "quote_index": 0, "extra": "허용하지 않은 필드"},
                          {"passage_id": True}, {"passage_id": 1}, {"passage_id": "s01p0"},
                          {"passage_id": "s1p9999"}, {"passage_id": "s1p0", "extra": "허용하지 않은 필드"}):
            invalid = fact_result()
            invalid["facts"][0]["citations"] = [malformed]
            cases.append(invalid)
        for bad in cases:
            with self.subTest(bad=type(bad).__name__):
                client = MagicMock()
                client.chat.completions.create.return_value = model_response(bad)
                generator = AnswerGenerator(client)
                with self.assertRaises(DocumentModelError) as caught:
                    generator.generate(sample_movie(), "질문", [], [source()])
                self.assertEqual(client.chat.completions.create.call_count, 2)
                self.assertEqual(generator.request_count, 2)
                self.assertNotIn("synthetic-private", str(caught.exception))
                self.assertFalse(any(row["stage"] == "semantic_model_review" for row in generator.audit))

    def test_no_evidence_skips_generation_and_does_not_claim_review_success(self):
        result = self.generate([])
        self.create.assert_not_called()
        self.assertEqual(result["sources"], [])
        self.assertTrue(result["validation"]["generation_skipped"])
        self.assertEqual(result["validation"]["semantic_check"], "not_run")
        # With no factual assertion, withholding is not labelled a truth check.
        # There is one generation call and no semantic-model review call.
        limitation = {"facts": [], "unconfirmed": "질문한 작품 장면의 등장 여부"}
        self.create.side_effect = [model_response(limitation)]
        limited = self.generate()
        self.assertEqual(self.create.call_count, 1)
        self.assertTrue(limited["validation"]["number_range"])
        self.assertEqual(limited["validation"]["semantic_check"], "no_factual_assertions")
        self.assertEqual(self.generator.audit[-1]["stage"], "no_factual_assertions")
        self.assertIsNone(self.generator.audit[-1]["passed"])
        self.assertFalse(any(row["stage"] == "semantic_model_review" for row in self.generator.audit))
        self.assertNotIn("truth_verified", limited["validation"])

    def test_semantic_issue_retries_entire_draft_once_and_second_issue_stops_at_four_calls(self):
        issue = "특정 영화의 장면이라는 주장을 현실 문서가 뒷받침하지 않습니다."
        unsupported = fact_result(text="이 영화에 그 장면이 나온다고 확인됩니다.")
        self.create.side_effect = [model_response(unsupported), model_response(review_result(False, issue)),
                                   model_response(fact_result()), model_response(review_result())]
        result = self.generate()
        self.assertEqual(self.create.call_count, 4)
        self.assertEqual(result["validation"]["attempts"], 2)
        self.assertNotIn("그 장면", result["content"])
        retried = json.loads(self.create.call_args_list[2].kwargs["messages"][1]["content"])
        self.assertEqual(retried["repair"], [issue])
        self.assertEqual([row["passed"] for row in self.generator.audit
                          if row["stage"] == "semantic_model_review"], [False, True])
        client = MagicMock()
        client.chat.completions.create.side_effect = [model_response(fact_result()), model_response(review_result(False, issue))] * 2
        with self.assertRaises(DocumentModelError):
            AnswerGenerator(client).generate(sample_movie(), "질문", [], [source()])
        self.assertEqual(client.chat.completions.create.call_count, 4)

    def test_verify_requires_film_evidence_and_different_documents_for_conflict(self):
        check = {"scope": "작품 속 묘사", "claim": "영화의 장면", "verdict": "확인됨", "reason": "장면을 확인했다. [근거 1]"}
        reality = {"scope": "현실 사실", "claim": "시간의 흐름", "verdict": "확인됨", "reason": "시간의 흐름을 설명한다. [근거 1]"}
        invalid = draft(checks=[check, reality])
        self.assertIn("현실 배경만으로 작품 장면을 판정할 수 없음", validate_answer(invalid, [source()], "verify"))
        checks = [{**check, "verdict": "근거 부족", "reason": "제공 문서에서 선택 작품의 장면을 확인하지 못했습니다."},
                  {**reality, "verdict": "출처 충돌", "reason": "두 문서의 설명이 충돌한다. [근거 1, 2]"}]
        evidence = [source(), source(text="다른 문장은 반대 현상을 서술한다.")]
        conflict = draft(answer="작품의 묘사는 확인할 수 없고 현실 설명은 추가 검토가 필요합니다.",
                         checks=checks, citations=draft()["citations"] + [{"source": 2, "quote": "다른 문장은 반대 현상을 서술한다."}])
        self.assertIn("출처 충돌에는 서로 다른 문서 근거가 필요함", validate_answer(conflict, evidence, "verify"))
        evidence[1]["document_id"] = "science-b"
        # A distinct document is mechanically necessary; these unit assertions
        # do not claim the two statements actually conflict in meaning.
        self.assertEqual(validate_answer(conflict, evidence, "verify"), [])
        film_conflict = draft(answer="작품 묘사에 관한 문서 간 차이를 추가로 확인해야 합니다.",
                              citations=conflict["citations"], checks=[
                                  {**check, "verdict": "출처 충돌", "reason": "작품 묘사의 두 설명을 비교했다. [근거 1, 2]"},
                                  {**reality, "verdict": "근거 부족", "reason": "현실에 대해서는 판정 근거가 부족합니다."}])
        self.assertIn("현실 배경만으로 작품 장면을 판정할 수 없음",
                      validate_answer(film_conflict, evidence, "verify"))
        evidence[0]["scope"] = "film_description"
        self.assertIn("작품 묘사의 출처 충돌에는 작품 근거 문서가 둘 이상 필요함",
                      validate_answer(film_conflict, evidence, "verify"))
        evidence[1]["scope"] = "film_description"
        self.assertEqual(validate_answer(film_conflict, evidence, "verify"), [])
        insufficient = {"checks": [
            {**check, "verdict": "근거 부족", "reason": "근거 부족 행에 숨긴 사실 단정 A",
             "citations": [{"passage_id": "s1p0"}]},
            {**reality, "verdict": "근거 부족", "reason": "근거 부족 행에 숨긴 사실 단정 B",
             "citations": [{"passage_id": "s1p0"}]}]}
        self.create.side_effect = [model_response(insufficient)]
        result = self.generate(mode="verify")
        actual_schema = self.create.call_args_list[0].kwargs["response_format"]["json_schema"]["schema"]
        self.assertEqual(set(actual_schema["properties"]), {"checks"})
        self.assertEqual(set(actual_schema["required"]), {"checks"})
        self.assertEqual(actual_schema["properties"]["checks"]["minItems"], 2)
        self.assertEqual(set(actual_schema["properties"]["checks"]["items"]["properties"]),
                         {"scope", "claim", "verdict", "reason", "citations"})
        self.assertEqual(self.create.call_count, 1)
        self.assertEqual(result["validation"]["semantic_check"], "no_factual_assertions")
        self.assertNotIn("숨긴 사실 단정", result["content"])
        self.assertTrue(all("확인하지 못했습니다" in row["reason"] for row in result["checks"]))
        self.assertFalse(any(row["stage"] == "semantic_model_review" for row in self.generator.audit))
        self.create.reset_mock()
        hybrid = deepcopy(insufficient)
        hybrid["checks"][0]["claim"] = "검증하지 못한 사용자 작품 주장"
        hybrid["checks"][1].update(verdict="확인됨", reason="제공 구절은 중력에 따른 시간 흐름을 설명합니다.")
        self.create.side_effect = [model_response(hybrid), model_response(verify_review_result(("c2", "supports", True)))]
        reviewed = self.generate(mode="verify")
        self.assertEqual(self.create.call_count, 2)
        payload = json.loads(self.create.call_args_list[1].kwargs["messages"][1]["content"])
        self.assertEqual(len(payload["items"]), 1)
        self.assertEqual(payload["items"][0]["scope"], "현실 사실")
        self.assertNotIn("검증하지 못한 사용자 작품 주장", json.dumps(payload, ensure_ascii=False))
        self.assertNotIn("question", payload)
        self.assertEqual(reviewed["validation"]["semantic_check"], "item_review_passed")
        self.create.reset_mock()
        contradiction = {"checks": [
            {"scope": "작품 속 묘사", "claim": "이 작품의 감독은 가상 감독이다.",
             "verdict": "근거와 상충", "reason": "제공 메타데이터의 감독은 김용화입니다.",
             "citations": [{"passage_id": "s1p0"}]},
            {"scope": "현실 사실", "claim": "강한 중력에서 시간이 느리게 흐른다.",
             "verdict": "확인됨", "reason": "제공 현실 문서는 강한 중력에서 시간이 느리게 흐른다고 설명합니다.",
             "citations": [{"passage_id": "s2p0"}]}]}
        self.create.side_effect = [model_response(contradiction), model_response(verify_review_result(
            ("c1", "contradicts", True), ("c2", "supports", True)))]
        judgment = self.generator.generate(sample_movie(), "두 주장을 확인해줘", [],
            [source(document_id="meta:753091", scope="movie_metadata", text="제목: 더 문\n연도: 2023\n감독: 김용화"), source()], "verify")
        self.assertEqual(self.create.call_count, 2)
        judgment_payload = json.loads(self.create.call_args_list[1].kwargs["messages"][1]["content"])
        reviewed_film = judgment_payload["items"][0]
        self.assertEqual(reviewed_film["service_reason"], contradiction["checks"][0]["reason"])
        self.assertEqual(reviewed_film["user_proposition"], contradiction["checks"][0]["claim"])
        self.assertNotIn("proposed_verdict", reviewed_film)
        self.assertNotIn("verdict", reviewed_film)
        self.assertNotEqual(reviewed_film["service_reason"], reviewed_film["user_proposition"])
        self.assertEqual(judgment["checks"][0]["verdict"], "근거와 상충")
        invalid_verdict = deepcopy(insufficient)
        invalid_verdict["checks"][0]["verdict"] = "허용하지 않은 판정"
        client = MagicMock()
        client.chat.completions.create.return_value = model_response(invalid_verdict)
        with self.assertRaises(DocumentModelError):
            AnswerGenerator(client).generate(sample_movie(), "검증 질문", [], [source()], "verify")
        self.assertEqual(client.chat.completions.create.call_count, 2)
        ambiguous = deepcopy(insufficient)
        ambiguous["checks"][1]["citations"] = [{"passage_id": "s1p1"}]
        long_source = source(text="첫 관측 구절을 설명하는 문장입니다. " * 20 + "두 번째 구절의 설명입니다.")
        self.assertGreater(len(quotation_parts(long_source["text"])), 1)
        client = MagicMock()
        client.chat.completions.create.return_value = model_response(ambiguous)
        withheld = AnswerGenerator(client).generate(sample_movie(), "검증 질문", [], [long_source], "verify")
        self.assertEqual(client.chat.completions.create.call_count, 1)
        self.assertEqual(withheld["validation"]["semantic_check"], "no_factual_assertions")
        self.assertNotIn("[근거", withheld["content"])

    def test_semantic_review_api_failure_is_safe_and_not_automatically_retried(self):
        error = AuthenticationError("synthetic-private-key", response=httpx.Response(
            401, request=httpx.Request("POST", "https://example.invalid")),
            body={"message": "synthetic-private-key"})
        self.create.side_effect = [model_response(fact_result()), error]
        with self.assertRaises(DocumentModelError) as caught:
            self.generate()
        self.assertEqual(caught.exception.http_status, 401)
        self.assertEqual(caught.exception.category, "인증 실패")
        self.assertNotIn("synthetic-private", str(caught.exception))
        self.assertEqual(self.create.call_count, 2)


if __name__ == "__main__":
    unittest.main()
