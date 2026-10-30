"""Offline preparation integration: real Chroma, synthetic provider boundaries."""

from __future__ import annotations

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from movie_lab.data import Movie
from movie_lab.document_models import own_movie_query
from movie_lab.document_pipeline import DocumentPipeline, SuccessCache, fingerprint
from movie_lab.external_index import ChunkConfig, ExternalIndex
from movie_lab.wiki import WikiError


def movie(movie_id="101", title="여행", year=2020, director="가상 감독"):
    return Movie(movie_id=movie_id, title=title, original_title=title, release_date="",
                 year=year, genres=("SF",), director=(director,), cast=(), overview="",
                 runtime=None, original_language="ko", production_countries=(),
                 vote_average=None, vote_count=None, tmdb_url="")


def document(identifier="own", title="여행", text=None, source_kind="live"):
    return {"candidate_id": identifier, "document_id": identifier, "title": title,
            "url": "https://example.org/wiki/" + identifier,
            "text": text if text is not None else "여행은 2020년 개봉한 SF 영화이며 가상 감독이 감독했다.",
            "source_kind": source_kind, "collected_at": "2026-10-22T00:00:00Z"}


class FakePlanner:
    model = "gpt-4o-mini"
    mode = "json_schema"
    reported_model = "gpt-4o-mini-2024-07-18"

    def __init__(self, selected=None):
        self.request_count = 0
        self.audit = []
        self.selected = selected
        self.histories = []

    def extract(self, selected_movie, question, history):
        self.request_count += 1
        self.histories.append(deepcopy(history))
        self.audit.append({"role": "extract_queries", "status": "success"})
        return {"queries": [own_movie_query(selected_movie)], "focus": question}

    def select(self, selected_movie, question, candidates):
        self.request_count += 1
        self.audit.append({"role": "select_documents", "status": "success"})
        selected = list(self.selected) if self.selected is not None else [row["candidate_id"] for row in candidates]
        return {"selected_ids": selected,
                "reasons": [{"candidate_id": value, "reason": "테스트 질문 관련 후보"} for value in selected]}


class FakeWiki:
    def __init__(self, documents, *, fail_search=False):
        self.documents = {row["candidate_id"]: deepcopy(row) for row in documents}
        self.request_count = 0
        self.fail_search = fail_search

    def search(self, query):
        self.request_count += 1
        if self.fail_search:
            raise WikiError("위키백과 타임아웃")
        return [{**row, "snippet": row.get("text", "")[:1100]} for row in self.documents.values()]

    def fetch_page(self, title):
        self.request_count += 1
        return deepcopy(next((row for row in self.documents.values() if row["title"] == title), None))


class FakeSnapshot:
    def __init__(self, documents):
        self.documents = {row["candidate_id"]: deepcopy(row) for row in documents}
        self.read_count = 0

    def candidates(self, selected_movie):
        return [{**row, "snippet": row.get("text", "")[:1100]} for row in self.documents.values()]

    def fetch(self, identifier):
        self.read_count += 1
        return deepcopy(self.documents.get(identifier))


class FakeEmbeddings:
    model = "offline-pipeline"
    dimensions = 3

    def __init__(self):
        self.request_count = 0
        self.inputs = []
        self.fail_once = False

    def embed_documents(self, texts):
        self.request_count += 1
        if self.fail_once:
            self.fail_once = False
            raise TimeoutError("Synthetic offline timeout")
        self.inputs.extend(texts)
        return [[1.0, 0.1, 0.2] for _ in texts]

    def embed_query(self, text):
        return self.embed_documents([text])[0]


