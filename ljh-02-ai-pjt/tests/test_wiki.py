"""Offline collection/fallback and the real known homonym pattern."""

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from zipfile import ZipFile

import requests

from movie_lab.document_models import classify_document_identity
from movie_lab.wiki import LiveUnavailable, SnapshotRepository, WikiClient, WikiError, resolve_user_agent
from tests.test_document_llm import sample_movie


def http_response(data=None, status=200):
    result = MagicMock(status_code=status, headers={}, content=b"{}")
    result.json.return_value = data
    return result


class WikiTests(unittest.TestCase):
    def setUp(self):
        self.session = MagicMock()
        self.sleep = MagicMock()
        self.client = WikiClient("MovieLab/0.3 (https://example.invalid/contact)",
                                 session=self.session, sleeper=self.sleep, min_interval=0)

    def test_search_and_fetch_reuse_step8_parameters_and_safe_empty_guard(self):
        self.session.get.side_effect = [http_response({"query": {"search": [
            {"pageid": 1, "title": "달", "snippet": '<span>천체</span> &amp; 위성'}]}}),
            http_response({"query": {"pages": [{"pageid": 1, "title": "달", "fullurl": "https://ko.wikipedia.org/wiki/달", "extract": "달은 위성이다."}]}}),
            http_response({"query": {"pages": [{"pageid": 2, "title": "빈 문서", "fullurl": "https://example.invalid", "extract": " "}]}})]
        candidates = self.client.search("달")
        self.assertEqual(candidates[0]["snippet"], "천체 & 위성")
        document = self.client.fetch_page("달")
        self.assertEqual(document["source_kind"], "live")
        self.assertEqual(document["document_id"], "wiki:1")
        self.assertIsNone(self.client.fetch_page("빈 문서"))
        search_args = self.session.get.call_args_list[0].kwargs
        self.assertEqual(search_args["timeout"], 12)
        self.assertIn("X-Request-ID", search_args["headers"])
        self.assertEqual(search_args["params"]["list"], "search")
        self.assertEqual(self.session.get.call_args_list[1].kwargs["params"]["prop"], "extracts|info")

    def test_retry_is_bounded_and_access_errors_are_not_retried(self):
        self.session.get.side_effect = requests.Timeout("sensitive request")
        with self.assertRaisesRegex(WikiError, "타임아웃"):
            self.client.search("달")
        self.assertEqual(self.session.get.call_count, 2)
        self.session.get.reset_mock()
        self.session.get.side_effect = None
        self.session.get.return_value = http_response(status=403)
        with self.assertRaises(WikiError) as caught:
            self.client.search("달")
        self.assertEqual(caught.exception.http_status, 403)
        self.assertEqual(self.session.get.call_count, 1)

    def test_invalid_json_and_empty_results_are_distinct(self):
        result = http_response()
        result.json.side_effect = ValueError("sensitive body")
        self.session.get.return_value = result
        with self.assertRaisesRegex(WikiError, "JSON 응답 형식 오류"):
            self.client.search("달")
        self.session.get.return_value = http_response({"query": {"search": []}})
        self.assertEqual(self.client.search("달"), [])

    def test_retry_after_numeric_and_http_dates_never_retry_early(self):
        now = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)
        for header in ("2", format_datetime(now + timedelta(seconds=2), usegmt=True)):
            with self.subTest(header_kind="numeric" if header == "2" else "HTTP-date"):
                session, sleeper = MagicMock(), MagicMock()
                limited = http_response(status=429)
                limited.headers = {"Retry-After": header}
                session.get.side_effect = [limited, http_response({"query": {"search": []}})]
                client = WikiClient("MovieLab test", session=session, sleeper=sleeper, min_interval=0,
                                    wall_clock=lambda: now.timestamp())
                self.assertEqual(client.search("달"), [])
                self.assertEqual(session.get.call_count, 2)
                sleeper.assert_called_once_with(2.0)
        for header in ("120", format_datetime(now + timedelta(seconds=120), usegmt=True)):
            with self.subTest(header_kind="long numeric" if header == "120" else "long HTTP-date"):
                session, sleeper = MagicMock(), MagicMock()
                limited = http_response(status=503)
                limited.headers = {"Retry-After": header}
                session.get.return_value = limited
                client = WikiClient("MovieLab test", session=session, sleeper=sleeper, min_interval=0,
                                    wall_clock=lambda: now.timestamp(), max_retry_wait=4)
                with self.assertRaisesRegex(WikiError, "대기 상한 초과") as caught:
                    client.search("달")
                self.assertEqual(caught.exception.http_status, 503)
                self.assertEqual(session.get.call_count, 1)
                sleeper.assert_not_called()

    def test_contact_setting_missing_or_invalid_is_safe_fallback_reason(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(LiveUnavailable):
                resolve_user_agent()
        with patch.dict("os.environ", {"WIKI_CONTACT": "test@example.invalid"}, clear=True):
            self.assertIn("MovieLab/", resolve_user_agent())

    def test_snapshot_selected_movie_only_and_wrong_moon_excluded(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "snapshots.zip"
            with ZipFile(archive, "w") as bundle:
                for movie_id, title, text in [
                    ("753091", "더 문", "《더 문》(Moon)은 2009년 공개된 덩컨 존스 감독의 영화이다."),
                    ("753091", "달", "달은 지구의 자연위성이다."),
                    ("17431", "더 문", "《더 문》은 2009년 공개된 영화이다."),
                ]:
                    bundle.writestr(f"movielab_wiki/wikipedia/{movie_id}_{title}.json", json.dumps({
                        "page_id": 422453 if title == "더 문" else 1, "title": title,
                        "url": "https://ko.wikipedia.org/wiki/" + title, "text": text,
                        "collected_at": "2026-09-01T00:00:00Z"}, ensure_ascii=False))
            repository = SnapshotRepository(archive)
            candidates = repository.candidates(sample_movie())
            self.assertEqual(len(candidates), 2)
            own = next(item for item in candidates if item["title"] == "더 문")
            document = repository.fetch(own["candidate_id"])
            self.assertEqual(document["source_kind"], "snapshot")
            self.assertEqual(document["collected_at"], "2026-09-01T00:00:00Z")
            self.assertEqual(classify_document_identity(sample_movie(), document).status, "불일치")
            background = next(item for item in candidates if item["title"] == "달")
            self.assertEqual(classify_document_identity(sample_movie(), repository.fetch(background["candidate_id"])).status, "확인 필요")
            with self.assertRaises(WikiError):
                repository.fetch("snapshot:../../.env")


if __name__ == "__main__":
    unittest.main()
