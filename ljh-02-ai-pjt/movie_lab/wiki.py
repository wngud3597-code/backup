"""Serial Wikipedia collection and selected-film-only snapshot fallback.

The search/fetch API parameters and empty-page guards follow step8_wiki_api.py.
The exercise stays unchanged; its import-time dotenv load and console output are
not imported into the app. API failures never expose exception bodies or headers.
"""

from __future__ import annotations

import html
import json
import math
import os
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote
from zipfile import BadZipFile, ZipFile

import requests
from dotenv import load_dotenv

from movie_lab.config import PROJECT_ROOT
from movie_lab.data import Movie


API_URL = "https://ko.wikipedia.org/w/api.php"
MAX_RESPONSE_BYTES = 10_000_000


class WikiError(RuntimeError):
    def __init__(self, category: str, http_status: int | None = None):
        super().__init__(category)
        self.category = category
        self.http_status = http_status


class LiveUnavailable(WikiError):
    """A safe reason to try the configured local snapshot repository."""


def resolve_user_agent() -> str:
    """Only inspect contact settings; never print their values."""
    configured = os.environ.get("WIKIMEDIA_USER_AGENT", "").strip()
    contact = os.environ.get("WIKI_CONTACT", "").strip()
    value = configured or (f"MovieLab/0.3 ({contact}) python-requests" if contact else "")
    if not value:
        raise LiveUnavailable("위키백과 연락처 설정이 없어 스냅샷 경로를 사용합니다")
    if not re.search(r"https?://[^\s)]+|[^\s()@]+@[^\s()@]+\.[^\s()@]+", value):
        raise LiveUnavailable("위키백과 요청 식별정보에 연락 가능한 이메일 또는 URL이 필요합니다")
    try:
        value.encode("latin-1")
    except UnicodeEncodeError:
        raise LiveUnavailable("위키백과 요청 식별정보는 HTTP 헤더에 사용할 문자로 설정해야 합니다") from None
    if "\r" in value or "\n" in value or len(value) > 500:
        raise LiveUnavailable("위키백과 요청 식별정보 형식을 확인해야 합니다")
    return value


