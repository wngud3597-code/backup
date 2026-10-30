"""Offline evidence assembly: selected metadata, source diversity and strict scope."""

from __future__ import annotations

import tempfile
import unittest
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from movie_lab.data import Movie, build_index_text
from movie_lab.external_index import ExternalIndex
from movie_lab.index import IndexConfig, MetadataIndex
from movie_lab.retrieval import EvidenceRetriever, RetrievalConfig
from tests.test_external_index import FakeEmbeddings


def selected_movie(movie_id="101", title="Space Film", year=2020):
    return Movie(movie_id, title, title, "", year, ("SF",), ("Director",), (),
                 "A space crew explores a distant planet.", 120, "en", (), 7.0, 100,
                 "https://example.org/movie/" + movie_id)


def hit(identifier, document_id, text, *, movie_id="101", **metadata):
    return {"id": identifier, "document_id": document_id, "movie_id": movie_id,
            "title": document_id, "url": "https://example.org/wiki/" + document_id,
            "text": text, "source_kind": "snapshot", "collected_at": "2026-09-01",
            "ready": True, **metadata}


class FixedExternal:
    def __init__(self, hits, *, fail=False):
        self.hits, self.fail, self.calls = hits, fail, []

    def search(self, movie_id, question, embedder, k=3):
        self.calls.append({"movie_id": movie_id, "question": question, "k": k})
        if self.fail:
            raise TimeoutError("Offline synthetic private detail must never be surfaced")
        return deepcopy(self.hits[:k])