class DocumentPipelineTests(unittest.TestCase):
    def setUp(self):
        network = patch("socket.socket.connect", side_effect=AssertionError("Offline integration test"))
        network.start()
        self.addCleanup(network.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.embedder = FakeEmbeddings()
        self.index = ExternalIndex(self.path / "external", self.embedder.model, 3, ChunkConfig(100, 10))
        self.addCleanup(self.index.close)
        self.cache = SuccessCache(self.path / "cache")

    def pipeline(self, *, planner=None, wiki=None, snapshots=None, source_mode="auto", live_reason=None):
        return DocumentPipeline(planner=planner or FakePlanner(), embedder=self.embedder,
                                index=self.index, cache=self.cache, wiki=wiki,
                                snapshots=snapshots, source_mode=source_mode,
                                live_reason=live_reason, snapshot_signature={"test": "fixture-v1"})

    def test_successful_repeat_reuses_collection_and_vectors_without_provider_requests(self):
        planner = FakePlanner()
        wiki = FakeWiki([document()])
        pipeline = self.pipeline(planner=planner, wiki=wiki)
        question = "여행의 배경을 확인해줘"
        history = [{"role": "assistant", "content": "이전 확인되지 않은 답변", "sources": []},
                   {"role": "user", "content": question}]
        first = pipeline.prepare(movie(), question, history)
        self.assertTrue(first["complete"], first)
        self.assertEqual(first["calls"], {"chat": 2, "embedding": 1, "wiki": 2})
        self.assertEqual(planner.histories, [[{"role": "assistant", "content": "이전 확인되지 않은 답변"}]])
        count = self.index.collection.count()
        repeated = pipeline.prepare(movie(), question, history)
        self.assertTrue(repeated["cache_hit"], repeated)
        self.assertTrue(repeated["complete"], repeated)
        self.assertEqual(repeated["calls"], {"chat": 0, "embedding": 0, "wiki": 0})
        self.assertEqual(repeated["index"]["embedded"], 0)
        self.assertEqual(self.index.collection.count(), count)
        self.assertEqual(repeated["documents"][0]["source_kind"], "live")

    def test_collection_success_survives_index_failure_and_resumes_without_chat_or_fetch(self):
        pipeline = self.pipeline(wiki=FakeWiki([document()]))
        self.embedder.fail_once = True
        failed = pipeline.prepare(movie(), "작품 정보를 확인해줘")
        self.assertTrue(failed["collection_success"], failed)
        self.assertFalse(failed["index_success"], failed)
        self.assertFalse(failed["complete"], failed)
        self.assertEqual(self.index.collection.count(), 0)
        resumed = pipeline.prepare(movie(), "작품 정보를 확인해줘")
        self.assertTrue(resumed["collection_success"], resumed)
        self.assertTrue(resumed["index_success"], resumed)
        self.assertTrue(resumed["cache_hit"], resumed)
        self.assertEqual(resumed["calls"], {"chat": 0, "embedding": 1, "wiki": 0})

    def test_distinct_question_reselects_but_reuses_same_document_body(self):
        planner, wiki = FakePlanner(), FakeWiki([document()])
        pipeline = self.pipeline(planner=planner, wiki=wiki)
        first = pipeline.prepare(movie(), "작품의 첫 질문")
        second = pipeline.prepare(movie(), "같은 작품의 다른 질문")
        self.assertTrue(first["complete"], first)
        self.assertTrue(second["complete"], second)
        self.assertFalse(second["cache_hit"])
        self.assertEqual(second["calls"], {"chat": 2, "embedding": 0, "wiki": 0})
        self.assertEqual(second["document_cache_hits"], 1)
        self.assertEqual(second["focus"], "같은 작품의 다른 질문")

    def test_refresh_then_revisit_other_question_never_restores_older_body(self):
        old = document(text="여행은 2020년 개봉한 영화로 가상 감독이 감독했다. 과거 확인용 본문.")
        wiki = FakeWiki([old])
        pipeline = self.pipeline(wiki=wiki)
        first_a = pipeline.prepare(movie(), "질문 A")
        first_b = pipeline.prepare(movie(), "질문 B")
        self.assertTrue(first_a["complete"] and first_b["complete"])
        newer = {**old, "text": "여행은 2020년 개봉한 영화로 가상 감독이 감독했다. 새로 갱신한 본문과 추가 근거.",
                 "collected_at": "2026-10-23T00:00:00Z"}
        wiki.documents["own"] = deepcopy(newer)
        refreshed = pipeline.prepare(movie(), "질문 A", refresh=True)
        self.assertTrue(refreshed["complete"], refreshed)
        self.assertGreater(refreshed["index"]["embedded"], 0)
        active_after_refresh = set(self.index.collection.get(include=[])["ids"])
        revisited = pipeline.prepare(movie(), "질문 B")
        self.assertTrue(revisited["complete"], revisited)
        self.assertTrue(revisited["cache_hit"])
        self.assertEqual(revisited["calls"], {"chat": 0, "embedding": 0, "wiki": 0})
        self.assertEqual(revisited["documents"][0]["collected_at"], newer["collected_at"])
        self.assertEqual(set(self.index.collection.get(include=[])["ids"]), active_after_refresh)
        texts = self.index.collection.get(include=["documents"])["documents"]
        self.assertTrue(any("새로 갱신한" in text for text in texts))
        self.assertFalse(any("과거 확인용" in text for text in texts))
        # A past reply's independent source snapshot is never passed into, or
        # mutated by, the preparation cache and remains the original reference.
        self.assertEqual(first_b["documents"][0]["collected_at"], old["collected_at"])

    def test_question_cache_contains_references_only_and_legacy_body_cache_is_not_promoted(self):
        from dataclasses import asdict
        from movie_lab.document_llm import PROMPT_ROOT
        question, selected_movie = "이전 질문 캐시를 재검사", movie()
        prompt_signature = fingerprint([(PROMPT_ROOT / name).read_text(encoding="utf-8")
                                        for name in ("extract_queries.txt", "select_documents.txt")])
        legacy_key = fingerprint({"version": "document-preparation-v2", "movie": asdict(selected_movie),
                                  "question": question, "history_unverified": [], "model": "gpt-4o-mini",
                                  "prompt_signature": prompt_signature, "source_mode": "auto",
                                  "snapshot": {"test": "fixture-v1"}})
        legacy = document(text="구버전 질문에만 남은 위험한 본문")
        self.cache.put("collection:" + legacy_key,
                       {"documents": [legacy], "report": {"collection_success": True}})
        wiki = FakeWiki([document()])
        report = self.pipeline(wiki=wiki).prepare(selected_movie, question)
        self.assertTrue(report["complete"], report)
        self.assertFalse(report["cache_hit"])
        self.assertEqual(report["calls"], {"chat": 2, "embedding": 1, "wiki": 2})
        self.assertFalse(any("위험한" in text for text in self.embedder.inputs))
        entries = [json.loads(path.read_text(encoding="utf-8"))["value"]
                   for path in (self.path / "cache").glob("*.json")]
        selections = [value for value in entries if isinstance(value, dict) and "references" in value]
        self.assertEqual(len(selections), 1)
        self.assertNotIn("documents", selections[0])
        self.assertFalse(any("text" in ref for ref in selections[0]["references"]))
        self.assertFalse(any("text" in doc for doc in selections[0]["report"]["documents"]))

    def test_older_snapshot_fallback_cannot_replace_newer_shared_live_body(self):
        live = document(text="여행은 2020년 개봉한 영화로 가상 감독이 감독했다. 최신 실시간 본문.")
        live_pipeline = self.pipeline(wiki=FakeWiki([live]))
        self.assertTrue(live_pipeline.prepare(movie(), "실시간 질문")["complete"])
        snapshot = {**live, "source_kind": "snapshot", "collected_at": "2026-09-01T00:00:00Z",
                    "text": "여행은 2020년 개봉한 영화로 가상 감독이 감독했다. 오래된 스냅샷 본문."}
        snapshot_pipeline = self.pipeline(snapshots=FakeSnapshot([snapshot]), source_mode="snapshot")
        refreshed = snapshot_pipeline.prepare(movie(), "스냅샷 질문", refresh=True)
        self.assertTrue(refreshed["complete"], refreshed)
        self.assertEqual(refreshed["index"]["embedded"], 0)
        self.assertEqual(refreshed["documents"][0]["source_kind"], "live")
        self.assertFalse(any("오래된 스냅샷" in text for text in self.embedder.inputs))

    def test_valid_own_document_is_included_even_when_selection_omits_it_and_body_is_short(self):
        own = document()
        self.assertLess(len(own["text"]), 120)
        pipeline = self.pipeline(planner=FakePlanner(selected=[]), wiki=FakeWiki([own]))
        report = pipeline.prepare(movie(), "영화에 대한 기본 정보를 확인해줘")
        self.assertTrue(report["complete"], report)
        self.assertEqual(report["selection"]["selected_ids"], [])
        self.assertEqual(report["documents"][0]["identity"], "일치")
        self.assertEqual(report["documents"][0]["title"], "여행")

    def test_wrong_moon_is_rejected_but_yearless_background_can_be_selected(self):
        selected_movie = movie("753091", "더 문", 2023, "김용화")
        wrong = document("wrong-moon", "더 문", "더 문(Moon)은 2009년 개봉한 영국 SF 영화로 덩컨 존스가 감독했다.", "snapshot")
        background = document("moon-background", "달", "달은 지구의 유일한 자연 위성이며 우주 탐사와 관련된다. " * 8, "snapshot")
        pipeline = self.pipeline(snapshots=FakeSnapshot([wrong, background]), source_mode="snapshot")
        report = pipeline.prepare(selected_movie, "달의 환경을 확인해줘")
        self.assertTrue(report["complete"], report)
        self.assertEqual([row["title"] for row in report["documents"]], ["달"])
        self.assertEqual(report["documents"][0]["identity"], "확인 필요")
        self.assertEqual(report["rejected"][0]["identity"], "불일치")
        self.assertFalse(report["live_collection_success"])
        self.assertEqual(report["calls"]["wiki"], 0)

    def test_live_failure_uses_same_snapshot_checks_and_preserves_snapshot_provenance(self):
        snapshot = document(source_kind="snapshot")
        snapshot["collected_at"] = "2026-09-01T00:00:00Z"
        pipeline = self.pipeline(wiki=FakeWiki([], fail_search=True), snapshots=FakeSnapshot([snapshot]))
        report = pipeline.prepare(movie(), "작품의 기본 정보를 확인해줘")
        self.assertTrue(report["complete"], report)
        self.assertTrue(report["live_attempted"])
        self.assertFalse(report["live_search_success"])
        self.assertFalse(report["live_collection_success"])
        self.assertEqual(report["live_reason"], "위키백과 타임아웃")
        self.assertEqual(report["documents"][0]["source_kind"], "snapshot")
        self.assertEqual(report["documents"][0]["collected_at"], "2026-09-01T00:00:00Z")
        metadata = self.index.collection.get(include=["metadatas"])["metadatas"][0]
        self.assertEqual(metadata["source_kind"], "snapshot")
        self.assertEqual(metadata["collected_at"], "2026-09-01T00:00:00Z")

    def test_empty_or_failed_collection_is_not_cached_as_success(self):
        for label, wiki in (("empty-search", FakeWiki([])),
                            ("empty-body", FakeWiki([document(text="")])),
                            ("failed-search", FakeWiki([], fail_search=True))):
            with self.subTest(label=label):
                pipeline = self.pipeline(wiki=wiki)
                question = "자료 확인 " + label
                first = pipeline.prepare(movie(), question)
                second = pipeline.prepare(movie(), question)
                self.assertFalse(first["complete"], first)
                self.assertFalse(first["collection_success"], first)
                self.assertFalse(second["cache_hit"], second)
                self.assertGreater(second["calls"]["chat"], 0)
                self.assertEqual(second["calls"]["embedding"], 0)
                self.assertFalse(list((self.path / "cache").glob("*.tmp")))
        self.assertEqual(self.index.collection.count(), 0)


if __name__ == "__main__":
    unittest.main()
