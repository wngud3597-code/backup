"""Stage counters and elapsed observations through a real offline StateGraph."""

import json
import unittest
from unittest.mock import Mock, patch

import httpx
from openai import APITimeoutError

from movie_lab.answering import AnswerGenerator
from movie_lab.rag import MovieRag
from tests.test_answering import model_response, review_result, verify_review_result
from tests.test_rag import FakePipeline, FakeRetriever
from tests.test_retrieval import selected_movie


class StageTimingTests(unittest.TestCase):
    def setUp(self):
        blocked = patch("socket.socket.connect", side_effect=AssertionError("Offline stage observation test"))
        blocked.start()
        self.addCleanup(blocked.stop)
        self.client = Mock()
        self.pipeline = FakePipeline()
        self.retriever = FakeRetriever()
        self.generator = AnswerGenerator(self.client, "gpt-4o-mini")
        self.pipeline_factory = Mock(return_value=self.pipeline)
        self.service = MovieRag(pipeline_factory=self.pipeline_factory,
                                retriever_factory=Mock(return_value=self.retriever),
                                generator_factory=Mock(return_value=self.generator))

    def assert_timing_shape(self, result):
        expected = {"preparation", "retrieval", "generation_node", "answer_generation", "semantic_review"}
        self.assertTrue(expected <= set(result["timings"]))
        for name in expected:
            self.assertIsInstance(result["timings"][name], (int, float))
            self.assertGreaterEqual(result["timings"][name], 0)
        self.assertEqual(result["trace"], ["retrieve", "generate"])

    def test_metadata_only_separates_generation_and_review_and_skips_preparation(self):
        self.retriever.embedder.request_count = 0
        self.client.chat.completions.create.side_effect = [model_response({"facts": [
            {"text": "제공 메타데이터의 감독은 Director입니다.", "citations": [{"passage_id": "s1p0"}]}],
            "unconfirmed": ""}), model_response(review_result())]
        result = self.service.answer(selected_movie(), "감독이 누구야?")
        self.assert_timing_shape(result)
        self.pipeline_factory.assert_not_called()
        self.assertEqual(result["timings"]["preparation"], 0)
        self.assertTrue(result["cache"]["preparation_skipped"])
        self.assertIsNone(result["cache"]["preparation_hit"])
        self.assertEqual(result["stage_calls"]["preparation"], {"chat": 0, "wiki": 0, "embedding": 0})
        self.assertEqual(result["stage_calls"]["retrieval"], {"embedding": 0})
        self.assertEqual(result["stage_calls"]["answer_generation"], {"chat": 1})
        self.assertEqual(result["stage_calls"]["semantic_review"], {"chat": 1})
        self.assertEqual(result["calls"]["answer_model"], 2)
        self.assertEqual(result["validation"]["semantic_check"], "model_review_passed")

    def test_cached_preparation_and_abstention_keep_generation_one_review_zero(self):
        self.pipeline.prepare = Mock(return_value={"complete": True, "movie_id": "101", "cache_hit": True,
            "document_cache_hits": 2, "calls": {"chat": 0, "wiki": 0, "embedding": 0}})
        self.client.chat.completions.create.return_value = model_response({"checks": [
            {"scope": "작품 속 묘사", "claim": "확인하지 못한 영화 장면", "verdict": "근거 부족", "reason": "정보 부족", "citations": []},
            {"scope": "현실 사실", "claim": "확인하지 못한 현실 설명", "verdict": "근거 부족", "reason": "정보 부족", "citations": []}]})
        result = self.service.answer(selected_movie(), "작품 장면과 현실 설명을 확인해줘", mode="verify")
        self.assert_timing_shape(result)
        self.assertFalse(result["cache"]["preparation_skipped"])
        self.assertTrue(result["cache"]["preparation_hit"])
        self.assertEqual(result["cache"]["document_body_hits"], 2)
        self.assertEqual(result["stage_calls"]["preparation"], {"chat": 0, "wiki": 0, "embedding": 0})
        self.assertEqual(result["stage_calls"]["answer_generation"], {"chat": 1})
        self.assertEqual(result["stage_calls"]["semantic_review"], {"chat": 0})
        self.assertEqual(result["timings"]["semantic_review"], 0)
        self.assertEqual(result["calls"]["answer_model"], 1)
        self.assertEqual(result["validation"]["semantic_check"], "no_factual_assertions")
        self.assertNotIn("[근거", result["content"])
        self.client.reset_mock()
        self.client.chat.completions.create.side_effect = [model_response({"checks": [
            {"scope": "작품 속 묘사", "claim": "감독은 Director다.", "verdict": "확인됨", "reason": "메타데이터의 감독은 Director입니다.", "citations": [{"passage_id": "s1p0"}]},
            {"scope": "현실 사실", "claim": "별도의 현실 주장", "verdict": "근거 부족", "reason": "정보 부족", "citations": []}]}),
            model_response(verify_review_result(("c1", "supports", True)))]
        fresh_generator = AnswerGenerator(self.client, "gpt-4o-mini")
        service = MovieRag(pipeline_factory=self.pipeline_factory, retriever_factory=Mock(return_value=self.retriever),
                           generator_factory=Mock(return_value=fresh_generator))
        verified = service.answer(selected_movie(), "영화와 현실 확인", mode="verify")
        self.assert_timing_shape(verified)
        self.assertEqual(verified["stage_calls"]["answer_generation"], {"chat": 1})
        self.assertEqual(verified["stage_calls"]["semantic_review"], {"chat": 1})
        self.assertEqual(verified["validation"]["semantic_check"], "item_review_passed")

    def test_semantic_timeout_preserves_failure_stage_counts_and_elapsed_values(self):
        self.retriever.embedder.request_count = 0
        self.client.chat.completions.create.side_effect = [model_response({"facts": [
            {"text": "제공 메타데이터의 감독은 Director입니다.", "citations": [{"passage_id": "s1p0"}]}],
            "unconfirmed": ""}), APITimeoutError(request=httpx.Request("POST", "https://synthetic-private.invalid"))]
        result = self.service.answer(selected_movie(), "감독이 누구야?")
        self.assert_timing_shape(result)
        self.assertEqual(result["failure_stage"], "semantic_review")
        self.assertEqual(result["stage_calls"]["answer_generation"], {"chat": 1})
        self.assertEqual(result["stage_calls"]["semantic_review"], {"chat": 1})
        self.assertEqual(result["calls"]["answer_model"], 2)
        self.assertEqual(self.client.chat.completions.create.call_count, 2)
        self.assertEqual(result["content"], "")
        self.assertTrue(result["validation"]["generation_failed"])
        self.assertEqual(result["error"]["category"], "타임아웃")
        self.assertNotIn("synthetic-private", json.dumps(result, ensure_ascii=False, default=str))

    def test_semantic_rejection_stage_replaces_a_previous_parse_failure(self):
        fact = {"facts": [{"text": "제공 메타데이터의 감독은 Director입니다.",
                           "citations": [{"passage_id": "s1p0"}]}], "unconfirmed": ""}
        rejection = review_result(False, "선택 원문 구절만으로 해당 사실을 확인하지 못했습니다.")
        for earlier_parse_failure in (False, True):
            with self.subTest(earlier_parse_failure=earlier_parse_failure):
                client = Mock()
                if earlier_parse_failure:
                    responses = [model_response("invalid-json"), model_response(fact), model_response(rejection)]
                else:
                    responses = [model_response(fact), model_response(rejection)] * 2
                client.chat.completions.create.side_effect = responses
                generator = AnswerGenerator(client, "gpt-4o-mini")
                retriever = FakeRetriever()
                retriever.embedder.request_count = 0
                service = MovieRag(pipeline_factory=Mock(return_value=FakePipeline()),
                                   retriever_factory=Mock(return_value=retriever),
                                   generator_factory=Mock(return_value=generator))
                result = service.answer(selected_movie(), "감독이 누구야?")
                self.assert_timing_shape(result)
                self.assertEqual(result["failure_stage"], "semantic_review")
                self.assertEqual(generator.last_failure_stage, "semantic_review")
                self.assertEqual(result["stage_calls"]["answer_generation"], {"chat": 2})
                self.assertEqual(result["stage_calls"]["semantic_review"], {"chat": 1 if earlier_parse_failure else 2})
                self.assertEqual(result["calls"]["answer_model"], 3 if earlier_parse_failure else 4)
                self.assertEqual(result["content"], "")
                self.assertTrue(result["validation"]["generation_failed"])
                if earlier_parse_failure:
                    self.assertEqual(result["validation"]["audit"][0]["stage"], "parse")


if __name__ == "__main__":
    unittest.main()
