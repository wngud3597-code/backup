"""UI connections use isolated boundary objects; no real API in these tests."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

from streamlit.testing.v1 import AppTest

from movie_lab.config import resolve_movies_path
from movie_lab.data import load_movies
from movie_lab.discovery import discover_movies
from movie_lab.state import append_user_message


PROJECT = Path(__file__).resolve().parents[1]


class Stage3AppTests(unittest.TestCase):
    def test_discovery_select_restores_movie_thread_without_api(self):
        movies = load_movies(resolve_movies_path())
        result = discover_movies("2023년 더 문", movies)
        with patch("movie_lab.services.search_catalog", return_value=result), patch("socket.socket.connect", side_effect=AssertionError("offline UI")):
            app = AppTest.from_file(str(PROJECT / "app.py")).run()
            threads = {}
            append_user_message(threads, "753091", "복원할 영화 질문")
            app.session_state["threads_by_movie"] = threads
            app.text_input(key="discovery_query").set_value("2023년 더 문")
            app.button(key="run_discovery").click().run()
            app.button(key="choose_discovery_753091").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.selectbox(key="selected_movie_id").value, "753091")
            self.assertEqual(app.text_area(key="document_question").value, "복원할 영화 질문")
            self.assertEqual(app.chat_message[0].markdown[0].value, "복원할 영화 질문")

    def test_prepare_is_explicit_stores_question_once_and_does_not_fake_answer(self):
        report = {"complete": True, "documents": [], "queries": ["테스트 전용 검색어"],
                  "index": {"chunk_count": 2}, "cache_hit": True}
        fake = Mock()
        fake.prepare.return_value = report
        with patch("movie_lab.document_pipeline.create_document_pipeline", return_value=fake) as factory, patch("socket.socket.connect", side_effect=AssertionError("offline UI")):
            app = AppTest.from_file(str(PROJECT / "app.py")).run()
            app.selectbox(key="selected_movie_id").select("157336").run()
            factory.assert_not_called()
            app.text_area(key="document_question").set_value("테스트 질문")
            app.button(key="prepare_documents").click().run()
            self.assertFalse(app.exception)
            fake.prepare.assert_called_once()
            self.assertEqual(len(app.session_state["threads_by_movie"]["157336"]), 1)
            self.assertTrue(all(message.name == "user" for message in app.chat_message))
            app.run()
            fake.prepare.assert_called_once()
            self.assertTrue(any("확인된 청크 2개" in caption.value for caption in app.caption))


if __name__ == "__main__":
    unittest.main()
