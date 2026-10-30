"""Focused quote reliability regressions using isolated model responses only."""

from copy import deepcopy
from dataclasses import replace
import json
import unittest
from unittest.mock import MagicMock

from movie_lab.answering import AnswerGenerator, materialize_citations, quotation_parts
from movie_lab.document_llm import DocumentModelError
from movie_lab.state import append_assistant_message, get_thread
from tests.test_answering import model_response, review_result, verify_review_result
from tests.test_document_llm import sample_movie


def selected_movie():
    return replace(sample_movie(), movie_id="157336", title="인터스텔라", original_title="Interstellar",
                   year=2014, director=("크리스토퍼 놀란",))


def separated_metadata():
    text = "감독: 크리스토퍼 놀란\n\n" + ("구절 사이에 있는 제공 메타데이터 설명입니다. " * 22) + "\n\n상영 시간(분): 169"
    parts = quotation_parts(text)
    director = next(index for index, part in enumerate(parts) if "감독: 크리스토퍼 놀란" in part)
    runtime = next(index for index, part in enumerate(parts) if "상영 시간(분): 169" in part)
    assert director != runtime
    return {"title": "인터스텔라", "url": "https://example.invalid/movie/157336", "document_id": "meta:157336",
            "movie_id": "157336", "scope": "movie_metadata", "text": text}, parts, director, runtime


def two_facts(director, runtime):
    return {"facts": [
        {"text": "제공 메타데이터의 감독은 크리스토퍼 놀란입니다.", "citations": [{"passage_id": f"s1p{director}"}]},
        {"text": "제공 메타데이터의 상영 시간은 169분입니다.", "citations": [{"passage_id": f"s1p{runtime}"}]}],
        "unconfirmed": ""}


