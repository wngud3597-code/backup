"""Question-scoped document preparation, with successful stage caches only."""

from __future__ import annotations

import hashlib
import json
import time
from copy import deepcopy
from pathlib import Path
from urllib.parse import unquote, urlsplit, urlunsplit

from movie_lab.config import (document_chunk_settings, resolve_document_cache_path,
                              resolve_document_index_path, resolve_snapshot_path)
from movie_lab.document_llm import DocumentModelError, create_document_planner
from movie_lab.document_models import classify_document_identity
from movie_lab.embeddings import create_gms_embeddings, failure_details
from movie_lab.external_index import ChunkConfig, ExternalIndex
from movie_lab.wiki import LiveUnavailable, SnapshotRepository, WikiError, create_wiki_client


PIPELINE_VERSION = "document-preparation-v3"
SELECTION_CACHE_PREFIX = "question-selection:v1:"
BODY_CACHE_PREFIX = "document-body:v1:"
ALIAS_CACHE_PREFIX = "document-alias:v1:"


def fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


class SuccessCache:
    def __init__(self, path: Path, ttl: float = 86400):
        self.path, self.ttl = Path(path), ttl

    def get(self, key: str):
        try:
            entry = json.loads((self.path / f"{fingerprint(key)}.json").read_text(encoding="utf-8"))
            if entry["success"] is True and 0 <= time.time() - entry["at"] < self.ttl:
                return entry["value"]
        except (OSError, ValueError, KeyError, TypeError):
            pass
        return None

    def put(self, key: str, value) -> None:
        if not value:
            return
        self.path.mkdir(parents=True, exist_ok=True)
        target = self.path / f"{fingerprint(key)}.json"
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps({"success": True, "at": time.time(), "value": value},
                                        ensure_ascii=False), encoding="utf-8")
        temporary.replace(target)


def _own_candidate(movie, candidate) -> bool:
    import re
    norm = lambda value: re.sub(r"[\W_]+", "", str(value).casefold())
    title = re.sub(r"\s*\(.*?\)\s*$", "", candidate.get("title", ""))
    return norm(title) in {norm(movie.title), norm(movie.original_title)} - {""}


def safe_error(error: Exception) -> dict:
    if isinstance(error, (DocumentModelError, WikiError)):
        return {"category": error.category, "http_status": error.http_status}
    return {key: value for key, value in failure_details(error).items() if key != "status"}


def _document_cache_identity(document: dict) -> str:
    """One current body per canonical document, shared across questions/films."""
    page_id = document.get("page_id")
    if type(page_id) is int:
        return fingerprint({"wikipedia_page_id": page_id})
    document_id = document.get("document_id")
    if isinstance(document_id, str) and document_id.strip():
        return fingerprint({"document_id": document_id})
    url = document.get("url")
    if isinstance(url, str) and url.strip():
        try:
            parsed = urlsplit(url.strip())
            if parsed.scheme in {"http", "https"} and parsed.netloc:
                canonical = urlunsplit(("https", parsed.netloc.casefold(),
                                        unquote(parsed.path).rstrip("/"), parsed.query, ""))
                return fingerprint({"url": canonical})
        except ValueError:
            pass
    identity = document.get("candidate_id")
    if identity is None:
        raise WikiError("문서 캐시에 사용할 식별정보가 없습니다")
    return fingerprint({"document_id": str(identity)})


def _source_time(document: dict) -> float | None:
    """Compare declared provenance, without assigning a fake snapshot date."""
    from datetime import datetime, timezone
    value = document.get("collected_at")
    if not isinstance(value, str):
        return None
    try:
        date = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return (date if date.tzinfo else date.replace(tzinfo=timezone.utc)).timestamp()
    except (ValueError, OverflowError):
        return None


