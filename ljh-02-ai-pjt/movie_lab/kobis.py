"""Independent KOBIS daily box-office lookup; no catalogue mapping or disk cache.

Only ``create_kobis_service`` loads credentials. Importing this module and tests
with an injected session do not read .env or make a request. Result caching is
disabled by default: each explicit lookup requests the provider again. The app
keeps only its current displayed result for ordinary rerenders, never in data.
"""

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import http.client
import logging
import os
import re
import time

import requests
from dotenv import load_dotenv

from movie_lab.config import PROJECT_ROOT


KOBIS_API_KEY_ENV = "KOBIS_API_KEY"
DAILY_ENDPOINT = (
    "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/"
    "searchDailyBoxOfficeList.json"
)
PUBLIC_SOURCE_URL = "https://www.kobis.or.kr/kobis/business/stat/boxs/findDailyBoxOfficeList.do"
DOCUMENTATION_URL = (
    "https://www.kobis.or.kr/kobisopenapi/homepg/apiservice/"
    "searchServiceInfo.do?serviceId=searchDailyBoxOffice"
)
TERMS_URL = "https://www.kobis.or.kr/kobisopenapi/homepg/board/findProvisionInfo.do"
KST = timezone(timedelta(hours=9))


def _integer(value):
    """Preserve unknown values separately from a real zero; monetary unit is KRW."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and re.fullmatch(r"[+-]?\d+", value.strip()):
        try:
            return int(value.strip())
        except ValueError:
            pass
    return None


def _text(value):
    return value.strip() if isinstance(value, str) and value.strip() else None


def _date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        raise ValueError("invalid date")
    if re.fullmatch(r"\d{8}", value):
        return datetime.strptime(value, "%Y%m%d").date()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("invalid date")
    return date.fromisoformat(value)


def _release_date(value):
    try:
        return _date(value).isoformat()
    except (TypeError, ValueError):
        return None


def _quiet_http_logging():
    """The GET query carries a key; suppress libraries' optional wire logging."""
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)
    logging.getLogger("requests.packages.urllib3.connectionpool").setLevel(logging.WARNING)
    http.client.HTTPConnection.debuglevel = 0
    http.client.HTTPSConnection.debuglevel = 0