class AnsweringReliabilityTests(unittest.TestCase):
    def test_two_quotes_of_one_source_survive_review_deduplication_and_movie_switch(self):
        source, parts, director, runtime = separated_metadata()
        raw = two_facts(director, runtime)
        raw["facts"][0]["text"] += " [근거 99]"
        raw["facts"][1]["text"] += " [근거 77]"
        # Exact duplicates collapse; distinct passages keep the same source N.
        duplicated = deepcopy(raw)
        duplicated["facts"][0]["citations"].append({"passage_id": f"s1p{director}"})
        canonical = materialize_citations(duplicated, [parts], "general")
        self.assertEqual(canonical["citations"], [
            {"source": 1, "quote": parts[director]}, {"source": 1, "quote": parts[runtime]}])
        client = MagicMock()
        client.chat.completions.create.side_effect = [model_response(raw), model_response(review_result())]
        result = AnswerGenerator(client).generate(selected_movie(), "감독과 상영 시간을 알려줘", [], [source])
        self.assertEqual(client.chat.completions.create.call_count, 2)
        self.assertEqual(len(result["sources"]), 1)
        self.assertEqual(result["sources"][0]["quote"], parts[director])
        self.assertEqual(result["sources"][0]["quotes"], [parts[director], parts[runtime]])
        self.assertEqual(result["content"].count("[근거 1]"), 2)
        self.assertNotIn("[근거 99]", result["content"])
        self.assertNotIn("[근거 77]", result["content"])
        payload = json.loads(client.chat.completions.create.call_args_list[1].kwargs["messages"][1]["content"])
        self.assertTrue(all("[근거" not in row["claim"] for row in payload["assertions"]))
        self.assertEqual([row["citations"][0]["quote"] for row in payload["assertions"]],
                         [parts[director], parts[runtime]])
        self.assertEqual([row["citations"][0]["source"] for row in payload["assertions"]], [1, 1])
        threads = {}
        saved = append_assistant_message(threads, "157336", result["content"], result["sources"])
        expected = deepcopy(saved)
        append_assistant_message(threads, "753091", "다른 영화의 별도 근거입니다. [근거 1]",
                                 [{"title": "다른 출처", "url": "https://example.invalid/other", "quote": "별도 구절"}])
        self.assertEqual(get_thread(threads, "753091")[0]["sources"][0]["title"], "다른 출처")
        result["sources"][0]["quotes"].append("나중에 입력 목록을 변경한 구절")
        self.assertEqual(get_thread(threads, "157336")[0], expected)

    def test_every_quote_is_checked_and_a_wrong_second_quote_cannot_hide_behind_first(self):
        source, parts, director, runtime = separated_metadata()
        invalid = {"answer": "감독과 상영 시간 설명입니다. [근거 1]", "checks": [],
                   "citations": [{"source": 1, "quote": parts[director]},
                                 {"source": 1, "quote": "원문 어디에도 없는 잘못된 두 번째 구절"}]}
        client = MagicMock()
        client.chat.completions.create.return_value = model_response(invalid)
        generator = AnswerGenerator(client)
        with self.assertRaises(DocumentModelError):
            generator.generate(selected_movie(), "감독과 시간", [], [source])
        self.assertEqual(client.chat.completions.create.call_count, 2)
        self.assertFalse(any(row["stage"] == "semantic_model_review" for row in generator.audit))

    def test_abstention_has_empty_citations_in_schema_and_drops_unnecessary_model_quotes(self):
        source, parts, director, runtime = separated_metadata()
        raw = {"checks": [
            {"scope": "작품 속 묘사", "claim": "확인하지 못한 작품 장면 [근거 1]", "verdict": "근거 부족",
             "reason": "관련 없는 원문을 이유로 넣었습니다. [근거 99]", "citations": [{"passage_id": f"s1p{director}"}]},
            {"scope": "현실 사실", "claim": "확인하지 못한 현실 주장", "verdict": "근거 부족",
             "reason": "정보가 없습니다.", "citations": []}]}
        client = MagicMock()
        client.chat.completions.create.return_value = model_response(raw)
        result = AnswerGenerator(client).generate(selected_movie(), "두 범위를 확인해줘", [], [source], "verify")
        self.assertEqual(client.chat.completions.create.call_count, 1)
        self.assertEqual(result["validation"]["semantic_check"], "no_factual_assertions")
        self.assertNotIn("[근거", result["content"])
        self.assertNotIn("quote", result["sources"][0])
        self.assertNotIn("quotes", result["sources"][0])
        schema = client.chat.completions.create.call_args.kwargs["response_format"]["json_schema"]["schema"]
        self.assertEqual(schema["properties"]["checks"]["items"]["properties"]["citations"]["minItems"], 0)
        mixed = deepcopy(raw)
        mixed["checks"][1].update(claim="실제 메타데이터의 감독 정보 [근거 1]", verdict="확인됨",
                                  reason="제공 메타데이터의 감독은 크리스토퍼 놀란입니다. [근거 88]",
                                  citations=[{"passage_id": f"s1p{director}"}])
        client = MagicMock()
        client.chat.completions.create.side_effect = [model_response(mixed), model_response(verify_review_result(("c2", "supports", True)))]
        checked = AnswerGenerator(client).generate(selected_movie(), "작품과 실제 정보를 확인해줘", [], [source], "verify")
        withheld_row, asserted_row = checked["checks"]
        self.assertNotIn("[근거", withheld_row["claim"])
        self.assertNotIn("[근거", withheld_row["reason"])
        self.assertNotIn("[근거", asserted_row["claim"])
        self.assertEqual(asserted_row["reason"].count("[근거 1]"), 1)
        self.assertNotIn("[근거 88]", asserted_row["reason"])
        self.assertEqual(checked["content"].count("[근거 1]"), 1)

    def test_non_abstaining_verdicts_without_citations_are_rejected_before_semantic_review(self):
        source, parts, director, runtime = separated_metadata()
        for verdict in ("확인됨", "근거와 상충", "출처 충돌"):
            with self.subTest(verdict=verdict):
                raw = {"checks": [
                    {"scope": "작품 속 묘사", "claim": "작품 감독에 대한 주장", "verdict": verdict,
                     "reason": "근거 없는 서비스 판정", "citations": []},
                    {"scope": "현실 사실", "claim": "현실 주장", "verdict": "근거 부족",
                     "reason": "현실 근거가 부족합니다.", "citations": []}]}
                client = MagicMock()
                client.chat.completions.create.return_value = model_response(raw)
                generator = AnswerGenerator(client)
                result = generator.generate(selected_movie(), "검증 질문", [], [source], "verify")
                self.assertEqual(client.chat.completions.create.call_count, 1)
                self.assertEqual(result["checks"][0]["verdict"], "검토 보류")
                self.assertEqual(result["checks"][1]["verdict"], "근거 부족")
                self.assertNotIn("[근거", result["checks"][0]["reason"])
                self.assertFalse(any(row["stage"] == "semantic_model_review" for row in generator.audit))


if __name__ == "__main__":
    unittest.main()
