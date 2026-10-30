"""Local movie metadata and a small, conservative snapshot identity check.

This module performs no network or model calls. The identity check only examines
the title and opening paragraph of a film's own article; it does not classify or
clean the complete collection of background documents.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, overload


class DataLoadError(ValueError):
    """An actionable local-data error, without exposing the document contents."""


@dataclass(frozen=True)
class Movie:
    movie_id: str
    title: str
    original_title: str
    release_date: str
    year: int | None
    genres: tuple[str, ...]
    director: tuple[str, ...]
    cast: tuple[str, ...]
    overview: str
    runtime: int | None
    original_language: str
    production_countries: tuple[str, ...]
    vote_average: float | None
    vote_count: int | None
    tmdb_url: str


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _texts(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(text for item in value if (text := _text(item)))


@overload
def _number(value: Any, *, integer: Literal[True]) -> int | None: ...


@overload
def _number(value: Any, *, integer: Literal[False] = False) -> float | None: ...


def _number(value: Any, *, integer: bool = False) -> int | float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(number):
        return None
    if integer:
        return int(number) if number.is_integer() else None
    return number


def _movie_id(value: Any, row: int) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise DataLoadError(f"영화 데이터 {row}번째 항목의 movie_id는 문자열 또는 정수여야 합니다.")
    movie_id = str(value).strip()
    if not movie_id:
        raise DataLoadError(f"영화 데이터 {row}번째 항목에 movie_id가 없습니다.")
    return movie_id


def load_movies(path: Path) -> dict[str, Movie]:
    """Read a JSON list and normalize its IDs and optional metadata fields.

    Required identity fields fail explicitly rather than quietly losing records.
    Missing descriptive fields remain empty; neither the record count nor a
    particular machine's data directory is fixed in the application logic.
    """
    path = Path(path)
    try:
        with path.open("r", encoding="utf-8-sig") as file:
            records = json.load(file)
    except FileNotFoundError as exc:
        raise DataLoadError(f"영화 데이터 파일을 찾을 수 없습니다: {path}") from exc
    except json.JSONDecodeError as exc:
        raise DataLoadError(
            f"영화 데이터의 JSON 형식이 올바르지 않습니다: {path} "
            f"({exc.lineno}행 {exc.colno}열)."
        ) from exc
    except UnicodeError as exc:
        raise DataLoadError(f"영화 데이터는 UTF-8 JSON 파일이어야 합니다: {path}") from exc
    except OSError as exc:
        raise DataLoadError(f"영화 데이터 파일을 읽을 수 없습니다. 경로와 권한을 확인하세요: {path}") from exc

    if not isinstance(records, list):
        raise DataLoadError("영화 데이터의 최상위 값은 영화 객체의 JSON 목록이어야 합니다.")
    if not records:
        raise DataLoadError("영화 데이터 목록이 비어 있습니다.")

    movies: dict[str, Movie] = {}
    for row, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            raise DataLoadError(f"영화 데이터 {row}번째 항목은 JSON 객체여야 합니다.")
        movie_id = _movie_id(record.get("movie_id"), row)
        if movie_id in movies:
            raise DataLoadError(f"정규화한 movie_id가 중복됩니다: {movie_id}")
        movies[movie_id] = Movie(
            movie_id=movie_id,
            title=_text(record.get("title")),
            original_title=_text(record.get("original_title")),
            release_date=_text(record.get("release_date")),
            year=_number(record.get("year"), integer=True),
            genres=_texts(record.get("genres")),
            director=_texts(record.get("director")),
            cast=_texts(record.get("cast")),
            overview=_text(record.get("overview")),
            runtime=_number(record.get("runtime"), integer=True),
            original_language=_text(record.get("original_language")),
            production_countries=_texts(record.get("production_countries")),
            vote_average=_number(record.get("vote_average")),
            vote_count=_number(record.get("vote_count"), integer=True),
            tmdb_url=_text(record.get("tmdb_url")),
        )
    return movies


def movie_label(movie: Movie) -> str:
    """Display homonymous films distinctly while the widget value remains an ID."""
    title = movie.title or movie.original_title or "제목 미상"
    year = str(movie.year) if movie.year is not None else "연도 미상"
    director = ", ".join(movie.director) or "감독 정보 없음"
    return f"{title} ({year}) · {director} · ID {movie.movie_id}"


def build_index_text(movie: Movie) -> str:
    """Build one reproducible metadata document; this does not create an index."""
    missing = "제공되지 않음"

    def shown(value: Any) -> str:
        if isinstance(value, tuple):
            return ", ".join(value) or missing
        return str(value) if value is not None and value != "" else missing

    fields = (
        ("영화 ID", movie.movie_id),
        ("제목", movie.title),
        ("원제", movie.original_title),
        ("개봉일", movie.release_date),
        ("연도", movie.year),
        ("감독", movie.director),
        ("장르", movie.genres),
        ("출연", movie.cast),
        ("줄거리", movie.overview),
        ("상영 시간(분)", movie.runtime),
        ("원어", movie.original_language),
        ("제작 국가", movie.production_countries),
        ("TMDB 평점", movie.vote_average),
        ("TMDB 평가 수", movie.vote_count),
        ("메타데이터 출처", movie.tmdb_url),
    )
    return "\n".join(f"{label}: {shown(value)}" for label, value in fields)


@dataclass(frozen=True)
class IdentityCheck:
    status: Literal["일치", "불일치", "확인 필요"]
    reason: str


def _normalized_title(value: str) -> str:
    # Only remove a trailing year/film qualifier, not arbitrary parenthetical
    # text that might be part of the actual title.
    value = re.sub(r"\s*\((?:\d{4}년?\s*)?(?:영화|film)?\)\s*$", "", value, flags=re.I)
    return re.sub(r"[\W_]+", "", value.casefold())


def classify_snapshot_identity(movie: Movie, document: Mapping[str, Any]) -> IdentityCheck:
    """Conservatively compare a putative own-film article, not all background.

    A shared title or a stored movie_id does not prove identity. A release year
    must be attached to film language in the opening paragraph, or explicitly
    appear in the title qualifier. Unrelated/background documents are left for
    later relevance selection and are never rejected just for lacking a year.
    """
    title = _text(document.get("title"))
    text = _text(document.get("text"))
    film_titles = {
        normalized
        for value in (movie.title, movie.original_title)
        if (normalized := _normalized_title(value))
    }
    if not title or not film_titles or _normalized_title(title) not in film_titles:
        return IdentityCheck("확인 필요", "영화 자체 문서로 식별되지 않은 배경/기타 문서입니다. 연도 누락만으로 제외하지 않습니다.")
    if not text:
        return IdentityCheck("확인 필요", "제목은 같지만 본문이 없어 작품을 확인할 수 없습니다.")

    opening = re.split(r"\n\s*\n", text, maxsplit=1)[0][:800]
    if not re.search(r"영화|\bfilm\b|\bmovie\b", opening, flags=re.I):
        return IdentityCheck("확인 필요", "같은 제목이지만 첫 문단에서 영화 문서임을 확인하지 못했습니다.")
    years = set()
    for pattern, value in (
        (r"\((\d{4})년?\s*(?:영화|film)\)", title),
        (r"(\d{4})년(?:에|도에)?\s*(?:개봉|공개|제작|발표)", opening),
        (r"(\d{4})년(?:의)?\s*(?:[가-힣A-Za-z]+\s+){0,3}영화", opening),
    ):
        years.update(int(year) for year in re.findall(pattern, value, flags=re.I))
    if movie.year is None or len(years) != 1:
        return IdentityCheck("확인 필요", "제목은 같지만 단일한 작품 연도를 대조할 수 없습니다.")

    document_year = next(iter(years))
    if document_year != movie.year:
        return IdentityCheck(
            "불일치",
            f"동명 영화의 작품 연도가 다릅니다: 선택 영화 {movie.year}년, 문서 {document_year}년.",
        )
    return IdentityCheck("일치", f"영화 제목과 첫 문단/제목의 작품 연도({document_year}년)가 일치합니다. 휴리스틱 검사이며 최종 사실 검증은 아닙니다.")
