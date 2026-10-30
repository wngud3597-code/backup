"""Bounded evidence retrieval for one selected film, without answer generation.

The metadata source is included by ID (or explicitly from the supplied file),
not similarity rank. One external search is diversified locally; no reranker,
additional language-model call, or extra topic embedding is hidden here.
"""

from __future__ import annotations

import re
import math
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import unquote, urlsplit, urlunsplit

from movie_lab.data import Movie, build_index_text
from movie_lab.discovery import _features
from movie_lab.embeddings import failure_details


@dataclass(frozen=True)
class RetrievalConfig:
    """top_k includes the mandatory metadata source; limits count final context."""

    top_k: int = 6
    max_context_chars: int = 14000
    max_per_document: int = 2

    def __post_init__(self) -> None:
        if type(self.top_k) is not int or not 1 <= self.top_k <= 30:
            raise ValueError("검색 근거 수는 1~30 사이의 정수여야 합니다.")
        if type(self.max_context_chars) is not int or self.max_context_chars < 400:
            raise ValueError("검색 문맥 상한은 400자 이상의 정수여야 합니다.")
        if type(self.max_per_document) is not int or not 1 <= self.max_per_document <= self.top_k:
            raise ValueError("문서별 청크 상한은 1 이상 전체 근거 수 이하여야 합니다.")


