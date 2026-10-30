"""Conservative metadata proposals for an otherwise unsupported director claim.

This module neither generates a final answer nor accepts a proposed verdict.
The caller must run the ordinary citation checks and independent item review.
The supplied catalog registry contains display names, not person IDs or a
complete alias registry; comparisons are limited to those exact spellings.
"""

from __future__ import annotations

from copy import deepcopy
from difflib import SequenceMatcher
import re
import unicodedata


_FIELDS = {"scope", "claim", "verdict", "reason", "citations"}
_NAME = r"(?P<name>[^,.;?!\n\r]{1,120}?)"
_CHECK = r"(?:말|것)이 맞(?:나요|습니까)\?"
_ACTIVE_END = (
    r"(?:했다\.?|했습니다\.?|했나요\?|했습니까\?|"
    r"했다는 " + _CHECK + r"|한 (?:게|것이) 맞(?:나요|습니까)\?)"
)
_COPULA_END = r"(?:이다\.?|다\.?|입니다\.?|인가요\?|이 맞나요\?|이라는 " + _CHECK + r")"
_AMBIGUOUS = re.compile(r"아니|않|못|만약|가정|라면|다면|경우|거짓|맞지|틀렸|틀린|소문")
_ROLE_SUFFIXES = ("감독", "감독님", "배우", "각본", "각본가", "작가", "연출", "선생님", "박사", "대표", "씨", "님")
_LATIN_ROLES = {"director", "actor", "actress", "writer", "screenwriter", "producer", "dr", "mr", "ms"}


def _director_name(movie, text, *, mixed=False):
    """Accept one affirmative, selected-film proposition in a small grammar."""
    if not isinstance(text, str) or not text.strip() or len(text) > 2000:
        return None
    text = text.strip()
    if "\n" in text or "\r" in text or _AMBIGUOUS.search(text):
        return None
    subjects = {"이 영화", movie.title, movie.original_title} - {""}
    subject = "(?:" + "|".join(re.escape(value) for value in sorted(subjects, key=len, reverse=True)) + ")"
    active = subject + r"(?:는|은) " + _NAME + r"(?:이|가) 감독"
    copula = subject + r"의 감독은 " + _NAME
    for pattern in (active + _ACTIVE_END, copula + _COPULA_END):
        match = re.fullmatch(pattern, text)
        if match:
            return match["name"]
    if mixed:
        # Only the first director clause is interpreted. The background clause
        # remains unverified and is never converted into a metadata fact.
        match = re.fullmatch(active + r"했(?:고|으며), 실제 (?P<background>[^\n\r?]+)\?", text)
        if match and "감독" not in match["background"] and re.search(_CHECK + r"$", match["background"] + "?"):
            return match["name"]
    return None


def _writing_system(name):
    systems = set()
    for character in name:
        if not character.isalpha():
            continue
        label = unicodedata.name(character, "")
        if "HANGUL" in label:
            systems.add("hangul")
        elif "LATIN" in label:
            systems.add("latin")
        elif "CJK" in label or "IDEOGRAPH" in label:
            systems.add("han")
        else:
            systems.add(label.split(" ", 1)[0])
    return systems


def _names_comparable(asserted, actual):
    if asserted == actual:
        return True
    left, right = re.sub(r"\s", "", asserted).casefold(), re.sub(r"\s", "", actual).casefold()
    # Abstention is deliberate: similarity does not establish an alias, and a
    # different writing system may merely be a translation/transliteration.
    return (len(_writing_system(asserted)) == 1
            and _writing_system(asserted) == _writing_system(actual)
            and left not in right and right not in left
            and SequenceMatcher(None, left, right).ratio() < 0.65)


def _full_name_shape(name):
    """Reject obvious partial/role spellings, without pretending to identify people.

    Even a real two-syllable Korean full name abstains in this narrow feature.
    Three-syllable aliases can still resemble names: a catalog spelling is not
    a worldwide person identifier or a complete alias registry.
    """
    if name.endswith(_ROLE_SUFFIXES):
        return False
    if re.fullmatch(r"[가-힣]{3,30}", name):
        return True
    tokens = name.split(" ")
    if len(tokens) < 2 or any(not token for token in tokens):
        return False
    if all(re.fullmatch(r"[가-힣]{2,20}", token) for token in tokens):
        return True
    return (not any(token.casefold() in _LATIN_ROLES for token in tokens)
            and all(len(token) >= 2 and all(character.isalpha() and "LATIN" in unicodedata.name(character, "")
                                           for character in token) for token in tokens))


