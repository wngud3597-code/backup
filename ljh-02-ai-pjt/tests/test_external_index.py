"""Offline external-document storage regressions; synthetic text stays in tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from movie_lab.external_index import ChunkConfig, ExternalIndex, chunk_document
from movie_lab.index import IndexConfigurationError


class FakeEmbeddings:
    model = "offline-external"
    dimensions = 3

    def __init__(self):
        self.inputs = []
        self.queries = []

    def embed_documents(self, texts):
        self.inputs.extend(texts)
        return [[1.0 if "space" in text else 0.1, 1.0 if "ocean" in text else 0.1, 0.1] for text in texts]

    def embed_query(self, text):
        self.queries.append(text)
        return [1.0 if "space" in text else 0.1, 1.0 if "ocean" in text else 0.1, 0.1]


def document(text=None, **changes):
    return {"title": "Example", "url": "https://example.org/wiki/Example",
            "text": text if text is not None else "A space crew travels. They encounter a distant planet.\n\nAn ocean is explored.",
            "source_kind": "snapshot", "collected_at": "2026-09-01T00:00:00Z", **changes}


class ExternalIndexTests(unittest.TestCase):
    def setUp(self):
        self.blocked = patch("socket.socket.connect", side_effect=AssertionError("Offline test"))
        self.blocked.start()
        self.addCleanup(self.blocked.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "external"
        self.embedder = FakeEmbeddings()

    def store(self, config=None):
        value = ExternalIndex(self.path, self.embedder.model, 3, config)
        self.addCleanup(value.close)
        return value

    def test_chunks_keep_boundaries_provenance_and_collision_free_stable_ids(self):
        source = document("First sentence ends here. Second sentence is also meaningful.\n\nA new paragraph has another sentence. " * 4)
        config = ChunkConfig(100, 15)
        chunks = chunk_document(source, "1", config)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(0 < len(chunk["text"]) <= 100 for chunk in chunks))
        self.assertEqual(chunks, chunk_document(source, "1", config))
        self.assertNotEqual(chunks[0]["id"], chunk_document(source, "2", config)[0]["id"])
        for index, chunk in enumerate(chunks):
            metadata = chunk["metadata"]
            self.assertEqual(metadata["movie_id"], "1")
            self.assertEqual(metadata["source_kind"], "snapshot")
            self.assertEqual(metadata["collected_at"], source["collected_at"])
            self.assertEqual(metadata["chunk_index"], index)
            self.assertEqual(len(metadata["body_hash"]), 64)
            self.assertIn("document_id", metadata)
        self.assertEqual(chunk_document(document("  \n "), "1"), [])
        with self.assertRaises(IndexConfigurationError):
            ChunkConfig(100, 100)

    def test_document_shared_by_two_movies_is_isolated_in_search(self):
        store = self.store()
        for movie_id in ("101", "202"):
            report = store.index_documents(movie_id, [document()], self.embedder)
            self.assertTrue(report["complete"], report)
        self.assertEqual(store.collection.count(), 2)
        for movie_id in ("101", "202"):
            hits = store.search(movie_id, "space", self.embedder, 10)
            self.assertEqual(len(hits), 1)
            self.assertEqual({hit["movie_id"] for hit in hits}, {movie_id})
            self.assertEqual(hits[0]["url"], "https://example.org/wiki/Example")
        self.assertEqual(store.search("missing", "space", self.embedder), [])
        self.assertEqual(len(self.embedder.queries), 2, "Empty movie scopes must not spend an API request")
        with self.assertRaises(IndexConfigurationError):
            store.search("", "space", self.embedder)

    def test_reopen_identical_content_skips_embedding_and_does_not_duplicate(self):
        store = self.store(ChunkConfig(60, 10))
        first = store.index_documents("101", [document()], self.embedder)
        self.assertTrue(first["complete"], first)
        reopened = self.store(ChunkConfig(60, 10))
        fresh = FakeEmbeddings()
        repeat = reopened.index_documents("101", [document(), document()], fresh)
        self.assertTrue(repeat["complete"], repeat)
        self.assertEqual(repeat["unique_docs"], 1)
        self.assertEqual(repeat["embedded"], 0)
        self.assertEqual(repeat["skipped"], first["chunk_count"])
        self.assertEqual(fresh.inputs, [])
        self.assertEqual(first["chunk_ids"], repeat["chunk_ids"])
        self.assertEqual(store.collection.count(), first["chunk_count"])

    def test_provenance_updates_without_reembedding_identical_body(self):
        store = self.store()
        first = store.index_documents("101", [document()], self.embedder)
        self.embedder.inputs.clear()
        second = store.index_documents("101", [document(source_kind="live", collected_at="2026-10-22T00:00:00Z")], self.embedder)
        self.assertTrue(second["complete"], second)
        self.assertEqual(second["embedded"], 0)
        self.assertEqual(self.embedder.inputs, [])
        self.assertEqual(first["chunk_ids"], second["chunk_ids"])
        hit = store.search("101", "space", self.embedder)[0]
        self.assertEqual(hit["source_kind"], "live")
        self.assertEqual(hit["collected_at"], "2026-10-22T00:00:00Z")

    def test_content_and_chunk_configuration_changes_remove_only_old_movie_generation(self):
        store = self.store(ChunkConfig(60, 10))
        first = store.index_documents("101", [document()], self.embedder)
        store.index_documents("202", [document()], self.embedder)
        changed = store.index_documents("101", [document("New space adventure. " * 9)], self.embedder)
        self.assertTrue(changed["complete"], changed)
        self.assertEqual(changed["removed"], first["chunk_count"])
        self.assertEqual(store.collection.get(ids=first["chunk_ids"], include=[])["ids"], [])
        reconfigured = self.store(ChunkConfig(100, 20))
        updated = reconfigured.index_documents("101", [document("New space adventure. " * 9)], self.embedder)
        self.assertTrue(updated["complete"], updated)
        self.assertEqual(updated["collection"], changed["collection"])
        self.assertEqual(updated["removed"], changed["chunk_count"])
        self.assertEqual(len(reconfigured.search("202", "space", self.embedder, 10)), first["chunk_count"])

    def test_partial_save_keeps_old_chunks_hidden_pending_and_reuses_saved_prefix(self):
        store = self.store(ChunkConfig(60, 10))
        old = store.index_documents("101", [document()], self.embedder)
        original = type(store.collection).upsert

        def interrupted(collection, **kwargs):
            original(collection, **{key: value[:1] for key, value in kwargs.items()})
            raise RuntimeError("Synthetic interrupted save")

        changed = document("A new ocean expedition searches distant shores. " * 8)
        with patch.object(type(store.collection), "upsert", new=interrupted):
            failed = store.index_documents("101", [changed], self.embedder)
        self.assertFalse(failed["complete"], failed)
        self.assertEqual(store.collection.get(ids=old["chunk_ids"], include=[])["ids"], old["chunk_ids"])
        hits = store.search("101", "space", self.embedder, 30)
        self.assertEqual({hit["id"] for hit in hits}, set(old["chunk_ids"]))
        self.embedder.inputs.clear()
        resumed = store.index_documents("101", [changed], self.embedder)
        self.assertTrue(resumed["complete"], resumed)
        self.assertEqual(resumed["skipped"], 1)
        self.assertEqual(resumed["embedded"], resumed["chunk_count"] - 1)
        self.assertEqual(store.collection.get(ids=old["chunk_ids"], include=[])["ids"], [])

    def test_failed_validation_never_deletes_old_chunks_and_empty_input_is_not_complete(self):
        store = self.store()
        old = store.index_documents("101", [document()], self.embedder)
        with patch.object(self.embedder, "embed_documents", return_value=[[float("nan"), 0, 1]]):
            failed = store.index_documents("101", [document("A changed space account.")], self.embedder)
        self.assertFalse(failed["complete"], failed)
        self.assertEqual(store.collection.get(ids=old["chunk_ids"], include=[])["ids"], old["chunk_ids"])
        empty = store.index_documents("101", [document("")], self.embedder)
        self.assertFalse(empty["complete"], empty)
        self.assertEqual(empty["rejected_docs"], 1)
        self.assertEqual(store.collection.count(), old["chunk_count"])


if __name__ == "__main__":
    unittest.main()
