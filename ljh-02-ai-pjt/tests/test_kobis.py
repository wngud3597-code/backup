"""KOBIS contract checks use substitute HTTP responses, never real credentials."""

from copy import deepcopy
from datetime import date, datetime, timezone
import json
import unittest
from unittest.mock import patch

import requests

from movie_lab.kobis import DAILY_ENDPOINT, KobisService, create_kobis_service


NOW = datetime(2026, 10, 22, 4, 0, tzinfo=timezone.utc)
# Intentionally not a real or realistically formatted credential.
TEST_SECRET = "TEST_ONLY_NOT_A_REAL_KEY"


def payload(**changes):
    row = {"rank": "1", "movieCd": "test-movie", "movieNm": "테스트 작품",
           "openDt": "2026-10-01", "audiCnt": "0", "audiAcc": "2500",
           "salesAmt": "100000", "salesAcc": "3000000", "scrnCnt": "",
           "showCnt": "20"}
    row.update(changes)
    return {"boxOfficeResult": {"boxofficeType": "일별 박스오피스",
                               "showRange": "20261021~20261021",
                               "dailyBoxOfficeList": [row]}}


class Response:
    def __init__(self, data=None, status=200):
        self.data, self.status_code = data, status

    def json(self):
        if isinstance(self.data, Exception):
            raise self.data
        return deepcopy(self.data)


