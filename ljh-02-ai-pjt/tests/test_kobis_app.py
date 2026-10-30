"""Isolated Streamlit integration checks; fixtures never appear in normal app runs."""
from copy import deepcopy
from datetime import date
from pathlib import Path
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
from movie_lab.kobis import KobisService
from movie_lab.state import append_assistant_message
from tests.test_kobis import NOW, Response, Session, payload

PROJECT=Path(__file__).resolve().parents[1]

class KobisAppTests(unittest.TestCase):
    def test_missing_key_lookup_and_rerun_do_not_block_movie_selection_or_history(self):
        service=KobisService(None, clock=lambda:NOW)
        with patch('movie_lab.kobis.create_kobis_service',return_value=service) as factory, \
             patch('socket.socket.connect',side_effect=AssertionError('offline UI')):
            app=AppTest.from_file(str(PROJECT/'app.py')).run()
            self.assertFalse(app.exception)
            factory.assert_not_called()
            app.button(key='kobis_submit').click().run()
            self.assertFalse(app.exception)
            self.assertTrue(any('KOBIS_API_KEY가 설정되지' in item.value for item in app.info))
            self.assertEqual(service.request_count,0)
            app.selectbox(key='selected_movie_id').select('157336').run()
            self.assertFalse(app.exception)
            self.assertEqual(app.selectbox(key='selected_movie_id').value,'157336')
            app.run()
            factory.assert_called_once()
            self.assertEqual(service.request_count,0)

    def test_rerun_only_redisplays_current_view_but_new_submit_requests_again(self):
        http=Session(Response(payload(scrnCnt='',audiCnt='0')),Response(payload(audiCnt='1')))
        # Exercise migration of a service retained before the cache-default fix.
        service=KobisService('TEST_ONLY_NOT_A_REAL_KEY',session=http,clock=lambda:NOW,cache_ttl=300)
        with patch('movie_lab.kobis.create_kobis_service',return_value=service) as factory, \
             patch('socket.socket.connect',side_effect=AssertionError('offline UI')):
            app=AppTest.from_file(str(PROJECT/'app.py')).run()
            threads={}
            append_assistant_message(threads,'157336','격리된 과거 답변 [근거 1]',
                                     [{'title':'테스트 출처','quote':'보존 구절','url':'https://example.org/isolated'}])
            original=deepcopy(threads)
            app.session_state['threads_by_movie']=threads
            app.date_input(key='kobis_target_date').set_value(date(2026,10,21))
            app.button(key='kobis_submit').click().run()
            self.assertFalse(app.exception)
            self.assertEqual(len(http.calls),1)
            self.assertIn('일별 관객 (명)',app.dataframe[0].value.columns)
            self.assertEqual(app.dataframe[0].value.iloc[0]['일별 관객 (명)'],'0')
            app.run()
            self.assertEqual(len(http.calls),1)
            app.button(key='kobis_submit').click().run()
            self.assertFalse(app.exception)
            self.assertEqual(len(http.calls),2)
            self.assertEqual(service.cache_ttl,0)
            self.assertFalse(app.session_state['kobis_report']['cache_hit'])
            self.assertEqual(app.dataframe[0].value.iloc[0]['일별 관객 (명)'],'1')
            app.run()
            self.assertEqual(len(http.calls),2)
            self.assertEqual(app.session_state['threads_by_movie'],original)
            factory.assert_called_once_with(cache_ttl=0)

    def test_kobis_http_failure_preserves_history_and_chat_area(self):
        service=KobisService('TEST_ONLY_NOT_A_REAL_KEY',session=Session(Response(status=503)),clock=lambda:NOW)
        with patch('movie_lab.kobis.create_kobis_service',return_value=service), \
             patch('socket.socket.connect',side_effect=AssertionError('offline UI')):
            app=AppTest.from_file(str(PROJECT/'app.py')).run()
            threads={}
            append_assistant_message(threads,'157336','격리된 과거 답변 [근거 1]',
                                     [{'title':'당시 출처','quote':'보존 구절','url':'https://example.org/isolated'}])
            original=deepcopy(threads)
            app.session_state['threads_by_movie']=threads
            app.selectbox(key='selected_movie_id').select('157336').run()
            app.date_input(key='kobis_target_date').set_value(date(2026,10,21))
            app.button(key='kobis_submit').click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.session_state['kobis_report']['error']['http_status'],503)
            self.assertEqual(service.request_count,1)
            self.assertTrue(any('KOBIS 요청을 처리하지 못했습니다' in row.value for row in app.warning))
            self.assertEqual(app.session_state['threads_by_movie'],original)
            self.assertEqual(len(app.chat_input),1)
            app.selectbox(key='selected_movie_id').select('753091').run()
            app.selectbox(key='selected_movie_id').select('157336').run()
            self.assertFalse(app.exception)
            self.assertEqual(app.session_state['threads_by_movie']['157336'],original['157336'])
            self.assertEqual(app.session_state['threads_by_movie']['753091'],[])
            self.assertEqual(service.request_count,1)

if __name__=='__main__':unittest.main()
