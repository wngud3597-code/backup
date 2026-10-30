"""Metadata-backed movie discovery; no model, network or embedding calls.

Explicit conditions are enforced against supplied metadata. Lexical/semantic
similarity only orders candidates and never proves the requested plot or facts.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from movie_lab.data import Movie


_COUNTRIES = {
    "한국": "South Korea", "대한민국": "South Korea", "미국": "United States of America",
    "영국": "United Kingdom", "일본": "Japan", "프랑스": "France", "독일": "Germany",
    "중국": "China", "캐나다": "Canada", "호주": "Australia", "인도": "India",
    "이탈리아": "Italy", "스페인": "Spain", "홍콩": "Hong Kong", "대만": "Taiwan",
}
_STOP = {"영화", "작품", "추천", "찾아줘", "찾아", "알려줘", "보여줘", "찾는", "감독", "장르",
         "관련", "대한", "같은", "어떤", "보고", "싶어", "있는", "이야기", "그리고", "내용",
         "하는", "되는", "겪는", "개봉", "주연", "출연", "최신", "이후", "이전", "이상", "이하"}
_PARTICLES = tuple(sorted(("으로부터", "에게서", "에서는", "으로는", "에서는", "에서", "으로", "에게",
                           "처럼", "보다", "까지", "부터", "하고", "이랑", "이라", "속으로", "속에",
                           "에는", "은", "는", "이", "가", "을", "를", "의", "에", "와", "과", "한"), key=len, reverse=True))


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9가-힣]+", "", value.casefold())


def _contains_name(query: str, name: str) -> bool:
    if not name:
        return False
    if name.casefold() not in query.casefold():
        return False
    pattern = re.escape(name).replace(r"\ ", r"\s*")
    return bool(re.search(r"(?<![a-zA-Z가-힣])" + pattern + r"(?=$|\s|[의이가을를은는·,])", query, re.I))


def _title_ids(query: str, movies: Mapping[str, Movie]) -> tuple[list[str], bool]:
    quoted = re.findall(r'[「『“"\']([^」』”"\']+)[」』”"\']', query)
    explicit = re.search(r"(?:제목|원제)\s*(?:이|가|는|은|:)?\s*(.+?)(?:\s+(?:영화|찾아|알려)|$)", query)
    candidates = quoted + ([explicit.group(1).strip()] if explicit else [])
    cleaned = re.sub(r"(?:19|20)\d{2}\s*년?\s*(?:개봉)?", " ", query)
    cleaned = re.sub(r"(?:영화|작품|찾아줘|찾아주세요|찾아|알려줘|알려주세요|보여줘|검색해줘|검색|추천해줘)", " ", cleaned)
    candidates.extend((query.strip(), cleaned.strip()))
    norms = {_norm(value) for value in candidates if _norm(value)}
    ids = [movie.movie_id for movie in movies.values()
           if any(_norm(title) in norms for title in (movie.title, movie.original_title) if title)]
    return ids, bool(quoted or explicit)


def parse_conditions(query: str, movies: Mapping[str, Movie]) -> dict[str, Any]:
    """Extract bounded, inspectable conditions using only the loaded catalogue.

    The parser deliberately reports unsupported factual filters instead of
    treating a language model's guess or semantic score as metadata evidence.
    """
    if not isinstance(query, str):
        raise ValueError("검색 질문은 문자열이어야 합니다.")
    query = query.strip()
    condition: dict[str, Any] = {"title_ids": [], "year_min": None, "year_max": None,
                               "directors": [], "genres": [], "countries": [], "cast": [],
                               "excluded_genres": [], "excluded_countries": [],
                               "runtime_min": None, "runtime_max": None,
                               "rating_min": None, "rating_max": None,
                               "rating_min_exclusive": False, "rating_max_exclusive": False,
                               "unsupported": []}
    # A complete catalogue title has priority over words that would otherwise
    # resemble filters (a numeric title, a genre word, or English 'and'/'or').
    # This is data-derived and preserves all homonyms rather than one winner.
    whole_title = _norm(query)
    exact_ids = [movie.movie_id for movie in movies.values()
                 if whole_title and any(_norm(title) == whole_title
                                        for title in (movie.title, movie.original_title) if title)]
    if exact_ids:
        condition["title_ids"] = exact_ids
        return condition
    title_ids, requested_title = _title_ids(query, movies)
    condition["title_ids"] = title_ids
    if requested_title and not title_ids:
        condition["unsupported"].append("요청한 제목·원제를 데이터에서 찾지 못했습니다.")
    if title_ids:
        # Once an exact title is recognized, its words are not independent
        # release-year, genre, director or boolean conditions. Remaining text
        # still supplies explicit constraints, e.g. '2017년 <original title>'.
        titles = {title for mid in title_ids for title in (movies[mid].title, movies[mid].original_title) if title}
        for title in sorted(titles, key=len, reverse=True):
            query = re.sub(re.escape(title), " ", query, flags=re.I)

    decade = re.search(r"((?:19|20)\d0)\s*년대", query)
    year_matches = list(re.finditer(r"(?<!\d)((?:19|20)\d{2})(?!\d)\s*년?(?:\s*(이후|이전|이상|이하|초과|미만|부터|까지|후|전))?", query))
    years = [match.groups() for match in year_matches]
    numeric_spans = [match.span() for match in year_matches]
    year_range = re.search(r"((?:19|20)\d{2})\s*년?\s*(?:[~∼–—-]|부터)\s*((?:19|20)\d{2})", query)
    if year_range:
        condition["year_min"], condition["year_max"] = map(int, year_range.groups())
    elif decade:
        condition["year_min"] = int(decade.group(1))
        condition["year_max"] = int(decade.group(1)) + 9
    elif years:
        for year, comparison in years:
            if comparison in ("이후", "이상", "부터", "후", "초과"):
                bound = int(year) + (comparison == "초과")
                previous = condition["year_min"]
                condition["year_min"] = max(bound, previous) if previous is not None else bound
            elif comparison in ("이전", "이하", "까지", "전", "미만"):
                bound = int(year) - (comparison == "미만")
                previous = condition["year_max"]
                condition["year_max"] = min(bound, previous) if previous is not None else bound
            else:
                condition["year_min"] = condition["year_max"] = int(year)

    names = sorted({name for movie in movies.values() for name in movie.director}, key=len, reverse=True)
    for name in names:
        if _contains_name(query, name):
            condition["directors"].append(name)
            if re.search(re.escape(name) + r"\s*(?:감독)?\s*(?:이?\s*아닌|제외|말고|빼고)", query):
                condition["unsupported"].append("감독 제외 조건은 현재 검증하지 않습니다. 조건을 나누어 검색하세요.")
    if "감독" in query and not condition["directors"]:
        # A last-name shorthand is accepted only if it identifies one actual
        # catalogue name. It is derived from the data, not an example alias.
        prefix = query.split("감독", 1)[0].strip().split()
        surname = prefix[-1] if prefix else ""
        matches = [name for name in names if name.split()[-1] == surname]
        if len(matches) == 1:
            condition["directors"] = matches
        else:
            condition["unsupported"].append("감독 조건을 데이터의 단일 감독과 대조할 수 없습니다.")

    all_genres = sorted({genre for movie in movies.values() for genre in movie.genres}, key=len, reverse=True)
    for genre in all_genres:
        found = re.search(re.escape(genre), query, re.I)
        if not found:
            continue
        after = query[found.end():found.end() + 22]
        if re.match(r"\s*(?:[이가을를은는]\s*)?(?:영화|작품|장르)?\s*(?:[이가을를은는]\s*)?(?:제외|빼고|아닌|말고|없는|없고|없이)", after):
            condition["excluded_genres"].append(genre)
        elif re.search(r"없|아니|않|말고|제외|빼고", after[:12]):
            condition["unsupported"].append("해석이 불명확한 장르 부정 조건입니다. ‘장르 제외’로 명시해 주세요.")
        elif genre != "가족" or re.search(r"가족\s*(?:영화|장르)|장르\s*(?:가|는|:)\s*가족", query):
            # '가족이 겪는 이야기' describes content, not a Family genre filter.
            condition["genres"].append(genre)
    genre_phrase = re.search(r"([가-힣A-Za-z]+)\s*장르", query)
    if genre_phrase and genre_phrase.group(1) not in all_genres:
        condition["unsupported"].append("요청한 장르가 제공된 장르 목록에 없습니다.")

    genre_alternation = "|".join(re.escape(genre) for genre in all_genres)
    for word, country in _COUNTRIES.items():
        negative = re.search(re.escape(word) + r"\s*(?:[이가을를은는]\s*)?(?:영화|작품|제작)?\s*(?:[이가을를은는]\s*)?(?:제외|빼고|아닌|말고)", query)
        if negative:
            condition["excluded_countries"].append(country)
            continue
        found = re.search(re.escape(word) + r"(?:의|에서|산)?\s*"
                          + rf"(?:(?:{genre_alternation}|(?:19|20)\d{{2}}년?)\s*)*"
                          + r"(?:영화|작품|제작)", query, flags=re.I)
        if not found:
            continue
        after = query[found.end():found.end() + 16]
        negative = re.match(r"\s*(?:[이가을를은는]\s*)?(?:제외|빼고|아닌|말고|없는|없고|없이)", after)
        if not negative and re.search(r"없|아니|않|말고|제외|빼고", after[:12]):
            condition["unsupported"].append("해석이 불명확한 제작국 부정 조건입니다. ‘국가 영화 제외’로 명시해 주세요.")
            continue
        key = "excluded_countries" if negative else "countries"
        condition[key].append(country)
    condition["countries"] = sorted(set(condition["countries"]))
    condition["excluded_countries"] = sorted(set(condition["excluded_countries"]))
    for name in {name for movie in movies.values() for name in movie.cast}:
        if _contains_name(query, name):
            condition["cast"].append(name)
    if re.search(r"주연|출연", query) and not condition["cast"]:
        condition["unsupported"].append("출연 조건을 제공된 출연 목록과 대조할 수 없습니다.")

    for match in re.finditer(r"(?<![\d.])(\d{1,3})\s*분\s*(이하|이상|미만|초과)", query):
        value, comparison = match.groups()
        numeric_spans.append(match.span())
        if comparison in ("이상", "초과"):
            bound = int(value) + (comparison == "초과")
            previous = condition["runtime_min"]
            condition["runtime_min"] = max(bound, previous) if previous is not None else bound
        else:
            bound = int(value) - (comparison == "미만")
            previous = condition["runtime_max"]
            condition["runtime_max"] = min(bound, previous) if previous is not None else bound
    rating_matches = list(re.finditer(r"평점\s*([+-]?\d+(?:\.\d+)?)\s*(?:점)?\s*(이상|이하|초과|미만)", query))
    for match in rating_matches:
        value, comparison = match.groups()
        numeric_spans.append(match.span())
        value = float(value)
        if not 0 <= value <= 10:
            condition["unsupported"].append("TMDB 평점 조건은 0~10 범위로 입력하세요.")
            continue
        key = "rating_min" if comparison in ("이상", "초과") else "rating_max"
        previous = condition[key]
        tighter = previous is None or (value > previous if key == "rating_min" else value < previous)
        if tighter:
            condition[key] = value
            condition[key + "_exclusive"] = comparison in ("초과", "미만")
        elif value == previous and comparison in ("초과", "미만"):
            condition[key + "_exclusive"] = True
    if "평점" in query and not rating_matches:
        condition["unsupported"].append("평점은 숫자와 이상·이하·초과·미만으로 명시해야 합니다.")
    for match in re.finditer(r"(?<![\d.])[+-]?\d+(?:\.\d+)?\s*(?:년|분|점)?\s*(?:이상|이하|미만|초과|이후|이전|부터|까지)", query):
        if not any(start <= match.start() and match.end() <= end for start, end in numeric_spans):
            condition["unsupported"].append("해석하지 못한 수치 조건이 있습니다. 조건 이름과 경계를 명시해 주세요.")
            break
    # Unsupported negation must never silently become the positive bound.
    # Catalogue-exact titles have already returned, and recognized title spans
    # are masked above, so numeric titles retain their existing interpretation.
    if re.search(r"(?:이상|이하|초과|미만|이후|이전)\s*(?:[이가은는]\s*)?(?:아닌|아니|아님|말고|제외|않)", query):
        condition["unsupported"].append("수치 조건의 부정은 현재 검증하지 않습니다. 반대 경계를 직접 입력하세요.")
    for word in ("넷플릭스", "디즈니플러스", "아카데미", "오스카", "수상", "관객수", "관객 수", "흥행", "실화", "현재 상영"):
        if word in query:
            condition["unsupported"].append(f"‘{word}’ 조건은 제공 메타데이터로 검증할 수 없습니다.")
    if re.search(r"\b(?:and|or)\b|또는|혹은", query, re.I):
        condition["unsupported"].append("OR 조건은 현재 탐색에서 검증하지 않습니다. 조건을 나누어 검색하세요.")
    return condition


def _matches(movie: Movie, condition: dict) -> tuple[bool, list[str]]:
    evidence = []
    if condition["title_ids"]:
        if movie.movie_id not in condition["title_ids"]:
            return False, []
        evidence.append(f"제목/원제 일치: {movie.title} / {movie.original_title}")
    for key, attribute, label in (("year", "year", "개봉 연도"), ("runtime", "runtime", "상영 시간(분)"), ("rating", "vote_average", "TMDB 평점")):
        low, high = condition[f"{key}_min"], condition[f"{key}_max"]
        if low is not None or high is not None:
            value = getattr(movie, attribute)
            if value is None or (low is not None and value < low) or (high is not None and value > high):
                return False, []
            if key == "rating" and ((condition["rating_min_exclusive"] and value == low)
                                     or (condition["rating_max_exclusive"] and value == high)):
                return False, []
            evidence.append(f"{label}: {value}")
    for key, values, label in (("directors", movie.director, "감독"), ("genres", movie.genres, "장르"),
                               ("cast", movie.cast, "출연")):
        if condition[key]:
            if not all(value in values for value in condition[key]):
                return False, []
            evidence.append(f"{label}: {', '.join(condition[key])}")
    if condition["excluded_genres"] and (not movie.genres or set(condition["excluded_genres"]) & set(movie.genres)):
        return False, []
    if condition["excluded_genres"]:
        evidence.append(f"제외 장르 없음: {', '.join(condition['excluded_genres'])}")
    if condition["countries"]:
        if not all(value in movie.production_countries for value in condition["countries"]):
            return False, []
        evidence.append(f"제작 국가: {', '.join(movie.production_countries)}")
    if condition["excluded_countries"]:
        if not movie.production_countries or set(condition["excluded_countries"]) & set(movie.production_countries):
            return False, []
        evidence.append(f"제외 제작 국가 없음: {', '.join(condition['excluded_countries'])}")
    return True, evidence


def filter_catalog(query: str, movies: Mapping[str, Movie], *, conditions: dict | None = None) -> dict:
    """Resolve supported metadata conditions before any semantic request.

    Missing required fields are recorded separately from unsupported grammar
    and a supported condition with no matching records. No similarity score is
    involved in this eligibility set.
    """
    condition = parse_conditions(query, movies) if conditions is None else conditions
    report = {"conditions": condition, "eligible_ids": [], "missing_by_movie": {},
              "state": "ready"}
    if not query.strip():
        report["state"] = "empty_query"
        return report
    if condition["unsupported"]:
        report["state"] = "unsupported"
        return report
    required = set()
    for key, attribute in (("directors", "director"), ("cast", "cast"),
                           ("genres", "genres"), ("excluded_genres", "genres"),
                           ("countries", "production_countries"),
                           ("excluded_countries", "production_countries")):
        if condition[key]:
            required.add(attribute)
    for key, attribute in (("year", "year"), ("runtime", "runtime"), ("rating", "vote_average")):
        if condition[key + "_min"] is not None or condition[key + "_max"] is not None:
            required.add(attribute)
    for movie in movies.values():
        if condition["title_ids"] and movie.movie_id not in condition["title_ids"]:
            continue
        missing = [field for field in sorted(required)
                   if getattr(movie, field) is None or getattr(movie, field) == ()]
        if missing:
            # A known contradictory field already excludes the record. Do not
            # label a 2020 film as uncertain for a 1900 filter merely because
            # its director field is absent.
            known = dict(condition)
            for key, attribute in (("directors", "director"), ("cast", "cast"),
                                   ("genres", "genres"), ("excluded_genres", "genres"),
                                   ("countries", "production_countries"),
                                   ("excluded_countries", "production_countries")):
                if attribute in missing:
                    known[key] = []
            for key, attribute in (("year", "year"), ("runtime", "runtime"), ("rating", "vote_average")):
                if attribute in missing:
                    known[key + "_min"] = known[key + "_max"] = None
            if not _matches(movie, known)[0]:
                continue
            report["missing_by_movie"][movie.movie_id] = missing
            continue
        if _matches(movie, condition)[0]:
            report["eligible_ids"].append(movie.movie_id)
    report["eligible_ids"].sort()
    if not report["eligible_ids"]:
        report["state"] = "unverifiable_data" if report["missing_by_movie"] else "no_results"
    return report


def _words(text: str) -> list[str]:
    words = []
    for word in re.findall(r"[a-zA-Z0-9]+|[가-힣]+", text.casefold()):
        if word in _STOP or word.isdigit():
            continue
        stem = word
        for particle in _PARTICLES:
            if stem.endswith(particle) and len(stem) > len(particle):
                stem = stem[:-len(particle)]
                break
        if stem and stem not in _STOP:
            words.append(stem)
    return words


def _features(text: str) -> Counter:
    terms: Counter = Counter()
    for word in _words(text):
        terms[f"w:{word}"] += 1
        if re.fullmatch(r"[가-힣]+", word):
            for index in range(len(word) - 1):
                terms[f"b:{word[index:index + 2]}"] += 0.3
            # Korean particles split one-syllable nouns such as 꿈/집 from the
            # longer query. A small character contribution enables recall.
            for char in word:
                terms[f"c:{char}"] += 0.025
    return terms


def _lexical_scores(query: str, movies: Sequence[Movie]) -> dict[str, float]:
    query_terms = _features(query)
    documents = {}
    frequency = Counter()
    for movie in movies:
        terms = _features(movie.overview)
        for field in (movie.title, movie.original_title):
            terms.update({term: count * 3 for term, count in _features(field).items()})
        terms.update({term: count * 2 for term, count in _features(" ".join(movie.director)).items()})
        documents[movie.movie_id] = terms
        frequency.update(terms.keys())
    if not movies:
        return {}
    average = sum(sum(terms.values()) for terms in documents.values()) / len(documents) or 1
    scores = {}
    for movie_id, terms in documents.items():
        length = sum(terms.values())
        score = 0.0
        for term, q_weight in query_terms.items():
            count = terms.get(term, 0)
            if count:
                inverse = math.log(1 + (len(movies) - frequency[term] + 0.5) / (frequency[term] + 0.5))
                score += q_weight * inverse * count * 2.2 / (count + 1.2 * (0.25 + 0.75 * length / average))
        scores[movie_id] = score
    return scores


def _snippet(movie: Movie, query: str) -> str | None:
    terms = [word for word in _words(query) if len(word) >= 2]
    for sentence in re.split(r"(?<=[.!?…])\s+", movie.overview):
        if any(term in sentence for term in terms):
            return sentence[:220]
    return None


def semantic_query(query: str, condition: dict) -> str:
    """Do not let already-enforced names/countries dominate lexical ranking."""
    for name in condition["directors"] + condition["cast"] + condition["genres"]:
        query = re.sub(re.escape(name), " ", query, flags=re.I)
    for word, country in _COUNTRIES.items():
        if country in condition["countries"] + condition["excluded_countries"]:
            query = query.replace(word, " ")
    query = re.sub(r"(?:19|20)\d{2}\s*년?\s*(?:이후|이전|이상|이하|부터|까지|년대)?", " ", query)
    return re.sub(r"\s+", " ", query).strip()


def discover_movies(query: str, movies: Mapping[str, Movie], semantic_hits: Sequence[dict] | None = None,
                    limit: int = 10) -> dict[str, Any]:
    """Return verified metadata conditions and ranked candidate IDs.

    ``semantic_hits`` are optional, externally obtained results. This function
    performs no API calls, does not increase semantic top-k and ignores unknown
    IDs. Explicit conditions always take precedence over either ranking method.
    """
    if type(limit) is not int or limit <= 0:
        raise ValueError("검색 개수는 양의 정수여야 합니다.")
    condition = parse_conditions(query, movies)
    eligibility = filter_catalog(query, movies, conditions=condition)
    ranking_query = semantic_query(query, condition)
    report = {"query": query.strip(), "semantic_query": ranking_query,
              "conditions": condition, "unverifiable": condition["unsupported"],
              "discovery_state": eligibility["state"],
              "eligible_count": len(eligibility["eligible_ids"]),
              "eligible_movie_ids": eligibility["eligible_ids"],
              "missing_by_movie": eligibility["missing_by_movie"],
              "results": [], "notes": ["명시 조건은 제공 메타데이터로 확인합니다. 줄거리·의미 유사도는 후보 순위이며 사실/조건 충족을 증명하지 않습니다."]}
    if not query.strip():
        report["notes"].append("검색할 제목이나 조건을 입력하세요.")
        return report
    if condition["unsupported"]:
        report["notes"].append("확인할 수 없는 명시 조건이 있어 작품을 확정하지 않았습니다. 조건을 수정해 주세요.")
        return report
    if eligibility["missing_by_movie"]:
        report["notes"].append(f"조건 확인에 필요한 필드가 없는 작품 {len(eligibility['missing_by_movie'])}건은 조건 충족으로 확정하지 않았습니다.")
    all_movies = list(movies.values())
    ranking_movies = ([movies[mid] for mid in condition["title_ids"]]
                      if condition["title_ids"] else all_movies)
    lexical = _lexical_scores(ranking_query, ranking_movies)
    semantic = {str(hit.get("movie_id")): rank for rank, hit in enumerate(semantic_hits or [], start=1)
                if str(hit.get("movie_id")) in movies}
    # Normalized lexical scores preserve strong matching metadata phrases. The
    # optional semantic signal adds candidate recall without overriding filters.
    maximum = max(lexical.values(), default=0) or 1
    exact_filters = (any(condition[key] for key in ("title_ids", "directors", "genres", "countries", "cast", "excluded_genres", "excluded_countries"))
                     or any(condition[f"{field}_{boundary}"] is not None
                            for field in ("year", "runtime", "rating") for boundary in ("min", "max")))
    eligible_ids = set(eligibility["eligible_ids"])
    for movie in all_movies:
        if movie.movie_id not in eligible_ids:
            continue
        matches, evidence = _matches(movie, condition)
        if not matches:
            continue
        local = lexical.get(movie.movie_id, 0)
        semantic_rank = semantic.get(movie.movie_id)
        if not exact_filters and local < 0.15 and semantic_rank is None:
            continue
        score = local / maximum + (0.12 / semantic_rank if semantic_rank else 0)
        snippet = _snippet(movie, query)
        if snippet:
            evidence.append(f"줄거리의 관련 구절(의미 조건 검증 아님): {snippet}")
        report["results"].append({"movie_id": movie.movie_id, "title": movie.title, "year": movie.year,
                                  "director": list(movie.director), "evidence": evidence,
                                  "score": round(score, 6), "semantic_rank": semantic_rank,
                                  "ranking_sources": (["keyword"] if local > 0 else [])
                                                     + (["semantic"] if semantic_rank else [])})
    report["results"].sort(key=lambda row: (-row["score"], row["movie_id"]))
    report["results"] = report["results"][:limit]
    if not report["results"] and eligibility["state"] == "unverifiable_data":
        report["notes"].append("필드 누락으로 조건을 확인할 수 없는 작품이 있어 결과를 확정하지 않았습니다.")
    elif not report["results"]:
        report["notes"].append("현재 데이터에서 조건과 대조할 수 있는 결과가 없습니다.")
    return report
