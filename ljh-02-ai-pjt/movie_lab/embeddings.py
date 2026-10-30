"""GMS embeddings using text input, with explicit validation and no automatic retries.

The same object embeds documents and queries. A dimension is configured explicitly
or learned from the first validated response; subsequent responses must match it.
No credentials are read until ``create_gms_embeddings`` is called.
"""

from __future__ import annotations

import logging
import math
import os
import re
from collections.abc import Sequence
from typing import Any

from dotenv import load_dotenv
from langchain_core.embeddings import Embeddings
from openai import APIConnectionError, APITimeoutError, OpenAI

from movie_lab.config import GMS_BASE_URL, GMS_KEY_ENV, PROJECT_ROOT, resolve_gms_embedding_model


MODEL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,119}\Z")
TIMEOUT_SECONDS = 30.0


class EmbeddingValidationError(ValueError):
    """A safe response/configuration error containing no response body or input."""


def resolve_embedding_model(value: str | None = None) -> str:
    model = resolve_gms_embedding_model(value)
    if not MODEL_ID.fullmatch(model):
        raise EmbeddingValidationError("임베딩 모델 설정 형식 오류")
    return model


def quiet_sdk_logging() -> None:
    """Do not emit HTTP headers, response bodies, or dotenv diagnostics."""
    for name in ("openai", "httpx", "httpcore", "dotenv"):
        logging.getLogger(name).setLevel(logging.CRITICAL)


def failure_details(error: Exception) -> dict[str, Any]:
    """Return only fixed categories/status codes, never the error string or body."""
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
    elif isinstance(error, EmbeddingValidationError):
        category = "임베딩 설정 또는 응답 검증 실패"
    else:
        category = "클라이언트 설정 또는 응답 처리 오류"
    return {"status": "failure", "category": category, "http_status": status}


class GmsEmbeddings(Embeddings):
    """LangChain-compatible GMS embeddings; this constructor never loads dotenv."""

    def __init__(
        self,
        model: str | None = None,
        dimensions: int | None = None,
        *,
        batch_size: int = 64,
        api_key: str | None = None,
        client: Any = None,
    ) -> None:
        self.model = resolve_embedding_model(model)
        if dimensions is not None and (type(dimensions) is not int or dimensions <= 0):
            raise EmbeddingValidationError("임베딩 차원은 양의 정수여야 합니다")
        if type(batch_size) is not int or batch_size <= 0:
            raise EmbeddingValidationError("임베딩 배치 크기는 양의 정수여야 합니다")
        self.dimensions = dimensions
        self.requested_dimensions = dimensions
        self.batch_size = batch_size
        self.reported_model: str | None = None
        self.request_count = 0
        self.embedded_text_count = 0
        quiet_sdk_logging()
        if client is not None:
            self._client = client
        else:
            if not api_key or not api_key.strip():
                raise EmbeddingValidationError("GMS_KEY 미설정")
            self._client = OpenAI(
                api_key=api_key,
                base_url=GMS_BASE_URL,
                max_retries=0,
                timeout=TIMEOUT_SECONDS,
            )

    def _validated_vectors(self, response: Any, count: int) -> list[list[float]]:
        data = getattr(response, "data", None)
        if not isinstance(data, list) or len(data) != count:
            raise EmbeddingValidationError("임베딩 응답 개수 불일치")
        ordered: list[list[float] | None] = [None] * count
        dimension = self.dimensions
        for item in data:
            index = getattr(item, "index", None)
            vector = getattr(item, "embedding", None)
            if type(index) is not int or not 0 <= index < count or ordered[index] is not None:
                raise EmbeddingValidationError("임베딩 응답 순서 식별 오류")
            if not isinstance(vector, list) or not vector:
                raise EmbeddingValidationError("임베딩 벡터가 비어 있거나 형식이 잘못되었습니다")
            if any(type(value) not in (int, float) or not math.isfinite(value) for value in vector):
                raise EmbeddingValidationError("임베딩 벡터에 유한수가 아닌 값이 있습니다")
            if dimension is None:
                dimension = len(vector)
            if len(vector) != dimension:
                raise EmbeddingValidationError("임베딩 벡터 차원 불일치")
            ordered[index] = [float(value) for value in vector]
        self.dimensions = dimension
        reported = getattr(response, "model", None)
        # Only record the requested ID or its versioned name, never arbitrary
        # server-returned text that could contain an error body or a credential.
        if isinstance(reported, str) and MODEL_ID.fullmatch(reported):
            if reported == self.model or reported.startswith(self.model + "-"):
                if self.reported_model is not None and reported != self.reported_model:
                    raise EmbeddingValidationError("임베딩 응답 모델이 호출 중 변경되었습니다")
                self.reported_model = reported
        return [vector for vector in ordered if vector is not None]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not isinstance(texts, Sequence) or isinstance(texts, (str, bytes)):
            raise EmbeddingValidationError("임베딩 입력은 문자열 목록이어야 합니다")
        if any(not isinstance(text, str) or not text.strip() for text in texts):
            raise EmbeddingValidationError("임베딩 입력에 빈 문자열 또는 잘못된 값이 있습니다")
        result: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = list(texts[start : start + self.batch_size])
            options: dict[str, Any] = {"model": self.model, "input": batch, "encoding_format": "float"}
            if self.requested_dimensions is not None:
                options["dimensions"] = self.requested_dimensions
            self.request_count += 1
            response = self._client.embeddings.create(**options)
            vectors = self._validated_vectors(response, len(batch))
            self.embedded_text_count += len(vectors)
            result.extend(vectors)
        return result

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


def create_gms_embeddings(
    model: str | None = None,
    dimensions: int | None = None,
    *,
    batch_size: int = 64,
) -> GmsEmbeddings:
    """Reuse the existing local dotenv -> GMS_KEY -> GMS endpoint convention."""
    quiet_sdk_logging()
    load_dotenv(dotenv_path=PROJECT_ROOT / ".env", override=False, verbose=False)
    return GmsEmbeddings(
        model=model,
        dimensions=dimensions,
        batch_size=batch_size,
        api_key=os.environ.get(GMS_KEY_ENV),
    )