def _metadata_quote(movie, sources, director):
    matches = []
    for number, source in enumerate(sources, 1):
        if not isinstance(source, dict):
            continue
        if (source.get("movie_id") != movie.movie_id or source.get("document_id") != f"meta:{movie.movie_id}"
                or source.get("scope") != "movie_metadata" or source.get("source_kind") != "metadata"):
            continue
        text = source.get("text")
        if not isinstance(text, str):
            return None
        lines = text.splitlines()
        ids = [line for line in lines if line.startswith("영화 ID:")]
        directors = [line for line in lines if line.startswith("감독:")]
        quote = f"감독: {director}"
        if ids != [f"영화 ID: {movie.movie_id}"] or directors != [quote]:
            return None
        matches.append({"source": number, "quote": quote})
    return matches[0] if matches else None


def propose_director_checks(movie, question, raw_result, sources, canonical_directors):
    """Return a copied draft and audit; proposals still require model review.

    Only a single-director selected movie, exact catalog names and the actual
    selected metadata source can repair an affirmative director row marked
    ``근거 부족``. Unsupported grammar and possible name variants abstain.
    Compact Korean names require at least three syllables, spaced Korean
    tokens at least two each, and Latin names at least two substantial words.
    Short real names, initials, role labels and mixed scripts also abstain.
    The catalog cannot prove global person identity or detect every alias.
    """
    result, audit = deepcopy(raw_result), []
    if not isinstance(result, dict) or not isinstance(result.get("checks"), list):
        return result, audit
    registry = (set(canonical_directors) if isinstance(canonical_directors, (set, frozenset, tuple, list))
                and all(isinstance(name, str) and name and name == name.strip() for name in canonical_directors) else set())
    actual = movie.director[0] if len(movie.director) == 1 else None
    asserted = _director_name(movie, question, mixed=True)
    quote = _metadata_quote(movie, sources, actual) if actual else None
    for index, row in enumerate(result["checks"], 1):
        if (not isinstance(row, dict) or set(row) != _FIELDS or row.get("scope") != "작품 속 묘사"
                or row.get("verdict") != "근거 부족" or not isinstance(row.get("reason"), str)
                or not row["reason"].strip() or not isinstance(row.get("citations"), list)):
            continue
        event = {"claim_id": f"c{index}", "comparison_scope": "provided_movie_metadata_director_name"}
        code = None
        if actual is None:
            code = "director_not_single"
        elif actual not in registry:
            code = "metadata_director_not_canonical"
        elif asserted is None:
            code = "question_not_unambiguous"
        elif asserted not in registry:
            code = "question_director_not_canonical"
        elif not _full_name_shape(actual) or not _full_name_shape(asserted):
            code = "director_name_shape_unsupported"
        elif not _names_comparable(asserted, actual):
            code = "director_identity_ambiguous"
        elif _director_name(movie, row.get("claim")) != asserted:
            code = "claim_mismatch"
        elif quote is None:
            code = "metadata_source_invalid"
        if code:
            audit.append({**event, "reason_code": code, "proposal": False})
            continue
        verdict = "확인됨" if asserted == actual else "근거와 상충"
        relation = "일치합니다" if asserted == actual else "상충합니다"
        row["verdict"] = verdict
        row["reason"] = (f"선택 영화의 제공 메타데이터의 감독 표기는 ‘{actual}’이며, "
                         f"‘{asserted} 감독’이라는 명제와 {relation}. 이 비교는 제공 데이터의 감독 표기에 한정합니다.")
        row["citations"] = [deepcopy(quote)]
        audit.append({**event, "reason_code": "proposed_metadata_director", "proposal": True,
                      "proposed_verdict": verdict, "review_required": True,
                      "metadata_director": actual, "question_director": asserted, **quote})
    return result, audit