class Session:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class KobisTests(unittest.TestCase):
    def service(self, *responses, **kwargs):
        session = Session(*responses)
        return KobisService(TEST_SECRET, session=session, clock=lambda: NOW, **kwargs), session

    def safe(self, result):
        rendered = json.dumps(result, ensure_ascii=False)
        self.assertNotIn(TEST_SECRET, rendered)
        self.assertNotIn("?key=", rendered)
        self.assertNotIn("RAW_REMOTE_MESSAGE", rendered)

    def test_daily_cumulative_unknown_zero_and_source(self):
        service, session = self.service(Response(payload()))
        result = service.daily_box_office(date(2026, 10, 21))
        self.assertEqual(result["status"], "success")
        row = result["rows"][0]
        self.assertEqual((row["audience_daily"], row["audience_cumulative"]), (0, 2500))
        self.assertEqual((row["sales_daily"], row["sales_cumulative"]), (100000, 3000000))
        self.assertIsNone(row["screens_daily"])
        self.assertEqual(result["source"]["query_date"], "2026-10-21")
        self.assertIn("+09:00", result["source"]["collected_at"])
        self.assertEqual(result["calls"], 1)
        url, options = session.calls[0]
        self.assertEqual(url, DAILY_ENDPOINT)
        self.assertTrue(url.startswith("https://"))
        self.assertEqual(options["params"]["targetDt"], "20261021")
        self.assertFalse(options["allow_redirects"])
        self.assertEqual(options["timeout"], 10)
        self.safe(result)

    def test_same_request_reuses_memory_with_snapshot_and_filters(self):
        other_day = payload()
        other_day["boxOfficeResult"]["showRange"] = "20261020~20261020"
        service, session = self.service(Response(payload()), Response(other_day), Response(payload()), cache_ttl=300)
        first = service.daily_box_office("2026-10-21")
        first["rows"][0]["title"] = "caller mutation"
        cached = service.daily_box_office("20261021")
        self.assertTrue(cached["cache_hit"])
        self.assertEqual(cached["calls"], 0)
        self.assertEqual(cached["rows"][0]["title"], "테스트 작품")
        self.assertEqual(len(session.calls), 1)
        self.assertFalse(service.daily_box_office("2026-10-20")["cache_hit"])
        self.assertFalse(service.daily_box_office("2026-10-21", rep_nation_cd="K")["cache_hit"])
        self.assertEqual(len(session.calls), 3)

    def test_default_cache_disabled_so_each_explicit_lookup_requests_again(self):
        for legacy_cache in (False, True):
            with self.subTest(legacy_cache=legacy_cache):
                options = {"cache_ttl": 300} if legacy_cache else {}
                service, session = self.service(Response(payload()), Response(payload()), **options)
                if not legacy_cache:
                    self.assertEqual(service.cache_ttl, 0)
                first = service.daily_box_office("2026-10-21")
                if legacy_cache:
                    self.assertTrue(service._cache)
                    service.cache_ttl = 0
                second = service.daily_box_office("2026-10-21")
                self.assertEqual(len(session.calls), 2)
                self.assertEqual((first["calls"], second["calls"]), (1, 1))
                self.assertFalse(second["cache_hit"])
                self.assertEqual(service._cache, {})

    def test_expiry_and_failed_refresh_do_not_restore_stale_success(self):
        tick = [0.0]
        service, session = self.service(Response(payload()), Response(payload()),
                                        Response(None, 503), Response(payload()),
                                        monotonic=lambda: tick[0], cache_ttl=5)
        service.daily_box_office("2026-10-21")
        tick[0] = 6
        self.assertEqual(service.daily_box_office("2026-10-21")["calls"], 1)
        self.assertEqual(service.daily_box_office("2026-10-21", refresh=True)["status"], "failure")
        self.assertEqual(service.daily_box_office("2026-10-21")["calls"], 1)
        self.assertEqual(len(session.calls), 4)

    def test_missing_key_is_no_network_and_no_environment_read(self):
        with patch("movie_lab.kobis.os.environ.get", side_effect=AssertionError("environment read")):
            service = KobisService(None, session=Session(), clock=lambda: NOW)
            self.assertFalse(service.configured)
            result = service.daily_box_office("2026-10-21")
        self.assertEqual((result["status"], result["calls"], service.request_count), ("unconfigured", 0, 0))
        self.safe(result)

    def test_factory_uses_quiet_existing_dotenv_pattern_only_when_invoked(self):
        with patch("movie_lab.kobis.load_dotenv") as dotenv, patch("movie_lab.kobis.os.environ.get", return_value=None) as env:
            service = create_kobis_service(session=Session(), clock=lambda: NOW)
        self.assertFalse(service.configured)
        self.assertFalse(dotenv.call_args.kwargs["override"])
        self.assertFalse(dotenv.call_args.kwargs["verbose"])
        self.assertEqual(dotenv.call_args.kwargs["dotenv_path"].name, ".env")
        env.assert_called_once_with("KOBIS_API_KEY")

    def test_invalid_dates_conditions_never_call(self):
        service, session = self.service()
        for value in ("2026-02-30", "2026-10-22", "2027-01-01", "no-date", None):
            with self.subTest(value=value):
                result = service.daily_box_office(value)
                self.assertEqual(result["error"]["category"], "invalid_request")
                self.assertEqual(result["calls"], 0)
        for options in ({"item_per_page": 11}, {"rep_nation_cd": "X"}, {"wide_area_cd": "bad"}):
            self.assertEqual(service.daily_box_office("2026-10-21", **options)["calls"], 0)
        self.assertEqual(session.calls, [])

    def test_http_errors_are_classified_without_raw_data_or_retry(self):
        for code, category in ((401, "authentication"), (403, "authentication"),
                               (429, "rate_limit"), (503, "server"), (302, "redirect"),
                               (400, "http_error")):
            with self.subTest(code=code):
                service, session = self.service(Response({"secret": TEST_SECRET}, code))
                result = service.daily_box_office("2026-10-21")
                self.assertEqual(result["error"]["category"], category)
                self.assertEqual(result["error"]["http_status"], code)
                self.assertEqual(len(session.calls), 1)
                self.safe(result)

    def test_timeout_network_exceptions_sanitized_and_not_cached(self):
        for error, category in ((requests.Timeout, "timeout"), (requests.ConnectionError, "network")):
            with self.subTest(category=category):
                service, session = self.service(error("RAW_REMOTE_MESSAGE ?key=" + TEST_SECRET), Response(payload()))
                result = service.daily_box_office("2026-10-21")
                self.assertEqual(result["error"]["category"], category)
                self.assertEqual(len(session.calls), 1)
                self.safe(result)
                self.assertEqual(service.daily_box_office("2026-10-21")["status"], "success")
                self.assertEqual(len(session.calls), 2)

    def test_internal_fault_invalid_json_and_empty_not_success_cached(self):
        responses = [Response({"faultInfo": {"errorCode": "unverified", "message": TEST_SECRET}}),
                     Response(ValueError(TEST_SECRET)), Response([]), Response({}),
                     Response({"boxOfficeResult": {"dailyBoxOfficeList": []}}),
                     Response(payload())]
        service, session = self.service(*responses)
        for category in ("api_fault", "invalid_json", "invalid_response", "invalid_response", "empty"):
            result = service.daily_box_office("2026-10-21")
            self.assertEqual(result["error"]["category"], category)
            self.assertFalse(result["cache_hit"])
            self.safe(result)
        self.assertEqual(service.daily_box_office("2026-10-21")["status"], "success")
        self.assertEqual(len(session.calls), 6)

    def test_response_for_another_day_is_not_accepted_or_cached(self):
        wrong = payload()
        wrong["boxOfficeResult"]["showRange"] = "20261020~20261020"
        service, session = self.service(Response(wrong), Response(payload()))
        self.assertEqual(service.daily_box_office("2026-10-21")["error"]["category"], "date_mismatch")
        self.assertEqual(service.daily_box_office("2026-10-21")["status"], "success")
        self.assertEqual(len(session.calls), 2)

    def test_bad_identifiers_invalid_and_missing_numeric_values_stay_unknown(self):
        bad = payload(movieCd="")
        service, session = self.service(Response(bad), Response(payload(audiCnt=None, salesAmt="not a number", openDt="")))
        self.assertEqual(service.daily_box_office("2026-10-21")["error"]["category"], "invalid_response")
        result = service.daily_box_office("2026-10-21")
        for name in ("audience_daily", "sales_daily", "release_date"):
            self.assertIsNone(result["rows"][0][name])
        self.assertEqual(len(session.calls), 2)


if __name__ == "__main__":
    unittest.main()
