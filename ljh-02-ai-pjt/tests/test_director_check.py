"""Offline metadata proposal boundaries; these mocks do not prove review accuracy."""

from copy import deepcopy
from dataclasses import replace
import unittest

from movie_lab.data import Movie, build_index_text
from movie_lab.director_check import propose_director_checks


def movie():
    return Movie("fixture-42", "테스트 영화", "Test Film", "2023-01-01", 2023, (), ("김용화",),
                 (), "격리된 테스트 데이터", 100, "ko", (), None, None, "https://example.invalid/movie")


def draft(name="크리스토퍼 놀란", claim=None):
    return {"checks": [
        {"scope": "작품 속 묘사", "claim": claim or f"이 영화는 {name}이 감독했다.", "verdict": "근거 부족",
         "reason": "현재 근거로 확인하지 못했습니다.", "citations": []},
        {"scope": "현실 사실", "claim": "격리된 현실 주장", "verdict": "근거 부족",
         "reason": "현실 근거를 확인하지 못했습니다.", "citations": []},
    ]}


def metadata(selected):
    return {"movie_id": selected.movie_id, "document_id": f"meta:{selected.movie_id}",
            "scope": "movie_metadata", "source_kind": "metadata", "text": build_index_text(selected)}


class DirectorProposalTests(unittest.TestCase):
    def setUp(self):
        self.movie = movie()
        self.sources = [{"scope": "background_unverified", "text": "다른 근거"}, metadata(self.movie)]
        self.registry = {"김용화", "크리스토퍼 놀란", "크리스토퍼 놀런", "Christopher Nolan", "놀란", "Nolan", "김용하"}

    def propose(self, question, raw=None, sources=None, selected=None, registry=None):
        return propose_director_checks(selected or self.movie, question, raw or draft(),
                                       self.sources if sources is None else sources,
                                       self.registry if registry is None else registry)

    def test_positive_and_contradicting_proposals_use_real_metadata_without_mutating_inputs(self):
        for name, verdict in (("김용화", "확인됨"), ("크리스토퍼 놀란", "근거와 상충")):
            with self.subTest(name=name):
                raw = draft(name)
                originals = deepcopy((raw, self.sources))
                result, audit = self.propose(f"이 영화는 {name}이 감독했고, 실제 달은 지구의 자연위성이라는 말이 맞나요?", raw)
                self.assertEqual(result["checks"][0]["verdict"], verdict)
                self.assertEqual(result["checks"][0]["citations"], [{"source": 2, "quote": "감독: 김용화"}])
                self.assertIn("제공 데이터의 감독 표기에 한정", result["checks"][0]["reason"])
                self.assertEqual(result["checks"][1], raw["checks"][1])
                self.assertEqual((raw, self.sources), originals)
                self.assertEqual(audit[0]["reason_code"], "proposed_metadata_director")
                self.assertTrue(audit[0]["review_required"])
                self.assertNotIn("accepted", audit[0])

    def test_supported_affirmative_grammar_and_exact_selected_title(self):
        cases = (
            ("이 영화의 감독은 김용화인가요?", "이 영화의 감독은 김용화다."),
            ("테스트 영화는 김용화가 감독한 게 맞나요?", "테스트 영화는 김용화가 감독했다."),
            ("이 영화는 김용화가 감독했다는 말이 맞나요?", "이 영화는 김용화가 감독했나요?"),
        )
        for question, claim in cases:
            with self.subTest(question=question):
                result, audit = self.propose(question, draft("김용화", claim))
                self.assertEqual(result["checks"][0]["verdict"], "확인됨")
                self.assertTrue(audit[0]["proposal"])

    def test_negations_assumptions_other_subjects_and_extra_director_clauses_abstain(self):
        questions = (
            "이 영화는 크리스토퍼 놀란이 감독하지 않았나요?",
            "이 영화의 감독은 크리스토퍼 놀란이 아닌가요?",
            "만약 이 영화는 크리스토퍼 놀란이 감독했다면 어떻게 되나요?",
            "이 영화는 크리스토퍼 놀란이 감독했다고 가정하면 맞나요?",
            "다른 영화는 크리스토퍼 놀란이 감독했나요?",
            "이 영화는 크리스토퍼 놀란이 감독했고, 김용화도 감독했다는 말이 맞나요?",
            "이 영화는 크리스토퍼 놀란이 감독했고, 실제 감독은 다른 사람이라는 말이 맞나요?",
            "이 영화는 크리스토퍼 놀란이 감독했고, 실제 달은 지구의 자연위성이라는 말이 맞나요? 앞의 주장은 거짓이다.",
            '"이 영화는 크리스토퍼 놀란이 감독했다"라는 주장은 거짓인가요?',
        )
        for question in questions:
            with self.subTest(question=question):
                raw = draft()
                result, audit = self.propose(question, raw)
                self.assertEqual(result, raw)
                self.assertEqual(audit[0]["reason_code"], "question_not_unambiguous")

    def test_unknown_partial_translated_or_similar_name_spellings_do_not_claim_identity(self):
        cases = (
            (self.movie, "미등록 감독", "question_director_not_canonical"),
            (replace(self.movie, director=("크리스토퍼 놀란",)), "놀란", "director_name_shape_unsupported"),
            (replace(self.movie, director=("크리스토퍼 놀란",)), "Christopher Nolan", "director_identity_ambiguous"),
            (replace(self.movie, director=("크리스토퍼 놀란",)), "크리스토퍼 놀런", "director_identity_ambiguous"),
            (self.movie, "놀란", "director_name_shape_unsupported"),
            (self.movie, "Nolan", "director_name_shape_unsupported"),
            (self.movie, "김용하", "director_identity_ambiguous"),
        )
        for selected, name, expected in cases:
            with self.subTest(name=name):
                result, audit = self.propose(f"이 영화는 {name}이 감독했나요?", draft(name),
                                             [metadata(selected)], selected)
                self.assertEqual(result, draft(name))
                self.assertEqual(audit[0]["reason_code"], expected)
        for name in ("김용화 감독", "김용화감독", "김용화(감독)", "김용화 배우", "김 Yonghwa", "C Nolan", "김 용화"):
            with self.subTest(unsupported_shape=name):
                raw = draft(name)
                result, audit = self.propose(f"이 영화는 {name}이 감독했나요?", raw, registry=self.registry | {name})
                self.assertEqual(result, raw)
                self.assertEqual(audit[0]["reason_code"], "director_name_shape_unsupported")
        short_name_movie = replace(self.movie, director=("김구",))
        result, audit = self.propose("이 영화는 김구가 감독했나요?", draft("김구"),
                                     [metadata(short_name_movie)], short_name_movie, self.registry | {"김구"})
        self.assertEqual(result, draft("김구"))
        self.assertEqual(audit[0]["reason_code"], "director_name_shape_unsupported")

    def test_empty_multiple_directors_or_mismatching_generated_claim_abstain(self):
        for directors in ((), ("김용화", "크리스토퍼 놀란")):
            with self.subTest(directors=directors):
                selected = replace(self.movie, director=directors)
                result, audit = self.propose("이 영화는 크리스토퍼 놀란이 감독했나요?", selected=selected)
                self.assertEqual(result, draft())
                self.assertEqual(audit[0]["reason_code"], "director_not_single")
        for claim in ("이 영화의 감독은 김용화다.", "이 영화는 크리스토퍼 놀란이 감독하지 않았다.",
                      "다른 영화는 크리스토퍼 놀란이 감독했다.", "이 영화는 크리스토퍼 놀란이 감독했다면 좋겠다.",
                      "이 영화는 크리스토퍼 놀란이 출연했다.", "이 영화는 크리스토퍼 놀란이 각본을 썼다.",
                      "이 영화에서 달이 빛나는 별로 등장했다.", "달은 지구의 자연위성이다."):
            with self.subTest(claim=claim):
                raw = draft(claim=claim)
                result, audit = self.propose("이 영화는 크리스토퍼 놀란이 감독했나요?", raw)
                self.assertEqual(result, raw)
                self.assertEqual(audit[0]["reason_code"], "claim_mismatch")
        for question, claim in (
            ("이 영화는 크리스토퍼 놀란이 출연했나요?", "이 영화는 크리스토퍼 놀란이 출연했다."),
            ("이 영화는 크리스토퍼 놀란이 각본을 썼나요?", "이 영화는 크리스토퍼 놀란이 각본을 썼다."),
            ("이 영화에서 달이 빛나는 별로 등장했나요?", "이 영화에서 달이 빛나는 별로 등장했다."),
            ("달은 지구의 자연위성인가요?", "달은 지구의 자연위성이다."),
        ):
            with self.subTest(other_proposition=question):
                raw = draft(claim=claim)
                result, audit = self.propose(question, raw)
                self.assertEqual(result, raw)
                self.assertEqual(audit[0]["reason_code"], "question_not_unambiguous")

    def test_source_binding_and_literal_id_director_lines_are_mandatory(self):
        original = metadata(self.movie)
        changes = (
            {"movie_id": "other"}, {"document_id": "meta:other"}, {"scope": "film_description"},
            {"source_kind": "snapshot"}, {"text": "감독: 김용화"},
            {"text": "영화 ID: other\n감독: 김용화"},
            {"text": "영화 ID: fixture-42\n감독: 크리스토퍼 놀란"},
            {"text": original["text"] + "\n감독: 크리스토퍼 놀란"},
            {"text": original["text"] + "\n영화 ID: other"},
        )
        for change in changes:
            with self.subTest(change=change):
                result, audit = self.propose("이 영화는 크리스토퍼 놀란이 감독했나요?", sources=[{**original, **change}])
                self.assertEqual(result, draft())
                self.assertEqual(audit[0]["reason_code"], "metadata_source_invalid")
        result, audit = self.propose("이 영화는 크리스토퍼 놀란이 감독했나요?", registry={"크리스토퍼 놀란"})
        self.assertEqual(result, draft())
        self.assertEqual(audit[0]["reason_code"], "metadata_director_not_canonical")

    def test_other_verdicts_scopes_and_unstructured_drafts_remain_unchanged(self):
        for key, value in (("verdict", "근거와 상충"), ("scope", "현실 사실"),
                           ("reason", []), ("reason", ""), ("citations", "malformed")):
            raw = draft()
            raw["checks"][0][key] = value
            result, audit = self.propose("이 영화는 크리스토퍼 놀란이 감독했나요?", raw)
            self.assertEqual(result, raw)
            self.assertEqual(audit, [])
        for raw in ({"checks": "bad"}, {"facts": []}):
            result, audit = propose_director_checks(self.movie, "감독이 누구인가요?", raw, self.sources, self.registry)
            self.assertEqual(result, raw)
            self.assertEqual(audit, [])


if __name__ == "__main__":
    unittest.main()
