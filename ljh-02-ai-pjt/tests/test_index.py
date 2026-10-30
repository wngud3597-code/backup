"""Offline Chroma regression tests. Fake vectors never enter the application."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from movie_lab.data import build_index_text, load_movies
from movie_lab.index import IndexConfig, IndexConfigurationError, MetadataIndex


PROJECT = Path(__file__).resolve().parents[1]


class FakeEmbeddings:
    """Small deterministic vectors for storage tests, not semantic evaluation."""

    def __init__(self, model="offline-test-embedding", dimensions=3):
        self.model = model
        self.dimensions = dimensions
        self.document_inputs = []
        self.query_inputs = []

    def vector(self, text):
        folded = text.casefold()
        vector = [
            1.0 if "space" in folded else 0.1,
            1.0 if "ocean" in folded else 0.1,
            1.0 if "garden" in folded else 0.1,
        ]
        return (vector + [0.1] * self.dimensions)[: self.dimensions]

    def embed_documents(self, texts):
        self.document_inputs.extend(texts)
        return [self.vector(text) for text in texts]

    def embed_query(self, text):
        self.query_inputs.append(text)
        return self.vector(text)


class MetadataIndexTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(
            patch("socket.socket.connect", side_effect=AssertionError("Network disabled in index tests"))
        )
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "chroma"
        source = Path(self.temp.name) / "movies.json"
        source.write_text(json.dumps([
            {"movie_id": "101", "title": "Space Journey", "year": 2020,
             "director": ["Space Director"], "genres": ["SF"],
             "overview": "A space crew explores distant planets."},
            {"movie_id": "202", "title": "Ocean Life", "year": 2021,
             "director": [], "genres": ["Documentary"],
             "overview": "An ocean expedition studies marine life."},
            {"movie_id": "303", "title": "Garden Days", "year": None,
             "overview": "A family grows a garden."},
        ]), encoding="utf-8")
        self.movies = load_movies(source)
        self.config = IndexConfig(model_id="offline-test-embedding", dimension=3)
        self.embedder = FakeEmbeddings()

    def store(self, **kwargs):
        store = MetadataIndex(self.path, self.config, **kwargs)
        # unittest cleanups run in reverse order: close every shared client before
        # TemporaryDirectory removes Windows SQLite/HNSW files. Chroma's client
        # close() is idempotent and releases one reference to the shared system.
        self.addCleanup(store.close)
        return store

    def assert_complete(self, report, *, count=3, embedded=None):
        self.assertTrue(report["complete"], report)
        self.assertEqual(report["failed"], [], report)
        self.assertEqual(report["count"], count, report)
        if embedded is not None:
            self.assertEqual(report["embedded"], embedded, report)

    def test_one_movie_one_stable_id_document_and_retrievable_metadata(self):
        store = self.store()
        report = store.index_movies(self.movies, self.embedder, batch_size=2)
        self.assert_complete(report, embedded=3)
        self.assertEqual(report["total"], 3)
        self.assertEqual(report["added"], 3)
        self.assertEqual(report["updated"], 0)
        self.assertEqual(report["skipped"], 0)
        records = store.collection.get(include=["documents", "metadatas"])
        self.assertEqual(set(records["ids"]), {"meta:101", "meta:202", "meta:303"})
        by_id = dict(zip(records["ids"], zip(records["documents"], records["metadatas"])))
        for movie_id, movie in self.movies.items():
            document, metadata = by_id[f"meta:{movie_id}"]
            self.assertEqual(document, build_index_text(movie))
            self.assertEqual(metadata["movie_id"], movie_id)
            self.assertEqual(metadata["title"], movie.title)
        self.assertEqual(store.collection.count(), 3)
        verified = store.verify_movies(self.movies)
        self.assertTrue(verified["complete"], verified)
        self.assertEqual(verified["verified"], 3)
        self.assertEqual(verified["missing"], [])
        self.assertEqual(verified["mismatched"], [])

    def test_identical_rerun_does_not_embed_or_duplicate_even_in_another_order(self):
        store = self.store()
        store.index_movies(self.movies, self.embedder)
        self.embedder.document_inputs.clear()
        reordered = dict(reversed(list(self.movies.items())))
        report = store.index_movies(reordered, self.embedder, batch_size=1)
        self.assert_complete(report, embedded=0)
        self.assertEqual(report["skipped"], 3)
        self.assertEqual(report["added"], 0)
        self.assertEqual(report["updated"], 0)
        self.assertEqual(self.embedder.document_inputs, [])
        self.assertEqual(store.collection.count(), 3)

    def test_only_changed_document_is_reembedded_and_replaced(self):
        store = self.store()
        store.index_movies(self.movies, self.embedder)
        changed = dict(self.movies)
        changed["101"] = replace(changed["101"], overview="A new space expedition.")
        self.embedder.document_inputs.clear()
        report = store.index_movies(changed, self.embedder)
        self.assert_complete(report, embedded=1)
        self.assertEqual(report["added"], 0)
        self.assertEqual(report["updated"], 1)
        self.assertEqual(report["skipped"], 2)
        self.assertEqual(self.embedder.document_inputs, [build_index_text(changed["101"])])
        saved = store.collection.get(ids=["meta:101"], include=["documents"])
        self.assertEqual(saved["documents"], [build_index_text(changed["101"])])
        self.assertTrue(store.verify_movies(changed)["complete"])

    def test_new_movie_is_added_without_reembedding_existing_movies(self):
        store = self.store()
        store.index_movies(self.movies, self.embedder)
        extended = dict(self.movies)
        extended["404"] = replace(self.movies["101"], movie_id="404", title="Second Space Journey")
        self.embedder.document_inputs.clear()
        report = store.index_movies(extended, self.embedder)
        self.assert_complete(report, count=4, embedded=1)
        self.assertEqual(report["added"], 1)
        self.assertEqual(report["skipped"], 3)
        self.assertEqual(self.embedder.document_inputs, [build_index_text(extended["404"])])

    def test_saved_subset_after_interrupted_upsert_is_reused_on_resume(self):
        store = self.store()
        original = type(store.collection).upsert

        def save_first_then_interrupt(collection, *args, **kwargs):
            self.assertFalse(args, "The index should use named Chroma upsert arguments")
            first = {
                key: value[:1] if key in {"ids", "documents", "metadatas", "embeddings", "uris"} and value is not None else value
                for key, value in kwargs.items()
            }
            original(collection, **first)
            raise RuntimeError("Controlled write interruption from an offline test")

        with patch.object(type(store.collection), "upsert", new=save_first_then_interrupt):
            report = store.index_movies(self.movies, self.embedder, batch_size=3)
        self.assertFalse(report["complete"], report)
        self.assertEqual(store.collection.count(), 1)
        self.assertEqual(len(report["failed"]), 2)
        self.embedder.document_inputs.clear()
        resumed = store.index_movies(self.movies, self.embedder, batch_size=3)
        self.assert_complete(resumed, embedded=2)
        self.assertEqual(resumed["skipped"], 1)
        self.assertEqual(len(self.embedder.document_inputs), 2)
        self.assertNotIn(build_index_text(self.movies["101"]), self.embedder.document_inputs)
        self.assertTrue(store.verify_movies(self.movies)["complete"])

    def test_embedding_failure_stops_without_claiming_complete_and_can_resume(self):
        store = self.store()
        original = self.embedder.embed_documents
        calls = 0

        def fail_second_batch(texts):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise TimeoutError("Synthetic embedding timeout")
            return original(texts)

        with patch.object(self.embedder, "embed_documents", side_effect=fail_second_batch):
            report = store.index_movies(self.movies, self.embedder, batch_size=1)
        self.assertFalse(report["complete"], report)
        self.assertEqual(calls, 2, "Failure should stop the job instead of advancing to later batches")
        self.assertEqual(store.collection.count(), 1)
        self.assertEqual(len(report["failed"]), 2)
        self.embedder.document_inputs.clear()
        resumed = store.index_movies(self.movies, self.embedder, batch_size=1)
        self.assert_complete(resumed, embedded=2)
        self.assertEqual(resumed["skipped"], 1)

    def test_different_model_dimension_or_text_version_cannot_reuse_path(self):
        store = self.store()
        store.index_movies(self.movies, self.embedder)
        changed = (
            IndexConfig(model_id="different-model", dimension=3),
            IndexConfig(model_id=self.config.model_id, dimension=4),
            IndexConfig(model_id=self.config.model_id, dimension=3, text_version="different-text-v2"),
        )
        for config in changed:
            with self.subTest(config=config), self.assertRaises(IndexConfigurationError):
                MetadataIndex(self.path, config)
        self.assertEqual(store.collection.count(), 3)
        self.assertTrue(store.verify_movies(self.movies)["complete"])

    def test_an_explicit_new_path_can_use_a_different_embedding_configuration(self):
        self.store().index_movies(self.movies, self.embedder)
        other = MetadataIndex(
            Path(self.temp.name) / "separate-index", IndexConfig(model_id="different-model", dimension=4)
        )
        self.addCleanup(other.close)
        report = other.index_movies(self.movies, FakeEmbeddings(model="different-model", dimensions=4))
        self.assert_complete(report, embedded=3)
        self.assertEqual(self.store(create=False).collection.count(), 3)

    def test_query_uses_configured_embedder_and_returns_movie_identity(self):
        store = self.store()
        store.index_movies(self.movies, self.embedder)
        hits = store.search("space", self.embedder, k=2)
        self.assertEqual(self.embedder.query_inputs, ["space"])
        self.assertEqual(hits[0]["movie_id"], "101")
        self.assertEqual(hits[0]["title"], "Space Journey")
        self.assertEqual(hits[0]["year"], 2020)
        self.assertIn("Space Director", str(hits[0]["director"]))
        self.assertIsInstance(hits[0]["distance"], float)
        self.assertEqual(len(hits), 2)

    def test_installed_chroma_query_honors_id_subset_and_empty_scope(self):
        store = self.store()
        store.index_movies(self.movies, self.embedder)
        vector = self.embedder.vector("space")
        self.assertEqual(store.search_vector(vector, k=3)[0]["movie_id"], "101")
        with patch.object(type(store.collection), "query", autospec=True, side_effect=type(store.collection).query) as query:
            hits = store.search_vector(vector, k=3, allowed_movie_ids=["202"])
            self.assertEqual([hit["movie_id"] for hit in hits], ["202"])
            self.assertEqual(query.call_args.kwargs["ids"], ["meta:202"])
            self.assertEqual(query.call_args.kwargs["n_results"], 1)
        self.embedder.query_inputs.clear()
        self.assertEqual(store.search("space", self.embedder, allowed_movie_ids=[]), [])
        with self.assertRaises(IndexConfigurationError):
            store.search("space", self.embedder, allowed_movie_ids=["missing"])
        self.assertEqual(self.embedder.query_inputs, [])
        self.assertEqual(store.collection.count(), 3)

    def test_subset_error_and_wrong_document_identity_never_widen_search(self):
        store = self.store()
        store.index_movies(self.movies, self.embedder)
        with patch.object(type(store.collection), "query", side_effect=RuntimeError("offline restricted failure")) as query:
            with self.assertRaises(RuntimeError):
                store.search_vector(self.embedder.vector("space"), allowed_movie_ids=["202"])
            self.assertEqual(query.call_count, 1)
            self.assertEqual(query.call_args.kwargs["ids"], ["meta:202"])
        invalid = {"ids": [["meta:101"]], "metadatas": [[{"movie_id": "202", "title": "Ocean Life"}]], "distances": [[0.1]]}
        with patch.object(type(store.collection), "query", return_value=invalid):
            with self.assertRaises(IndexConfigurationError):
                store.search_vector(self.embedder.vector("space"), allowed_movie_ids=["202"])

    def test_wrong_embedder_model_is_rejected_before_document_or_query_call(self):
        store = self.store()
        wrong = FakeEmbeddings(model="different-model")
        with self.assertRaises(IndexConfigurationError):
            store.index_movies(self.movies, wrong)
        self.assertEqual(wrong.document_inputs, [])
        store.index_movies(self.movies, self.embedder)
        with self.assertRaises(IndexConfigurationError):
            store.search("space", wrong)
        self.assertEqual(wrong.query_inputs, [])
        self.assertEqual(store.collection.count(), 3)

    def test_wrong_vector_dimension_is_not_stored(self):
        store = self.store()
        malformed = FakeEmbeddings()
        # The configured dimensions still say three; inspect returned vectors too.
        with patch.object(malformed, "vector", return_value=[0.1, 0.2]):
            report = store.index_movies(self.movies, malformed)
            self.assertFalse(report["complete"], report)
        self.assertEqual(store.collection.count(), 0)

    def test_reopened_store_reuses_persisted_hashes_without_embedding(self):
        self.store().index_movies(self.movies, self.embedder)
        reopened = self.store(create=False)
        fresh = FakeEmbeddings()
        report = reopened.index_movies(self.movies, fresh)
        self.assert_complete(report, embedded=0)
        self.assertEqual(fresh.document_inputs, [])
        self.assertTrue(reopened.verify_movies(self.movies)["complete"])

    def test_a_separate_process_can_read_saved_collection_without_api_credentials(self):
        self.store().index_movies(self.movies, self.embedder)
        program = "\n".join([
            "import json, socket, sys",
            "def blocked(*args, **kwargs): raise RuntimeError('network disabled')",
            "socket.socket.connect = blocked",
            "from pathlib import Path",
            "from movie_lab.index import IndexConfig, MetadataIndex",
            "store = MetadataIndex(Path(sys.argv[1]), IndexConfig(model_id='offline-test-embedding', dimension=3), create=False)",
            "print(json.dumps({'count': store.collection.count(), 'ids': sorted(store.collection.get(include=[])['ids'])}))",
            "store.close()",
        ])
        environment = {key: value for key, value in os.environ.items() if key not in {"GMS_KEY", "OPENAI_API_KEY"}}
        result = subprocess.run(
            [sys.executable, "-X", "utf8", "-c", program, str(self.path)],
            cwd=PROJECT, env=environment, capture_output=True, text=True, encoding="utf-8", timeout=40,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        result_json = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual(result_json, {"count": 3, "ids": ["meta:101", "meta:202", "meta:303"]})

    def test_verification_distinguishes_missing_and_changed_movies(self):
        store = self.store()
        store.index_movies({"101": self.movies["101"]}, self.embedder)
        changed = dict(self.movies)
        changed["101"] = replace(changed["101"], title="Changed Space Journey")
        verified = store.verify_movies(changed)
        self.assertFalse(verified["complete"], verified)
        self.assertEqual(verified["verified"], 0)
        self.assertEqual(set(verified["missing"]), {"202", "303"})
        self.assertEqual(verified["mismatched"], ["101"])


if __name__ == "__main__":
    unittest.main()
