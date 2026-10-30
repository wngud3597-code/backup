from __future__ import annotations

import json
import unittest
from dataclasses import replace
from pathlib import Path

from movie_lab.data import classify_snapshot_identity, load_movies


class SnapshotIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        project = Path(__file__).resolve().parents[1]
        cls.movies = load_movies(project / "data" / "movies.json")
        cls.fixture = json.loads(
            (Path(__file__).parent / "fixtures" / "snapshot_identity.json").read_text(
                encoding="utf-8"
            )
        )

    def test_known_2023_movie_linked_to_2009_article_is_mismatch(self):
        check = classify_snapshot_identity(
            self.movies["753091"], self.fixture["documents"]["753091_moon"]
        )
        self.assertEqual(check.status, "불일치")
        self.assertIn("2023", check.reason)
        self.assertIn("2009", check.reason)

    def test_same_article_matches_2009_movie(self):
        check = classify_snapshot_identity(
            self.movies["17431"], self.fixture["documents"]["17431_moon"]
        )
        self.assertEqual(check.status, "일치")

    def test_background_document_is_not_rejected_for_years(self):
        document = self.fixture["documents"]["753091_lunar"]
        check = classify_snapshot_identity(self.movies["753091"], document)
        self.assertEqual(check.status, "확인 필요")
        self.assertEqual(
            classify_snapshot_identity(
                self.movies["753091"],
                {"title": "달", "text": "달은 지구의 자연위성이다."},
            ).status,
            "확인 필요",
        )

    def test_same_title_without_film_or_year_is_not_confirmed(self):
        movie = self.movies["753091"]
        cases = (
            {"title": "더 문", "text": ""},
            {"title": "더 문", "text": "동명의 단어다."},
            {"title": "더 문", "text": "한국 영화다."},
        )
        for document in cases:
            with self.subTest(document=document):
                self.assertEqual(
                    classify_snapshot_identity(movie, document).status, "확인 필요"
                )

    def test_title_qualifier_and_missing_movie_year(self):
        movie = self.movies["753091"]
        document = {
            "title": "더 문 (2023년 영화)",
            "text": "더 문은 대한민국의 영화다.",
        }
        self.assertEqual(classify_snapshot_identity(movie, document).status, "일치")
        self.assertEqual(
            classify_snapshot_identity(replace(movie, year=None), document).status,
            "확인 필요",
        )

    def test_unrelated_years_in_later_paragraphs_are_not_release_years(self):
        document = {
            "title": "더 문",
            "text": "더 문은 2023년에 개봉한 영화다.\n\n2009년에 개봉한 영화와 이름이 같다.",
        }
        self.assertEqual(
            classify_snapshot_identity(self.movies["753091"], document).status, "일치"
        )

    def test_ambiguous_opening_stays_unconfirmed(self):
        document = {
            "title": "더 문",
            "text": "2023년에 개봉한 영화와 2009년에 개봉한 영화가 있다.",
        }
        self.assertEqual(
            classify_snapshot_identity(self.movies["753091"], document).status,
            "확인 필요",
        )

    def test_fixture_preserves_provenance_and_content_hash(self):
        for document in self.fixture["documents"].values():
            self.assertEqual(len(document["archive_member_sha256"]), 64)
            self.assertTrue(document["archive_member"].endswith(".json"))
            self.assertTrue(document["url"].startswith("https://ko.wikipedia.org/"))
            self.assertTrue(document["text_is_opening_excerpt"])


if __name__ == "__main__":
    unittest.main()
