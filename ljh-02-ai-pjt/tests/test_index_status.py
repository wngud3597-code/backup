"""Local index status and UI notices, without GMS calls."""

import json
import tempfile
import unittest
from contextlib import ExitStack
from dataclasses import asdict, replace
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from movie_lab.data import load_movies
from movie_lab.index import IndexConfig, MetadataIndex, inspect_index_status
from tests.test_index import FakeEmbeddings


PROJECT = Path(__file__).resolve().parents[1]


class IndexStatusTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch("socket.socket.connect", side_effect=AssertionError("offline status test")))
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "chroma"
        actual = load_movies(PROJECT / "data/movies.json")
        self.movies = {mid: actual[mid] for mid in ("753091", "17431")}
        self.config = IndexConfig("offline-test-embedding", 3)

    def populate(self, movies):
        store = MetadataIndex(self.path, self.config)
        store.index_movies(movies, FakeEmbeddings())
        store.close()

    def test_absent_empty_partial_and_ready_are_distinct(self):
        self.assertEqual(inspect_index_status(self.path, self.movies)["state"], "absent")
        self.populate({})
        status = inspect_index_status(self.path, self.movies)
        self.assertEqual(status["state"], "partial")
        self.assertEqual(status["count"], 0)
        self.populate({"753091": self.movies["753091"]})
        self.assertEqual(inspect_index_status(self.path, self.movies)["verified"], 1)
        self.populate(self.movies)
        status = inspect_index_status(self.path, self.movies)
        self.assertEqual(status["state"], "ready")
        self.assertEqual(status["count"], 2)

    def test_corrupt_manifest_or_missing_database_is_unavailable(self):
        self.path.mkdir()
        (self.path / "metadata_index.json").write_text("{bad", encoding="utf-8")
        self.assertEqual(inspect_index_status(self.path, self.movies)["state"], "unavailable")
        # A valid-looking manifest alone must not initialize a replacement DB.
        document = {"schema_version": 1, "collection": self.config.collection_name,
                    "config": {"model_id": self.config.model_id, "dimension": 3, "text_version": self.config.text_version}}
        (self.path / "metadata_index.json").write_text(json.dumps(document), encoding="utf-8")
        self.assertEqual(inspect_index_status(self.path, self.movies)["state"], "unavailable")
        self.assertFalse((self.path / "chroma.sqlite3").exists())

    def test_data_change_and_text_version_change_do_not_claim_ready(self):
        self.populate(self.movies)
        changed = dict(self.movies)
        changed["753091"] = replace(changed["753091"], title="변경된 제목")
        self.assertEqual(inspect_index_status(self.path, changed)["state"], "partial")
        with patch("movie_lab.index.METADATA_TEXT_VERSION", "new-version"):
            self.assertEqual(inspect_index_status(self.path, self.movies)["state"], "incompatible")

    def test_ui_displays_actual_count_absence_and_safe_connection_failure(self):
        with patch("movie_lab.config.resolve_index_path", return_value=self.path):
            app = AppTest.from_file(str(PROJECT / "app.py")).run()
            self.assertFalse(app.exception)
            self.assertTrue(any("색인이 없습니다" in item.value for item in app.caption))
            self.path.mkdir()
            (self.path / "metadata_index.json").write_text("{bad", encoding="utf-8")
            app.run()
            self.assertFalse(app.exception)
            self.assertTrue(any("저장소 연결에 실패" in item.value for item in app.warning))
        with patch("movie_lab.index.read_index_config", side_effect=RuntimeError("private-error-marker")):
            self.assertEqual(inspect_index_status(self.path, self.movies), {"state": "unavailable", "count": None})
        self.path = self.path / "ready-store"
        self.populate(self.movies)
        catalog = self.path.parent / "two-movies.json"
        catalog.write_text(json.dumps([asdict(movie) for movie in self.movies.values()]), encoding="utf-8")
        with patch("movie_lab.config.resolve_index_path", return_value=self.path), patch("movie_lab.config.resolve_movies_path", return_value=catalog):
            app = AppTest.from_file(str(PROJECT / "app.py")).run()
            self.assertFalse(app.exception)
            self.assertTrue(any("메타데이터 색인 2건" in item.value for item in app.caption))


if __name__ == "__main__":
    unittest.main()
