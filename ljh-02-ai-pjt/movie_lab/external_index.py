"""Movie-scoped external documents: boundary-aware chunks and resumable Chroma writes.

Opening this module or a store never reads credentials or calls an embedding API.
Stored vectors are the authority for resuming interrupted writes. Uncommitted chunks
are excluded from search, and old generations are removed only after replacement
chunks have been read back and verified.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from bisect import bisect_right
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit, urlunsplit

from movie_lab.index import IndexConfigurationError


CHUNK_ALGORITHM = "paragraph-sentence-v1"


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ChunkConfig:
    size: int = 900
    overlap: int = 120

    def __post_init__(self) -> None:
        if type(self.size) is not int or self.size < 40:
            raise IndexConfigurationError("청크 크기는 40자 이상의 정수여야 합니다.")
        if type(self.overlap) is not int or not 0 <= self.overlap < self.size:
            raise IndexConfigurationError("청크 중복 길이는 0 이상 크기 미만이어야 합니다.")

    @property
    def version(self) -> str:
        return f"{CHUNK_ALGORITHM}:{self.size}:{self.overlap}"


def _normalized_body(document: dict) -> str:
    body = document.get("text", document.get("body", ""))
    if not isinstance(body, str):
        return ""
    return "\n".join(line.rstrip() for line in body.replace("\r\n", "\n").replace("\r", "\n").split("\n")).strip()


def _document_id(document: dict) -> str:
    url = document.get("url", "")
    if isinstance(url, str) and url.strip():
        parts = urlsplit(url.strip())
        if parts.scheme in {"http", "https"} and parts.netloc:
            canonical = urlunsplit(("https", parts.netloc.casefold(), unquote(parts.path).rstrip("/"), parts.query, ""))
            return "doc:" + _hash(canonical)
    identifier = document.get("document_id", document.get("page_id"))
    if identifier is not None and str(identifier).strip():
        return "doc:" + _hash(f"id:{identifier}")
    title = document.get("title")
    if not isinstance(title, str) or not title.strip():
        raise IndexConfigurationError("외부 문서의 URL, ID 또는 제목이 필요합니다.")
    return "doc:" + _hash("title:" + title.strip())


def _split_text(body: str, config: ChunkConfig) -> list[str]:
    # Prefer paragraph endings, then sentence endings. Long sentences still have
    # a whitespace/hard boundary fallback so a chunk never exceeds the limit.
    paragraphs = [match.end() for match in re.finditer(r"\n\s*\n", body)]
    sentences = [match.end() for match in re.finditer(r"(?<=[.!?。！？])\s+", body)]
    result, start = [], 0
    while start < len(body):
        limit = min(start + config.size, len(body))
        end = limit
        if limit < len(body):
            minimum = start + max(config.overlap + 1, config.size // 2)
            for boundaries in (paragraphs, sentences):
                position = bisect_right(boundaries, limit) - 1
                if position >= 0 and boundaries[position] >= minimum:
                    end = boundaries[position]
                    break
            else:
                whitespace = [match.end() + start for match in re.finditer(r"\s+", body[start:limit])]
                available = [point for point in whitespace if point >= minimum]
                if available:
                    end = available[-1]
        text = body[start:end].strip()
        if text:
            result.append(text)
        if end >= len(body):
            break
        start = max(start + 1, end - config.overlap)
    return result


def chunk_document(document: dict, movie_id: str, config: ChunkConfig | None = None) -> list[dict]:
    """Return stable IDs and flat provenance metadata, without embedding anything."""
    config = config or ChunkConfig()
    if not isinstance(movie_id, str) or not movie_id.strip():
        raise IndexConfigurationError("영화 ID가 필요합니다.")
    if not isinstance(document, dict):
        raise IndexConfigurationError("외부 문서는 객체여야 합니다.")
    body = _normalized_body(document)
    if not body:
        return []
    document_id, body_hash = _document_id(document), _hash(body)
    generation = _hash(f"{movie_id}\0{document_id}\0{body_hash}\0{config.version}")
    metadata = {
        "movie_id": movie_id, "document_id": document_id,
        "title": str(document.get("title") or "제목 없음"),
        "url": str(document.get("url") or ""),
        "source_kind": str(document.get("source_kind") or document.get("source") or "unknown"),
        "collected_at": str(document.get("collected_at") or ""),
        "body_hash": body_hash, "chunk_version": config.version,
        "generation": generation,
    }
    return [{"id": f"ext:{generation}:{index}", "text": text,
             "metadata": {**metadata, "chunk_index": index}}
            for index, text in enumerate(_split_text(body, config))]


class ExternalIndex:
    """A collection distinct from metadata, with mandatory movie-scoped searches."""

    def __init__(self, path: Path, model_id: str, dimension: int,
                 chunk_config: ChunkConfig | None = None, *, create: bool = True):
        if not isinstance(model_id, str) or not model_id.strip() or type(dimension) is not int or dimension <= 0:
            raise IndexConfigurationError("외부 색인의 임베딩 모델과 차원이 필요합니다.")
        self.path, self.model_id, self.dimension = Path(path), model_id, dimension
        self.chunk_config = chunk_config or ChunkConfig()
        signature = _hash(json.dumps({"model": model_id, "dimension": dimension,
                                      "algorithm": CHUNK_ALGORITHM}, sort_keys=True))[:12]
        self.collection_name = f"movie_external_v1_{signature}"
        import chromadb
        from chromadb.config import Settings
        self.client = chromadb.PersistentClient(path=str(self.path),
                                               settings=Settings(anonymized_telemetry=False, allow_reset=False))
        header = {"scope": "movie_external", "embedding_model": model_id,
                  "embedding_dimension": dimension, "chunk_algorithm": CHUNK_ALGORITHM}
        try:
            if create:
                self.collection = self.client.get_or_create_collection(
                    name=self.collection_name, embedding_function=None, metadata=header,
                    configuration={"hnsw": {"space": "cosine"}})
            else:
                self.collection = self.client.get_collection(name=self.collection_name, embedding_function=None)
            if any((self.collection.metadata or {}).get(key) != value for key, value in header.items()):
                raise IndexConfigurationError("외부 컬렉션 설정이 일치하지 않습니다.")
        except Exception:
            self.client.close()
            raise

    def close(self) -> None:
        self.client.close()

    def _check_embedder(self, embedder: Any) -> None:
        if (getattr(embedder, "model", None) != self.model_id
                or getattr(embedder, "dimensions", self.dimension) not in (None, self.dimension)):
            raise IndexConfigurationError("외부 색인과 임베딩 모델·차원이 일치하지 않습니다.")

    def _vector_ok(self, value: Any) -> bool:
        try:
            return (len(value) == self.dimension and all(math.isfinite(float(item)) for item in value)
                    and sum(float(item) ** 2 for item in value) > 0)
        except (TypeError, ValueError, OverflowError):
            return False

    def _records(self, ids: list[str]) -> dict[str, tuple]:
        records = {}
        for start in range(0, len(ids), 128):
            result = self.collection.get(ids=ids[start:start + 128], include=["documents", "metadatas", "embeddings"])
            vectors = result.get("embeddings")
            for index, identifier in enumerate(result["ids"]):
                records[identifier] = (result["documents"][index], result["metadatas"][index],
                                       vectors[index] if vectors is not None else None)
        return records

    def _matches(self, chunk: dict, record: tuple | None) -> bool:
        # Provenance may change from snapshot to a later live fetch with identical
        # text; updating it must not spend another embedding call.
        if record is None:
            return False
        text, metadata, vector = record
        return (text == chunk["text"] and isinstance(metadata, dict)
                and all(metadata.get(key) == chunk["metadata"][key] for key in
                        ("movie_id", "document_id", "body_hash", "chunk_version", "chunk_index", "generation"))
                and self._vector_ok(vector))

    def index_documents(self, movie_id: str, documents: list[dict], embedder: Any) -> dict:
        self._check_embedder(embedder)
        if not isinstance(movie_id, str) or not movie_id.strip():
            raise IndexConfigurationError("영화 ID가 필요합니다.")
        grouped, rejected = {}, 0
        for document in documents:
            chunks = chunk_document(document, movie_id, self.chunk_config)
            if not chunks:
                rejected += 1
                continue
            # A URL is one logical document; accidental repeated candidates never
            # create parallel entries in one preparation request.
            grouped[chunks[0]["metadata"]["document_id"]] = chunks
        embedded = skipped = indexed_docs = 0
        chunk_ids, failed, removed = [], [], 0
        error_category, http_status = None, None
        for document_id, chunks in grouped.items():
            ids = [chunk["id"] for chunk in chunks]
            try:
                records = self._records(ids)
                pending = [chunk for chunk in chunks if not self._matches(chunk, records.get(chunk["id"]))]
                skipped += len(chunks) - len(pending)
                # Bound request size and allow exact reuse of a successfully
                # persisted prefix if the process is interrupted later.
                for start in range(0, len(pending), 64):
                    batch = pending[start:start + 64]
                    vectors = embedder.embed_documents([chunk["text"] for chunk in batch])
                    embedded += len(vectors)
                    if len(vectors) != len(batch) or any(not self._vector_ok(vector) for vector in vectors):
                        raise IndexConfigurationError("외부 문서 임베딩의 개수·차원이 올바르지 않습니다.")
                    self.collection.upsert(ids=[chunk["id"] for chunk in batch],
                                           documents=[chunk["text"] for chunk in batch], embeddings=vectors,
                                           metadatas=[{**chunk["metadata"], "ready": False} for chunk in batch])
                saved = self._records(ids)
                if any(not self._matches(chunk, saved.get(chunk["id"])) for chunk in chunks):
                    raise IndexConfigurationError("외부 청크 저장 결과를 확인하지 못했습니다.")
                updates = [chunk for chunk in chunks if saved[chunk["id"]][1] != {**chunk["metadata"], "ready": True}]
                if updates:
                    self.collection.update(ids=[chunk["id"] for chunk in updates],
                                           metadatas=[{**chunk["metadata"], "ready": True} for chunk in updates])
                confirmed = self._records(ids)
                if any(not self._matches(chunk, confirmed.get(chunk["id"]))
                       or confirmed[chunk["id"]][1].get("ready") is not True for chunk in chunks):
                    raise IndexConfigurationError("외부 청크 활성화 결과를 확인하지 못했습니다.")
                previous = self.collection.get(where={"$and": [{"movie_id": movie_id}, {"document_id": document_id}]}, include=[])
                stale = list(set(previous["ids"]) - set(ids))
                if stale:
                    self.collection.delete(ids=stale)
                    remaining = self.collection.get(ids=stale, include=[])
                    if remaining["ids"]:
                        raise IndexConfigurationError("이전 청크 정리 결과를 확인하지 못했습니다.")
                    removed += len(stale)
                indexed_docs += 1
                chunk_ids.extend(ids)
            except Exception as error:
                from movie_lab.embeddings import failure_details
                detail = failure_details(error)
                error_category, http_status = detail["category"], detail["http_status"]
                failed.append(document_id)
                # Continue no further API calls once one document fails.
                break
        total = len(self.collection.get(where={"movie_id": movie_id}, include=[])["ids"])
        return {"collection": self.collection_name, "collected_docs": len(documents),
                "unique_docs": len(grouped), "indexed_docs": indexed_docs, "rejected_docs": rejected,
                "chunk_count": len(chunk_ids), "chunk_ids": chunk_ids, "embedded": embedded,
                "skipped": skipped, "removed": removed, "stored_movie_chunks": total,
                "failed": failed, "complete": bool(grouped) and not rejected and indexed_docs == len(grouped),
                "error_category": error_category, "http_status": http_status,
                "chunk_version": self.chunk_config.version, "model_id": self.model_id, "dimension": self.dimension}

    def search(self, movie_id: str, query: str, embedder: Any, k: int = 3) -> list[dict]:
        self._check_embedder(embedder)
        if (not isinstance(movie_id, str) or not movie_id.strip() or not isinstance(query, str)
                or not query.strip() or type(k) is not int or k <= 0):
            raise IndexConfigurationError("외부 검색에는 영화 ID·질문·양의 결과 수가 필요합니다.")
        where = {"$and": [{"movie_id": movie_id}, {"ready": True}]}
        count = len(self.collection.get(where=where, include=[])["ids"])
        if not count:
            return []
        vector = embedder.embed_query(query)
        if not self._vector_ok(vector):
            raise IndexConfigurationError("외부 검색 임베딩 차원이 일치하지 않습니다.")
        result = self.collection.query(query_embeddings=[vector], n_results=min(k, count), where=where,
                                       include=["documents", "metadatas", "distances"])
        hits = []
        for identifier, text, metadata, distance in zip(result["ids"][0], result["documents"][0],
                                                       result["metadatas"][0], result["distances"][0]):
            if metadata.get("movie_id") != movie_id:
                raise IndexConfigurationError("외부 검색에서 영화 ID 격리를 확인하지 못했습니다.")
            hits.append({"id": identifier, "text": text, **metadata, "distance": float(distance)})
        return hits

    def ready_documents(self, movie_id: str) -> list[dict]:
        """Read this film's committed chunks for local keyword candidates.

        No embedding or whole-catalogue read occurs. The same movie/ready
        predicate used in semantic search also protects this local read.
        """
        if not isinstance(movie_id, str) or not movie_id.strip():
            raise IndexConfigurationError("외부 청크 조회에는 영화 ID가 필요합니다.")
        result = self.collection.get(where={"$and": [{"movie_id": movie_id}, {"ready": True}]},
                                     include=["documents", "metadatas"])
        rows = []
        for identifier, text, metadata in zip(result["ids"], result["documents"], result["metadatas"]):
            if metadata.get("movie_id") != movie_id or metadata.get("ready") is not True:
                raise IndexConfigurationError("외부 청크 조회의 영화·준비 상태를 확인하지 못했습니다.")
            rows.append({"id": identifier, "text": text, **metadata})
        return rows
