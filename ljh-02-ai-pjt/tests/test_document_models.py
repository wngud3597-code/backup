"""Conservative identity evidence: no transliteration aliases or API calls."""

import unittest
from dataclasses import replace

from movie_lab.document_models import classify_document_identity
from tests.test_document_llm import sample_movie


class DocumentIdentityTests(unittest.TestCase):
    def setUp(self):
        self.movie = replace(sample_movie(), title="항성 여행", original_title="Stellar Journey", year=2014,
                             director=("크리스토퍼 놀란",))

    def test_transliteration_difference_is_review_not_conflict(self):
        document = {"title": "항성 여행", "text": "항성 여행(Stellar Journey)은 2014년에 개봉한 크리스토퍼 놀런 감독의 영화이다."}
        checked = classify_document_identity(self.movie, document)
        self.assertEqual(checked.status, "확인 필요")
        self.assertIn("전사·철자 차이", checked.reason)
        self.assertIn("충돌로 확정하지", checked.reason)
        # No one-character edit heuristic equates arbitrary people.
        other = replace(self.movie, director=("김용화",))
        document["text"] = "항성 여행(Stellar Journey)은 2014년에 개봉한 김용호 감독의 영화이다."
        self.assertEqual(classify_document_identity(other, document).status, "확인 필요")

    def test_body_original_year_and_exact_director_can_supplement_opening(self):
        document = {"title": "항성 여행", "text": "항성 여행은 2014년에 개봉한 영화이다.\n\nStellar Journey(2014)는 크리스토퍼 놀란이 감독한 작품이다."}
        checked = classify_document_identity(self.movie, document)
        self.assertEqual(checked.status, "일치")
        self.assertIn("보조 확인", checked.reason)
        document["text"] = "항성 여행은 2009년에 개봉한 영화이다.\n\nStellar Journey(2014)는 크리스토퍼 놀란이 감독한 작품이다."
        self.assertEqual(classify_document_identity(self.movie, document).status, "불일치")


if __name__ == "__main__":
    unittest.main()
