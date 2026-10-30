"""Persistent movie metadata index. No API calls occur when opening/inspecting it."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from movie_lab.data import Movie, build_index_text


METADATA_TEXT_VERSION = "movie-metadata-v1"
MANIFEST_NAME = "metadata_index.json"


class IndexConfigurationError(ValueError):
    """Safe configuration error, without paths, credentials or server bodies."""


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _write_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


@dataclass(frozen=True)
class IndexConfig:
    model_id: str
    dimension: int
    text_version: str = METADATA_TEXT_VERSION

    def __post_init__(self):
        if not isinstance(self.model_id, str) or not self.model_id.strip():
            raise IndexConfigurationError("임베딩 모델 설정이 없습니다.")
        if type(self.dimension) is not int or self.dimension <= 0:
            raise IndexConfigurationError("검증된 임베딩 차원이 필요합니다.")
        if not isinstance(self.text_version, str) or not self.text_version:
            raise IndexConfigurationError("텍스트 구성 버전이 필요합니다.")

    @property
    def collection_name(self) -> str:
        signature = _digest(json.dumps(asdict(self), sort_keys=True))[:12]
        return f"movie_metadata_v1_{signature}"


def read_index_config(path: Path) -> IndexConfig:
    try:
        value = json.loads((Path(path) / MANIFEST_NAME).read_text(encoding="utf-8"))
        config = IndexConfig(**value["config"])
        if value.get("schema_version") != 1 or value.get("collection") != config.collection_name:
            raise IndexConfigurationError("저장소 설정 파일이 현재 규약과 다릅니다.")
        return config
    except IndexConfigurationError:
        raise
    except (OSError, ValueError, TypeError, KeyError) as error:
        raise IndexConfigurationError("색인 설정을 읽을 수 없습니다.") from error


class MetadataIndex:
    def __init__(self, path: Path, config: IndexConfig, *, create: bool = True):
        self.path = Path(path)
        self.config = config
        manifest = self.path / MANIFEST_NAME
        if manifest.exists():
            if read_index_config(self.path) != config:
                raise IndexConfigurationError("기존 색인의 모델·차원·텍스트 버전이 다릅니다. 별도 저장 경로를 사용하세요.")
        elif not create:
            raise IndexConfigurationError("메타데이터 색인이 없습니다.")
        if not create and not (self.path / "chroma.sqlite3").is_file():
            raise IndexConfigurationError("Chroma 저장 파일이 없습니다.")

        import chromadb
        from chromadb.config import Settings

        self.client = chromadb.PersistentClient(
            path=str(self.path), settings=Settings(anonymized_telemetry=False, allow_reset=False)
        )
        header = {"scope": "movie_metadata", "embedding_model": config.model_id,
                  "embedding_dimension": config.dimension, "text_version": config.text_version}
        try:
            if create:
                self.collection = self.client.get_or_create_collection(
                    name=config.collection_name, embedding_function=None, metadata=header,
                    configuration={"hnsw": {"space": "cosine"}},
                )
            else:
                self.collection = self.client.get_collection(name=config.collection_name, embedding_function=None)
            if any((self.collection.metadata or {}).get(key) != value for key, value in header.items()):
                raise IndexConfigurationError("컬렉션의 임베딩 설정이 저장소 설정과 다릅니다.")
            if create and not manifest.exists():
                _write_json(manifest, {"schema_version": 1, "collection": config.collection_name,
                                      "config": asdict(config), "id_prefix": "meta:",
                                      "scope": "movie_metadata", "provider": "GMS"})
        except Exception:
            self.client.close()
            raise

    def close(self) -> None:
        self.client.close()

    def _check_embedder(self, embedder: Any) -> None:
        if getattr(embedder, "model", None) != self.config.model_id:
            raise IndexConfigurationError("색인과 임베딩 클라이언트의 모델이 다릅니다.")
        dimension = getattr(embedder, "dimensions", None)
        if dimension is not None and dimension != self.config.dimension:
            raise IndexConfigurationError("색인과 임베딩 클라이언트의 차원이 다릅니다.")

    def _vector_ok(self, vector: Any) -> bool:
        try:
            return len(vector) == self.config.dimension and all(math.isfinite(float(v)) for v in vector)
        except (TypeError, ValueError, OverflowError):
            return False

    def _records(self, movie_ids: list[str], *, vectors: bool = True) -> dict[str, tuple]:
        records = {}
        include = ["documents", "metadatas"] + (["embeddings"] if vectors else [])
        for start in range(0, len(movie_ids), 128):
            result = self.collection.get(ids=[f"meta:{mid}" for mid in movie_ids[start:start + 128]], include=include)
            embeddings = result.get("embeddings")
            for position, identifier in enumerate(result["ids"]):
                records[identifier] = (result["documents"][position], result["metadatas"][position],
                                       embeddings[position] if embeddings is not None else None)
        return records

    def _matches(self, movie: Movie, record: tuple | None, *, vectors: bool = True) -> bool:
        if record is None:
            return False
        text = build_index_text(movie)
        document, metadata, vector = record
        return (document == text and isinstance(metadata, dict)
                and all(metadata.get(key) == value for key, value in self._metadata(movie, text).items())
                and (not vectors or self._vector_ok(vector)))

    def _metadata(self, movie: Movie, text: str) -> dict:
        return {"movie_id": movie.movie_id, "title": movie.title,
                "original_title": movie.original_title,
                "year": movie.year if movie.year is not None else -1,
                "director": ", ".join(movie.director), "genres": ", ".join(movie.genres),
                "text_hash": _digest(text), "text_version": self.config.text_version}

    def verify_movies(self, movies: Mapping[str, Movie], *, check_vectors: bool = True) -> dict:
        records = self._records(list(movies), vectors=check_vectors)
        missing, mismatched = [], []
        for movie_id, movie in movies.items():
            record = records.get(f"meta:{movie_id}")
            if record is None:
                missing.append(movie_id)
            elif not self._matches(movie, record, vectors=check_vectors):
                mismatched.append(movie_id)
        count = self.collection.count()
        return {"total": len(movies), "verified": len(movies) - len(missing) - len(mismatched),
                "missing": missing, "mismatched": mismatched, "count": count,
                "complete": not missing and not mismatched and count == len(movies)}

    def index_movies(self, movies: Mapping[str, Movie], embedder: Any, batch_size: int = 64, *, on_progress=None) -> dict:
        self._check_embedder(embedder)
        if type(batch_size) is not int or batch_size <= 0:
            raise IndexConfigurationError("배치 크기는 양의 정수여야 합니다.")
        before = self._records(list(movies))
        skipped_ids = {mid for mid, movie in movies.items() if self._matches(movie, before.get(f"meta:{mid}"))}
        pending = [mid for mid in movies if mid not in skipped_ids]
        embedded = 0
        error_category = None
        http_status = None
        for start in range(0, len(pending), batch_size):
            batch = pending[start:start + batch_size]
            texts = [build_index_text(movies[mid]) for mid in batch]
            try:
                vectors = embedder.embed_documents(texts)
                embedded += len(vectors)
                if len(vectors) != len(batch) or any(not self._vector_ok(vector) for vector in vectors):
                    raise IndexConfigurationError("저장할 벡터의 개수 또는 차원이 올바르지 않습니다.")
                metadatas = [self._metadata(movies[mid], text) for mid, text in zip(batch, texts)]
                self.collection.upsert(ids=[f"meta:{mid}" for mid in batch],
                                       documents=texts, metadatas=metadatas, embeddings=vectors)
                saved = self._records(batch)
                if any(not self._matches(movies[mid], saved.get(f"meta:{mid}")) for mid in batch):
                    raise IndexConfigurationError("배치 저장 결과를 확인하지 못했습니다.")
                if on_progress is not None:
                    on_progress(self.collection.count(), len(movies))
            except Exception as error:
                from movie_lab.embeddings import failure_details
                detail = failure_details(error)
                error_category, http_status = detail["category"], detail["http_status"]
                break
        # The database is authoritative even if upsert saved a subset then raised.
        verification = self.verify_movies(movies)
        failed = [mid for mid in movies if mid in set(verification["missing"] + verification["mismatched"])]
        saved_changed = set(pending) - set(failed)
        added = sum(f"meta:{mid}" not in before for mid in saved_changed)
        report = {"total": len(movies), "added": added, "updated": len(saved_changed) - added,
                  "skipped": len(skipped_ids), "failed": failed, "count": verification["count"],
                  "embedded": embedded, "complete": verification["complete"] and error_category is None,
                  "verified": verification["verified"], "error_category": error_category,
                  "http_status": http_status,
                  "collection": self.config.collection_name, "config": asdict(self.config)}
        _write_json(self.path / "last_index_run.json", report)
        return report

    def _search_scope(self, k: int, allowed_movie_ids: Sequence[str] | None) -> tuple[int, list[str] | None]:
        if type(k) is not int or k <= 0:
            raise IndexConfigurationError("검색 개수는 양의 정수여야 합니다.")
        if allowed_movie_ids is None:
            return min(k, self.collection.count()), None
        if (not isinstance(allowed_movie_ids, Sequence) or isinstance(allowed_movie_ids, (str, bytes))
                or any(not isinstance(mid, str) or not mid.strip() for mid in allowed_movie_ids)):
            raise IndexConfigurationError("허용 영화 ID 목록 형식이 올바르지 않습니다.")
        identifiers = sorted({f"meta:{mid}" for mid in allowed_movie_ids})
        if not identifiers:
            return 0, []
        saved = self.collection.get(ids=identifiers, include=[])["ids"]
        if set(saved) != set(identifiers):
            raise IndexConfigurationError("조건에 맞는 영화의 저장 문서가 누락되어 제한 검색을 중단했습니다.")
        return min(k, len(identifiers)), identifiers

    def _query_vector(self, vector: Any, count: int, identifiers: list[str] | None) -> list[dict]:
        if not count:
            return []
        if not self._vector_ok(vector):
            raise IndexConfigurationError("질문 임베딩 차원이 색인과 다릅니다.")
        options = {"query_embeddings": [vector], "n_results": count,
                   "include": ["metadatas", "distances"]}
        if identifiers is not None:
            options["ids"] = identifiers
        # A rejected/failed restricted query must never retry without its scope.
        result = self.collection.query(**options)
        try:
            ids, metadatas, distances = result["ids"][0], result["metadatas"][0], result["distances"][0]
        except (KeyError, IndexError, TypeError) as error:
            raise IndexConfigurationError("검색 응답의 문서 구조가 올바르지 않습니다.") from error
        if len(ids) != len(metadatas) or len(ids) != len(distances) or len(set(ids)) != len(ids):
            raise IndexConfigurationError("검색 응답의 문서 개수 또는 ID가 올바르지 않습니다.")
        hits = []
        for identifier, metadata, distance in zip(ids, metadatas, distances):
            if (not isinstance(metadata, dict) or not isinstance(metadata.get("movie_id"), str)
                    or identifier != f"meta:{metadata['movie_id']}"
                    or (identifiers is not None and identifier not in identifiers)
                    or not isinstance(distance, (int, float)) or not math.isfinite(distance)):
                raise IndexConfigurationError("검색 응답이 허용 영화 ID 또는 저장 문서와 대응하지 않습니다.")
            hits.append({"document_id": identifier, "movie_id": metadata["movie_id"],
                         "title": metadata["title"], "original_title": metadata.get("original_title", ""),
                         "year": metadata.get("year") if metadata.get("year") != -1 else None,
                         "director": metadata.get("director", ""), "genres": metadata.get("genres", ""),
                         "distance": float(distance)})
        return hits

    def search(self, query: str, embedder: Any, k: int = 5,
               *, allowed_movie_ids: Sequence[str] | None = None) -> list[dict]:
        self._check_embedder(embedder)
        if not isinstance(query, str) or not query.strip():
            raise IndexConfigurationError("빈 검색어입니다.")
        count, identifiers = self._search_scope(k, allowed_movie_ids)
        if not count:
            return []
        return self._query_vector(embedder.embed_query(query), count, identifiers)

    def search_vector(self, vector: Any, k: int = 5,
                      *, allowed_movie_ids: Sequence[str] | None = None) -> list[dict]:
        """Compare scopes with the exact same validated query vector, API-free."""
        count, identifiers = self._search_scope(k, allowed_movie_ids)
        return self._query_vector(vector, count, identifiers)

    def status(self) -> dict:
        return {"state": "ready" if self.collection.count() else "empty",
                "count": self.collection.count(), "collection": self.config.collection_name,
                "config": asdict(self.config)}

    def get_movie_source(self, movie: Movie) -> dict:
        """Read the selected film by stable ID; similarity cannot displace it.

        This read performs no embedding. A stale/missing row is rejected so a
        caller can explicitly use the supplied metadata file as its fallback.
        """
        record = self._records([movie.movie_id], vectors=False).get(f"meta:{movie.movie_id}")
        if not self._matches(movie, record, vectors=False):
            raise IndexConfigurationError("선택 영화의 저장 메타데이터가 없거나 현재 파일과 다릅니다.")
        return {"document_id": f"meta:{movie.movie_id}", "movie_id": movie.movie_id,
                "title": f"{movie.title or movie.original_title} · 영화 메타데이터",
                "url": movie.tmdb_url, "text": record[0], "source_kind": "metadata",
                "scope": "movie_metadata", "identity": "일치",
                "identity_reason": "안정 ID와 현재 제공 메타데이터의 일치를 확인했습니다."}


def inspect_index_status(path: Path, movies: Mapping[str, Movie]) -> dict:
    """Read only local state; no dotenv, API clients or embedding calls."""
    if not (Path(path) / MANIFEST_NAME).exists():
        return {"state": "unavailable", "count": None} if (Path(path) / "chroma.sqlite3").exists() else {"state": "absent", "count": 0}
    store = None
    try:
        config = read_index_config(path)
        if config.text_version != METADATA_TEXT_VERSION:
            return {"state": "incompatible", "count": None}
        store = MetadataIndex(path, config, create=False)
        verification = store.verify_movies(movies, check_vectors=False)
        store.close()
        store = None
        return {"state": "ready" if verification["complete"] else "partial", **verification,
                "collection": config.collection_name, "config": asdict(config)}
    except Exception:
        return {"state": "unavailable", "count": None}
    finally:
        if store is not None:
            try:
                store.close()
            except Exception:
                pass  # The operation above already returned a safe unavailable state.
