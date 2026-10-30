import unittest
from pathlib import Path
from unittest.mock import patch

from movie_lab.config import GMS_BASE_URL, GMS_KEY_ENV, PROJECT_ROOT, resolve_gms_chat_model, resolve_gms_embedding_model, resolve_index_path, resolve_movies_path


class ConfigTests(unittest.TestCase):
    def test_embedding_model_and_runtime_directory_are_independent_settings(self):
        with patch("movie_lab.config.os.environ.get", return_value=None):
            self.assertEqual(resolve_gms_embedding_model(), "text-embedding-3-small")
            self.assertEqual(resolve_index_path(), PROJECT_ROOT / "data/runtime/chroma")
        with patch("movie_lab.config.os.environ.get", return_value="alternate-embedding"):
            self.assertEqual(resolve_gms_embedding_model(), "alternate-embedding")
        self.assertEqual(resolve_index_path("data/runtime/other"), PROJECT_ROOT / "data/runtime/other")

    def test_gms_model_is_configurable_without_loading_key(self):
        with patch("movie_lab.config.os.environ.get", return_value=None) as getenv:
            self.assertEqual(resolve_gms_chat_model(), "gpt-4o-mini")
            getenv.assert_called_once_with("GMS_CHAT_MODEL")
        with patch("movie_lab.config.os.environ.get", return_value=" another-model "):
            self.assertEqual(resolve_gms_chat_model(), "another-model")
            self.assertEqual(resolve_gms_chat_model("gpt-4o-mini"), "gpt-4o-mini")

    def test_default_and_relative_paths_use_project_root(self):
        with patch("movie_lab.config.os.environ.get", return_value=None) as getenv:
            self.assertEqual(resolve_movies_path(), PROJECT_ROOT / "data/movies.json")
            getenv.assert_called_once_with("MOVIES_DATA_PATH")
        self.assertEqual(resolve_movies_path("other/movies.json"), PROJECT_ROOT / "other/movies.json")

    def test_configurable_data_path_does_not_read_credentials(self):
        with patch("movie_lab.config.os.environ.get", return_value="input/catalog.json") as getenv:
            self.assertEqual(resolve_movies_path(), PROJECT_ROOT / "input/catalog.json")
            getenv.assert_called_once_with("MOVIES_DATA_PATH")
        absolute = Path(__file__).resolve()
        with patch("movie_lab.config.os.environ.get") as getenv:
            self.assertEqual(resolve_movies_path(absolute), absolute)
            getenv.assert_not_called()
        self.assertEqual(GMS_KEY_ENV, "GMS_KEY")
        self.assertEqual(GMS_BASE_URL, "https://gms.ssafy.io/gmsapi/api.openai.com/v1/")


if __name__ == "__main__":
    unittest.main()
