"""Offline service contracts: bounded retrieval and filter-aware success cache."""

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock, patch

from movie_lab.data import load_movies
from movie_lab.discovery import filter_catalog
from movie_lab.index import IndexConfig, IndexConfigurationError
from movie_lab.services import discovery_cache_key, search_catalog, valid_discovery_hits


class DiscoveryServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        all_movies = load_movies(Path(__file__).resolve().parents[1] / "data/movies.json")
        cls.movies = {mid: all_movies[mid] for mid in ("157336", "27205", "496243")}
        cls.config = IndexConfig("offline-embedding", 3)

    def hit(self, mid="157336"):
        return {"movie_id": mid, "document_id": f"meta:{mid}", "title": self.movies[mid].title,
                "distance": 0.1}

    def test_title_unsupported_empty_and_missing_data_skip_store_and_embedding(self):
        queries = ("Interstellar", "평점 -1 이상 영화", "평점 10 이상 영화", "2010년 이후가 아닌 영화", " ")
        with patch("movie_lab.services.read_index_config") as config, patch("movie_lab.services.create_gms_embeddings") as client:
            for query in queries:
                result = search_catalog(query, self.movies)
                self.assertEqual(result["semantic_hits"], [])
            missing = replace(self.movies["157336"], runtime=None)
            result = search_catalog("120분 이하 영화", {missing.movie_id: missing})
            self.assertEqual(result["discovery_state"], "unverifiable_data")
            config.assert_not_called()
            client.assert_not_called()

    def test_scope_is_passed_and_identical_success_reuses_filter_cache(self):
        store = MagicMock()
        store.verify_movies.return_value = {"missing": [], "mismatched": []}
        store.search.return_value = [self.hit()]
        with TemporaryDirectory() as temp, patch("movie_lab.services.resolve_document_cache_path", return_value=Path(temp)), \
                patch("movie_lab.services.read_index_config", return_value=self.config), \
                patch("movie_lab.services.MetadataIndex", return_value=store) as index, \
                patch("movie_lab.services.create_gms_embeddings") as client:
            first = search_catalog("2010년 이후 SF 영화", self.movies)
            second = search_catalog("2010년 이후 SF 영화", dict(reversed(list(self.movies.items()))))
            self.assertFalse(first["semantic_cache_hit"])
            self.assertTrue(second["semantic_cache_hit"])
            self.assertEqual(first["semantic_hits"], second["semantic_hits"])
            self.assertEqual(set(store.search.call_args.kwargs["allowed_movie_ids"]), {"157336", "27205"})
            self.assertEqual(store.search.call_args.kwargs["k"], 3)
            self.assertEqual(set(store.verify_movies.call_args.args[0]), {"157336", "27205"})
            self.assertEqual(index.call_count, 1)
            self.assertEqual(client.call_count, 1)
            self.assertEqual(store.search.call_count, 1)

    def test_cache_key_covers_all_movie_fields_scope_boundaries_and_settings(self):
        query = "2010년 이후 SF 영화"
        base = discovery_cache_key(query, self.movies, self.config, filter_catalog(query, self.movies))
        for field, value in (("runtime", 170), ("vote_average", 8.4), ("genres", ("SF",)),
                             ("cast", ("Changed Cast",)), ("production_countries", ("South Korea",)),
                             ("overview", "Changed plot")):
            changed = dict(self.movies)
            changed["157336"] = replace(changed["157336"], **{field: value})
            with self.subTest(field=field):
                self.assertNotEqual(base, discovery_cache_key(query, changed, self.config, filter_catalog(query, changed)))
        other = "2010년 초과 SF 영화"
        self.assertNotEqual(base, discovery_cache_key(other, self.movies, self.config, filter_catalog(other, self.movies)))
        self.assertNotEqual(base, discovery_cache_key(query, self.movies, IndexConfig("different-model", 4), filter_catalog(query, self.movies)))
        reversed_movies = dict(reversed(list(self.movies.items())))
        self.assertEqual(base, discovery_cache_key(query, reversed_movies, self.config, filter_catalog(query, reversed_movies)))

    def test_invalid_cached_identity_is_not_reused_and_bad_response_is_not_saved(self):
        cache = MagicMock()
        cache.get.return_value = [self.hit("496243")]
        store = MagicMock()
        store.verify_movies.return_value = {"missing": [], "mismatched": []}
        store.search.return_value = [self.hit()]
        with patch("movie_lab.services.read_index_config", return_value=self.config), \
                patch("movie_lab.services.SuccessCache", return_value=cache), \
                patch("movie_lab.services.MetadataIndex", return_value=store), \
                patch("movie_lab.services.create_gms_embeddings"):
            result = search_catalog("2010년 이후 SF 영화", self.movies)
            self.assertTrue(result["semantic_cache_rejected"])
            self.assertFalse(result["semantic_cache_hit"])
            self.assertEqual(store.search.call_count, 1)
            cache.put.assert_called_once()
            cache.reset_mock()
            cache.get.return_value = None
            store.search.return_value = [{**self.hit(), "document_id": "meta:496243"}]
            with self.assertRaises(IndexConfigurationError):
                search_catalog("2010년 이후 SF 영화", self.movies)
            cache.put.assert_not_called()
        self.assertFalse(valid_discovery_hits([self.hit(), self.hit()], self.movies, self.movies))

    def test_storage_mismatch_or_restricted_failure_cannot_trigger_unfiltered_retry(self):
        cache = MagicMock()
        cache.get.return_value = None
        store = MagicMock()
        store.verify_movies.return_value = {"missing": ["157336"], "mismatched": []}
        with patch("movie_lab.services.read_index_config", return_value=self.config), \
                patch("movie_lab.services.SuccessCache", return_value=cache), \
                patch("movie_lab.services.MetadataIndex", return_value=store), \
                patch("movie_lab.services.create_gms_embeddings") as client:
            with self.assertRaises(IndexConfigurationError):
                search_catalog("2010년 이후 SF 영화", self.movies)
            client.assert_not_called()
            store.search.assert_not_called()
            store.verify_movies.return_value = {"missing": [], "mismatched": []}
            store.search.side_effect = TimeoutError("Offline restricted search timeout")
            with self.assertRaises(TimeoutError):
                search_catalog("2010년 이후 SF 영화", self.movies)
            self.assertEqual(store.search.call_count, 1)
            self.assertIn("allowed_movie_ids", store.search.call_args.kwargs)
            cache.put.assert_not_called()


if __name__ == "__main__":
    unittest.main()
