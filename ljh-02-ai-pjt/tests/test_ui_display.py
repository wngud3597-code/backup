"""Pure selection-card and saved-citation presentation checks; no clients/data IO."""

from copy import deepcopy
from dataclasses import replace
import unittest

from movie_lab.data import Movie
from movie_lab.display import metadata_quote_fields, movie_summary, suggested_questions


def movie(**changes):
    base = Movie(movie_id='test-movie', title='격리된 테스트 영화', original_title='Test',
                 release_date='2014-01-01', year=2014, genres=('SF', '드라마'),
                 director=('감독 가',), cast=('배우 가', '배우 나'), overview='미리 보여주지 않을 줄거리',
                 runtime=169, original_language='ko', production_countries=('한국',),
                 vote_average=8.36, vote_count=12345, tmdb_url='https://example.org/test-movie')
    return replace(base, **changes)


def source():
    quote = ('연도: 2014\n감독: 감독 가\n장르: SF, 드라마\n출연: 배우 가, 배우 나\n'
             '상영 시간(분): 169\nTMDB 평점: 8.36\nTMDB 평가 수: 12345\n줄거리: 감추어 둔 줄거리')
    return {'source_kind': 'metadata', 'scope': 'movie_metadata', 'movie_id': 'test-movie',
            'document_id': 'meta:test-movie', 'quote': quote, 'quotes': [quote],
            'text': quote + '\n개봉일: 2014-01-01', 'url': 'https://example.org/test-movie'}


class UiDisplayTests(unittest.TestCase):
    def test_card_formats_actual_fields_but_keeps_unrounded_original(self):
        value = movie()
        before = deepcopy(value)
        shown = movie_summary(value)
        self.assertEqual(shown['director'], '감독 가')
        self.assertEqual(shown['runtime'], '169분')
        self.assertEqual(shown['genres'], 'SF, 드라마')
        self.assertEqual(shown['rating'], '약 8.4/10점')
        self.assertEqual(shown['vote_count'], '12,345개 평가')
        self.assertEqual(shown['year'], '2014년')
        self.assertEqual(shown['cast'], '배우 가, 배우 나')
        self.assertNotIn(value.overview, ' '.join(shown.values()))
        self.assertEqual(value.vote_average, 8.36)
        self.assertEqual(value, before)

    def test_missing_and_real_zero_remain_distinct(self):
        missing = movie(director=(), cast=(), genres=(), runtime=None,
                        vote_average=None, vote_count=None, year=None)
        self.assertEqual(movie_summary(missing)['director'], '감독 정보 없음')
        self.assertEqual({value for key, value in movie_summary(missing).items() if key != 'director'}, {'미상'})
        self.assertEqual(suggested_questions(missing), [])
        zero = movie(runtime=0, vote_average=0.0, vote_count=0)
        self.assertEqual(movie_summary(zero)['runtime'], '0분')
        self.assertEqual(movie_summary(zero)['rating'], '약 0.0/10점')
        self.assertEqual(movie_summary(zero)['vote_count'], '0개 평가')
        self.assertEqual(movie_summary(movie(vote_average=float('nan')))['rating'], '미상')

    def test_suggestions_only_ask_available_field_groups_and_do_not_mutate(self):
        full = movie()
        before = deepcopy(full)
        questions = suggested_questions(full)
        self.assertEqual(len(questions), 3)
        self.assertEqual(len(set(questions)), 3)
        self.assertTrue(all(isinstance(question, str) for question in questions))
        self.assertIn('감독', questions[0])
        self.assertIn('출연진', questions[0])
        self.assertIn('상영 시간', questions[1])
        self.assertIn('TMDB 평점', questions[1])
        self.assertIn('평가 수', questions[1])
        self.assertIn('개봉 연도', questions[2])
        self.assertIn('장르', questions[2])
        self.assertNotIn(full.overview, ' '.join(questions))
        self.assertEqual(full, before)
        sparse = movie(director=(), runtime=None, vote_average=None, vote_count=None, year=None)
        sparse_questions = suggested_questions(sparse)
        self.assertEqual(len(sparse_questions), 2)
        self.assertIn('출연진', sparse_questions[0])
        self.assertIn('장르', sparse_questions[1])
        self.assertFalse(any(term in ' '.join(sparse_questions)
                             for term in ('감독', '상영', '평점', '평가 수', '연도')))

    def test_extended_preview_is_exact_saved_lines_and_keeps_original_quotes(self):
        saved = source()
        before = deepcopy(saved)
        answer = '개봉 연도, 감독, 장르, 출연진, 상영 시간과 TMDB 평점 및 평가 수입니다. [근거 1]'
        answer_before = answer
        fields = metadata_quote_fields(answer, 1, saved)
        self.assertEqual(fields, saved['quote'].splitlines()[:-1])
        self.assertTrue(all(field in saved['quote'] for field in fields))
        self.assertFalse(any('줄거리' in field for field in fields))
        self.assertIn('TMDB 평점: 8.36', fields)
        self.assertNotIn('TMDB 평점: 8.4', fields)
        self.assertEqual(answer, answer_before)
        self.assertEqual(saved, before)
        # This row is in text but not in the answer's saved quote: never borrow it.
        self.assertEqual(metadata_quote_fields('개봉일 [근거 1]', 1, saved), [])

    def test_fields_belong_to_their_own_inline_citation(self):
        saved = source()
        answer = ('감독은 감독 가입니다. [근거 1] TMDB 평점은 8.36점입니다. [근거 2] '
                  '평가 수는 12345개입니다. [근거 2] 장르는 SF입니다. [근거 1]')
        self.assertEqual(metadata_quote_fields(answer, 1, saved), ['감독: 감독 가', '장르: SF, 드라마'])
        self.assertEqual(metadata_quote_fields(answer, 2, saved),
                         ['TMDB 평점: 8.36', 'TMDB 평가 수: 12345'])
        self.assertEqual(metadata_quote_fields('감독에 관한 앞 문단입니다.\n\n장르는 SF입니다. [근거 1]',
                                              1, saved), ['장르: SF, 드라마'])

    def test_grouped_and_legacy_quotes_support_only_explicit_metadata_fields(self):
        saved = source()
        saved.pop('quotes')
        self.assertEqual(metadata_quote_fields('2014년에 개봉했습니다. [근거 1, 2]', 2, saved),
                         ['연도: 2014'])
        self.assertEqual(metadata_quote_fields('평가수입니다. [근거 1] [근거 2]', 2, saved),
                         ['TMDB 평가 수: 12345'])
        self.assertEqual(metadata_quote_fields('참고한 문서입니다. [근거 1]', 1, saved), [])
        self.assertEqual(metadata_quote_fields('장르입니다. [근거 2]', 1, saved), [])
        self.assertEqual(metadata_quote_fields('장르입니다. [근거 0]', 0, saved), [])
        external = {**saved, 'source_kind': 'snapshot', 'scope': 'background'}
        self.assertEqual(metadata_quote_fields('장르입니다. [근거 1]', 1, external), [])


if __name__ == '__main__':
    unittest.main()
