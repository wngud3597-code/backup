"""Execute the actual two-node StateGraph with offline boundary doubles."""

from copy import deepcopy
import unittest
from unittest.mock import Mock, patch

from movie_lab.document_llm import DocumentModelError
from movie_lab.rag import MovieRag
from tests.test_retrieval import selected_movie


def source():
    return {"title": "격리된 테스트 메타데이터", "url": "https://example.org/movie/101",
            "text": "감독: Director", "movie_id": "101", "document_id": "meta:101",
            "source_kind": "metadata", "scope": "movie_metadata", "identity": "일치"}


class FakePipeline:
    def __init__(self, fail=False):
        self.fail, self.calls, self.closed = fail, [], False

    def prepare(self, movie, question, history, **options):
        self.calls.append((movie.movie_id, question, deepcopy(history), options))
        if self.fail:
            raise DocumentModelError("격리된 자료 준비 연결 실패")
        return {"complete": True, "movie_id": movie.movie_id,
                "calls": {"chat": 2, "embedding": 1, "wiki": 0}}

    def close(self):
        self.closed = True


class FakeRetriever:
    def __init__(self, sources=None):
        self.sources = [source()] if sources is None else sources
        self.calls = []
        self.embedder = Mock(request_count=1)

    def retrieve(self, movie, question, preparation=None):
        self.calls.append((movie.movie_id, question, deepcopy(preparation)))
        return {"sources": deepcopy(self.sources), "context": "격리된 테스트 문맥",
                "diagnostics": {"warnings": [], "metadata_origin": "provided_file"}}


class FakeGenerator:
    model = "gpt-4o-mini"
    reported_model = "offline-test"

    def __init__(self, fail=False):
        self.request_count, self.audit, self.calls = 0, [], []
        self.fail = fail

    def generate(self, movie, question, history, sources, mode, warnings):
        self.request_count += 1
        self.calls.append((movie.movie_id, question, deepcopy(history), deepcopy(sources), mode, list(warnings)))
        if self.fail:
            raise DocumentModelError("격리된 답변 생성 실패")
        return {"content": "격리된 테스트 답변입니다. [근거 1]",
                "sources": [{**row, "quote": "감독: Director"} for row in sources],
                "validation": {"semantic_check": "offline_test_double"}, "checks": []}