class DocumentPipeline:
    def __init__(self, *, planner, embedder, index, cache, snapshots=None, wiki=None,
                 live_reason=None, source_mode="auto", snapshot_signature=None):
        self.planner, self.embedder, self.index, self.cache = planner, embedder, index, cache
        self.snapshots, self.wiki = snapshots, wiki
        self.live_reason, self.source_mode = live_reason, source_mode
        self.snapshot_signature = snapshot_signature

    def _body(self, candidate: dict, *, snapshot: bool, refresh: bool) -> tuple[dict | None, bool]:
        """Resolve references through the newest body, never a question snapshot.

        Aliases account for Wikipedia redirects and selected-film ZIP paths.
        The canonical body is the only cache record containing full text. A
        successful newer live collection cannot be rolled back by an older
        snapshot fallback of the same document.
        """
        alias_key = ALIAS_CACHE_PREFIX + fingerprint({
            "candidate": candidate.get("candidate_id"),
            "source": "snapshot" if snapshot else "live",
            "snapshot": self.snapshot_signature if snapshot else None})
        alias = self.cache.get(alias_key)
        identity = alias.get("identity") if isinstance(alias, dict) else _document_cache_identity(candidate)
        if not refresh:
            cached = self.cache.get(BODY_CACHE_PREFIX + identity)
            if isinstance(cached, dict) and isinstance(cached.get("document"), dict):
                document = cached["document"]
                if isinstance(document.get("text"), str) and document["text"].strip():
                    return deepcopy(document), True
        document = (self.snapshots.fetch(candidate["candidate_id"]) if snapshot
                    else self.wiki.fetch_page(candidate["title"]))
        if not document or not isinstance(document.get("text"), str) or not document["text"].strip():
            return None, False
        identity = _document_cache_identity(document)
        previous = self.cache.get(BODY_CACHE_PREFIX + identity)
        previous = previous.get("document") if isinstance(previous, dict) else None
        if isinstance(previous, dict):
            old_at, new_at = _source_time(previous), _source_time(document)
            if (document.get("source_kind") == "snapshot"
                    and previous.get("source_kind") == "live"
                    and (old_at is None or new_at is None or new_at < old_at)):
                document = previous
        self.cache.put(BODY_CACHE_PREFIX + identity, {"document": document})
        self.cache.put(alias_key, {"identity": identity})
        return deepcopy(document), False

    def prepare(self, movie, question: str, history=None, *, refresh=False, progress=None) -> dict:
        def announce(label):
            if progress is not None:
                progress(label)
        history = [{"role": row["role"], "content": row["content"]} for row in (history or [])[-6:]]
        if history and history[-1] == {"role": "user", "content": question}:
            history = history[:-1]
        from dataclasses import asdict
        from movie_lab.document_llm import PROMPT_ROOT
        prompt_signature = fingerprint([(PROMPT_ROOT / name).read_text(encoding="utf-8")
                                        for name in ("extract_queries.txt", "select_documents.txt")])
        key = fingerprint({"version": PIPELINE_VERSION, "movie": asdict(movie), "question": question.strip(),
                           "history_unverified": history, "model": self.planner.model,
                           "prompt_signature": prompt_signature,
                           "source_mode": self.source_mode, "snapshot": self.snapshot_signature})
        report = {"movie_id": movie.movie_id, "question": question, "complete": False,
                  "collection_success": False, "index_success": False, "cache_hit": False,
                  "live_attempted": False, "live_search_success": False, "live_collection_success": False,
                  "live_reason": self.live_reason, "queries": [], "focus": "", "selection": {},
                  "documents": [], "rejected": [], "warnings": [], "stages": []}
        body_hits = 0
        initial_llm = self.planner.request_count
        initial_embed = self.embedder.request_count
        initial_live = self.wiki.request_count if self.wiki else 0
        try:
            # Stage-3 collection caches embedded complete old bodies in each
            # question. They are deliberately never promoted into this cache.
            selected_cache = None if refresh else self.cache.get(SELECTION_CACHE_PREFIX + key)
            if selected_cache:
                report.update(deepcopy(selected_cache["report"]))
                report["cache_hit"] = True
                report["collection_success"] = report["index_success"] = report["complete"] = False
                report["rejected"] = []
                documents, references = [], []
                announce("질문별 선별을 재사용하고 문서별 최신 본문을 확인하는 중")
                for reference in selected_cache["references"]:
                    document, hit = self._body(reference, snapshot=reference["source_kind"] == "snapshot",
                                               refresh=False)
                    body_hits += int(hit)
                    if not document:
                        report["rejected"].append({"title": reference["title"], "reason": "빈 본문"})
                        continue
                    identity = classify_document_identity(movie, document)
                    if identity.status == "불일치":
                        report["rejected"].append({"title": document["title"], "reason": identity.reason,
                                                   "identity": identity.status})
                        continue
                    if identity.status != "일치" and (not reference["selected"] or len(document["text"].strip()) < 120):
                        continue
                    documents.append({**document, "identity": identity.status, "identity_reason": identity.reason})
                    references.append(reference)
            else:
                announce("질문과 최근 대화에서 검색어를 추출하는 중")
                extracted = self.planner.extract(movie, question, history)
                report["queries"], report["focus"] = extracted["queries"], extracted.get("focus", "")
                report["stages"].append("검색어 추출 성공")
                candidates, snapshot = [], False
                if self.wiki is not None and self.source_mode != "snapshot":
                    report["live_attempted"] = True
                    try:
                        announce("위키백과 후보를 직렬 검색하는 중")
                        for query in report["queries"][:3]:
                            search_key = "wiki-search:" + fingerprint(query)
                            rows = None if refresh else self.cache.get(search_key)
                            if not rows:
                                rows = self.wiki.search(query)
                                if rows:
                                    self.cache.put(search_key, rows)
                            candidates.extend(rows)
                        report["live_search_success"] = bool(candidates)
                    except WikiError as error:
                        report["live_reason"] = error.category
                        candidates = []
                if not candidates:
                    snapshot = True
                    if self.snapshots is None:
                        raise WikiError("실시간 자료를 얻지 못했습니다. 스냅샷 ZIP 경로를 설정하세요")
                    announce("제공된 스냅샷에서 후보를 읽는 중")
                    candidates = self.snapshots.candidates(movie)
                documents, references = [], []
                for fallback_attempt in range(2):
                    unique = {row["candidate_id"]: row for row in candidates}
                    candidates = list(unique.values())[:30]
                    if not candidates:
                        raise WikiError("선택 영화의 문서 후보가 없습니다")
                    announce("후보 제목·요약을 모델로 선별하는 중")
                    selected = self.planner.select(movie, question, candidates)
                    report["selection"] = selected
                    report["candidate_titles"] = [{"candidate_id": row["candidate_id"], "title": row["title"]} for row in candidates]
                    selected_ids = set(selected["selected_ids"])
                    fetch_list = [row for row in candidates if row["candidate_id"] in selected_ids or _own_candidate(movie, row)]
                    # Own-film candidates are always checked; a validated one is
                    # included even when general relevance/length selection omits it.
                    fetch_list.sort(key=lambda row: not _own_candidate(movie, row))
                    announce("본문 수집·동명 작품 대조 중")
                    live_failed = False
                    for candidate in fetch_list[:7]:
                        try:
                            document, hit = self._body(candidate, snapshot=snapshot, refresh=refresh)
                            body_hits += int(hit)
                        except WikiError as error:
                            if not snapshot:
                                live_failed = True
                                report["live_reason"] = error.category
                                break
                            report["warnings"].append(error.category)
                            continue
                        if not document or not document.get("text", "").strip():
                            report["rejected"].append({"title": candidate["title"], "reason": "빈 본문"})
                            continue
                        identity = classify_document_identity(movie, document)
                        if identity.status == "불일치":
                            report["rejected"].append({"title": document["title"], "reason": identity.reason, "identity": identity.status})
                            continue
                        if identity.status != "일치" and candidate["candidate_id"] not in selected_ids:
                            continue
                        if identity.status != "일치" and len(document["text"].strip()) < 120:
                            report["rejected"].append({"title": document["title"], "reason": "배경 문서 본문 부족"})
                            continue
                        document = {**document, "identity": identity.status, "identity_reason": identity.reason}
                        documents.append(document)
                        references.append({**{key: candidate.get(key) for key in
                                               ("candidate_id", "document_id", "page_id", "title", "url")},
                                           "source_kind": "snapshot" if snapshot else "live",
                                           "selected": candidate["candidate_id"] in selected_ids})
                        if len(documents) >= 4:
                            break
                    if not snapshot and (live_failed or not documents) and self.snapshots is not None and fallback_attempt == 0:
                        snapshot, documents, references = True, [], []
                        candidates = self.snapshots.candidates(movie)
                        report["warnings"].append("실시간 본문 수집 실패 또는 빈 결과로 스냅샷 후보를 다시 선별했습니다")
                        continue
                    break
            if not documents:
                raise WikiError("작품 식별·질문 관련성 검사 후 사용할 문서가 없습니다")
            report["documents"] = [{key: row.get(key) for key in
                ("document_id", "candidate_id", "title", "url", "source_kind", "collected_at", "identity", "identity_reason")}
                for row in documents]
            report["collection_success"] = True
            report["live_collection_success"] = all(row["source_kind"] == "live" for row in documents)
            if not selected_cache:
                report["stages"].append("문서 수집·작품 대조 성공")
                # Reference-only question cache: no body can be restored from an
                # older question and overwrite a later refresh's active chunks.
                self.cache.put(SELECTION_CACHE_PREFIX + key,
                               {"references": references, "report": deepcopy(report)})
            announce("청킹·변경분 임베딩·외부 컬렉션 저장을 확인하는 중")
            indexed = self.index.index_documents(movie.movie_id, documents, self.embedder)
            report["index"] = indexed
            report["index_success"] = indexed["complete"]
            report["complete"] = report["collection_success"] and report["index_success"]
            if indexed["complete"]:
                report["stages"].append("외부 문서 색인 검증 성공")
            else:
                report["error"] = {"category": indexed["error_category"], "http_status": indexed["http_status"]}
        except Exception as error:
            report["error"] = safe_error(error)
        report["calls"] = {"chat": self.planner.request_count - initial_llm,
                           "embedding": self.embedder.request_count - initial_embed,
                           "wiki": (self.wiki.request_count if self.wiki else 0) - initial_live}
        report["live_attempted_this_run"] = report["calls"]["wiki"] > 0
        report["document_cache_hits"] = body_hits
        report["llm_audit"] = list(self.planner.audit)
        report["structured_mode"] = self.planner.mode
        report["chat_model"] = self.planner.model
        report["reported_chat_model"] = self.planner.reported_model
        return report

    def close(self):
        self.index.close()


