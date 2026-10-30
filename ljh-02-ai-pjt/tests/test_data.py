from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

from movie_lab.data import DataLoadError, build_index_text, load_movies, movie_label


class MovieDataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "movies.json"

    def write(self, records):
        self.path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
        return self.path

    def test_actual_release_data_count_and_unique_string_ids(self):
        movies = load_movies(Path(__file__).resolve().parents[1] / "data" / "movies.json")
        # This checks the currently supplied dataset, not an application limit.
        self.assertEqual(len(movies), 964)
        self.assertEqual(len({movie.movie_id for movie in movies.values()}), 964)
        self.assertTrue(all(isinstance(key, str) and key == movie.movie_id for key, movie in movies.items()))
        self.assertEqual(movies["157336"].original_title, "Interstellar")
        self.assertTrue(all(build_index_text(movie) for movie in movies.values()))
        self.assertNotEqual(movie_label(movies["753091"]), movie_label(movies["17431"]))
        self.assertIn("2023", movie_label(movies["753091"]))
        self.assertIn("2009", movie_label(movies["17431"]))

    def test_integer_ids_and_omitted_or_empty_fields(self):
        self.write([
            {"movie_id": 7, "title": "  테스트  ", "director": [], "genres": None},
            {"movie_id": " 8 ", "title": None, "year": "2023", "cast": ["", " 배우 ", None],
             "runtime": "0", "vote_average": 0, "vote_count": "0"},
        ])
        movies = load_movies(self.path)
        self.assertEqual(list(movies), ["7", "8"])
        self.assertEqual(movies["7"].director, ())
        self.assertEqual(movies["7"].title, "테스트")
        self.assertIn("감독 정보 없음", movie_label(movies["7"]))
        self.assertIn("제목 미상", movie_label(movies["8"]))
        self.assertEqual(movies["8"].cast, ("배우",))
        self.assertIn("TMDB 평점: 0.0", build_index_text(movies["8"]))
        self.assertIn("상영 시간(분): 0", build_index_text(movies["8"]))
        self.assertIn("줄거리: 제공되지 않음", build_index_text(movies["7"]))

    def test_all_provided_fields_are_preserved_in_index_text(self):
        row = {
            "movie_id": "11", "title": "작품", "original_title": "Original", "year": 2024,
            "release_date": "2024-01-02", "director": ["감독"], "genres": ["SF"], "cast": ["배우"],
            "overview": "줄거리 원문", "runtime": 110, "original_language": "ko",
            "production_countries": ["South Korea"], "vote_average": 7.5, "vote_count": 25,
            "tmdb_url": "https://www.themoviedb.org/movie/11",
        }
        movie = load_movies(self.write([row]))["11"]
        text = build_index_text(movie)
        for value in ("Original", "2024-01-02", "감독", "SF", "배우", "줄거리 원문", "110", "ko", "South Korea", "7.5", "25", row["tmdb_url"]):
            with self.subTest(value=value):
                self.assertIn(value, text)
        with self.assertRaises(FrozenInstanceError):
            movie.title = "변경"

    def test_duplicate_normalized_id_is_not_silently_overwritten(self):
        with self.assertRaisesRegex(DataLoadError, "중복"):
            load_movies(self.write([{"movie_id": 1}, {"movie_id": " 1 "}]))

    def test_missing_path_and_directory_raise_friendly_error(self):
        with self.assertRaisesRegex(DataLoadError, "찾을 수 없습니다"):
            load_movies(self.path)
        with self.assertRaises(DataLoadError):
            load_movies(Path(self.temp.name))

    def test_bad_json_and_encoding_do_not_echo_file_contents(self):
        self.path.write_text('{"private_marker": this is invalid}', encoding="utf-8")
        with self.assertRaises(DataLoadError) as context:
            load_movies(self.path)
        self.assertNotIn("private_marker", str(context.exception))
        self.path.write_bytes(b"\xff\xfe\x00")
        with self.assertRaisesRegex(DataLoadError, "UTF-8"):
            load_movies(self.path)

    def test_bad_root_record_or_identity(self):
        for records in ({"movies": []}, [], [None], [{}], [{"movie_id": " "}], [{"movie_id": True}], [{"movie_id": 1.2}]):
            with self.subTest(records=records), self.assertRaises(DataLoadError):
                load_movies(self.write(records))

    def test_bom_and_unusable_optional_values(self):
        self.path.write_text(json.dumps([{"movie_id": "1", "year": "bad", "runtime": 1.25, "vote_average": float("nan"), "director": "감독"}], ensure_ascii=False), encoding="utf-8-sig")
        movie = load_movies(self.path)["1"]
        self.assertIsNone(movie.year)
        self.assertIsNone(movie.runtime)
        self.assertIsNone(movie.vote_average)
        self.assertEqual(movie.director, ("감독",))


if __name__ == "__main__":
    unittest.main()
