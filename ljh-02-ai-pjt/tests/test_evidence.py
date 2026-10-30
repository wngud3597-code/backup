"""Citation numbering tests, not semantic claim/evidence evaluation."""

import json
from pathlib import Path
import unittest

from movie_lab.evidence import cited_sources


FIXTURE = Path(__file__).parent / "fixtures" / "conversations.json"


class CitationTests(unittest.TestCase):
    def setUp(self):
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.sources = [
            fixture["movie_a"]["sources"][0],
            fixture["movie_a"]["next_sources"][0],
            fixture["movie_b"]["sources"][0],
        ]

    def test_original_single_and_comma_separated_patterns(self):
        used = cited_sources("확인 [근거 3, 1] 그리고 [근거2]", self.sources)
        self.assertEqual([number for number, _ in used], [1, 2, 3])

    def test_duplicate_and_out_of_range_citations_do_not_add_sources(self):
        used = cited_sources("[근거 1, 1, 0, 9] [근거 1]", self.sources)
        self.assertEqual(used, [(1, self.sources[0])])

    def test_only_cited_sources_are_returned(self):
        self.assertEqual(
            cited_sources("확인 [근거 2]", self.sources),
            [(2, self.sources[1])],
        )

    def test_uncited_or_malformed_answer_returns_empty_list(self):
        for answer in ("출처 없는 답변", "[근거 없음]", "[근거 -1]", "[근거 9]"):
            with self.subTest(answer=answer):
                self.assertEqual(cited_sources(answer, self.sources), [])

    def test_extraction_does_not_reorder_or_modify_source_snapshots(self):
        before = json.dumps(self.sources, ensure_ascii=False)
        cited_sources("[근거 3, 1]", self.sources)
        self.assertEqual(json.dumps(self.sources, ensure_ascii=False), before)


if __name__ == "__main__":
    unittest.main()
