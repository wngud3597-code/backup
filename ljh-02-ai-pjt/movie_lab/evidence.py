"""Pure citation extraction reused from step7_skeleton.py's source display."""

import re


# Accepts the original forms: [근거 3] and [근거 3, 5].
CITE_PATTERN = re.compile(r"\[근거\s*([\d,\s]+)\]")


def cited_sources(answer: str, sources: list[dict]) -> list[tuple[int, dict]]:
    """Return each actually cited source once, in the answer's source order.

    Numbering starts at 1 within this answer's source snapshot. Invalid or
    out-of-range numbers do not select a source. An answer with no valid
    citations returns an empty list so the UI can show the existing notice.
    This checks numbering only, not whether a claim is supported by a source.
    """
    numbers = {
        int(number)
        for group in CITE_PATTERN.findall(answer)
        for number in group.split(",")
        if number.strip().isdigit()
    }
    return [
        (number, source)
        for number, source in enumerate(sources, start=1)
        if number in numbers
    ]


def source_caption(source: dict) -> str:
    """Describe only this answer's stored provenance; never infer a live fetch."""
    kind, scope = source.get("source_kind"), source.get("scope")
    if kind == "metadata" or scope == "movie_metadata":
        category = "영화 메타데이터"
    elif scope == "film_description":
        category = "작품 문서"
    elif scope == "background_unverified":
        category = "배경 문서 · 작품 식별 확인 필요"
    else:
        category = "문서 분류 미상"
    provenance = {"metadata": "제공 메타데이터", "live": "실시간 수집",
                  "snapshot": "제공 스냅샷"}.get(kind, "출처 방식 미상")
    collected_at = source.get("collected_at")
    collected_at = collected_at.strip() if isinstance(collected_at, str) and collected_at.strip() else "미상"
    return f"{category} · {provenance} · 수집 시점: {collected_at}"


def source_quotes(source: dict) -> list[str]:
    """Preserve legacy quote and all unique new quotes without changing state."""
    candidates = [source.get("quote")]
    if isinstance(source.get("quotes"), list):
        candidates.extend(source["quotes"])
    result, seen = [], set()
    for value in candidates:
        if not isinstance(value, str) or not value.strip():
            continue
        quote = value.strip()
        if quote not in seen:
            result.append(quote)
            seen.add(quote)
    return result