class RetrievalTests(unittest.TestCase):
    def setUp(self):
        no_network = patch("socket.socket.connect", side_effect=AssertionError("Offline retrieval test"))
        no_network.start()
        self.addCleanup(no_network.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.movie = selected_movie()
        self.embedder = FakeEmbeddings()

    def stores(self):
        metadata = MetadataIndex(self.path / "metadata", IndexConfig(self.embedder.model, 3))
        external = ExternalIndex(self.path / "external", self.embedder.model, 3)
        self.addCleanup(metadata.close)
        self.addCleanup(external.close)
        return metadata, external

    def test_stable_metadata_id_is_read_directly_and_other_movie_never_enters_evidence(self):
        metadata, external = self.stores()
        other = selected_movie("202", "Ocean Film")
        metadata.index_movies({self.movie.movie_id: self.movie, other.movie_id: other}, self.embedder)
        for movie_id in (self.movie.movie_id, other.movie_id):
            external.index_documents(movie_id, [{"title": "Background", "url": "https://example.org/wiki/background",
                                                "text": "A space crew studies the ocean.", "source_kind": "snapshot"}], self.embedder)
        self.embedder.inputs.clear()
        retrieved = EvidenceRetriever(metadata, external, self.embedder).retrieve(self.movie, "ocean")
        self.assertEqual(retrieved["sources"][0]["document_id"], "meta:101")
        self.assertEqual(retrieved["sources"][0]["text"], build_index_text(self.movie))
        self.assertEqual(retrieved["diagnostics"]["metadata_origin"], "metadata_index")
        self.assertEqual({source["movie_id"] for source in retrieved["sources"]}, {"101"})
        self.assertEqual(self.embedder.queries, ["ocean"])
        self.assertEqual(self.embedder.inputs, [], "Metadata ID lookup cannot re-embed any document")
        self.assertEqual({row["movie_id"] for row in external.ready_documents("101")}, {"101"})
        self.assertEqual(external.ready_documents("missing"), [])
        self.assertIn("[근거 1]", retrieved["context"])
        self.assertIn("scope: movie_metadata", retrieved["context"])

    def test_missing_store_and_external_failure_keep_provided_metadata_without_private_errors(self):
        external = FixedExternal([], fail=True)
        retrieved = EvidenceRetriever(None, external, self.embedder).retrieve(self.movie, "감독은 누구야?")
        self.assertEqual(len(retrieved["sources"]), 1)
        self.assertEqual(retrieved["sources"][0]["document_id"], "meta:101")
        self.assertEqual(retrieved["sources"][0]["source_kind"], "metadata")
        self.assertEqual(retrieved["diagnostics"]["metadata_origin"], "provided_file")
        self.assertIsNotNone(retrieved["diagnostics"]["external_error"])
        self.assertNotIn("private detail", str(retrieved))
        no_external = EvidenceRetriever(None, None, self.embedder).retrieve(self.movie, "감독은 누구야?")
        self.assertEqual(no_external["sources"][0]["movie_id"], "101")

    def test_same_document_overlap_is_removed_and_other_documents_get_a_slot(self):
        repeated = "A space crew reaches a distant planet and studies its atmosphere. " * 4
        external = FixedExternal([
            hit("a:0", "film", repeated),
            hit("a:1", "film", repeated + "A minor trailing detail."),
            hit("a:2", "film", "A distinct account of the film crew and production decisions."),
            hit("a:3", "film", "A further distinct account of film photography and soundtrack."),
            hit("b:0", "ocean", "Ocean currents influence temperatures around distant shores."),
            hit("c:0", "physics", "Relative motion changes measured elapsed time."),
        ])
        retrieved = EvidenceRetriever(None, external, self.embedder,
                                      RetrievalConfig(top_k=5, max_per_document=2)).retrieve(self.movie, "space and time")
        identifiers = [source.get("chunk_id") for source in retrieved["sources"][1:]]
        self.assertEqual(identifiers[:3], ["a:0", "b:0", "c:0"])
        self.assertNotIn("a:1", identifiers)
        self.assertNotIn("a:3", identifiers)
        self.assertEqual(len(external.calls), 1)
        self.assertEqual(external.calls[0]["k"], 15)
        self.assertEqual(retrieved["diagnostics"]["duplicates_removed"], 1)
        self.assertEqual(retrieved["diagnostics"]["document_cap_removed"], 1)

    def test_movie_scope_and_ready_defense_excludes_malformed_provider_hits(self):
        external = FixedExternal([
            hit("other:0", "foreign", "Other movie content.", movie_id="202"),
            hit("pending:0", "pending", "A partially persisted chunk.", ready=False),
            hit("ready:0", "ready", "Available background content."),
        ])
        retrieved = EvidenceRetriever(None, external, self.embedder).retrieve(self.movie, "content")
        self.assertEqual([source.get("chunk_id") for source in retrieved["sources"][1:]], ["ready:0"])
        self.assertEqual(retrieved["diagnostics"]["rejected_cross_movie"], 1)
        self.assertEqual(retrieved["diagnostics"]["rejected_unready"], 1)

    def test_identity_requires_current_movie_preparation_and_mismatch_is_excluded(self):
        external = FixedExternal([
            hit("own:0", "own", "A description of the selected film."),
            hit("background:0", "background", "General scientific background information."),
            hit("wrong:0", "wrong", "A different homonymous film description."),
        ])
        preparation = {"movie_id": "101", "documents": [
            {"url": "https://example.org/wiki/own", "identity": "일치", "identity_reason": "제목과 연도 일치"},
            {"url": "https://example.org/wiki/wrong", "identity": "불일치", "identity_reason": "연도 불일치"},
        ]}
        retriever = EvidenceRetriever(None, external, self.embedder)
        retrieved = retriever.retrieve(self.movie, "영화와 현실", preparation)
        by_document = {source["document_id"]: source for source in retrieved["sources"]}
        self.assertEqual(by_document["own"]["scope"], "film_description")
        self.assertEqual(by_document["background"]["scope"], "background_unverified")
        self.assertNotIn("wrong", by_document)
        self.assertIn("identity_reason: 제목과 연도 일치", retrieved["context"])
        another_preparation = {**preparation, "movie_id": "202"}
        unverified = retriever.retrieve(self.movie, "영화와 현실", another_preparation)
        self.assertTrue(all(source["identity"] == "확인 필요" for source in unverified["sources"][1:]))

    def test_context_limit_keeps_metadata_first_and_only_exposes_included_raw_text(self):
        external = FixedExternal([hit("a:0", "background", "Background evidence sentence. " * 200)])
        config = RetrievalConfig(top_k=3, max_context_chars=1800)
        retrieved = EvidenceRetriever(None, external, self.embedder, config).retrieve(self.movie, "background")
        self.assertLessEqual(len(retrieved["context"]), config.max_context_chars)
        self.assertEqual(retrieved["sources"][0]["document_id"], "meta:101")
        self.assertEqual(len(retrieved["sources"]), 2)
        self.assertTrue(retrieved["sources"][1]["truncated"])
        self.assertIn(retrieved["sources"][1]["text"], retrieved["context"])
        self.assertEqual(retrieved["diagnostics"]["context_chars"], len(retrieved["context"]))

    def test_stale_metadata_row_falls_back_to_current_file_without_reindexing(self):
        metadata, _ = self.stores()
        metadata.index_movies({"101": self.movie}, self.embedder)
        modified = replace(self.movie, overview="The supplied metadata was corrected.")
        self.embedder.inputs.clear()
        retrieved = EvidenceRetriever(metadata, None, self.embedder).retrieve(modified, "줄거리 정보")
        self.assertEqual(retrieved["diagnostics"]["metadata_origin"], "provided_file")
        self.assertEqual(retrieved["sources"][0]["text"], build_index_text(modified))
        self.assertEqual(self.embedder.inputs, [])
        saved = metadata.collection.get(ids=["meta:101"], include=["documents"])
        self.assertEqual(saved["documents"], [build_index_text(self.movie)])

    def test_tight_context_never_drops_mandatory_metadata_because_url_is_long(self):
        selected = replace(self.movie, tmdb_url="https://example.org/" + "long-path-" * 150)
        retrieved = EvidenceRetriever(None, None, self.embedder,
                                      RetrievalConfig(top_k=1, max_context_chars=400, max_per_document=1)).retrieve(selected, "감독은?")
        self.assertEqual(len(retrieved["sources"]), 1)
        self.assertEqual(retrieved["sources"][0]["document_id"], "meta:101")
        self.assertEqual(retrieved["sources"][0]["url"], selected.tmdb_url)
        self.assertLessEqual(len(retrieved["context"]), 400)
        self.assertIn("scope: movie_metadata", retrieved["context"])

    def test_local_keyword_hints_recover_a_topic_missed_by_semantic_candidates_without_another_search(self):
        class LocalExternal(FixedExternal):
            def ready_documents(self, movie_id):
                return [*self.hits,
                        hit("science:0", "science", "Photosynthesis and chlorophyll explain the observed plant color."),
                        hit("foreign:0", "foreign", "Photosynthesis chlorophyll.", movie_id="202"),
                        hit("pending:0", "pending", "Photosynthesis chlorophyll.", ready=False)]
        external = LocalExternal([hit("myth:0", "myth", "A myth describes a green-colored magical plant.")])
        preparation = {"movie_id": "101", "queries": ["Space Film 2020 Director", "photosynthesis chlorophyll", "Space Film"]}
        retrieved = EvidenceRetriever(None, external, self.embedder).retrieve(self.movie, "Why does the plant look green?", preparation)
        selected = [source.get("chunk_id") for source in retrieved["sources"][1:]]
        self.assertEqual(selected[0], "science:0")
        self.assertNotIn("foreign:0", selected)
        self.assertNotIn("pending:0", selected)
        self.assertEqual(len(external.calls), 1)
        self.assertEqual(retrieved["diagnostics"]["keyword_hints"], ["photosynthesis chlorophyll"])
        self.assertEqual(retrieved["diagnostics"]["local_candidates_added"], 1)
        self.assertEqual(self.embedder.inputs, [])
        self.assertEqual(self.embedder.queries, [])

    def test_local_read_failure_preserves_semantic_candidates_without_retry(self):
        class FailedLocalExternal(FixedExternal):
            def ready_documents(self, movie_id):
                raise RuntimeError("Synthetic private store detail")
        external = FailedLocalExternal([hit("existing:0", "existing", "Existing stored evidence.")])
        retrieved = EvidenceRetriever(None, external, self.embedder).retrieve(self.movie, "Existing evidence?")
        self.assertEqual(retrieved["sources"][1]["chunk_id"], "existing:0")
        self.assertEqual(len(external.calls), 1)
        self.assertTrue(any("로컬 키워드" in row for row in retrieved["diagnostics"]["warnings"]))
        self.assertNotIn("private store", str(retrieved))

    def test_semantic_502_preserves_movie_scoped_local_evidence_with_truthful_warning(self):
        class SyntheticBadGateway(RuntimeError):
            status_code = 502

        class LocalAfter502(FixedExternal):
            def __init__(self):
                super().__init__([])
                self.ready_calls = []

            def search(self, movie_id, question, embedder, k=3):
                self.calls.append({"movie_id": movie_id, "question": question, "k": k})
                raise SyntheticBadGateway("Synthetic private server detail")

            def ready_documents(self, movie_id):
                self.ready_calls.append(movie_id)
                return [hit("science:0", "science", "Photosynthesis explains the observed plant color."),
                        hit("foreign:0", "foreign", "Photosynthesis evidence for another movie.", movie_id="202"),
                        hit("pending:0", "pending", "Photosynthesis unfinished evidence.", ready=False)]

        external = LocalAfter502()
        retrieved = EvidenceRetriever(None, external, self.embedder).retrieve(self.movie, "photosynthesis plant color")
        self.assertEqual(retrieved["sources"][0]["document_id"], "meta:101")
        self.assertEqual([row.get("chunk_id") for row in retrieved["sources"][1:]], ["science:0"])
        self.assertEqual({row["movie_id"] for row in retrieved["sources"]}, {"101"})
        self.assertEqual(external.ready_calls, ["101"])
        self.assertEqual(len(external.calls), 1)
        self.assertEqual(retrieved["diagnostics"]["external_error"]["http_status"], 502)
        self.assertIn("의미 검색에 실패했습니다. 이번에 실제 확보된 저장 근거 범위에서 답합니다.",
                      retrieved["diagnostics"]["warnings"])
        self.assertNotIn("제공된 영화 메타데이터로 확인할 수 있는 부분만", str(retrieved["diagnostics"]["warnings"]))
        self.assertNotIn("private server detail", str(retrieved))
        self.assertEqual(self.embedder.inputs, [])
        self.assertEqual(self.embedder.queries, [])


if __name__ == "__main__":
    unittest.main()
