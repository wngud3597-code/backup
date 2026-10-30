"""Stored-result presentation checks only; no model/client calls."""

import ast
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from movie_lab.display import answer_for_display, metadata_quote_fields
from movie_lab.evidence import source_quotes
from movie_lab.state import append_assistant_message, get_thread


ROOT = Path(__file__).resolve().parents[1]


def saved_cases():
    path = ROOT / 'artifacts/review_completion/browser/api_events.jsonl'
    return {row['movie_id']: row['result']
            for row in map(json.loads, path.read_text(encoding='utf-8').splitlines())
            if row['event'] == 'answer_result'}


class DisplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = saved_cases()

    def test_saved_director_item_changes_only_presentation_not_verdict_or_snapshot(self):
        case = deepcopy(self.cases['753091'])
        before = deepcopy(case)
        shown = answer_for_display(case['content'], case['sources'])
        self.assertIn('**영화 정보 · 감독 · 근거와 상충**', shown)
        self.assertNotIn('**작품 속 묘사 · 근거와 상충**', shown)
        self.assertIn('**현실 사실 · 확인됨**', shown)
        self.assertIn('감독은 김용화입니다. [근거 1]', shown)
        self.assertEqual(case, before)
        self.assertEqual(answer_for_display(shown, case['sources']), shown)
        general = self.cases['157336']
        self.assertEqual(answer_for_display(general['content'], general['sources']), general['content'])

    def test_ambiguous_scene_negative_mixed_or_missing_evidence_is_not_reclassified(self):
        case = self.cases['753091']
        original = case['content']
        for claim in ('영화 속 장면에서 감독은 크리스토퍼 놀란이다.',
                      '만약 이 영화는 크리스토퍼 놀란이 감독했다면?',
                      '이 영화는 크리스토퍼 놀란이 감독하지 않았다.',
                      '이 영화는 크리스토퍼 놀란이 감독했고 출연했다.'):
            answer = original.replace('이 영화는 크리스토퍼 놀란이 감독했다.', claim)
            self.assertEqual(answer_for_display(answer, case['sources']), answer)
        for change in ('missing_director', 'wrong_document_id', 'film_source', 'unknown_id'):
            sources = deepcopy(case['sources'])
            if change == 'missing_director':
                sources[0]['quote'] = '제목: 더 문\n연도: 2023'
                sources[0].pop('quotes', None)
            elif change == 'wrong_document_id':
                sources[0]['document_id'] = 'meta:other'
            elif change == 'film_source':
                sources[0]['scope'] = 'film_description'
            else:
                sources[0].pop('movie_id', None)
            self.assertEqual(answer_for_display(original, sources), original)
        mixed = original.replace('감독은 김용화입니다. [근거 1]', '감독은 김용화입니다. [근거 1, 2]')
        self.assertEqual(answer_for_display(mixed, case['sources']), mixed)

    def test_field_preview_has_only_exact_separate_original_lines_and_no_plot(self):
        case = self.cases['157336']
        source = case['sources'][0]
        before = deepcopy(source)
        fields = metadata_quote_fields(case['content'], 1, source)
        self.assertEqual(fields, ['감독: 크리스토퍼 놀란', '상영 시간(분): 169'])
        originals = source_quotes(source)
        self.assertGreaterEqual(len(originals), 2)
        for field in fields:
            self.assertTrue(any(field in quote for quote in originals))
            self.assertNotIn('\n', field)
            self.assertNotIn('쿠퍼', field)
        self.assertEqual(metadata_quote_fields('상영 시간은 169분입니다. [근거 1]', 1, source), ['상영 시간(분): 169'])
        self.assertEqual(metadata_quote_fields('상영 시간 [근거 2]', 1, source), [])
        self.assertEqual(source, before)

    def test_unknown_metadata_layout_does_not_invent_a_field(self):
        legacy = {'source_kind': 'metadata', 'scope': 'movie_metadata', 'quote': '옛 인용에는 러닝타임을 숫자로 분리할 수 없다.'}
        before = deepcopy(legacy)
        self.assertEqual(metadata_quote_fields('상영 시간 확인 [근거 1]', 1, legacy), [])
        self.assertEqual(source_quotes(legacy), [legacy['quote']])
        self.assertEqual(legacy, before)

    def test_real_renderer_keeps_full_metadata_quotes_in_closed_expander(self):
        source = (ROOT / 'app.py').read_text(encoding='utf-8')
        node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == 'render_sources')
        renderer = ast.get_source_segment(source, node)
        case = self.cases['157336']
        program = ('import streamlit as st\nfrom urllib.parse import urlsplit\n'
                   'from movie_lab.evidence import cited_sources\n' + renderer + '\n'
                   f'render_sources({case["content"]!r}, {case["sources"]!r})\n')
        with patch('socket.socket.connect', side_effect=AssertionError('offline display')):
            app = AppTest.from_string(program).run()
            self.assertFalse(app.exception)
            self.assertEqual(len(app.expander), 2)
            self.assertFalse(app.expander[1].proto.expanded)
            self.assertIn('전체 원래 인용', app.expander[1].label)
            original_markdown = [r.value for r in app.expander[1].markdown]
            self.assertEqual(original_markdown, source_quotes(case['sources'][0]))
            self.assertIn('감독: 크리스토퍼 놀란', [r.value for r in app.markdown])
            self.assertIn('상영 시간(분): 169', [r.value for r in app.markdown])
            app.run()
            self.assertFalse(app.exception)

    def test_display_preserves_single_quote_and_movie_thread_snapshots(self):
        threads = {}
        for movie_id, case in self.cases.items():
            append_assistant_message(threads, movie_id, case['content'], case['sources'])
        before = deepcopy(threads)
        for movie_id in ('157336', '753091', '157336'):
            for message in get_thread(threads, movie_id):
                answer_for_display(message['content'], message['sources'])
                for number, source in enumerate(message['sources'], 1):
                    metadata_quote_fields(message['content'], number, source)
        self.assertEqual(threads, before)
        self.assertEqual(source_quotes({'quote': '과거 단일 인용'}), ['과거 단일 인용'])


if __name__ == '__main__':
    unittest.main()