class WikiClient:
    """One serial client, timeout 12s, one retry only for transient failures."""

    def __init__(self, user_agent: str, *, session: Any = None, timeout: float = 12.0,
                 retry_count: int = 1, min_interval: float = 0.3, sleeper: Any = time.sleep,
                 max_retry_wait: float = 4.0, wall_clock: Any = time.time):
        if not user_agent or "\r" in user_agent or "\n" in user_agent:
            raise LiveUnavailable("위키백과 요청 식별정보 형식을 확인해야 합니다")
        if (retry_count not in (0, 1) or timeout <= 0 or min_interval < 0
                or not isinstance(max_retry_wait, (int, float)) or not math.isfinite(max_retry_wait) or max_retry_wait < 0):
            raise WikiError("위키백과 요청 제한 설정 오류")
        self._user_agent = user_agent
        self.session = session if session is not None else requests.Session()
        self.timeout = timeout
        self.retry_count = retry_count
        self.min_interval = min_interval
        self._sleep = sleeper
        self.max_retry_wait = max_retry_wait
        self._wall_clock = wall_clock
        self._lock = threading.Lock()
        self._last_request = 0.0
        self.request_count = 0
        self.success_count = 0

    def _wait_before_retry(self, delay: float, status: int | None = None) -> None:
        # Never cap a server-requested delay and then retry earlier than allowed.
        # A caller can fall back to a snapshot rather than hold a UI indefinitely.
        if not math.isfinite(delay) or delay > self.max_retry_wait:
            raise WikiError("위키백과 재시도 대기 상한 초과로 대체 경로가 필요합니다", status)
        if delay > 0:
            self._sleep(delay)

    def _retry_delay(self, response: Any) -> float:
        value = response.headers.get("Retry-After")
        if value is None or not str(value).strip():
            return 0.75
        try:
            seconds = float(value)
            if not math.isfinite(seconds) or seconds < 0:
                raise WikiError("위키백과 재시도 대기 설정 형식 오류", response.status_code)
            return seconds
        except (TypeError, ValueError):
            try:
                moment = parsedate_to_datetime(str(value))
                if moment.tzinfo is None:
                    moment = moment.replace(tzinfo=timezone.utc)
                return max(0.0, moment.timestamp() - self._wall_clock())
            except (TypeError, ValueError, OverflowError):
                # Invalid Retry-After does not supply an enforceable deadline.
                return 0.75

    def _request(self, params: dict) -> dict:
        # The same lock spans each request and its backoff. No concurrent fanout.
        with self._lock:
            for attempt in range(self.retry_count + 1):
                delay = self.min_interval - (time.monotonic() - self._last_request)
                if delay > 0:
                    self._sleep(delay)
                self._last_request = time.monotonic()
                self.request_count += 1
                try:
                    response = self.session.get(API_URL, params={**params, "maxlag": 5},
                                                headers={"User-Agent": self._user_agent,
                                                         "X-Request-ID": str(uuid.uuid4())},
                                                timeout=self.timeout)
                except requests.Timeout:
                    if attempt < self.retry_count:
                        self._wait_before_retry(0.75 * (2 ** attempt))
                        continue
                    raise WikiError("위키백과 타임아웃") from None
                except requests.ConnectionError:
                    if attempt < self.retry_count:
                        self._wait_before_retry(0.75 * (2 ** attempt))
                        continue
                    raise WikiError("위키백과 네트워크 연결 실패") from None
                except requests.RequestException:
                    raise WikiError("위키백과 요청 실패") from None
                status = response.status_code
                if status != 200:
                    if status in {429, 500, 502, 503, 504} and attempt < self.retry_count:
                        self._wait_before_retry(self._retry_delay(response), status)
                        continue
                    category = "위키백과 요청 제한" if status == 429 else (
                        "위키백과 접근 제한" if status in {401, 403} else "위키백과 HTTP 오류")
                    raise WikiError(category, status)
                if len(getattr(response, "content", b"")) > MAX_RESPONSE_BYTES:
                    raise WikiError("위키백과 응답 크기 제한 초과")
                try:
                    data = response.json()
                except (ValueError, TypeError):
                    raise WikiError("위키백과 JSON 응답 형식 오류") from None
                if not isinstance(data, dict):
                    raise WikiError("위키백과 JSON 응답 구조 오류")
                if "error" in data:
                    detail = data.get("error")
                    if isinstance(detail, dict) and detail.get("code") == "maxlag" and attempt < self.retry_count:
                        self._wait_before_retry(self._retry_delay(response), status)
                        continue
                    raise WikiError("위키백과 API 오류")
                self.success_count += 1
                return data
        raise WikiError("위키백과 요청 실패")

    def search(self, query: str, limit: int = 5) -> list[dict]:
        if not isinstance(query, str) or not query.strip():
            return []
        if type(limit) is not int or not 1 <= limit <= 10:
            raise WikiError("위키백과 검색 개수 설정 오류")
        data = self._request({"action": "query", "list": "search", "srsearch": query[:300],
                              "srlimit": limit, "format": "json", "formatversion": 2})
        query_data = data.get("query", {})
        if not isinstance(query_data, dict):
            raise WikiError("위키백과 검색 응답 구조 오류")
        items = query_data.get("search", [])
        if not isinstance(items, list):
            raise WikiError("위키백과 검색 응답 구조 오류")
        result = []
        for item in items:
            if not isinstance(item, dict) or type(item.get("pageid")) is not int or not isinstance(item.get("title"), str):
                continue
            result.append({"candidate_id": f"wiki:{item['pageid']}", "page_id": item["pageid"],
                           "title": item["title"], "snippet": html.unescape(re.sub(
                               r"<[^>]+>", "", str(item.get("snippet", "")))),
                           "url": f"https://ko.wikipedia.org/wiki/{quote(item['title'].replace(' ', '_'))}",
                           "source_kind": "live", "collected_at": datetime.now(timezone.utc).isoformat()})
        return result

    def fetch_page(self, title: str) -> dict | None:
        if not isinstance(title, str) or not title.strip():
            return None
        data = self._request({"action": "query", "prop": "extracts|info", "titles": title,
                              "explaintext": 1, "inprop": "url", "redirects": 1,
                              "format": "json", "formatversion": 2})
        query_data = data.get("query", {})
        if not isinstance(query_data, dict):
            raise WikiError("위키백과 본문 응답 구조 오류")
        pages = query_data.get("pages", [])
        if not isinstance(pages, list):
            raise WikiError("위키백과 본문 응답 구조 오류")
        if not pages or not isinstance(pages[0], dict) or "missing" in pages[0]:
            return None
        page = pages[0]
        text = page.get("extract", "")
        if not isinstance(text, str) or not text.strip():
            return None
        if type(page.get("pageid")) is not int or not isinstance(page.get("title"), str) or not isinstance(page.get("fullurl"), str):
            raise WikiError("위키백과 문서 식별정보 오류")
        return {"candidate_id": f"wiki:{page['pageid']}", "document_id": f"wiki:{page['pageid']}",
                "page_id": page["pageid"], "title": page["title"], "url": page["fullurl"],
                "text": text.strip(), "source_kind": "live", "source": "wikipedia",
                "collected_at": datetime.now(timezone.utc).isoformat()}


