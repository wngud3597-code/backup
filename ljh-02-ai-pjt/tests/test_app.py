"""Offline UI tests. Synthetic answers are injected only by this test module."""

import json
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch, Mock

from streamlit.testing.v1 import AppTest

from movie_lab.state import append_assistant_message, append_user_message


PROJECT = Path(__file__).resolve().parents[1]
MOVIE_A = "753091"  # 더 문 (2023)
MOVIE_B = "17431"  # 더 문 (2009)


class MovieAppTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch("socket.socket.connect", side_effect=AssertionError("Network disabled in offline UI tests")))
        # These original preservation tests isolate the new generation boundary.
        offline = Mock()
        offline.answer.return_value = {"content": "", "error": {"category": "격리된 테스트 연결 실패"}}
        self.stack.enter_context(patch("movie_lab.rag.create_rag_service", return_value=offline))
        self.resolve_path = self.stack.enter_context(patch("movie_lab.config.resolve_movies_path", return_value=PROJECT / "data/movies.json"))
        self.fixture = json.loads((PROJECT / "tests/fixtures/conversations.json").read_text(encoding="utf-8"))

    def app(self):
        app = AppTest.from_file(str(PROJECT / "app.py"), default_timeout=10).run()
        self.assertFalse(app.exception)
        return app

    def test_real_catalog_and_id_selection_survive_rerun(self):
        app = self.app()
        selector = app.selectbox(key="selected_movie_id")
        self.assertEqual(len(selector.options), 964)
        self.assertIsNone(selector.value)
        self.assertEqual(len(app.chat_message), 0)
        app.selectbox(key="selected_movie_id").select(MOVIE_A).run()
        self.assertFalse(app.exception)
        self.assertIn("2023", app.subheader[0].value)
        self.assertTrue(any("**감독** 김용화" in row.value for row in app.markdown))
        self.assertEqual(app.selectbox(key="selected_movie_id").value, MOVIE_A)
        app.run()
        self.assertEqual(app.selectbox(key="selected_movie_id").value, MOVIE_A)
        self.assertFalse(app.exception)

    def test_questions_restore_after_movie_switch_and_do_not_duplicate_on_rerun(self):
        app = self.app()
        for movie_id, question in ((MOVIE_A, "A 질문"), (MOVIE_B, "B 질문")):
            app.selectbox(key="selected_movie_id").select(movie_id).run()
            app.chat_input(key="question").set_value(question).run()
            self.assertFalse(app.exception)
        app.selectbox(key="selected_movie_id").select(MOVIE_A).run()
        self.assertEqual([message.markdown[0].value for message in app.chat_message], ["A 질문"])
        app.run()
        self.assertEqual(len(app.session_state["threads_by_movie"][MOVIE_A]), 1)
        self.assertEqual(len(app.session_state["threads_by_movie"][MOVIE_B]), 1)
        self.assertEqual(len(app.chat_message), 1)
        self.assertFalse(app.exception)

    def test_answer_local_citations_restore_and_ignore_uncited_sources(self):
        app = self.app()
        threads = {}
        a, b = self.fixture["movie_a"], self.fixture["movie_b"]
        first_sources = a["sources"] + [{"title": "인용하지 않은 테스트 출처", "url": "https://example.invalid/unused"}]
        first_sources[0]["quote"] = "격리된 테스트 근거 구절"
        append_assistant_message(threads, MOVIE_A, a["answer"], first_sources)
        append_assistant_message(threads, MOVIE_A, a["next_answer"], a["next_sources"])
        append_assistant_message(threads, MOVIE_B, b["answer"], b["sources"])
        app.session_state["threads_by_movie"] = threads
        app.selectbox(key="selected_movie_id").select(MOVIE_A).run()

        def assert_a_sources():
            rendered = "\n".join(markdown.value for markdown in app.markdown)
            self.assertIn(a["sources"][0]["title"], rendered)
            self.assertIn(a["next_sources"][0]["title"], rendered)
            self.assertIn(a["sources"][0]["url"], rendered)
            self.assertIn("격리된 테스트 근거 구절", rendered)
            self.assertNotIn(b["sources"][0]["title"], rendered)
            self.assertNotIn("인용하지 않은 테스트 출처", rendered)
            self.assertEqual(len([m for m in app.chat_message if m.name == "assistant"]), 2)
            self.assertFalse(app.exception)

        assert_a_sources()
        app.selectbox(key="selected_movie_id").select(MOVIE_B).run()
        self.assertIn(b["sources"][0]["title"], "\n".join(m.value for m in app.markdown))
        app.selectbox(key="selected_movie_id").select(MOVIE_A).run()
        app.chat_input(key="question").set_value(a["next_question"]).run()
        app.run()
        assert_a_sources()
        self.assertEqual(len(app.session_state["threads_by_movie"][MOVIE_A]), 3)

    def test_clear_callback_only_clears_selected_movie(self):
        app = self.app()
        threads = {}
        append_user_message(threads, MOVIE_A, "A 질문")
        append_user_message(threads, MOVIE_B, "B 질문")
        app.session_state["threads_by_movie"] = threads
        app.selectbox(key="selected_movie_id").select(MOVIE_A).run()
        app.button(key="clear_current_thread").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state["threads_by_movie"][MOVIE_A], [])
        self.assertEqual(len(app.session_state["threads_by_movie"][MOVIE_B]), 1)

    def test_missing_data_and_bad_json_show_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "movies.json"
            self.resolve_path.return_value = path
            app = self.app()
            self.assertEqual(len(app.error), 1)
            self.assertIn("MOVIES_DATA_PATH", app.error[0].value)
            path.write_text("{invalid", encoding="utf-8")
            app = self.app()
            self.assertEqual(len(app.error), 1)
            self.assertIn("JSON", app.error[0].value)
            self.assertEqual(len(app.selectbox), 0)

    def test_minimal_record_displays_missing_fields_without_error(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "movies.json"
            path.write_text('[{"movie_id": 7, "director": []}]', encoding="utf-8")
            self.resolve_path.return_value = path
            app = self.app()
            app.selectbox(key="selected_movie_id").select("7").run()
            self.assertFalse(app.exception)
            self.assertIn("제목 미상", app.subheader[0].value)
            self.assertTrue(any("**감독** 감독 정보 없음" in row.value for row in app.markdown))
            self.assertTrue(any("줄거리 정보가 없습니다" in m.value for m in app.markdown))


if __name__ == "__main__":
    unittest.main()
