"""Fixed-response contract tests, not measurements of model accuracy."""

from copy import deepcopy
from dataclasses import replace
import json
import unittest
from unittest.mock import MagicMock, patch

from movie_lab.answering import AnswerGenerator
from movie_lab.data import build_index_text
from movie_lab.state import append_assistant_message, get_thread
from tests.test_answering import model_response, verify_review_result
from tests.test_document_llm import sample_movie


class DirectorIntegrationTests(unittest.TestCase):
    def setUp(self):
        block = patch("socket.socket.connect", side_effect=AssertionError("Offline director integration"))
        block.start()
        self.addCleanup(block.stop)
        self.movie = replace(sample_movie(), movie_id="unit-director", title="격리된 작품", director=("박하늘",))
        self.sources = [
            {"movie_id": self.movie.movie_id, "document_id": "meta:" + self.movie.movie_id,
             "title": "격리된 메타데이터", "url": "https://example.invalid/fixture/metadata",
             "scope": "movie_metadata", "source_kind": "metadata", "text": build_index_text(self.movie)},
            {"movie_id": self.movie.movie_id, "document_id": "fixture:moon", "title": "격리된 배경",
             "url": "https://example.invalid/fixture/moon", "source_kind": "snapshot",
             "scope": "background_unverified", "text": "달은 지구의 자연위성이다."},
        ]
        self.raw = {"checks": [
            {"scope": "작품 속 묘사", "claim": "이 영화는 이소연이 감독했다.", "verdict": "근거 부족",
             "reason": "격리된 생성기의 메타데이터 활용 누락", "citations": []},
            {"scope": "현실 사실", "claim": "실제 달은 지구의 자연위성이다.", "verdict": "확인됨",
             "reason": "배경 구절은 달을 지구의 자연위성이라고 설명합니다.",
             "citations": [{"source": 2, "quote": "달은 지구의 자연위성이다."}]},
        ]}
        self.question = "이 영화는 이소연이 감독했고, 실제 달은 지구의 자연위성이라는 말이 맞나요?"

    def generate(self, relation="contradicts", supported=True):
        client = MagicMock()
        client.chat.completions.create.side_effect = [model_response(self.raw), model_response(
            verify_review_result(("c1", relation, supported), ("c2", "supports", True)))]
        generator = AnswerGenerator(client, max_attempts=1, canonical_directors={"박하늘", "이소연"})
        result = generator.generate(self.movie, self.question, [], self.sources, "verify")
        self.assertEqual(client.chat.completions.create.call_count, 2)
        return generator, client, result

    def test_code_proposal_enters_same_batch_and_keeps_source_number_and_past_snapshot(self):
        before = deepcopy(self.sources)
        generator, client, result = self.generate()
        self.assertEqual(result["checks"][0]["verdict"], "근거와 상충")
        self.assertEqual(result["checks"][1]["verdict"], "확인됨")
        request = json.loads(client.chat.completions.create.call_args_list[1].kwargs["messages"][1]["content"])
        self.assertEqual([row["claim_id"] for row in request["items"]], ["c1", "c2"])
        self.assertEqual(request["items"][0]["user_proposition"], self.raw["checks"][0]["claim"])
        self.assertNotIn("proposed_verdict", request["items"][0])
        self.assertNotIn("verdict", request["items"][0])
        self.assertEqual(request["items"][0]["citations"][0]["quote"], "감독: 박하늘")
        self.assertEqual(result["sources"][0]["quote"], "감독: 박하늘")
        self.assertEqual(self.sources, before)
        threads = {}
        append_assistant_message(threads, self.movie.movie_id, result["content"], result["sources"])
        snapshot = deepcopy(get_thread(threads, self.movie.movie_id)[0])
        result["sources"][0]["quote"] = "나중의 별도 객체 변경"
        self.assertEqual(get_thread(threads, self.movie.movie_id)[0], snapshot)
        self.assertTrue(any(row["stage"] == "director_field_proposals" for row in generator.audit))

    def test_rejected_code_proposal_holds_only_director_and_keeps_background_reference(self):
        for relation, supported in (("supports", True), ("contradicts", False)):
            with self.subTest(relation=relation, supported=supported):
                generator, client, result = self.generate(relation, supported)
                self.assertEqual(result["checks"][0]["verdict"], "검토 보류")
                self.assertNotIn("[근거", result["checks"][0]["reason"])
                self.assertEqual(result["checks"][1]["verdict"], "확인됨")
                self.assertIn("[근거 2]", result["checks"][1]["reason"])
                self.assertNotIn("quote", result["sources"][0])
                self.assertEqual(result["sources"][1]["quote"], "달은 지구의 자연위성이다.")
                self.assertEqual(result["validation"]["semantic_check"], "item_review_partial")


if __name__ == "__main__":
    unittest.main()
