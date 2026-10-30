"""Offline checks of input-only examples and answer-local source snapshots.

All answers below are isolated synthetic fixtures. No client, search request or
Chroma store is opened. AppTest renders expander children on the server; it
cannot prove that a real browser opened a collapsed expander.
"""

from contextlib import ExitStack
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from movie_lab.data import load_movies
from movie_lab.display import suggested_questions
from movie_lab.state import append_assistant_message, append_user_message


PROJECT = Path(__file__).resolve().parents[1]
MOVIE_A = "157336"  # Interstellar; real metadata, synthetic conversations only.
MOVIE_B = "753091"  # The Moon (2023).


class MovieUIFlowTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.movies = load_movies(PROJECT / "data/movies.json")
        self.boundaries = {}
        for name in (
            "socket.socket.connect",
            "movie_lab.services.search_catalog",
            "movie_lab.rag.create_rag_service",
            "movie_lab.document_pipeline.create_document_pipeline",
            "movie_lab.kobis.create_kobis_service",
            "movie_lab.embeddings.create_gms_embeddings",
        ):
            self.boundaries[name] = self.stack.enter_context(patch(
                name, side_effect=AssertionError("Offline UI boundary must not be called")
            ))
        self.stack.enter_context(patch(
            "movie_lab.config.resolve_movies_path", return_value=PROJECT / "data/movies.json"
        ))
        self.stack.enter_context(patch(
            "movie_lab.index.inspect_index_status",
            return_value={"state": "ready", "count": len(self.movies)},
        ))

    def app(self):
        app = AppTest.from_file(str(PROJECT / "app.py"), default_timeout=10).run()
        self.assertFalse(app.exception)
        return app

    def assert_no_requests(self):
        # An app may catch an exception, so absence of app.exception alone is
        # insufficient: assert that each request boundary was never reached.
        for name, boundary in self.boundaries.items():
            with self.subTest(boundary=name):
                self.assertEqual(boundary.call_count, 0)

    @staticmethod
    def rendered(app):
        return "\n".join(row.value for row in app.markdown)

    def test_search_examples_only_fill_the_form_without_search_or_messages(self):
        app = self.app()
        threads_before = deepcopy(app.session_state["threads_by_movie"])
        for index in range(3):
            button = app.button(key=f"discovery_example_{index}")
            example = button.label
            button.click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.text_input(key="discovery_query").value, example)
            self.assertEqual(app.session_state["threads_by_movie"], threads_before)
            self.assertEqual(len(app.chat_message), 0)
            self.assertIsNone(app.session_state.filtered_state.get("discovery_report"))
            self.assert_no_requests()
        app.run()
        self.assertEqual(app.session_state["threads_by_movie"], threads_before)
        self.assert_no_requests()

    def test_question_suggestions_prefill_without_submission_and_switch_clears_draft(self):
        app = self.app()
        app.selectbox(key="selected_movie_id").select(MOVIE_A).run()
        threads_before = deepcopy(app.session_state["threads_by_movie"])
        expected = suggested_questions(self.movies[MOVIE_A])
        self.assertTrue(expected)
        for index, text in enumerate(expected):
            app.button(key=f"suggest_question_{MOVIE_A}_{index}").click().run()
            self.assertFalse(app.exception)
            # The actual chat-input delta instructs a browser to prefill. Using
            # AppTest.ChatInput.set_value here would simulate Send instead.
            chat = app.chat_input(key="question")
            self.assertTrue(chat.proto.set_value)
            self.assertEqual(chat.proto.value, text)
            # AppTest.value exposes the testing delta's prefill string rather
            # than chat_input's return. The actual widget state is reset to
            # None, and unchanged messages/client counts prove no submission.
            self.assertIsNone(app.session_state["question"])
            self.assertEqual(app.session_state["threads_by_movie"], threads_before)
            self.assertEqual(len(app.chat_message), 0)
            self.assert_no_requests()
        app.selectbox(key="selected_movie_id").select(MOVIE_B).run()
        self.assertFalse(app.exception)
        self.assertEqual(app.chat_input(key="question").proto.value, "")
        self.assertEqual(app.session_state["threads_by_movie"][MOVIE_A], [])
        self.assertEqual(app.session_state["threads_by_movie"][MOVIE_B], [])
        app.run()
        self.assertEqual(len(app.chat_message), 0)
        self.assert_no_requests()

    def test_movie_switch_rerun_and_source_render_keep_each_original_snapshot(self):
        app = self.app()
        threads = {}
        legacy = {"title": "격리 A 첫 답변 출처", "url": "https://example.invalid/a-first",
                  "quote": "격리 A의 과거 단일 원문 구절"}
        multiple = {"title": "격리 A 둘째 답변 출처", "url": "https://example.invalid/a-second",
                    "movie_id": MOVIE_A, "document_id": f"meta:{MOVIE_A}",
                    "source_kind": "metadata", "scope": "movie_metadata",
                    "quote": "제목: 격리 A\n감독: 격리 감독\n상영 시간(분): 169",
                    "quotes": ["제목: 격리 A\n감독: 격리 감독\n상영 시간(분): 169",
                               "원문에서 따로 보존한 둘째 구절"]}
        other = {"title": "격리 B 답변 출처", "url": "https://example.invalid/b",
                 "source_kind": "snapshot", "scope": "film_description",
                 "quote": "격리 B에서만 보이는 원문 구절"}
        append_user_message(threads, MOVIE_A, "격리 A 첫 질문")
        first = append_assistant_message(threads, MOVIE_A, "격리 A 첫 답변 [근거 1]", [legacy])
        append_user_message(threads, MOVIE_A, "격리 A 둘째 질문")
        second = append_assistant_message(threads, MOVIE_A, "감독 정보를 확인한 격리 A 답변 [근거 1]", [multiple])
        append_user_message(threads, MOVIE_B, "격리 B 질문")
        append_assistant_message(threads, MOVIE_B, "격리 B 답변 [근거 1]", [other])
        self.assertNotEqual(first["answer_id"], second["answer_id"])
        expected = deepcopy(threads)
        app.session_state["threads_by_movie"] = threads

        def assert_a():
            self.assertFalse(app.exception)
            rendered = self.rendered(app)
            for source in (legacy, multiple):
                self.assertIn(f"**[근거 1]** {source['title']}", rendered)
                self.assertIn(source["url"], rendered)
                self.assertIn(source["quote"], rendered)
            self.assertIn(multiple["quotes"][1], rendered)
            self.assertNotIn(other["title"], rendered)
            self.assertEqual(sum(row.label == "답변에 사용한 근거 1건" for row in app.expander), 2)
            self.assertTrue(any(row.label == "전체 원래 인용 · 2개 구절" for row in app.expander))
            self.assertEqual(app.session_state["threads_by_movie"], expected)

        app.selectbox(key="selected_movie_id").select(MOVIE_A).run()
        assert_a()
        app.selectbox(key="selected_movie_id").select(MOVIE_B).run()
        rendered = self.rendered(app)
        self.assertIn(f"**[근거 1]** {other['title']}", rendered)
        self.assertIn(other["quote"], rendered)
        self.assertNotIn(legacy["title"], rendered)
        app.selectbox(key="selected_movie_id").select(MOVIE_A).run()
        assert_a()
        app.run()  # Includes re-rendering collapsed source/detail containers.
        assert_a()
        app.radio(key="answer_mode").set_value("작품·현실 배경 확인").run()
        assert_a()
        self.assert_no_requests()


if __name__ == "__main__":
    unittest.main()