def create_document_pipeline(snapshot_archive=None, source_mode="auto") -> DocumentPipeline:
    planner = create_document_planner()
    from movie_lab.index import read_index_config
    from movie_lab.config import resolve_index_path
    embedding_config = read_index_config(resolve_index_path())
    embedder = create_gms_embeddings(embedding_config.model_id, embedding_config.dimension)
    size, overlap = document_chunk_settings()
    index = ExternalIndex(resolve_document_index_path(), embedder.model, embedding_config.dimension, ChunkConfig(size, overlap))
    wiki, reason = None, None
    if source_mode != "snapshot":
        try:
            wiki = create_wiki_client()
        except LiveUnavailable as error:
            reason = error.category
    else:
        reason = "스냅샷 모드를 명시적으로 선택했습니다"
    path = resolve_snapshot_path(snapshot_archive)
    snapshots = SnapshotRepository(path) if path.is_file() else None
    attributes = path.stat() if path.is_file() else None
    signature = {"mtime_ns": attributes.st_mtime_ns, "size": attributes.st_size} if attributes else None
    return DocumentPipeline(planner=planner, embedder=embedder, index=index,
                            cache=SuccessCache(resolve_document_cache_path()), snapshots=snapshots,
                            wiki=wiki, live_reason=reason, source_mode=source_mode, snapshot_signature=signature)
