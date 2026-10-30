"""기존 GMS 설정으로 짧은 요청을 한 번 보낸다. 앱 상태는 변경하지 않는다."""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
from langchain_core.globals import set_debug, set_verbose
from langchain_openai import ChatOpenAI
from langsmith import tracing_context
from openai import APIConnectionError, APITimeoutError
from pydantic import SecretStr

from movie_lab.config import GMS_BASE_URL, GMS_KEY_ENV, resolve_gms_chat_model


PROMPT = "연결 확인이라고만 답해 주세요."
TIMEOUT_SECONDS = 20.0
MODEL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,119}\Z")


def failure_details(error: Exception) -> dict:
    """예외 원문·헤더·응답 본문을 출력하지 않고 정해진 분류만 반환한다."""
    status = getattr(error, "status_code", None)
    status = status if type(status) is int and 100 <= status <= 599 else None
    code = getattr(error, "code", None)
    body = getattr(error, "body", None)
    if not isinstance(code, str) and isinstance(body, dict):
        detail = body.get("error", body)
        code = detail.get("code") if isinstance(detail, dict) else None
    code = code.lower() if isinstance(code, str) else ""

    if isinstance(error, APITimeoutError):
        category = "타임아웃"
    elif isinstance(error, APIConnectionError):
        category = "네트워크 연결 실패"
    elif status == 401:
        category = "인증 실패"
    elif code in {"model_not_found", "unsupported_model", "invalid_model", "model_not_supported"}:
        category = "모델 미지원 또는 모델 접근 불가"
    elif status == 403:
        category = "접근 권한 부족"
    elif status == 429:
        category = "사용 한도 부족" if code == "insufficient_quota" else "요청 제한 또는 사용 한도 확인 필요"
    elif status == 404:
        category = "API 경로 또는 리소스 확인 필요"
    elif status in {408, 504}:
        category = "서버 응답 시간 초과"
    elif status is not None and status >= 500:
        category = "GMS 또는 상위 API 서버 오류"
    elif status == 400:
        category = "요청 형식 또는 호출 옵션 확인 필요"
    else:
        category = "클라이언트 설정 또는 응답 처리 오류"
    return {"status": "failure", "category": category, "http_status": status}


def run_check(model: str | None = None) -> int:
    # SDK debug/trace 설정이 있더라도 이번 검사는 키·요청 로그를 내보내지 않는다.
    for name in ("openai", "httpx", "httpcore", "dotenv", "langchain", "langchain_openai", "langsmith"):
        logging.getLogger(name).setLevel(logging.CRITICAL)
    set_debug(False)
    set_verbose(False)
    try:
        # 기존 load_dotenv 기본 동작과 같이 이미 설정된 환경변수가 우선이다.
        load_dotenv(dotenv_path=PROJECT_ROOT / ".env", override=False, verbose=False)
        model_name = resolve_gms_chat_model(model)
        if not MODEL_ID.fullmatch(model_name):
            print(json.dumps({"status": "failure", "category": "모델 설정 형식 오류"}, ensure_ascii=False))
            return 2
        key = os.environ.get(GMS_KEY_ENV)
        if not key or not key.strip():
            print(json.dumps({"status": "failure", "category": "GMS_KEY 미설정"}, ensure_ascii=False))
            return 2

        with tracing_context(enabled=False):
            client = ChatOpenAI(
                model=model_name,
                api_key=SecretStr(key),
                base_url=GMS_BASE_URL,
                timeout=TIMEOUT_SECONDS,
                max_retries=0,
                streaming=False,
                use_responses_api=False,
            )
            response = client.invoke(PROMPT)  # 실제 요청은 이 한 곳뿐이며 자동 재시도하지 않는다.

        content = response.content
        if not isinstance(content, str) or not content.strip():
            print(json.dumps({"status": "failure", "category": "비어 있거나 예상하지 못한 응답"}, ensure_ascii=False))
            return 1
        # 정상 응답도 한 줄로 짧게 표시하며, 키가 포함됐다면 제거한다.
        reply = " ".join(content.replace(key, "[숨김]").split())[:120]
        reported_model = response.response_metadata.get("model_name")
        reported_model = reported_model if isinstance(reported_model, str) and MODEL_ID.fullmatch(reported_model) else None
        if reported_model:
            reported_model = reported_model.replace(key, "[숨김]")
        print(json.dumps({"status": "success", "requested_model": model_name.replace(key, "[숨김]"),
                          "reported_model": reported_model, "response": reply}, ensure_ascii=False))
        return 0
    except Exception as error:
        print(json.dumps(failure_details(error), ensure_ascii=False))
        return 3 if isinstance(error, APIConnectionError) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="GMS에 짧은 연결 확인 요청을 1회 보냅니다. 키는 출력하지 않습니다.")
    parser.add_argument("--model", help="GMS_CHAT_MODEL 및 기본 모델보다 우선할 모델 ID")
    args = parser.parse_args()
    return run_check(args.model)


if __name__ == "__main__":
    raise SystemExit(main())
