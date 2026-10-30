"""Offline tests; all generated answer examples live in test fixtures only."""

import json
from pathlib import Path
import unittest
from uuid import UUID

from movie_lab.evidence import cited_sources
from movie_lab.state import (
    append_assistant_message,
    append_user_message,
    build_payload,
    clear_thread,
    get_thread,
)


FIXTURE = Path(__file__).parent / "fixtures" / "conversations.json"


class MovieStateTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.a = self.data["movie_a"]
        self.b = self.data["movie_b"]
        self.threads = {}

    def add_turn(self, fixture):
        append_user_message(
            self.threads, fixture["movie_id"], fixture["question"]
        )
        return append_assistant_message(
            self.threads,
            fixture["movie_id"],
            fixture["answer"],
            fixture["sources"],
        )

    def test_a_b_a_restores_selected_movie_history_and_sources(self):
        answer_a = self.add_turn(self.a)
        thread_a = get_thread(self.threads, self.a["movie_id"])
        self.add_turn(self.b)

        restored = get_thread(self.threads, self.a["movie_id"])
        self.assertIs(restored, thread_a)
        self.assertEqual(restored[-1], answer_a)
        self.assertEqual(restored[-1]["sources"], self.a["sources"])
        self.assertNotEqual(restored[-1]["sources"], self.b["sources"])

    def test_each_answer_has_its_own_evidence_one_and_unique_id(self):
        first = self.add_turn(self.a)
        append_user_message(
            self.threads, self.a["movie_id"], self.a["next_question"]
        )
        second = append_assistant_message(
            self.threads,
            self.a["movie_id"],
            self.a["next_answer"],
            self.a["next_sources"],
        )

        self.assertNotEqual(first["answer_id"], second["answer_id"])
        self.assertEqual(str(UUID(first["answer_id"])), first["answer_id"])
        self.assertEqual(set(first), {"role", "answer_id", "content", "sources"})
        self.assertEqual(
            cited_sources(first["content"], first["sources"])[0][1]["url"],
            self.a["sources"][0]["url"],
        )
        self.assertEqual(
            cited_sources(second["content"], second["sources"])[0][1]["url"],
            self.a["next_sources"][0]["url"],
        )

    def test_source_snapshot_survives_input_mutation_and_new_answer(self):
        first = self.add_turn(self.a)
        expected_title = first["sources"][0]["title"]
        expected_origin = first["sources"][0]["details"]["origin"]
        self.a["sources"][0]["title"] = "mutated outside state"
        self.a["sources"][0]["details"]["origin"] = "mutated nested field"
        self.a["sources"].clear()
        self.add_turn(self.b)

        self.assertEqual(first["sources"][0]["title"], expected_title)
        self.assertEqual(first["sources"][0]["details"]["origin"], expected_origin)

    def test_rerun_style_reads_do_not_change_history_or_sources(self):
        self.add_turn(self.a)
        before = json.dumps(self.threads, ensure_ascii=False, sort_keys=True)
        for _ in range(3):
            for message in get_thread(self.threads, self.a["movie_id"]):
                if message["role"] == "assistant":
                    cited_sources(message["content"], message["sources"])
            build_payload(self.threads, self.a["movie_id"], "테스트 시스템")
        self.assertEqual(
            json.dumps(self.threads, ensure_ascii=False, sort_keys=True), before
        )

    def test_clear_removes_only_the_selected_movie(self):
        self.add_turn(self.a)
        self.add_turn(self.b)
        before_b = list(get_thread(self.threads, self.b["movie_id"]))
        clear_thread(self.threads, self.a["movie_id"])
        self.assertEqual(get_thread(self.threads, self.a["movie_id"]), [])
        self.assertEqual(get_thread(self.threads, self.b["movie_id"]), before_b)

    def test_payload_copies_only_role_content_and_latest_question_once(self):
        self.add_turn(self.a)
        self.add_turn(self.b)
        append_user_message(
            self.threads, self.a["movie_id"], self.a["next_question"]
        )
        payload = build_payload(
            self.threads, self.a["movie_id"], "테스트 시스템"
        )
        self.assertEqual(payload[0], {"role": "system", "content": "테스트 시스템"})
        self.assertEqual(len(payload), 4)
        self.assertEqual(
            sum(m["content"] == self.a["next_question"] for m in payload), 1
        )
        self.assertNotIn(self.b["question"], [m["content"] for m in payload])
        self.assertTrue(all(set(m) == {"role", "content"} for m in payload))
        payload[1]["content"] = "changed payload"
        self.assertEqual(
            get_thread(self.threads, self.a["movie_id"])[0]["content"],
            self.a["question"],
        )

    def test_ids_are_normalized_and_invalid_messages_rejected(self):
        append_user_message(self.threads, 157336, "테스트 입력")
        self.assertIn("157336", self.threads)
        self.assertIs(get_thread(self.threads, " 157336 "), self.threads["157336"])
        with self.assertRaises(ValueError):
            get_thread(self.threads, " ")
        with self.assertRaises(ValueError):
            append_user_message(self.threads, "other", " ")
        with self.assertRaises(TypeError):
            append_assistant_message(self.threads, "other", "answer", [None])
        self.assertNotIn("other", self.threads)


if __name__ == "__main__":
    unittest.main()
