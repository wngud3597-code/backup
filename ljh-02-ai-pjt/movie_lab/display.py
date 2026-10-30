"""Read-only presentation of stored answers; never change review/state contracts."""

import math
import re

from movie_lab.data import Movie
from movie_lab.evidence import CITE_PATTERN, source_quotes


_DIRECTOR_CLAIM = re.compile(
    r"^(?:(?:이|해당|선택한) 영화는 [가-힣A-Za-z][가-힣A-Za-z .·'\-]{1,80}(?:이|가) 감독(?:했다|하였다|했습니다)"
    r"|(?:이|해당|선택한) 영화의 감독은 [가-힣A-Za-z][가-힣A-Za-z .·'\-]{1,80}(?:이다|입니다))\.?$"
)
_ITEM = re.compile(
    r"(?P<header>\*\*작품 속 묘사 · (?:확인됨|근거와 상충|근거 부족|출처 충돌|검토 보류)\*\*)"
    r"\n\n확인 대상: (?P<claim>[^\n]+)\n\n(?P<reason>.*?)(?=\n\n\*\*|\Z)", re.S
)


def _numbers(text):
    return {int(number.strip()) for group in CITE_PATTERN.findall(text)
            for number in group.split(',') if number.strip().isdigit()}


def _metadata(source):
    return source.get('source_kind') == 'metadata' and source.get('scope') == 'movie_metadata'


def _director_row(source):
    return any(line.strip().startswith('감독: ') and line.strip()[len('감독: '):].strip()
               for quote in source_quotes(source) for line in quote.splitlines())


def _names(values: tuple[str, ...]) -> str:
    return ', '.join(value.strip() for value in values if isinstance(value, str) and value.strip())


def _count(value: int | None) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _rating(value: float | None) -> bool:
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and 0 <= value <= 10)


def movie_summary(movie: Movie) -> dict[str, str]:
    """Format supplied metadata for the selection card without changing it.

    The approximate rating is a one-decimal preview. The unrounded value stays
    on Movie for the detail view. Counts are evaluations, not audience numbers;
    real zero remains distinct from a missing value. No synopsis is included.
    """
    return {
        'director': _names(movie.director) or '감독 정보 없음',
        'runtime': f'{movie.runtime:,}분' if _count(movie.runtime) else '미상',
        'genres': _names(movie.genres) or '미상',
        'rating': f'약 {movie.vote_average:.1f}/10점' if _rating(movie.vote_average) else '미상',
        'vote_count': f'{movie.vote_count:,}개 평가' if _count(movie.vote_count) else '미상',
        'year': f'{movie.year}년' if _count(movie.year) and movie.year > 0 else '미상',
        'cast': _names(movie.cast) or '미상',
    }


def suggested_questions(movie: Movie) -> list[str]:
    """At most three question strings about fields actually provided by Movie.

    Suggestions never send a question or supply an answer. Missing fields are
    omitted individually, including within a partially available field group.
    """
    groups = [
        [('감독', bool(_names(movie.director))), ('주요 출연진', bool(_names(movie.cast)))],
        [('상영 시간', _count(movie.runtime)), ('TMDB 평점', _rating(movie.vote_average)),
         ('TMDB 평가 수', _count(movie.vote_count))],
        [('개봉 연도', _count(movie.year) and movie.year > 0), ('장르', bool(_names(movie.genres)))],
    ]
    return ['이 영화의 ' + ', '.join(label for label, present in group if present) + ' 정보를 알려줘.'
            for group in groups if any(present for _, present in group)]


def _cited_fragments(answer: str, number: int) -> str:
    """Associate field names with their own citation, not other cited clauses.

    A new citation ends the preceding span; an uncited earlier paragraph is
    not borrowed. Consecutive citations may refer to the same preceding span.
    This only selects display hints and does not validate or rewrite a claim.
    """
    fragments, previous_end, last_fragment = [], 0, ''
    for match in CITE_PATTERN.finditer(answer):
        prefix = answer[previous_end:match.start()]
        fragment = prefix.rsplit('\n\n', 1)[-1] if prefix.strip() else last_fragment
        if number in _numbers(match[0]):
            fragments.append(fragment)
        previous_end, last_fragment = match.end(), fragment
    return '\n'.join(fragments)


def answer_for_display(answer: str, sources: list[dict]) -> str:
    """Relabel only a clear director item citing its own stored metadata row.

    The result is ephemeral UI text. Unknown grammar, mixed scopes, missing IDs,
    scene claims and unquoted holds retain their original saved presentation.
    No claim, verdict, model input or source object is rewritten.
    """
    changed = False

    def item(match):
        nonlocal changed
        claim = match['claim'].strip()
        if (not _DIRECTOR_CLAIM.fullmatch(claim)
                or re.search(r'않|아니|만약|라면|다면|장면|극중|영화 속|에서|각본|배우|출연', claim)):
            return match[0]
        numbers = _numbers(match['reason'])
        if not numbers or any(number < 1 or number > len(sources) for number in numbers):
            return match[0]
        cited = [sources[number - 1] for number in sorted(numbers)]
        ids = {source.get('movie_id') for source in cited}
        if len(ids) != 1 or not all(
            _metadata(source) and isinstance(source.get('movie_id'), str) and source['movie_id']
            and source.get('document_id') == f"meta:{source['movie_id']}" and _director_row(source)
            for source in cited
        ):
            return match[0]
        changed = True
        return match[0].replace(match['header'], match['header'].replace('작품 속 묘사', '영화 정보 · 감독'), 1)

    displayed = _ITEM.sub(item, answer)
    if changed:
        displayed = displayed.replace('작품 속 묘사와 현실 사실을 나누어 확인했습니다.',
                                      '영화 정보와 작품·현실 배경을 구분해 확인했습니다.', 1)
    return displayed


def metadata_quote_fields(answer: str, number: int, source: dict) -> list[str]:
    """Return separate exact lines from that answer's saved quotations only.

    This is a field preview, not a new supporting quotation or fact check.
    Distant lines remain separate UI elements. Unknown layouts are not guessed.
    """
    if not _metadata(source) or number < 1:
        return []
    relevant = _cited_fragments(answer, number)
    compact = re.sub(r'\s+', '', relevant)
    labels = []
    if '감독' in compact:
        labels.append('감독: ')
    if any(term in compact for term in ('상영시간', '러닝타임', '런타임')):
        labels.append('상영 시간(분): ')
    if any(term in compact for term in ('평점', '평가점수')):
        labels.append('TMDB 평점: ')
    if any(term in compact for term in ('평가수', '평가개수', '평가건수', '투표수', '투표개수')):
        labels.append('TMDB 평가 수: ')
    if '연도' in compact or '년도' in compact or re.search(r'(?<!\d)\d{4}년', compact):
        labels.append('연도: ')
    if '개봉일' in compact:
        labels.append('개봉일: ')
    if '장르' in compact:
        labels.append('장르: ')
    if any(term in compact for term in ('출연', '배우', '캐스팅', '주연')):
        labels.append('출연: ')
    lines, seen = [], set()
    for quote in source_quotes(source):
        for raw_line in quote.splitlines():
            line = raw_line.strip()
            if (any(line.startswith(label) and line[len(label):].strip() for label in labels)
                    and line in quote and line not in seen):
                seen.add(line)
                lines.append(line)
    return lines
