"""Shared, plain document dictionaries and conservative film identity checks."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from movie_lab.data import IdentityCheck, Movie, classify_snapshot_identity


def own_movie_query(movie: Movie) -> str:
    """A model cannot omit the selected film's own search query."""
    parts = [movie.title or movie.original_title]
    if movie.original_title and movie.original_title != movie.title:
        parts.append(movie.original_title)
    if movie.year is not None:
        parts.append(str(movie.year))
    parts.extend(movie.director[:1])
    return " ".join(part for part in parts if part).strip()


def classify_document_identity(movie: Movie, document: Mapping[str, Any]) -> IdentityCheck:
    """Reuse the known homonym check and cross-check a stated film director.

    A background article stays reviewable; missing years never reject it. A
    same-title/year result stays reviewable when its stated director cannot be
    compared. Spelling/transliteration differences are not source conflicts or
    proof of different people. Additional body evidence may establish identity
    without declaring two arbitrary director names equivalent.
    """
    checked = classify_snapshot_identity(movie, document)
    if checked.status != "일치" or not movie.director:
        return checked
    text = str(document.get("text", ""))
    opening = re.split(r"\n\s*\n", text, maxsplit=1)[0][:800]
    normalize = lambda value: re.sub(r"[\W_]+", "", value.casefold())
    # Agreement with any metadata director is positive evidence. If no alias is
    # present, we leave the article for review rather than guessing equivalence.
    if any(normalize(director) in normalize(opening) for director in movie.director):
        return IdentityCheck("일치", checked.reason + " 메타데이터 감독도 첫 문단에서 확인했습니다.")
    if re.search(r"감독|directed\s+by", opening, flags=re.I):
        return IdentityCheck("확인 필요", "제목·연도는 같지만 감독 표기를 대조하지 못했습니다. 전사·철자 차이일 수 있어 불일치나 출처 충돌로 확정하지 않습니다.")
    # A later explicit statement can supplement an opening that omits the
    # director. Require the actual original title, the selected release year,
    # and an exact metadata director with a director role in the same sentence.
    # A mere body mention/interview or a near-spelled name is insufficient.
    original = normalize(movie.original_title)
    if original and original != normalize(movie.title) and movie.year is not None:
        for sentence in re.split(r"(?<=[.!?。])\s+|\n\s*\n", text[:5000]):
            normalized = normalize(sentence)
            if original not in normalized or str(movie.year) not in sentence:
                continue
            for director in movie.director:
                pattern = re.escape(director).replace(r"\ ", r"\s+")
                role = re.search(pattern + r"\s*(?:(?:이|가|은|는)\s*)?(?:감독|연출)", sentence, re.I)
                reverse = re.search(r"(?:감독(?:은|:)?|directed\s+by)\s*" + pattern, sentence, re.I)
                if role or reverse:
                    return IdentityCheck("일치", checked.reason + " 본문 동일 문장의 원제·연도·명시 감독으로 보조 확인했습니다.")
    return checked
