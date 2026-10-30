from __future__ import annotations

import re
import unittest
from dataclasses import replace
from pathlib import Path

from movie_lab.data import load_movies
from movie_lab.discovery import discover_movies, filter_catalog, parse_conditions


ROOT = Path(__file__).resolve().parents[1]


class DiscoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.movies = load_movies(ROOT / "data/movies.json")

    def test_original_queries_improve_with_identical_old_semantic_top_three(self):
        # Frozen real earlier results: no extra model calls and no larger top-k.
        # Minimal reproduction of artifacts/review/semantic_search.jsonl, kept
        # inside this isolated test so archived test code does not need logs.
        original = [
            {"query": "크리스토퍼 놀란 감독의 우주 탐사와 상대성 이론 영화", "hits": [{"movie_id": mid} for mid in ("135397", "49047", "207932")]},
            {"query": "가난한 가족이 부유한 집에 들어가 계층 갈등을 겪는 한국 영화", "hits": [{"movie_id": mid} for mid in ("901121", "1255", "614696")]},
            {"query": "꿈속으로 들어가 생각을 심는 영화", "hits": [{"movie_id": mid} for mid in ("488623", "705996", "38")]},
        ]
        for record, expected in zip(original, ("157336", "496243", "27205")):
            with self.subTest(query=record["query"]):
                result = discover_movies(record["query"], self.movies, record["hits"], limit=3)
                self.assertEqual(result["results"][0]["movie_id"], expected)
                self.assertTrue(all(row["evidence"] for row in result["results"]))

    def test_exact_original_title_and_homonyms(self):
        result = discover_movies("Interstellar", self.movies)
        self.assertEqual([row["movie_id"] for row in result["results"]], ["157336"])
        both = discover_movies("더 문", self.movies)
        self.assertEqual({row["movie_id"] for row in both["results"]}, {"753091", "17431"})
        only = discover_movies("2023년 더 문", self.movies)
        self.assertEqual([row["movie_id"] for row in only["results"]], ["753091"])
        self.assertIn("개봉 연도: 2023", only["results"][0]["evidence"])

    def test_catalogue_titles_take_priority_over_filter_tokens(self):
        # Cover actual titles selected by their syntax, rather than product
        # aliases or examples hard-coded into the discovery implementation.
        titles = {title for movie in self.movies.values() for title in (movie.title, movie.original_title)
                  if title and re.search(r"\band\b|\bor\b|^(?:19|20)\d{2}$", title, re.I)}
        for title in titles:
            with self.subTest(title=title):
                expected = {movie.movie_id for movie in self.movies.values()
                            if title.casefold() in {movie.title.casefold(), movie.original_title.casefold()}}
                result = discover_movies(title, self.movies, limit=len(self.movies))
                self.assertEqual({row["movie_id"] for row in result["results"]}, expected)
                self.assertEqual(result["unverifiable"], [])
                self.assertIsNone(result["conditions"]["year_min"])
        # A genre-like exact title from any catalogue must also stay a title.
        movie = replace(self.movies["157336"], movie_id="genre-title", title="공포", original_title="", genres=("드라마",))
        self.assertEqual(discover_movies("공포", {movie.movie_id: movie})["results"][0]["movie_id"], movie.movie_id)
        self.assertEqual(discover_movies('"1917" 2019년 영화', self.movies)["results"][0]["movie_id"], "530915")
        result = discover_movies("2017년 Beauty and the Beast 영화", self.movies)
        self.assertEqual([row["movie_id"] for row in result["results"]], ["321612"])

    def test_director_year_genre_and_semantic_hits_never_override_filters(self):
        bad_hits = [{"movie_id": "496243", "title": "기생충"}, {"movie_id": "not-in-data"}]
        result = discover_movies("2010년대 크리스토퍼 놀란 감독 SF 영화", self.movies, bad_hits)
        self.assertTrue(result["results"])
        for row in result["results"]:
            movie = self.movies[row["movie_id"]]
            self.assertIn("크리스토퍼 놀란", movie.director)
            self.assertIn("SF", movie.genres)
            self.assertTrue(2010 <= movie.year <= 2019)
        empty = discover_movies("2050년 봉준호 감독 SF 영화", self.movies, bad_hits)
        self.assertEqual(empty["results"], [])

    def test_metadata_filters_and_unverifiable_requests(self):
        result = discover_movies("한국 영화 120분 이하 평점 7 이상 공포 빼고", self.movies)
        self.assertTrue(result["results"])
        for row in result["results"]:
            movie = self.movies[row["movie_id"]]
            self.assertIn("South Korea", movie.production_countries)
            self.assertLessEqual(movie.runtime, 120)
            self.assertGreaterEqual(movie.vote_average, 7)
            self.assertNotIn("공포", movie.genres)
        for query in ("아무개 감독 영화", "넷플릭스 실화 영화", "슬래셔 장르 영화", "봉준호 또는 박찬욱 감독 영화", '제목이 "없는 제목 확실히 12345" 영화'):
            with self.subTest(query=query):
                result = discover_movies(query, self.movies)
                self.assertTrue(result["unverifiable"])
                self.assertEqual(result["results"], [])

    def test_missing_fields_are_not_guessed(self):
        empty = replace(self.movies["157336"], movie_id="empty", year=None, director=(), genres=(), runtime=None, vote_average=None)
        movies = {empty.movie_id: empty}
        self.assertEqual(discover_movies("2014년 영화", movies)["results"], [])
        self.assertEqual(discover_movies("평점 8 이상 영화", movies)["results"], [])
        self.assertTrue(discover_movies("크리스토퍼 놀란 감독 영화", movies)["unverifiable"])

    def test_negative_conditions_and_numeric_boundaries(self):
        base = self.movies["157336"]
        movies = {movie.movie_id: movie for movie in (
            replace(base, movie_id="a", year=2010, genres=("공포",), production_countries=("United States of America",), vote_average=0, runtime=120),
            replace(base, movie_id="b", year=2011, genres=("드라마",), production_countries=("South Korea",), vote_average=10, runtime=140),
            replace(base, movie_id="c", year=2009, genres=("드라마",), production_countries=("United Kingdom",), vote_average=7.5, runtime=100),
            replace(base, movie_id="unknown", year=2010, genres=(), production_countries=(), vote_average=None, runtime=None),
        )}
        cases = {
            "공포 없는 영화": {"b", "c"}, "미국 영화 말고": {"b", "c"},
            "미국이 아닌 영화": {"b", "c"}, "미국 말고 한국 영화": {"b"},
            "2010년 초과 영화": {"b"}, "2010년 미만 영화": {"c"},
            "평점 10 이상 영화": {"b"}, "평점 10 초과 영화": set(),
            "평점 0 이상 영화": {"a", "b", "c"}, "평점 0 미만 영화": set(),
            "평점 7.5 초과 영화": {"b"}, "평점 7.5 이하 영화": {"a", "c"},
            "130분 이상 100분 이상 영화": {"b"}, "120분 초과 영화": {"b"},
        }
        for query, expected in cases.items():
            with self.subTest(query=query):
                result = discover_movies(query, movies)
                self.assertEqual(result["unverifiable"], [])
                self.assertEqual({row["movie_id"] for row in result["results"]}, expected)
        for query in ("평점 11 이상 영화", "평점 -1 이하 영화", "평점 10.01 이상 영화", "평점 열 이상 영화",
                      "평점 7 이상 9 이하 영화", "평점 7 이상이 아닌 영화", "공포가 있지 않은 영화", "미국 영화가 있지 않은 영화"):
            with self.subTest(query=query):
                result = discover_movies(query, movies)
                self.assertTrue(result["unverifiable"])
                self.assertEqual(result["results"], [])

    def test_negated_year_and_colloquial_rating_abstain(self):
        for query in ("2010년 이후가 아닌 영화", "2010년 이전이 아닌 영화", "평점 7 이상은 아니야"):
            with self.subTest(query=query):
                result = discover_movies(query, self.movies)
                self.assertTrue(result["unverifiable"])
                self.assertEqual(result["results"], [])

    def test_arbitrary_movie_and_boundaries_are_not_example_aliases(self):
        expected = self.movies["753091"]
        result = discover_movies('제목이 "더 문" 2023년 영화', self.movies)
        self.assertEqual([row["movie_id"] for row in result["results"]], [expected.movie_id])
        parsed = parse_conditions("2010년부터 2020년까지 봉준호 감독 영화", self.movies)
        self.assertEqual((parsed["year_min"], parsed["year_max"]), (2010, 2020))
        self.assertEqual(parsed["directors"], ["봉준호"])
        genres = parse_conditions("공포가 아닌 코미디 영화", self.movies)
        self.assertEqual(genres["excluded_genres"], ["공포"])
        self.assertEqual(genres["genres"], ["코미디"])
        self.assertEqual(parse_conditions("한국의 SF 영화", self.movies)["countries"], ["South Korea"])
        self.assertEqual(discover_movies("   ", self.movies)["results"], [])
        with self.assertRaises(ValueError):
            discover_movies("영화", self.movies, limit=0)

    def test_prefilter_matches_independent_actual_metadata_predicates(self):
        # The oracle compares actual fields, not the product parser/_matches.
        cases = [
            ("크리스토퍼 놀란 감독의 우주 탐사와 상대성 이론 영화", lambda m: "크리스토퍼 놀란" in m.director),
            ("가난한 가족이 부유한 집에 들어가 계층 갈등을 겪는 한국 영화", lambda m: "South Korea" in m.production_countries),
            ("꿈속으로 들어가 생각을 심는 영화", lambda m: True),
            ("크리스토퍼 놀란 감독 2010년대 SF 영화", lambda m: "크리스토퍼 놀란" in m.director and m.year is not None and 2010 <= m.year <= 2019 and "SF" in m.genres),
            ("한국 스릴러 영화 2010년 이후", lambda m: "South Korea" in m.production_countries and "스릴러" in m.genres and m.year is not None and m.year >= 2010),
            ("공포 없는 영화", lambda m: bool(m.genres) and "공포" not in m.genres),
            ("미국 영화 말고", lambda m: bool(m.production_countries) and "United States of America" not in m.production_countries),
            ("크리스토퍼 놀란 감독 1900년 영화", lambda m: "크리스토퍼 놀란" in m.director and m.year == 1900),
            ("평점 10 이상 영화", lambda m: m.vote_average is not None and m.vote_average >= 10),
            ("평점 0 이하 영화", lambda m: m.vote_average is not None and m.vote_average <= 0),
        ]
        for field, word, boundary in (("year", "2010년", 2010), ("runtime", "120분", 120), ("vote_average", "평점 7", 7)):
            for suffix, compare in (("이상", lambda a, b: a >= b), ("초과", lambda a, b: a > b),
                                    ("이하", lambda a, b: a <= b), ("미만", lambda a, b: a < b)):
                cases.append((f"{word} {suffix} 영화", lambda m, f=field, b=boundary, c=compare: getattr(m, f) is not None and c(getattr(m, f), b)))
        for title in ("더 문", "Interstellar", "Beauty and the Beast", "1917", "2012", "300"):
            cases.append((title, lambda m, t=title: t.casefold() in (m.title.casefold(), m.original_title.casefold())))
        cases.append(("2023년 더 문", lambda m: m.title == "더 문" and m.year == 2023))
        for query, predicate in cases:
            with self.subTest(query=query):
                actual = filter_catalog(query, self.movies)
                expected = {m.movie_id for m in self.movies.values() if predicate(m)}
                self.assertEqual(set(actual["eligible_ids"]), expected)
                self.assertEqual(actual["state"], "ready" if expected else "no_results")

    def test_prefilter_distinguishes_unsupported_missing_and_supported_empty(self):
        for query in ("2010년 이후가 아닌 영화", "2010년 이전이 아닌 영화", "평점 7 이상은 아니야",
                      "평점 -1 이상 영화", "평점 -0.5 이하 영화", "평점 11 이상 영화",
                      "넷플릭스에서 볼 수 있는 영화", "실화인 영화", "알수없는이름 감독 영화", "공포 또는 코미디 영화"):
            with self.subTest(query=query):
                report = filter_catalog(query, self.movies)
                self.assertEqual(report["state"], "unsupported")
                self.assertEqual(report["eligible_ids"], [])
        unknown = replace(self.movies["157336"], movie_id="missing", runtime=None)
        report = discover_movies("120분 이하 영화", {unknown.movie_id: unknown})
        self.assertEqual(report["discovery_state"], "unverifiable_data")
        self.assertEqual(report["missing_by_movie"], {"missing": ["runtime"]})
        self.assertEqual(filter_catalog("평점 10 이상 영화", self.movies)["state"], "no_results")
        self.assertEqual(filter_catalog("  ", self.movies)["state"], "empty_query")


if __name__ == "__main__":
    unittest.main()