class KobisService:
    """Finite timeout, zero automatic retries, and result caching off by default.

    Official terms do not establish a TTL exception to the storage restriction.
    Keep the current screen in session state; do not call this method merely to
    rerender it. A positive cache_ttl remains injectable for isolated tests or
    separately authorized use, and is neither enabled nor exposed by the app.
    No result is written to disk by this class.
    """

    def __init__(self, api_key=None, *, session=None, timeout=10.0,
                 cache_ttl=0.0, clock=None, monotonic=None):
        if not 0 < timeout <= 60 or not 0 <= cache_ttl <= 3600:
            raise ValueError("KOBIS timeout/cache TTL 설정 범위를 확인하세요.")
        self._api_key = api_key.strip() if isinstance(api_key, str) else ""
        self._session = session
        self.timeout = float(timeout)
        self.cache_ttl = float(cache_ttl)
        self._clock = clock or (lambda: datetime.now(KST))
        self._monotonic = monotonic or time.monotonic
        self._cache = {}
        self.request_count = 0

    @property
    def configured(self):
        return bool(self._api_key)

    def _result(self, target_date=None, *, status="failure", category=None,
                message=None, http_status=None, calls=0):
        return {
            "status": status, "target_date": target_date, "rows": [],
            "source": {
                "title": "영화진흥위원회 통합전산망 오픈 API · 일별 박스오피스",
                "url": PUBLIC_SOURCE_URL, "documentation_url": DOCUMENTATION_URL,
                "terms_url": TERMS_URL, "query_date": target_date,
                "aggregation_date": target_date, "collected_at": None,
            },
            "cache_hit": False, "calls": calls,
            "error": ({"category": category, "http_status": http_status,
                       "message": message} if category else None),
        }

    def daily_box_office(self, target_date, *, refresh=False, item_per_page=10,
                         multi_movie_yn="", rep_nation_cd="", wide_area_cd=""):
        """Return today's view of one *past* day's independently sourced top 10.

        Daily audience/revenue and cumulative audience/revenue have separate
        fields. Missing numeric data is None, never synthesized as zero. Filter
        parameters are part of the cache key; the secret is not part of it.
        """
        try:
            day = _date(target_date)
            today = self._clock().astimezone(KST).date()
            valid_options = (
                isinstance(item_per_page, int) and not isinstance(item_per_page, bool)
                and 1 <= item_per_page <= 10
                and multi_movie_yn in ("", "Y", "N")
                and rep_nation_cd in ("", "K", "F")
                and isinstance(wide_area_cd, str)
                and (not wide_area_cd or re.fullmatch(r"\d{1,10}", wide_area_cd))
            )
            if day >= today or not valid_options:
                raise ValueError("invalid request")
        except (TypeError, ValueError, OverflowError):
            return self._result(category="invalid_request", message="지난 날짜와 조회 조건을 확인하세요.")
        day_text = day.isoformat()
        if not self.cache_ttl:
            # Also discard entries held by a service from before cache disablement.
            self._cache.clear()
        if not self.configured:
            return self._result(day_text, status="unconfigured", category="missing_key",
                                message="KOBIS_API_KEY를 로컬 환경에 설정한 뒤 조회하세요.")
        cache_key = (day_text, item_per_page, multi_movie_yn, rep_nation_cd, wide_area_cd)
        now = self._monotonic()
        cached = self._cache.get(cache_key)
        if cached and not refresh and now - cached[0] < self.cache_ttl:
            result = deepcopy(cached[1])
            result.update(cache_hit=True, calls=0)
            return result
        # No stale success is reused after expiry or an explicit refresh failure.
        self._cache.pop(cache_key, None)
        params = {"key": self._api_key, "targetDt": day.strftime("%Y%m%d"),
                  "itemPerPage": str(item_per_page)}
        for name, value in (("multiMovieYn", multi_movie_yn),
                            ("repNationCd", rep_nation_cd), ("wideAreaCd", wide_area_cd)):
            if value:
                params[name] = value
        _quiet_http_logging()
        if self._session is None:
            self._session = requests.Session()
            self._session.mount("https://", requests.adapters.HTTPAdapter(max_retries=0))
        self.request_count += 1
        try:
            response = self._session.get(DAILY_ENDPOINT, params=params,
                                         timeout=self.timeout, allow_redirects=False)
        except requests.Timeout:
            return self._result(day_text, category="timeout", calls=1,
                                message="KOBIS 응답 시간이 초과되었습니다. 자동 재시도하지 않았습니다.")
        except requests.RequestException:
            return self._result(day_text, category="network", calls=1,
                                message="KOBIS 연결에 실패했습니다. 자동 재시도하지 않았습니다.")
        status = response.status_code
        if status != 200:
            category = ("authentication" if status in (401, 403) else
                        "rate_limit" if status == 429 else
                        "redirect" if 300 <= status < 400 else
                        "server" if status >= 500 else "http_error")
            return self._result(day_text, category=category, calls=1, http_status=status,
                                message="KOBIS 요청을 처리하지 못했습니다. 상태 코드와 설정을 확인하세요.")
        try:
            payload = response.json()
        except (TypeError, ValueError):
            return self._result(day_text, category="invalid_json", calls=1, http_status=status,
                                message="KOBIS 응답 JSON을 읽지 못했습니다.")
        if not isinstance(payload, dict):
            return self._result(day_text, category="invalid_response", calls=1, http_status=status,
                                message="KOBIS 응답 구조를 확인할 수 없습니다.")
        if "faultInfo" in payload:
            # The official per-code meanings were not verified; do not invent
            # authentication/quota diagnoses from an untrusted message string.
            return self._result(day_text, category="api_fault", calls=1, http_status=status,
                                message="KOBIS 내부 오류 응답입니다. 키·권한·조회 조건을 확인하세요.")
        box = payload.get("boxOfficeResult")
        rows = box.get("dailyBoxOfficeList") if isinstance(box, dict) else None
        if not isinstance(rows, list):
            return self._result(day_text, category="invalid_response", calls=1, http_status=status,
                                message="KOBIS 일별 목록의 응답 구조를 확인할 수 없습니다.")
        show_range = _text(box.get("showRange"))
        expected_range = day.strftime("%Y%m%d") + "~" + day.strftime("%Y%m%d")
        if show_range and show_range != expected_range:
            return self._result(day_text, category="date_mismatch", calls=1, http_status=status,
                                message="KOBIS 응답 집계일이 요청한 날짜와 다릅니다.")
        if not rows:
            return self._result(day_text, status="empty", category="empty", calls=1,
                                http_status=status, message="해당 날짜·조건의 일별 박스오피스가 없습니다.")
        clean = []
        for row in rows:
            if not isinstance(row, dict) or not _text(row.get("movieCd")) or not _text(row.get("movieNm")):
                return self._result(day_text, category="invalid_response", calls=1, http_status=status,
                                    message="KOBIS 영화 식별 필드가 누락되었습니다.")
            clean.append({
                "rank": _integer(row.get("rank")), "movie_code": _text(row.get("movieCd")),
                "title": _text(row.get("movieNm")), "release_date": _release_date(row.get("openDt")),
                "audience_daily": _integer(row.get("audiCnt")),
                "audience_cumulative": _integer(row.get("audiAcc")),
                "sales_daily": _integer(row.get("salesAmt")),
                "sales_cumulative": _integer(row.get("salesAcc")),
                "screens_daily": _integer(row.get("scrnCnt")),
                "screenings_daily": _integer(row.get("showCnt")),
            })
        result = self._result(day_text, status="success", calls=1)
        result["rows"] = clean
        result["boxoffice_type"] = _text(box.get("boxofficeType"))
        result["show_range"] = show_range
        result["source"]["collected_at"] = self._clock().astimezone(KST).isoformat(timespec="seconds")
        if self.cache_ttl:
            if len(self._cache) >= 16:
                self._cache.pop(next(iter(self._cache)))
            self._cache[cache_key] = (self._monotonic(), deepcopy(result))
        return result


def create_kobis_service(**kwargs):
    """Explicit approved client entry point; never print credentials or dotenv."""
    load_dotenv(dotenv_path=PROJECT_ROOT / ".env", override=False, verbose=False)
    return KobisService(os.environ.get(KOBIS_API_KEY_ENV), **kwargs)
