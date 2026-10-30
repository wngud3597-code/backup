"""Two bounded GMS document-planning roles; imports never read credentials."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from movie_lab.config import GMS_BASE_URL, GMS_KEY_ENV, PROJECT_ROOT, resolve_gms_chat_model
from movie_lab.data import Movie
from movie_lab.document_models import own_movie_query
from movie_lab.embeddings import MODEL_ID, failure_details, quiet_sdk_logging


PROMPT_ROOT = Path(__file__).resolve().parents[1] / "prompts"
EXTRACT_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "queries": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 4},
        "focus": {"type": "string"},
    }, "required": ["queries", "focus"],
}
SELECT_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "selected_ids": {"type": "array", "items": {"type": "string"}, "maxItems": 6},
        "reasons": {"type": "array", "maxItems": 6, "items": {
            "type": "object", "additionalProperties": False,
            "properties": {"candidate_id": {"type": "string"}, "reason": {"type": "string"}},
            "required": ["candidate_id", "reason"],
        }},
    }, "required": ["selected_ids", "reasons"],
}


class DocumentModelError(RuntimeError):
    """Only fixed failure categories are available to UI/logging callers."""

    def __init__(self, category: str, http_status: int | None = None):
        super().__init__(category)
        self.category = category
        self.http_status = http_status


def _movie_context(movie: Movie) -> dict:
    return {"movie_id": movie.movie_id, "title": movie.title, "original_title": movie.original_title,
            "year": movie.year, "director": list(movie.director), "genres": list(movie.genres),
            "overview": movie.overview[:3500]}


def _unsupported_schema(error: Exception) -> bool:
    if getattr(error, "status_code", None) != 400:
        return False
    body = getattr(error, "body", None)
    if not isinstance(body, dict):
        return False
    detail = body.get("error", body)
    if not isinstance(detail, dict):
        return False
    code = str(detail.get("code", "")).casefold()
    param = str(detail.get("param", "")).casefold()
    message = str(detail.get("message", "")).casefold()
    return code in {"unsupported_response_format", "json_schema_not_supported"} or (
        ("response_format" in param or "json_schema" in message)
        and any(word in message for word in ("not supported", "unsupported", "does not support"))
    )


def _short_string(value: Any, maximum: int, *, allow_empty: bool = False) -> bool:
    return isinstance(value, str) and len(value) <= maximum and (allow_empty or bool(value.strip()))


def _compact(value: str) -> str:
    return re.sub(r"[^가-힣a-z0-9]+", "", value.casefold())


def _without_movie_facets(movie: Movie, value: str) -> str:
    """Reject identity facets presented as if they were background topics.

    This only checks that an actual topic exists. It cannot prove semantic
    relevance, which still depends on the prompt and visible selection reasons.
    """
    text = _compact(re.sub(r"\b(?:18|19|20|21)\d{2}(?:년)?\b", "", value))
    facets = [movie.title, movie.original_title, *movie.director, *movie.cast, *movie.genres]
    if movie.year is not None:
        facets.append(str(movie.year))
    for facet in sorted({_compact(item) for item in facets if item}, key=len, reverse=True):
        text = text.replace(facet, "")
    return text


def _is_topic_query(movie: Movie, value: str) -> bool:
    text = _without_movie_facets(movie, value)
    for term in ("위키백과", "wikipedia", "개봉년도", "개봉연도", "영화정보", "영화", "작품",
                 "감독", "출연진", "출연", "배우", "제목", "원제", "개봉", "연도", "년"):
        text = text.replace(term, "")
    # One-character Korean concepts (달/물/빛/암) can be legitimate topics.
    return text not in {"", "이", "의", "은", "는", "가", "을", "를", "에", "와", "과"} and bool(re.search(r"[가-힣a-z]", text))


def _metadata_only_question(movie: Movie, question: str) -> bool:
    residual = _without_movie_facets(movie, question)
    # A narrow whole-question grammar creates an exception only for requests
    # such as '감독이 누구야?' or '개봉 연도 알려줘'. Merely mentioning a
    # metadata field inside a substantive question does not create an exception.
    field = r"감독|제목|원제|개봉일|개봉연도|개봉년도|개봉|연도|장르|배우|출연진|출연|상영시간|러닝타임|평점|제작국가|국가|언어"
    filler = r"이|그|영화|작품|의|은|는|가|을|를|와|과|좀|하고|도|에|대해|대한|정보|누구|누가|언제|무엇|뭐|몇|어떤|인지|인가요|인가|야|요|알려줘|알려주세요|궁금해|궁금합니다|확인|해줘|해주세요|질문"
    return bool(re.search(field, residual)) and bool(re.fullmatch(f"(?:(?:{field})|(?:{filler}))+", residual))


class LlmDocumentPlanner:
    """Injectable OpenAI-compatible client; at most two requests per role call."""

    def __init__(self, client: Any, model: str | None = None, *, structured_mode: str = "json_schema"):
        self.model = resolve_gms_chat_model(model)
        if not MODEL_ID.fullmatch(self.model):
            raise DocumentModelError("채팅 모델 설정 형식 오류")
        if structured_mode not in {"json_schema", "json"}:
            raise DocumentModelError("구조화 출력 설정 형식 오류")
        self.client = client
        self.mode = structured_mode
        self.request_count = 0
        self.reported_model: str | None = None
        self.audit: list[dict] = []

    def _complete(self, role: str, schema: dict, payload: dict, validate: Any,
                  *, repair_instruction: str = "") -> dict:
        prompt = (PROMPT_ROOT / f"{role}.txt").read_text(encoding="utf-8")
        messages = [{"role": "system", "content": prompt},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]
        for attempt in range(2):
            options = {"model": self.model, "messages": messages, "temperature": 0,
                       "max_tokens": 1200}
            if self.mode == "json_schema":
                options["response_format"] = {"type": "json_schema", "json_schema": {
                    "name": f"movie_{role}", "strict": True, "schema": schema}}
            # Fallback uses ordinary text containing JSON. No unverified JSON
            # object mode is assumed to be available on the gateway.
            self.request_count += 1
            try:
                response = self.client.chat.completions.create(**options)
            except Exception as error:
                if attempt == 0 and self.mode == "json_schema" and _unsupported_schema(error):
                    self.audit.append({"role": role, "mode": "json_schema", "status": "unsupported"})
                    self.mode = "json"
                    continue
                details = failure_details(error)
                self.audit.append({"role": role, "mode": self.mode, "status": "failure",
                                   "http_status": details["http_status"]})
                raise DocumentModelError(details["category"], details["http_status"]) from None
            reported = getattr(response, "model", None)
            if isinstance(reported, str) and MODEL_ID.fullmatch(reported) and (
                reported == self.model or reported.startswith(self.model + "-")):
                self.reported_model = reported
            try:
                content = response.choices[0].message.content
                if not isinstance(content, str) or len(content) > 20000:
                    raise ValueError
                result = json.loads(content)
                if not validate(result):
                    raise ValueError
            except (AttributeError, IndexError, TypeError, ValueError, KeyError):
                self.audit.append({"role": role, "mode": self.mode, "status": "invalid_output"})
                if attempt == 0:
                    messages.append({"role": "user", "content":
                                     "이전 출력이 스키마·허용 ID·검색 주제 검사에 실패했습니다. JSON 객체만 정확한 스키마와 허용 ID로 다시 출력하세요. "
                                     + repair_instruction})
                    continue
                raise DocumentModelError("모델 JSON·스키마·후보 ID 검증 실패") from None
            self.audit.append({"role": role, "mode": self.mode, "status": "success"})
            return result
        raise DocumentModelError("모델 출력 검증 실패")

    def extract(self, movie: Movie, question: str, history: list[dict] | None = None) -> dict:
        if not isinstance(question, str) or not question.strip():
            raise DocumentModelError("자료 준비 질문이 비어 있습니다")
        recent = [{"role": item.get("role"), "content": str(item.get("content", ""))[:1500]}
                  for item in (history or [])[-6:] if item.get("role") in {"user", "assistant"}]
        requires_topic = not _metadata_only_question(movie, question)

        def valid(result: Any) -> bool:
            return (isinstance(result, dict) and set(result) == {"queries", "focus"}
                    and isinstance(result["queries"], list) and 1 <= len(result["queries"]) <= 4
                    and all(_short_string(value, 220) for value in result["queries"])
                    and _short_string(result["focus"], 1000, allow_empty=True)
                    and (not requires_topic or any(_is_topic_query(movie, value) for value in result["queries"])))

        result = self._complete("extract_queries", EXTRACT_SCHEMA,
                                {"selected_movie_metadata": _movie_context(movie),
                                 "unverified_current_question": question[:4000],
                                 "unverified_recent_conversation": recent,
                                 "background_topic_required": requires_topic}, valid,
                                repair_instruction="제목·원제·연도·감독만 나열하지 마세요. background_topic_required가 true이면 현재 질문을 검증할 배경 개념 검색어를 적어도 하나 포함하고, 구체적인 배경 주제 검색어를 앞에 배치하세요.")
        own = own_movie_query(movie)
        queries = list(dict.fromkeys(value.strip() for value in result["queries"]))
        background = [value for value in queries if _is_topic_query(movie, value)]
        ancillary = [value for value in queries if value not in background]
        # The caller deliberately caps searches. Preserve its budget for the
        # selected film followed by actual question topics, not bare facets.
        result["queries"] = list(dict.fromkeys([own, *background, *ancillary]))
        result["mode"] = self.mode
        return result

    def select(self, movie: Movie, question: str, candidates: list[dict]) -> dict:
        if not candidates:
            return {"selected_ids": [], "reasons": [], "mode": self.mode}
        if len(candidates) > 30:
            raise DocumentModelError("선별 후보는 한 번에 30개 이하여야 합니다")
        identifiers = [candidate.get("candidate_id") for candidate in candidates if isinstance(candidate, dict)]
        if len(identifiers) != len(candidates) or any(not isinstance(value, str) or not value for value in identifiers):
            raise DocumentModelError("후보 ID가 누락되었거나 중복되었습니다")
        allowed = set(identifiers)
        if len(allowed) != len(candidates):
            raise DocumentModelError("후보 ID가 누락되었거나 중복되었습니다")

        def valid(result: Any) -> bool:
            if not isinstance(result, dict) or set(result) != {"selected_ids", "reasons"}:
                return False
            ids, reasons = result["selected_ids"], result["reasons"]
            if not isinstance(ids, list) or len(ids) > 6 or any(not isinstance(value, str) for value in ids):
                return False
            if len(ids) != len(set(ids)) or not set(ids) <= allowed:
                return False
            if not isinstance(reasons, list) or len(reasons) != len(ids):
                return False
            if any(not isinstance(row, dict) or set(row) != {"candidate_id", "reason"}
                   or not isinstance(row["candidate_id"], str)
                   or not _short_string(row["reason"], 700) for row in reasons):
                return False
            return len({row["candidate_id"] for row in reasons}) == len(ids) and {
                row["candidate_id"] for row in reasons} == set(ids)

        items = [{"candidate_id": row["candidate_id"], "title": str(row.get("title", ""))[:250],
                  "snippet": str(row.get("snippet", ""))[:1300]} for row in candidates]
        result = self._complete("select_documents", SELECT_SCHEMA,
                                {"selected_movie_metadata": _movie_context(movie),
                                 "unverified_question": question[:4000],
                                 "untrusted_search_candidates": items}, valid)
        result["mode"] = self.mode
        return result


def create_document_planner(model: str | None = None) -> LlmDocumentPlanner:
    """Only explicitly invoked client creation loads .env and reads GMS_KEY."""
    quiet_sdk_logging()
    load_dotenv(dotenv_path=PROJECT_ROOT / ".env", override=False, verbose=False)
    key = os.environ.get(GMS_KEY_ENV)
    if not key or not key.strip():
        raise DocumentModelError("GMS_KEY 미설정")
    client = OpenAI(api_key=key, base_url=GMS_BASE_URL, max_retries=0, timeout=25.0)
    return LlmDocumentPlanner(client, model)