def _canonical_url(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return ""
        return urlunsplit(("https", parsed.netloc.casefold(), unquote(parsed.path).rstrip("/"), parsed.query, ""))
    except ValueError:
        return ""


def _compact(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _near_duplicate(text: str, previous: str) -> bool:
    first, second = _compact(text), _compact(previous)
    if not first or not second:
        return False
    if first in second or second in first:
        return True
    # Only remove substantial repeated coverage, not ordinary 120/900 overlap.
    return SequenceMatcher(None, first, second, autojunk=False).ratio() >= 0.88


def _keyword_scores(question: str, hints: list[str], rows: list[dict]) -> dict[str, float]:
    """Local BM25-style scores are candidate ranks, not claim verification.

    Reuse the catalogue's Korean features, without repeating the article title
    into each chunk. Background query hints add topic recall for paraphrases.
    """
    query = _features(question)
    for hint in hints:
        # Short, selected topic queries should retain their two-syllable stems
        # across Korean suffixes. Ignore single-character hint noise; it must
        # not outweigh the topic with arbitrary grammatical overlap.
        query.update({term: max(weight, 1.0) * 3 for term, weight in _features(hint).items()
                      if not term.startswith("c:")})
    documents = {row["id"]: _features(row["text"]) for row in rows}
    frequency: Counter = Counter()
    for features in documents.values():
        frequency.update(features.keys())
    average = sum(sum(features.values()) for features in documents.values()) / max(1, len(documents)) or 1
    scores = {}
    for identifier, features in documents.items():
        length, score = sum(features.values()), 0.0
        for term, query_weight in query.items():
            count = features.get(term, 0)
            if count:
                inverse = math.log(1 + (len(documents) - frequency[term] + 0.5) / (frequency[term] + 0.5))
                score += query_weight * inverse * count * 2.2 / (count + 1.2 * (0.25 + 0.75 * length / average))
        scores[identifier] = score
    return scores


def _source_block(number: int, source: dict, *, compact: bool = False) -> str:
    if compact:
        # Keep the selected metadata even under an unusually tight context cap.
        # Full title/URL remain in the inspectable source object, not lost.
        return (f"[근거 {number}]\nscope: {source['scope']}\nsource_kind: {source['source_kind']}\n"
                f"identity: {source.get('identity', '확인 필요')}\n"
                f"identity_reason: {source.get('identity_reason', '')[:100]}\n원문:\n{source['text']}")
    return (f"[근거 {number}]\n"
            f"scope: {source['scope']}\nsource_kind: {source['source_kind']}\n"
            f"identity: {source.get('identity', '확인 필요')}\n"
            f"identity_reason: {source.get('identity_reason', '')}\n"
            f"title: {source['title']}\nurl: {source['url']}\n"
            f"원문:\n{source['text']}")


class EvidenceRetriever:
    def __init__(self, metadata_index, external_index, embedder, config: RetrievalConfig | None = None):
        self.metadata_index, self.external_index, self.embedder = metadata_index, external_index, embedder
        self.config = config or RetrievalConfig()

    def _metadata_source(self, movie: Movie, diagnostics: dict) -> dict:
        if self.metadata_index is not None:
            try:
                source = self.metadata_index.get_movie_source(movie)
                diagnostics["metadata_origin"] = "metadata_index"
                return source
            except Exception:
                diagnostics["warnings"].append("저장 메타데이터를 확인하지 못해 제공된 영화 파일을 사용합니다.")
        diagnostics["metadata_origin"] = "provided_file"
        return {"document_id": f"meta:{movie.movie_id}", "movie_id": movie.movie_id,
                "title": f"{movie.title or movie.original_title} · 제공 영화 메타데이터 (movies.json)",
                "url": movie.tmdb_url, "text": build_index_text(movie), "source_kind": "metadata",
                "scope": "movie_metadata", "identity": "일치",
                "identity_reason": "선택한 movie_id의 제공 메타데이터이며 저장 색인 일치는 별도로 확인하지 않았습니다."}

    def _external_source(self, hit: dict, movie: Movie, preparation_report: dict | None) -> dict:
        identity, reason = "확인 필요", "작품 자체 문서 여부와 사실 정확성은 확인되지 않았습니다."
        own_document = False
        if preparation_report and preparation_report.get("movie_id") == movie.movie_id:
            url = _canonical_url(hit.get("url"))
            for document in preparation_report.get("documents", []):
                if (url and _canonical_url(document.get("url")) == url
                        or document.get("document_id") == hit.get("document_id")):
                    identity = document.get("identity", "확인 필요")
                    reason = document.get("identity_reason") or reason
                    own_document = identity == "일치"
                    break
        return {"title": str(hit.get("title") or "제목 없음"), "url": str(hit.get("url") or ""),
                "text": hit["text"], "source_kind": str(hit.get("source_kind") or "unknown"),
                "movie_id": movie.movie_id, "document_id": str(hit.get("document_id") or hit.get("id")),
                "chunk_id": str(hit.get("id") or ""),
                "scope": "film_description" if own_document else "background_unverified",
                "identity": identity, "identity_reason": reason,
                "collected_at": str(hit.get("collected_at") or "미상"),
                "body_hash": str(hit.get("body_hash") or "")}

    def retrieve(self, movie: Movie, question: str, preparation_report: dict | None = None) -> dict:
        if not isinstance(question, str) or not question.strip():
            raise ValueError("검색할 질문이 필요합니다.")
        diagnostics = {"movie_id": movie.movie_id, "metadata_origin": None,
                       "external_candidates": 0, "external_selected": 0,
                       "duplicates_removed": 0, "document_cap_removed": 0,
                       "rejected_cross_movie": 0, "rejected_unready": 0,
                       "external_error": None, "warnings": [], "semantic_candidates": 0,
                       "local_chunks_scanned": 0, "keyword_candidates": 0,
                       "local_candidates_added": 0, "keyword_hints": [],
                       "candidate_fusion": "local-bm25-plus-semantic-v1",
                       "limits": {"top_k_including_metadata": self.config.top_k,
                                  "max_context_chars": self.config.max_context_chars,
                                  "max_per_document": self.config.max_per_document,
                                  "external_search_calls_max": 1}}
        mandatory = self._metadata_source(movie, diagnostics)
        candidates = []
        if self.external_index is not None and self.config.top_k > 1:
            try:
                candidates = self.external_index.search(movie.movie_id, question.strip(), self.embedder,
                                                        k=self.config.top_k * 3)
            except Exception as error:
                diagnostics["external_error"] = {key: value for key, value in failure_details(error).items() if key != "status"}
                diagnostics["warnings"].append("의미 검색에 실패했습니다. 이번에 실제 확보된 저장 근거 범위에서 답합니다.")
        elif self.external_index is None:
            diagnostics["warnings"].append("이번 검색은 영화 메타데이터만 사용하도록 제한했습니다." if self.config.top_k == 1
                                           else "외부 문서 색인이 없어 영화 메타데이터만 포함했습니다.")
        diagnostics["semantic_candidates"] = len(candidates)
        ready_reader = getattr(self.external_index, "ready_documents", None)
        if callable(ready_reader) and self.config.top_k > 1:
            try:
                local = [row for row in ready_reader(movie.movie_id)
                         if row.get("movie_id") == movie.movie_id and row.get("ready") is True
                         and isinstance(row.get("text"), str) and row["text"].strip()]
                diagnostics["local_chunks_scanned"] = len(local)
                hints = []
                if preparation_report and preparation_report.get("movie_id") == movie.movie_id:
                    facets = [movie.title, movie.original_title, *movie.director]
                    if movie.year is not None:
                        facets.append(str(movie.year))
                    for value in preparation_report.get("queries", [])[1:]:
                        if not isinstance(value, str) or not value.strip():
                            continue
                        residual = re.sub(r"[^가-힣a-z0-9]", "", value.casefold())
                        for facet in sorted(set(facets), key=len, reverse=True):
                            residual = residual.replace(re.sub(r"[^가-힣a-z0-9]", "", facet.casefold()), "")
                        if residual:
                            hints.append(value[:220])
                    hints = hints[:3]
                diagnostics["keyword_hints"] = hints
                scores = _keyword_scores(question, hints, local)
                local.sort(key=lambda row: (-scores.get(row["id"], 0), row["id"]))
                local = [row for row in local if scores.get(row["id"], 0) > 0][:self.config.top_k * 3]
                diagnostics["keyword_candidates"] = len(local)
                semantic_rank = {row["id"]: rank for rank, row in enumerate(candidates, 1)}
                merged = {row["id"]: row for row in candidates}
                for row in local:
                    merged.setdefault(row["id"], row)
                diagnostics["local_candidates_added"] = len(merged) - len(candidates)
                maximum = max(scores.values(), default=0) or 1
                # Lexical strength admits missing topics; a small semantic
                # signal preserves relevance without expanding API top-k.
                def rank(row):
                    return scores.get(row["id"], 0) / maximum + (0.12 / semantic_rank[row["id"]] if row["id"] in semantic_rank else 0)
                candidates = sorted(merged.values(), key=lambda row: (-rank(row), row["id"]))
                diagnostics["candidate_ranking"] = [{"chunk_id": row["id"],
                    "keyword_score": round(scores.get(row["id"], 0), 6),
                    "semantic_rank": semantic_rank.get(row["id"])} for row in candidates]
                if local:
                    diagnostics["warnings"].append("선택 영화의 저장 청크에서 키워드 후보를 보완했습니다. 키워드·의미 순위는 주장 사실 여부를 검증하지 않습니다.")
            except Exception:
                diagnostics["warnings"].append("로컬 키워드 후보를 읽지 못해 확보한 의미 검색 후보만 사용합니다.")
        diagnostics["external_candidates"] = len(candidates)
        counts: Counter = Counter()
        by_document: dict[str, list[str]] = {}
        selected, remaining = [], []
        # Give distinct documents one slot before allowing another chunk from
        # the same document. This prevents a long film article from occupying
        # all available evidence slots solely through overlapping chunks.
        for hit in candidates:
            if hit.get("movie_id") != movie.movie_id:
                diagnostics["rejected_cross_movie"] += 1
                continue
            if hit.get("ready") is False:
                diagnostics["rejected_unready"] += 1
                continue
            text = hit.get("text")
            if not isinstance(text, str) or not text.strip():
                continue
            source = self._external_source(hit, movie, preparation_report)
            if source["identity"] == "불일치":
                continue
            document_id = source["document_id"]
            if any(_near_duplicate(text, previous) for previous in by_document.get(document_id, [])):
                diagnostics["duplicates_removed"] += 1
                continue
            by_document.setdefault(document_id, []).append(text)
            if counts[document_id] == 0:
                selected.append(source)
                counts[document_id] += 1
            else:
                remaining.append(source)
        for source in remaining:
            document_id = source["document_id"]
            if counts[document_id] < self.config.max_per_document:
                selected.append(source)
                counts[document_id] += 1
            else:
                diagnostics["document_cap_removed"] += 1
        ordered = [mandatory, *selected]
        sources, blocks = [], []
        for source in ordered[:self.config.top_k]:
            number = len(sources) + 1
            block = _source_block(number, source)
            separator_size = 2 if blocks else 0
            available = self.config.max_context_chars - sum(len(value) for value in blocks) - max(0, len(blocks) - 1) * 2 - separator_size
            compact = number == 1 and len(block) - len(source["text"]) + 40 > available
            if compact:
                block = _source_block(number, source, compact=True)
                diagnostics["warnings"].append("메타데이터를 유지하기 위해 문맥의 출처 헤더를 줄였습니다. 전체 제목과 URL은 출처 목록에 보존했습니다.")
            if len(block) > available:
                header_size = len(block) - len(source["text"])
                if available - header_size < 40:
                    diagnostics["warnings"].append("문맥 상한 때문에 일부 근거를 포함하지 못했습니다.")
                    continue
                source = {**source, "text": source["text"][:available - header_size], "truncated": True}
                block = _source_block(number, source, compact=compact)
                diagnostics["warnings"].append("문맥 상한에 맞춰 일부 원문을 잘랐습니다. 잘린 부분은 근거로 사용할 수 없습니다.")
            sources.append(source)
            blocks.append(block)
        diagnostics["external_selected"] = sum(source["source_kind"] != "metadata" for source in sources)
        diagnostics["context_chars"] = len("\n\n".join(blocks))
        if diagnostics["duplicates_removed"] or diagnostics["document_cap_removed"]:
            diagnostics["warnings"].append("겹치는 청크와 문서별 상한을 적용했습니다. 부족한 주제는 추가 검색 없이 확인 불가로 남깁니다.")
        return {"sources": sources, "context": "\n\n".join(blocks), "diagnostics": diagnostics}
