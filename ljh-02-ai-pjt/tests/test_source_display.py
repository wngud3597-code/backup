"""Only stored answer snapshots are displayed; no app/API clients are created."""

import ast
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from movie_lab.evidence import source_caption, source_quotes


PROJECT = Path(__file__).resolve().parents[1]


class SourceDisplayTests(unittest.TestCase):
    def setUp(self):
        blocked = patch("socket.socket.connect", side_effect=AssertionError("Offline source display test"))
        blocked.start()
        self.addCleanup(blocked.stop)

    def test_saved_classification_provenance_and_collection_time_are_distinct(self):
        for source, fragments in (
            ({"source_kind": "metadata", "scope": "movie_metadata"},
             ("영화 메타데이터", "제공 메타데이터", "수집 시점: 미상")),
            ({"source_kind": "snapshot", "scope": "film_description", "collected_at": "2026-09-10"},
             ("작품 문서", "제공 스냅샷", "수집 시점: 2026-09-10")),
            ({"source_kind": "live", "scope": "background_unverified", "collected_at": "2026-10-22T01:00:00Z"},
             ("배경 문서", "작품 식별 확인 필요", "실시간 수집", "2026-10-22T01:00:00Z")),
            ({"title": "과거 형식 출처"}, ("문서 분류 미상", "출처 방식 미상", "수집 시점: 미상")),
        ):
            with self.subTest(source=source):
                before = deepcopy(source)
                caption = source_caption(source)
                for fragment in fragments:
                    self.assertIn(fragment, caption)
                self.assertEqual(source, before)

    def test_legacy_and_multiple_quotes_keep_order_without_duplicate_or_state_mutation(self):
        self.assertEqual(source_quotes({"quote": "예전 구절"}), ["예전 구절"])
        source = {"quote": "첫 구절", "quotes": ["첫 구절", "둘째 구절", " 둘째 구절 ", "", None, 7]}
        before = deepcopy(source)
        self.assertEqual(source_quotes(source), ["첫 구절", "둘째 구절"])
        self.assertEqual(source, before)
        self.assertEqual(source_quotes({"quotes": ["목록만 있는 구절"]}), ["목록만 있는 구절"])
        self.assertEqual(source_quotes({"quote": None, "quotes": "목록이 아님"}), [])

    def test_actual_render_function_keeps_numbers_shows_metadata_and_multiple_quotes_once(self):
        # Extract only the actual render function, avoiding app startup and every
        # client boundary. This verifies its Streamlit elements, not a copy.
        app_source = (PROJECT / "app.py").read_text(encoding="utf-8")
        function = next(node for node in ast.parse(app_source).body
                        if isinstance(node, ast.FunctionDef) and node.name == "render_sources")
        renderer = ast.get_source_segment(app_source, function)
        sources = [
            {"title": "과거 단일 출처", "url": "https://example.org/legacy", "quote": "보존된 옛 구절"},
            {"title": "작품 스냅샷", "url": "https://example.org/film", "source_kind": "snapshot",
             "scope": "film_description", "collected_at": "2026-09-10",
             "quote": "첫 작품 구절", "quotes": ["첫 작품 구절", "둘째 작품 구절", "둘째 작품 구절"]},
            {"title": "배경 실시간", "url": "https://example.org/background", "source_kind": "live",
             "scope": "background_unverified", "quotes": ["배경 근거 구절"]},
            {"title": "인용되지 않은 출처", "quote": "보이면 안 되는 구절"},
        ]
        program = ("import streamlit as st\nfrom urllib.parse import urlsplit\n"
                   "from movie_lab.evidence import cited_sources\n" + renderer + "\n"
                   f"sources = {sources!r}\n"
                   "render_sources('확인 [근거 3, 1, 2] [근거 2]', sources)\n"
                   "render_sources('인용 없는 안내', sources)\n")
        app = AppTest.from_string(program).run()
        self.assertFalse(app.exception)
        markdown = [row.value for row in app.markdown]
        for number, title in ((1, "과거 단일 출처"), (2, "작품 스냅샷"), (3, "배경 실시간")):
            self.assertIn(f"**[근거 {number}]** {title}", markdown)
        for quote in ("보존된 옛 구절", "첫 작품 구절", "둘째 작품 구절", "배경 근거 구절"):
            self.assertEqual(markdown.count(quote), 1)
        self.assertFalse(any("인용되지 않은 출처" in value or "보이면 안 되는 구절" in value for value in markdown))
        captions = "\n".join(row.value for row in app.caption)
        for fragment in ("문서 분류 미상", "작품 문서", "제공 스냅샷", "2026-09-10",
                         "배경 문서", "실시간 수집", "수집 시점: 미상", "답변에 인용된 근거가 없습니다."):
            self.assertIn(fragment, captions)
        app.run()
        self.assertFalse(app.exception)
        self.assertEqual([row.value for row in app.markdown], markdown)


if __name__ == "__main__":
    unittest.main()