def create_wiki_client() -> WikiClient:
    load_dotenv(dotenv_path=PROJECT_ROOT / ".env", override=False, verbose=False)
    return WikiClient(resolve_user_agent())


class SnapshotRepository:
    """Read only the selected movie's JSON members; never extract the archive."""

    def __init__(self, archive: str | Path):
        self.archive = Path(archive)
        self._entries: set[str] | None = None
        self.read_count = 0

    def _names(self) -> set[str]:
        if self._entries is None:
            try:
                with ZipFile(self.archive) as bundle:
                    self._entries = {name for name in bundle.namelist()
                                     if name.startswith("movielab_wiki/wikipedia/") and name.endswith(".json")}
            except (OSError, BadZipFile):
                raise WikiError("스냅샷 ZIP 경로 또는 형식을 확인해야 합니다") from None
        return self._entries

    def fetch(self, candidate_id: str) -> dict | None:
        if not isinstance(candidate_id, str) or not candidate_id.startswith("snapshot:"):
            raise WikiError("스냅샷 후보 ID 형식 오류")
        name = candidate_id.removeprefix("snapshot:")
        if name not in self._names():
            raise WikiError("허용되지 않은 스냅샷 후보 ID")
        try:
            with ZipFile(self.archive) as bundle:
                if bundle.getinfo(name).file_size > MAX_RESPONSE_BYTES:
                    raise WikiError("스냅샷 문서 크기 제한 초과")
                record = json.loads(bundle.read(name).decode("utf-8-sig"))
        except (OSError, BadZipFile, UnicodeError, json.JSONDecodeError, KeyError):
            raise WikiError("스냅샷 문서 읽기 또는 JSON 형식 오류") from None
        self.read_count += 1
        if not isinstance(record, dict):
            raise WikiError("스냅샷 문서 구조 오류")
        text = record.get("text", "")
        if not isinstance(text, str) or not text.strip():
            return None
        title, url, page_id = record.get("title"), record.get("url"), record.get("page_id")
        if not isinstance(title, str) or not title.strip() or not isinstance(url, str):
            raise WikiError("스냅샷 문서 식별정보 오류")
        document_id = f"wiki:{page_id}" if type(page_id) is int else f"snapshot:{name}"
        collected_at = record.get("collected_at")
        return {**record, "candidate_id": candidate_id, "document_id": document_id,
                "title": title.strip(), "text": text.strip(), "url": url,
                "source_kind": "snapshot", "source": record.get("source", "wikipedia"),
                "collected_at": collected_at if isinstance(collected_at, str) and collected_at.strip() else "미상"}

    def candidates(self, movie: Movie) -> list[dict]:
        prefix = f"movielab_wiki/wikipedia/{movie.movie_id}_"
        result = []
        for name in sorted(self._names()):
            if not name.startswith(prefix):
                continue
            document = self.fetch(f"snapshot:{name}")
            if document is None:
                continue
            result.append({key: document.get(key) for key in
                           ("candidate_id", "document_id", "page_id", "title", "url", "source_kind", "collected_at")}
                          | {"snippet": document["text"][:1100]})
        return result
