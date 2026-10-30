"""Bounded, isolated model parsing checks; no key or network access."""

import json
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
from openai import AuthenticationError, BadRequestError

from movie_lab.data import Movie
from movie_lab.document_llm import DocumentModelError, LlmDocumentPlanner


def sample_movie():
    return Movie("753091", "더 문", "더 문", "2023-08-02", 2023, ("SF",), ("김용화",),
                 (), "달에 고립된 우주대원을 구출한다.", 129, "ko", ("대한민국",), None, None, "")


def response(value):
    return SimpleNamespace(model="gpt-4o-mini-2024-07-18", choices=[SimpleNamespace(
        message=SimpleNamespace(content=value if isinstance(value, str) else json.dumps(value)))])


class DocumentPlannerTests(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.planner = LlmDocumentPlanner(self.client, "gpt-4o-mini")
        self.create = self.client.chat.completions.create

    def test_extract_own_movie_query_added_and_unverified_history_marked(self):
        self.create.return_value = response({"queries": ["달", "우주 구조"], "focus": "달 구조 가능성"})
        result = self.planner.extract(sample_movie(), "달에서 구조 가능해?", [
            {"role": "assistant", "content": "검증되지 않은 주장", "sources": [{"url": "private"}]}])
        self.assertEqual(result["queries"][0], "더 문 2023 김용화")
        options = self.create.call_args.kwargs
        self.assertEqual(options["response_format"]["type"], "json_schema")
        self.assertEqual(options["model"], "gpt-4o-mini")
        self.assertEqual(self.planner.reported_model, "gpt-4o-mini-2024-07-18")
        payload = json.loads(options["messages"][1]["content"])
        self.assertIn("unverified_recent_conversation", payload)
        self.assertNotIn("sources", payload["unverified_recent_conversation"][0])
        self.assertEqual(self.planner.request_count, 1)

    def test_invalid_json_has_only_one_repair_and_no_response_echo(self):
        self.create.return_value = response("private-key-bad-json")
        with self.assertRaises(DocumentModelError) as caught:
            self.planner.extract(sample_movie(), "달에 관해")
        self.assertEqual(self.create.call_count, 2)
        self.assertNotIn("private-key", str(caught.exception))

    def test_facets_only_output_is_repaired_and_topics_precede_ancillary_queries(self):
        movie = sample_movie()
        self.create.side_effect = [response({"queries": ["더 문", "2023", "김용화"], "focus": "질문"}),
                                  response({"queries": ["김용화", "달 중력", "우주 구조"], "focus": "중력과 구조"})]
        result = self.planner.extract(movie, "달 중력이 구조에 미치는 영향은?")
        self.assertEqual(self.create.call_count, 2)
        self.assertEqual(result["queries"][:3], ["더 문 2023 김용화", "달 중력", "우주 구조"])
        self.assertIn("배경 개념 검색어", self.create.call_args.kwargs["messages"][-1]["content"])

    def test_metadata_question_allows_identity_queries_but_substantive_question_does_not(self):
        self.create.return_value = response({"queries": ["더 문", "2023", "김용화"], "focus": "감독"})
        result = self.planner.extract(sample_movie(), "감독이 누구야?")
        self.assertEqual(result["queries"][0], "더 문 2023 김용화")
        self.assertEqual(self.create.call_count, 1)
        with self.assertRaises(DocumentModelError):
            self.planner.extract(sample_movie(), "감독이 묘사한 우주 구조는 가능한가?")
        self.assertEqual(self.create.call_count, 3)

    def test_unsupported_schema_falls_back_to_ordinary_json_once(self):
        error = BadRequestError("private", response=httpx.Response(400, request=httpx.Request("POST", "https://example.invalid")),
                                body={"param": "response_format", "message": "json_schema is not supported"})
        self.create.side_effect = [error, response({"queries": ["달"], "focus": "배경"})]
        result = self.planner.extract(sample_movie(), "달 질문")
        self.assertEqual(result["mode"], "json")
        self.assertNotIn("response_format", self.create.call_args_list[1].kwargs)
        self.assertEqual(self.create.call_count, 2)
        self.assertEqual(self.planner.audit[0]["status"], "unsupported")

    def test_auth_failure_does_not_retry_or_expose_body(self):
        self.create.side_effect = AuthenticationError("private-key", response=httpx.Response(401, request=httpx.Request("POST", "https://example.invalid")), body={"message": "private-key"})
        with self.assertRaises(DocumentModelError) as caught:
            self.planner.extract(sample_movie(), "질문")
        self.assertEqual(self.create.call_count, 1)
        self.assertEqual(caught.exception.http_status, 401)
        self.assertNotIn("private", str(caught.exception))

    def test_selection_ids_and_reasons_must_match_allowed_candidates(self):
        candidates = [{"candidate_id": "wiki:1", "title": "달", "snippet": "천체"}]
        self.create.side_effect = [response({"selected_ids": ["wiki:secret"], "reasons": []}),
                                  response({"selected_ids": ["wiki:1"], "reasons": [{"candidate_id": "wiki:1", "reason": "배경"}]})]
        result = self.planner.select(sample_movie(), "달 질문", candidates)
        self.assertEqual(result["selected_ids"], ["wiki:1"])
        self.assertEqual(self.create.call_count, 2)
        self.create.reset_mock()
        self.create.side_effect = None
        self.assertEqual(self.planner.select(sample_movie(), "질문", [])["selected_ids"], [])
        self.create.assert_not_called()


if __name__ == "__main__":
    unittest.main()