class MovieRagTests(unittest.TestCase):
    def setUp(self):
        blocked = patch("socket.socket.connect", side_effect=AssertionError("Offline StateGraph test"))
        blocked.start()
        self.addCleanup(blocked.stop)
        self.movie = selected_movie()

    def service(self, *, pipeline=None, retriever=None, generator=None, retriever_factory=None):
        self.pipeline = pipeline or FakePipeline()
        self.retriever = retriever or FakeRetriever()
        self.generator = generator or FakeGenerator()
        self.pipeline_factory = Mock(return_value=self.pipeline)
        self.retriever_factory = retriever_factory or Mock(return_value=self.retriever)
        self.generator_factory = Mock(return_value=self.generator)
        self.progress = []
        return MovieRag(pipeline_factory=self.pipeline_factory, retriever_factory=self.retriever_factory,
                        generator_factory=self.generator_factory, progress=self.progress.append)

    def test_role_models_do_not_mislabel_last_review_response_as_generation_model(self):
        generator = FakeGenerator()
        generator.model = "gpt-4o-mini"
        generator.review_model = "gpt-5.4-mini"
        generator.reported_model = "gpt-5.4-mini-server"
        generator.reported_models = {"generate_answer": "gpt-4o-mini-server",
                                     "review_verify": "gpt-5.4-mini-server"}
        result = self.service(generator=generator).answer(self.movie, "확인할 주장", mode="verify")
        self.assertEqual(result["validation"]["reported_model"], "gpt-4o-mini-server")
        self.assertEqual(result["validation"]["review_model"], "gpt-5.4-mini")
        self.assertEqual(result["validation"]["reported_models"]["review_verify"], "gpt-5.4-mini-server")

    def test_real_stategraph_runs_retrieve_then_generate_and_deduplicates_current_history(self):
        service = self.service()
        question = "우주선에서 시간이 다르게 흐르는 이유는?"
        history = [{"role": "user", "content": "우주선 장면을 설명해줘"},
                   {"role": "assistant", "content": "검증되지 않은 이전 설명", "answer_id": "old", "sources": []},
                   {"role": "user", "content": question}]
        original = deepcopy(history)
        result = service.answer(self.movie, question, history, mode="verify", refresh=True)
        self.assertEqual(result["trace"], ["retrieve", "generate"])
        self.assertEqual(result["mode"], "verify")
        self.assertEqual(self.generator.calls[0][4], "verify")
        self.assertEqual(self.generator.calls[0][2], [{"role": "user", "content": history[0]["content"]},
                                                    {"role": "assistant", "content": history[1]["content"]}])
        self.assertEqual(history, original)
        self.assertTrue(self.pipeline.calls[0][3]["refresh"])
        self.assertTrue(self.pipeline.closed)
        self.assertEqual(self.retriever_factory.call_args.kwargs, {"metadata_only": False})
        self.assertEqual(result["calls"]["answer_model"], 1)
        self.assertTrue(self.progress)

    def test_metadata_question_skips_preparation_and_requests_metadata_only_retrieval(self):
        service = self.service()
        result = service.answer(self.movie, "감독이 누구야?")
        self.pipeline_factory.assert_not_called()
        self.assertEqual(self.retriever_factory.call_args.kwargs, {"metadata_only": True})
        self.assertEqual(result["preparation"], {})
        self.assertEqual(result["calls"]["chat"], 0)
        self.assertEqual(result["trace"], ["retrieve", "generate"])
        self.assertEqual(len(self.generator.calls), 1)

    def test_preparation_failure_closes_resource_and_generates_only_available_evidence(self):
        service = self.service(pipeline=FakePipeline(fail=True))
        result = service.answer(self.movie, "우주 공간의 온도는 어느 정도야?")
        self.assertTrue(self.pipeline.closed)
        self.assertFalse(result["preparation"]["complete"])
        self.assertEqual(result["sources"][0]["movie_id"], "101")
        self.assertTrue(any("자료 준비 연결에 실패" in row for row in self.generator.calls[0][5]))
        self.assertEqual(result["trace"], ["retrieve", "generate"])

    def test_failed_retriever_factory_falls_back_to_provided_movie_metadata(self):
        factory = Mock(side_effect=RuntimeError("Synthetic private connection information"))
        service = self.service(retriever_factory=factory)
        result = service.answer(self.movie, "감독이 누구야?")
        used = self.generator.calls[0][3]
        self.assertEqual(used[0]["document_id"], "meta:101")
        self.assertEqual(result["retrieval"]["diagnostics"]["metadata_origin"], "provided_file")
        self.assertIn("메타데이터로 부분 처리", result["error"]["category"])
        self.assertNotIn("private connection", str(result))
        self.assertEqual(result["trace"], ["retrieve", "generate"])

    def test_empty_evidence_skips_generator_and_reports_unverified_answer(self):
        service = self.service(retriever=FakeRetriever(sources=[]))
        result = service.answer(self.movie, "감독이 누구야?")
        self.generator_factory.assert_not_called()
        self.assertTrue(result["validation"]["generation_skipped"])
        self.assertEqual(result["sources"], [])
        self.assertEqual(result["calls"]["answer_model"], 0)

    def test_generation_failure_returns_no_answer_and_preserves_callers_history(self):
        service = self.service(generator=FakeGenerator(fail=True))
        history = [{"role": "user", "content": "감독이 누구야?"}]
        original = deepcopy(history)
        result = service.answer(self.movie, "감독이 누구야?", history)
        self.assertEqual(history, original)
        self.assertEqual(result["content"], "")
        self.assertEqual(result["sources"], [])
        self.assertTrue(result["validation"]["generation_failed"])
        self.assertEqual(result["trace"], ["retrieve", "generate"])


if __name__ == "__main__":
    unittest.main()
