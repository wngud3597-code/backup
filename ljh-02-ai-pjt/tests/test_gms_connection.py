"""실제 API는 호출하지 않는다. 단일 호출과 안전한 실패 출력을 검증한다."""

import io
import json
import unittest
from contextlib import ExitStack, redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from openai import APIConnectionError, APITimeoutError, AuthenticationError, BadRequestError, NotFoundError, RateLimitError

from scripts import check_gms_connection as smoke


class GmsConnectionTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.load = self.stack.enter_context(patch.object(smoke, "load_dotenv"))
        self.getenv = self.stack.enter_context(patch.object(smoke.os.environ, "get", return_value="synthetic-test-key"))
        self.client_type = self.stack.enter_context(patch.object(smoke, "ChatOpenAI"))
        self.client = self.client_type.return_value
        self.client.invoke.return_value = SimpleNamespace(content="연결 확인", response_metadata={"model_name": "gpt-4o-mini"})

    def run_check(self):
        output = io.StringIO()
        with redirect_stdout(output):
            code = smoke.run_check("gpt-4o-mini")
        self.assertNotIn("synthetic-test-key", output.getvalue())
        return code, json.loads(output.getvalue())

    def test_one_request_existing_endpoint_no_retry_and_local_dotenv(self):
        code, result = self.run_check()
        self.assertEqual(code, 0)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["response"], "연결 확인")
        self.assertEqual(result["requested_model"], "gpt-4o-mini")
        options = self.client_type.call_args.kwargs
        self.assertEqual(options["base_url"], "https://gms.ssafy.io/gmsapi/api.openai.com/v1/")
        self.assertEqual(options["model"], "gpt-4o-mini")
        self.assertEqual(options["max_retries"], 0)
        self.assertEqual(options["timeout"], 20)
        self.assertFalse(options["streaming"])
        self.assertFalse(options["use_responses_api"])
        self.assertEqual(options["api_key"].get_secret_value(), "synthetic-test-key")
        self.client.invoke.assert_called_once_with(smoke.PROMPT)
        self.load.assert_called_once_with(dotenv_path=smoke.PROJECT_ROOT / ".env", override=False, verbose=False)

    def test_missing_key_does_not_construct_client_or_request(self):
        self.getenv.return_value = None
        code, result = self.run_check()
        self.assertEqual(code, 2)
        self.assertEqual(result["category"], "GMS_KEY 미설정")
        self.client_type.assert_not_called()

    def test_api_failure_is_classified_without_echoing_error_or_retrying(self):
        response = httpx.Response(401, request=httpx.Request("POST", "https://example.invalid"))
        self.client.invoke.side_effect = AuthenticationError("synthetic-test-key", response=response, body={"message": "synthetic-test-key"})
        code, result = self.run_check()
        self.assertEqual(code, 1)
        self.assertEqual(result, {"status": "failure", "category": "인증 실패", "http_status": 401})
        self.client.invoke.assert_called_once()

    def test_timeout_and_network_failures_are_distinct(self):
        request = httpx.Request("POST", "https://example.invalid")
        timeout = APITimeoutError(request=request)
        network = APIConnectionError(request=request, message="synthetic-test-key")
        self.assertEqual(smoke.failure_details(timeout)["category"], "타임아웃")
        self.assertEqual(smoke.failure_details(network)["category"], "네트워크 연결 실패")

    def test_model_error_is_not_inferred_from_any_404(self):
        response = httpx.Response(404, request=httpx.Request("POST", "https://example.invalid"))
        error = NotFoundError("private error", response=response, body={"code": "model_not_found"})
        self.assertEqual(smoke.failure_details(error)["category"], "모델 미지원 또는 모델 접근 불가")
        error = NotFoundError("private error", response=response, body=None)
        self.assertEqual(smoke.failure_details(error)["category"], "API 경로 또는 리소스 확인 필요")

    def test_quota_and_request_option_failures(self):
        request = httpx.Request("POST", "https://example.invalid")
        quota = RateLimitError("private error", response=httpx.Response(429, request=request), body={"code": "insufficient_quota"})
        bad_request = BadRequestError("private error", response=httpx.Response(400, request=request), body=None)
        self.assertEqual(smoke.failure_details(quota)["category"], "사용 한도 부족")
        self.assertEqual(smoke.failure_details(bad_request)["category"], "요청 형식 또는 호출 옵션 확인 필요")

    def test_empty_response_is_not_success_and_normal_response_redacts_key(self):
        self.client.invoke.return_value.content = " "
        code, result = self.run_check()
        self.assertEqual(code, 1)
        self.assertEqual(result["status"], "failure")
        self.client.invoke.return_value.content = "연결 확인 synthetic-test-key"
        code, result = self.run_check()
        self.assertEqual(code, 0)
        self.assertIn("[숨김]", result["response"])


if __name__ == "__main__":
    unittest.main()
