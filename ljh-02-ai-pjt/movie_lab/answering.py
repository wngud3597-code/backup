"""Bounded grounded generation, mechanical citation checks, then semantic review.

The model returns no titles or URLs. They come only from retrieval. A semantic
review by the same model is recorded separately from exact string checks; it is
not a proof of truth or a replacement for inspecting representative answers.
"""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import time

from movie_lab.document_llm import (DocumentModelError, _unsupported_schema,
                                    create_document_planner)
from movie_lab.embeddings import failure_details
from movie_lab.evidence import CITE_PATTERN
from movie_lab.director_check import propose_director_checks
from movie_lab.config import gms_chat_options


PROMPTS = Path(__file__).resolve().parents[1] / "prompts"
VERDICTS = ("확인됨", "근거와 상충", "근거 부족", "출처 충돌")
SCOPES = ("작품 속 묘사", "현실 사실")
REVIEW_HOLD = "검토 보류"
RELATION_BY_VERDICT = {"확인됨": "supports", "근거와 상충": "contradicts", "출처 충돌": "conflicting"}
ANSWER_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "answer": {"type": "string"},
        "citations": {"type": "array", "items": {"type": "object", "additionalProperties": False,
            "properties": {"source": {"type": "integer"}, "quote_index": {"type": "integer"}},
            "required": ["source", "quote_index"]}},
        "checks": {"type": "array", "items": {"type": "object", "additionalProperties": False,
            "properties": {"scope": {"type": "string", "enum": list(SCOPES)},
                "claim": {"type": "string"}, "verdict": {"type": "string", "enum": list(VERDICTS)},
                "reason": {"type": "string"}}, "required": ["scope", "claim", "verdict", "reason"]}},
    }, "required": ["answer", "citations", "checks"],
}
REVIEW_SCHEMA = {"type": "object", "additionalProperties": False,
                 "properties": {"reason": {"type": "string"}, "supported": {"type": "boolean"}},
                 "required": ["reason", "supported"]}
VERIFY_REVIEW_SCHEMA = {"type": "object", "additionalProperties": False,
    "properties": {"items": {"type": "array", "maxItems": 6, "items": {
        "type": "object", "additionalProperties": False,
        "properties": {"claim_id": {"type": "string"},
            "evidence_relation": {"type": "string", "enum": ["supports", "contradicts", "insufficient", "conflicting"]},
            "service_reason_supported": {"type": "boolean"}, "reason": {"type": "string"}},
        "required": ["claim_id", "evidence_relation", "service_reason_supported", "reason"]}}},
    "required": ["items"]}


def held_reason():
    return "제안한 판정과 인용 근거의 관계를 일치하게 검토하지 못해 판단을 보류합니다. 이 안내는 주장이 거짓이거나 근거가 부족하다는 판정이 아닙니다."


def citation_numbers(text):
    return {int(number.strip()) for group in CITE_PATTERN.findall(text)
            for number in group.split(",") if number.strip().isdigit()}


def render_answer(result):
    content = result["answer"].strip()
    for row in result["checks"]:
        content += (f"\n\n**{row['scope']} · {row['verdict']}**\n\n"
                    f"확인 대상: {row['claim']}\n\n{row['reason']}")
    return content


def quotation_parts(text, maximum=220):
    """Return actual contiguous excerpts; the model selects indexes, not text."""
    parts, start = [], 0
    while start < len(text):
        end = min(start + maximum, len(text))
        if end < len(text):
            boundary = text.rfind("\n", start + min(60, maximum // 2), end)
            if boundary < 0:
                boundary = text.rfind(" ", start + min(60, maximum // 2), end)
            if boundary >= 0:
                end = boundary + 1
        part = text[start:end].strip()
        if len(part) >= 2:
            parts.append(part)
        start = end
    return parts


def materialize_citations(result, passages, mode):
    """Map source/excerpt indexes and render labels outside the model."""
    def without_labels(value):
        # Labels belong to this answer's resolved citations, including when a
        # user proposition mentions an earlier answer's citation number.
        return re.sub(r"\[근거[^\]]*\]", "", value).strip() if isinstance(value, str) else value

    def resolved(citations):
        if not isinstance(citations, list):
            raise ValueError("인용 목록 오류")
        rows = []
        for row in citations:
            if isinstance(row, dict) and set(row) == {"passage_id"}:
                match = re.fullmatch(r"s([1-9]\d*)p(0|[1-9]\d*)", row["passage_id"]) if isinstance(row["passage_id"], str) else None
                if match is None:
                    raise ValueError("원문 구절 ID 오류")
                number, index = map(int, match.groups())
                if not 1 <= number <= len(passages) or not 0 <= index < len(passages[number - 1]):
                    raise ValueError("원문 구절 ID 범위 오류")
                rows.append({"source": number, "quote": passages[number - 1][index]})
            elif isinstance(row, dict) and set(row) == {"source", "quote_index"}:
                number, index = row["source"], row["quote_index"]
                if (type(number) is not int or not 1 <= number <= len(passages)
                        or type(index) is not int or not 0 <= index < len(passages[number - 1])):
                    raise ValueError("원문 구간 번호 범위 오류")
                rows.append({"source": number, "quote": passages[number - 1][index]})
            elif (isinstance(row, dict) and set(row) == {"source", "quote"}
                  and type(row["source"]) is int and isinstance(row["quote"], str)):
                rows.append(row)  # Canonical fixtures receive full validation below.
            else:
                raise ValueError("인용 객체 필드 오류")
        return rows

    def labels(rows):
        numbers = [row["source"] for row in rows if isinstance(row, dict) and type(row.get("source")) is int]
        return "" if not numbers else " [근거 " + ", ".join(map(str, dict.fromkeys(numbers))) + "]"

    if mode == "general" and isinstance(result, dict) and set(result) == {"facts", "unconfirmed"}:
        if (not isinstance(result["facts"], list) or len(result["facts"]) > 4
                or not isinstance(result["unconfirmed"], str) or len(result["unconfirmed"]) > 1600):
            raise ValueError("사실·확인 보류 항목 오류")
        merged, paragraphs, assertions = {}, [], []
        for fact in result["facts"]:
            if (not isinstance(fact, dict) or set(fact) != {"text", "citations"}
                    or not isinstance(fact["text"], str) or not fact["text"].strip()):
                raise ValueError("사실 항목 오류")
            citations = resolved(fact["citations"])
            if not citations:
                raise ValueError("사실 항목에 원문 근거 필요")
            text = without_labels(fact["text"])
            if not text:
                raise ValueError("사실 설명 누락")
            paragraphs.append(text + labels(citations))
            assertions.append({"claim": text, "verdict": "확인됨", "citations": citations})
            for citation in citations:
                merged[(citation["source"], citation["quote"])] = citation
        if result["unconfirmed"].strip():
            paragraphs.append("이번 근거로 확인하지 못한 부분: " + result["unconfirmed"].strip())
        return {"answer": "\n\n".join(paragraphs) or "이번 근거로 질문 내용을 확인하지 못했습니다.",
                "citations": list(merged.values()), "checks": [], "_assertions": assertions}

    if mode == "verify" and isinstance(result, dict) and set(result) == {"checks"}:
        if not isinstance(result["checks"], list) or not 2 <= len(result["checks"]) <= 6:
            raise ValueError("작품·현실 판정 목록 오류")
        merged, checks, assertions, pre_holds = {}, [], [], []
        for index, raw in enumerate(result["checks"], 1):
            if (not isinstance(raw, dict) or set(raw) != {"scope", "claim", "verdict", "reason", "citations"}
                    or not isinstance(raw["reason"], str)):
                raise ValueError("판정 항목 필드 오류")
            row = dict(raw)
            row["claim"] = without_labels(row.get("claim"))
            row["reason"] = without_labels(row["reason"])
            proposed = row.get("verdict")
            if proposed not in VERDICTS or row.get("scope") not in SCOPES or not isinstance(row.get("claim"), str) or not row["claim"].strip():
                raise ValueError("판정 항목 형식 오류")
            invalid = []
            try:
                citations = resolved(row.pop("citations"))
            except ValueError:
                citations, invalid = [], ["인용 구절 식별 오류"]
            if row.get("verdict") == "근거 부족":
                # A limitation is not established by unrelated source text.
                # Even an unnecessary quotation suggested by the model is not
                # carried into the displayed or stored citation snapshot.
                citations = []
                row["reason"] = "이번에 제공된 " + ("작품" if row.get("scope") == "작품 속 묘사" else "현실 배경") + " 근거로 이 주장을 확인하지 못했습니다."
            row["reason"] += labels(citations)
            if proposed != "근거 부족":
                invalid = invalid or ([] if citations else ["판정의 근거 인용 누락"])
                if invalid:
                    pre_holds.append({"claim_id": f"c{index}", "proposed_verdict": proposed,
                                      "accepted": False, "reason_code": "citation_validation", "errors": invalid})
                    row["verdict"], row["reason"], citations = REVIEW_HOLD, held_reason(), []
                else:
                    assertions.append({"claim_id": f"c{index}", "scope": row["scope"],
                        "user_proposition": row["claim"], "service_reason": without_labels(row["reason"]),
                        "proposed_verdict": proposed, "citations": citations})
            checks.append(row)
            for citation in citations:
                merged[(citation["source"], citation["quote"])] = citation
        return {"answer": "작품 속 묘사와 현실 사실을 나누어 확인했습니다.", "citations": list(merged.values()), "checks": checks,
                "_assertions": assertions, "_pre_review_holds": pre_holds}
    if isinstance(result, dict):
        result.setdefault("checks", [])
        if isinstance(result.get("citations"), list):
            result["citations"] = resolved(result["citations"])
            if mode == "general" and isinstance(result.get("answer"), str) and not citation_numbers(result["answer"]):
                result["answer"] += labels(result["citations"])
    return result


def validate_answer(result, sources, mode="general", *, require_all_scopes=True, allow_review_hold=False):
    """Return fixed mechanical errors; never mark semantic entailment here."""
    if not isinstance(result, dict) or set(result) != {"answer", "citations", "checks"}:
        return ["답변 필드 오류"]
    answer, citations, checks = result["answer"], result["citations"], result["checks"]
    if not isinstance(answer, str) or not answer.strip() or len(answer) > 9000:
        return ["답변 본문 오류"]
    if not isinstance(checks, list) or len(checks) > 6 or not isinstance(citations, list) or len(citations) > 32:
        return ["인용·판정 목록 오류"]
    for row in checks:
        if (not isinstance(row, dict) or set(row) != {"scope", "claim", "verdict", "reason"}
                or row["scope"] not in SCOPES or row["verdict"] not in (*VERDICTS, *((REVIEW_HOLD,) if allow_review_hold else ()))
                or any(not isinstance(row[k], str) or not row[k].strip() or len(row[k]) > 2000 for k in ("claim", "reason"))):
            return ["판정 항목 오류"]
    if mode == "general" and checks:
        return ["일반 질문에는 checks를 출력하지 말고 answer와 citations만 작성해야 함"]
    if mode == "verify" and require_all_scopes and {row["scope"] for row in checks} != set(SCOPES):
        return ["확인 모드의 checks에는 작품 속 묘사와 현실 사실을 각각 최소 한 항목씩 포함해야 함"]
    content = render_answer(result)
    if re.search(r"https?://", content):
        return ["원문 링크는 모델 본문 대신 실제 출처 메타데이터에서 표시함"]
    used = citation_numbers(content)
    # Reject malformed labels rather than silently ignoring a number typo.
    labels = re.findall(r"\[근거[^\]]*\]", content)
    if any(CITE_PATTERN.fullmatch(label) is None or not re.fullmatch(r"\[근거\s*\d+(?:\s*,\s*\d+)*\s*\]", label) for label in labels):
        return ["인용 번호 형식 오류"]
    if any(number < 1 or number > len(sources) for number in used):
        return ["인용 번호 범위 오류"]
    mapping, seen = {}, set()
    for row in citations:
        if (not isinstance(row, dict) or set(row) != {"source", "quote"}
                or type(row["source"]) is not int or not 1 <= row["source"] <= len(sources)
                or not isinstance(row["quote"], str) or not 2 <= len(row["quote"]) <= 240):
            return ["인용 구절 필드 오류"]
        pair = (row["source"], row["quote"])
        if pair in seen or row["quote"] not in sources[row["source"] - 1]["text"]:
            return ["인용 구절 원문 포함 오류"]
        seen.add(pair)
        mapping.setdefault(row["source"], []).append(row["quote"])
    if set(mapping) != used:
        return [f"인용 구절 목록 불일치: 구절이 없는 실제 인용 번호 {sorted(used - set(mapping))}; 사용하지 않은 번호 {sorted(set(mapping) - used)}"]
    # A response consisting only of an explicit evidence limitation may have
    # no citations. Whether it makes an unsupported factual claim is decided
    # by the separate semantic review, not inferred from number presence.
    for row in checks:
        refs = citation_numbers(row["claim"] + "\n" + row["reason"])
        if row["verdict"] not in ("근거 부족", REVIEW_HOLD) and not refs:
            return ["판정의 근거 인용 누락"]
        if row["scope"] == "작품 속 묘사" and row["verdict"] not in ("근거 부족", REVIEW_HOLD):
            if not any(sources[n - 1].get("scope") in ("movie_metadata", "film_description") for n in refs):
                return ["현실 배경만으로 작품 장면을 판정할 수 없음"]
            if row["verdict"] == "출처 충돌" and len({sources[n - 1]["document_id"] for n in refs
                    if sources[n - 1].get("scope") in ("movie_metadata", "film_description")}) < 2:
                return ["작품 묘사의 출처 충돌에는 작품 근거 문서가 둘 이상 필요함"]
        if row["verdict"] == "출처 충돌" and len({sources[n - 1]["document_id"] for n in refs}) < 2:
            return ["출처 충돌에는 서로 다른 문서 근거가 필요함"]
    return []


def _item_citations(item):
    return [{"source": row["source"], "quote": row["quote"]} for row in item["citations"]]


def _item_errors(result, item, sources):
    index = int(item["claim_id"][1:]) - 1
    return validate_answer({"answer": "항목별 인용 검사", "checks": [result["checks"][index]],
                            "citations": _item_citations(item)}, sources, "verify", require_all_scopes=False)


def _keep_item_citations(result, items):
    result["citations"] = list({(row["source"], row["quote"]): row
                                for item in items for row in _item_citations(item)}.values())


def prepare_verify_items(result, items, sources):
    """Check real originals and source scope independently before model review."""
    kept, held = [], []
    for item in items:
        errors = _item_errors(result, item, sources)
        if errors:
            row = result["checks"][int(item["claim_id"][1:]) - 1]
            row["verdict"], row["reason"] = REVIEW_HOLD, held_reason()
            held.append({"claim_id": item["claim_id"], "proposed_verdict": item["proposed_verdict"],
                         "accepted": False, "reason_code": "citation_validation", "errors": errors})
        else:
            kept.append(item)
    _keep_item_citations(result, kept)
    return result, kept, held


def apply_verify_review(result, items, review, sources):
    """Accept only exact per-ID relation matches; keep independent valid rows.

    This validates a supplied model judgment. It does not decide scientific
    entailment by keyword, override false, or treat a hold as evidence shortage.
    """
    result = deepcopy(result)
    expected_ids = {item["claim_id"] for item in items}
    protocol_errors, groups = [], {}
    top_valid = (isinstance(review, dict) and set(review) == {"items"}
                 and isinstance(review["items"], list) and len(review["items"]) <= 24)
    if not top_valid:
        protocol_errors.append("review_format_invalid")
    else:
        for row in review["items"]:
            if not isinstance(row, dict) or not isinstance(row.get("claim_id"), str):
                protocol_errors.append("review_item_id_invalid")
            elif row["claim_id"] not in expected_ids:
                protocol_errors.append("unknown_claim_id")
            else:
                groups.setdefault(row["claim_id"], []).append(row)
    decisions, accepted_items = [], []
    for item in items:
        proposed = item["proposed_verdict"]
        rows = groups.get(item["claim_id"], [])
        row = rows[0] if len(rows) == 1 else None
        errors = _item_errors(result, item, sources)
        code = None
        if errors:
            code = "citation_validation"
        elif not top_valid:
            code = "review_format_invalid"
        elif not rows:
            code = "missing_claim_id"
        elif len(rows) != 1:
            code = "duplicate_claim_id"
        elif (set(row) != {"claim_id", "evidence_relation", "service_reason_supported", "reason"}
              or row["evidence_relation"] not in ("supports", "contradicts", "insufficient", "conflicting")
              or type(row["service_reason_supported"]) is not bool
              or not isinstance(row["reason"], str) or not row["reason"].strip() or len(row["reason"]) > 2000):
            code = "review_item_format_invalid"
        elif row["evidence_relation"] != RELATION_BY_VERDICT.get(proposed):
            code = "relation_mismatch"
        elif row["service_reason_supported"] is not True:
            code = "service_reason_unsupported"
        accepted = code is None
        decisions.append({"claim_id": item["claim_id"], "proposed_verdict": proposed,
                          "expected_relation": RELATION_BY_VERDICT.get(proposed),
                          "evidence_relation": row.get("evidence_relation") if row else None,
                          "service_reason_supported": row.get("service_reason_supported") if row else None,
                          "accepted": accepted, "reason_code": code or "accepted",
                          "review_reason": row.get("reason") if row and isinstance(row.get("reason"), str) else None,
                          **({"errors": errors} if errors else {})})
        if accepted:
            accepted_items.append(item)
        else:
            check = result["checks"][int(item["claim_id"][1:]) - 1]
            check["verdict"], check["reason"] = REVIEW_HOLD, held_reason()
    _keep_item_citations(result, accepted_items)
    if any(not row["accepted"] for row in decisions):
        result["answer"] = "작품 속 묘사와 현실 사실의 항목별 검토 결과입니다."
    return result, decisions, protocol_errors


class AnswerGenerator:
    def __init__(self, client, model="gpt-4o-mini", structured_mode="json_schema", *, max_attempts=2,
                 canonical_directors=(), review_model=None):
        if type(max_attempts) is not int or not 1 <= max_attempts <= 2:
            raise ValueError("답변 작성 시도는 1~2회여야 합니다.")
        self.client, self.model, self.mode = client, model, structured_mode
        self.review_model = review_model or model
        self.max_attempts = max_attempts
        self.canonical_directors = frozenset(canonical_directors)
        self.request_count, self.reported_model, self.audit = 0, None, []
        self.reported_models, self.request_audit = {}, []
        self.metrics = {key: {"seconds": 0.0, "calls": 0} for key in ("answer_generation", "semantic_review")}
        self.last_failure_stage = None

    def _request(self, role, schema, payload):
        stage = "semantic_review" if role.startswith("review_") else "answer_generation"
        started = time.perf_counter()
        try:
            return self._request_impl(role, schema, payload)
        except Exception:
            self.last_failure_stage = stage
            raise
        finally:
            self.metrics[stage]["seconds"] += time.perf_counter() - started

    def _request_impl(self, role, schema, payload):
        request_model = self.review_model if role.startswith("review_") else self.model
        options = {**gms_chat_options(request_model),
                   "messages": [{"role": "system", "content": (PROMPTS / f"{role}.txt").read_text(encoding="utf-8")},
                                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]}
        if self.mode == "json_schema":
            options["response_format"] = {"type": "json_schema", "json_schema": {
                "name": f"movie_{role}", "strict": True, "schema": schema}}
        self.request_count += 1
        self.metrics["semantic_review" if role.startswith("review_") else "answer_generation"]["calls"] += 1
        record = {"role": role, "requested_model": request_model,
                  "options": deepcopy({key: value for key, value in options.items() if key != "messages"}),
                  "payload": deepcopy(payload),
                  "payload_sha256": hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                                              separators=(",", ":")).encode("utf-8")).hexdigest()}
        self.request_audit.append(record)
        started = time.perf_counter()
        try:
            response = self.client.chat.completions.create(**options)
        except Exception as error:
            info = failure_details(error)
            record.update(status="error", error={key: value for key, value in info.items() if key != "status"})
            if self.mode == "json_schema" and _unsupported_schema(error):
                self.mode = "json"
                raise ValueError("구조화 출력 대신 JSON으로 재처리") from None
            raise DocumentModelError(info["category"], info["http_status"]) from None
        finally:
            record["seconds"] = time.perf_counter() - started
        reported = getattr(response, "model", None)
        if isinstance(reported, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,150}", reported):
            self.reported_model = reported
            self.reported_models[role] = reported
            record["reported_model"] = reported
        try:
            content = response.choices[0].message.content
            if not isinstance(content, str) or len(content) > 22000:
                raise ValueError
            record.update(status="response", raw_output=content)
            finish = getattr(response.choices[0], "finish_reason", None)
            if finish in ("stop", "length", "content_filter", "tool_calls", "function_call"):
                record["finish_reason"] = finish
            usage = getattr(response, "usage", None)
            if hasattr(usage, "model_dump"):
                record["usage"] = usage.model_dump()
            parsed = json.loads(content)
            record["parsed_output"] = deepcopy(parsed)
            return parsed
        except (AttributeError, IndexError, TypeError, ValueError):
            record["status"] = "parsing_error"
            raise ValueError("응답 JSON 파싱 실패") from None

    def _review_verify(self, result, items, sources, selected_movie, pre_holds):
        enriched = deepcopy(items)
        for item in enriched:
            for citation in item["citations"]:
                citation["scope"] = sources[citation["source"] - 1].get("scope", "background_unverified")
                citation["document_id"] = sources[citation["source"] - 1]["document_id"]
        # The model independently classifies relation to the USER proposition.
        # The proposed verdict is retained only on the code side for comparison.
        request = {"selected_movie": selected_movie,
                   "items": [{k: v for k, v in item.items() if k != "proposed_verdict"} for item in enriched]}
        review, review_error = {"items": []}, None
        if items:
            schema = deepcopy(VERIFY_REVIEW_SCHEMA)
            schema["properties"]["items"]["items"]["properties"]["claim_id"]["enum"] = [item["claim_id"] for item in items]
            try:
                review = self._request("review_verify", schema, request)
            except ValueError:
                review, review_error = None, {"category": "의미 검토 JSON 파싱 실패"}
            except DocumentModelError as error:
                review, review_error = None, {"category": error.category, "http_status": error.http_status}
        result, decisions, protocol_errors = apply_verify_review(result, enriched, review, sources)
        decisions = sorted([*pre_holds, *decisions], key=lambda row: int(row["claim_id"][1:]))
        accepted = sum(row["accepted"] for row in decisions)
        held = len(decisions) - accepted
        if held:
            result["answer"] = "작품 속 묘사와 현실 사실의 항목별 검토 결과입니다."
        status = ("item_review_held" if not accepted else "item_review_partial" if held or protocol_errors
                  else "item_review_passed") if decisions else "no_factual_assertions"
        if status in ("item_review_held", "item_review_partial"):
            self.last_failure_stage = "semantic_review" if items else "citation_validation"
        if not decisions:
            self.audit.append({"stage": "no_factual_assertions", "passed": None})
        else:
            self.audit.append({"stage": "verify_item_review", "passed": status == "item_review_passed",
                               "request": request, "response": review, "decisions": decisions,
                               "protocol_errors": protocol_errors, "review_error": review_error})
        final_errors = validate_answer(result, sources, "verify", allow_review_hold=True)
        if final_errors:
            self.last_failure_stage = "citation_validation"
            raise DocumentModelError("검토 결과 인용 검사 실패")
        return result, {"semantic_check": status, "reviewed_items": len(items),
                        "accepted_items": accepted, "held_items": held,
                        "item_decisions": decisions, "protocol_errors": protocol_errors,
                        **({"review_error": review_error} if review_error else {})}

    def generate(self, movie, question, history, sources, mode="general", warnings=None):
        if mode not in ("general", "verify"):
            raise ValueError("답변 모드를 확인하세요.")
        if not sources:
            return {"content": "사용할 근거를 확보하지 못했습니다. 자료 경로와 연결 상태를 확인한 뒤 다시 질문해 주세요.",
                    "sources": [], "validation": {"generation_skipped": True, "semantic_check": "not_run"}}
        evidence = [{"number": n, "text": source["text"], "scope": source.get("scope", "background_unverified"),
                     "identity": source.get("identity", "확인 필요"),
                     "identity_reason": source.get("identity_reason", "")}
                    for n, source in enumerate(sources, 1)]
        passages = [quotation_parts(source["text"]) for source in sources]
        generation_evidence = [{**{key: value for key, value in row.items() if key != "text"},
                                "passages": [{"passage_id": f"s{row['number']}p{i}", "text": part} for i, part in enumerate(parts)]}
                               for row, parts in zip(evidence, passages)]
        payload = {"selected_movie": {"movie_id": movie.movie_id, "title": movie.title},
                   "question": question, "unverified_recent_conversation": history,
                   "mode": mode, "evidence": generation_evidence, "retrieval_limits": warnings or []}
        feedback, previous_draft = [], None
        schema = deepcopy(ANSWER_SCHEMA)
        schema["properties"]["citations"]["items"] = {
            "type": "object", "additionalProperties": False,
            "properties": {"passage_id": {"type": "string", "enum": [
                f"s{n}p{i}" for n, parts in enumerate(passages, 1) for i in range(len(parts))]}},
            "required": ["passage_id"]}
        if mode == "general":
            # A normal answer has no claim-verdict table. Excluding the field
            # from its actual schema prevents structured decoding from filling
            # an irrelevant verification table despite a mode instruction.
            citations_schema = deepcopy(schema["properties"]["citations"])
            citations_schema["minItems"] = 1
            schema = {"type": "object", "additionalProperties": False,
                      "properties": {"facts": {"type": "array", "minItems": 0, "maxItems": 4, "items": {
                          "type": "object", "additionalProperties": False,
                          "properties": {"citations": citations_schema, "text": {"type": "string"}},
                          "required": ["text", "citations"]}}, "unconfirmed": {"type": "string"}},
                      "required": ["facts", "unconfirmed"]}
        else:
            check_schema = schema["properties"]["checks"]
            check_schema["minItems"] = 2
            check_schema["items"]["properties"]["citations"] = deepcopy(schema["properties"]["citations"])
            # JSON Schema admits an empty list; code requires references for
            # assertive verdicts and drops references on an evidence limitation.
            check_schema["items"]["properties"]["citations"]["minItems"] = 0
            check_schema["items"]["required"].append("citations")
            schema = {"type": "object", "additionalProperties": False,
                      "properties": {"checks": check_schema}, "required": ["checks"]}
        for attempt in range(self.max_attempts):
            self.last_failure_stage = None
            try:
                result = self._request("generate_answer", schema, {**payload, "repair": feedback,
                                                                   "previous_unverified_draft": previous_draft})
                if mode == "verify":
                    raw_checks = deepcopy(result.get("checks")) if isinstance(result, dict) else None
                    result, director_audit = propose_director_checks(
                        movie, question, result, sources, self.canonical_directors)
                    self.audit.append({"stage": "director_field_proposals", "decisions": director_audit,
                                       "raw_checks": raw_checks,
                                       "proposed_checks": deepcopy(result.get("checks")) if isinstance(result, dict) else None})
                result = materialize_citations(result, passages, mode)
                assertions = result.pop("_assertions", None) if isinstance(result, dict) else None
                pre_holds = result.pop("_pre_review_holds", []) if isinstance(result, dict) else []
                if mode == "verify":
                    if assertions is None:
                        raise ValueError("확인 모드 항목 출력 형식 오류")
                    result, assertions, mechanical_holds = prepare_verify_items(result, assertions, sources)
                    pre_holds.extend(mechanical_holds)
                # Extra proposed quotations are not displayed citations. Drop
                # only well-formed, in-range, exact quotations never used by
                # the answer; cited numbers and missing quotes remain strict.
                if isinstance(result, dict) and isinstance(result.get("answer"), str) and isinstance(result.get("checks"), list):
                    reasons = [row.get("reason", "") for row in result["checks"] if isinstance(row, dict) and isinstance(row.get("reason", ""), str)]
                    used = citation_numbers(result["answer"] + "\n" + "\n".join(reasons))
                    if isinstance(result.get("citations"), list):
                        kept, removed = [], []
                        for citation in result["citations"]:
                            if (isinstance(citation, dict) and set(citation) == {"source", "quote"}
                                    and type(citation["source"]) is int and 1 <= citation["source"] <= len(sources)
                                    and citation["source"] not in used and isinstance(citation["quote"], str)
                                    and 2 <= len(citation["quote"]) <= 240
                                    and citation["quote"] in sources[citation["source"] - 1]["text"]):
                                removed.append(citation["source"])
                            else:
                                kept.append(citation)
                        result["citations"] = kept
                        if removed:
                            self.audit.append({"stage": "unused_quotations_removed", "numbers": removed})
                previous_draft = result
                errors = validate_answer(result, sources, mode, allow_review_hold=mode == "verify")
                if errors:
                    self.last_failure_stage = "citation_validation"
                    feedback = errors
                    self.audit.append({"stage": "mechanical", "passed": False, "issues": errors, "draft": result})
                    continue
                self.audit.append({"stage": "mechanical", "passed": True, "draft": result})
                verification_validation = {}
                if mode == "verify":
                    result, verification_validation = self._review_verify(result, assertions, sources,
                                                                         payload["selected_movie"], pre_holds)
                elif assertions is None:
                    assertions = [{"claim": result["answer"], "verdict": "확인됨", "citations": result["citations"]}]
                if mode != "verify" and assertions:
                    review_assertions = deepcopy(assertions)
                    for assertion in review_assertions:
                        for citation in assertion["citations"]:
                            citation["scope"] = sources[citation["source"] - 1].get("scope", "background_unverified")
                            citation["document_id"] = sources[citation["source"] - 1]["document_id"]
                    review = self._request("review_answer", REVIEW_SCHEMA, {"assertions": review_assertions, "mode": mode,
                                           "selected_movie": payload["selected_movie"]})
                elif mode != "verify":
                    # No facts are asserted. Withheld user propositions and
                    # fixed limitation templates do not pass a truth test.
                    review = {"reason": "단정한 사실 없음", "supported": True}
                    self.audit.append({"stage": "no_factual_assertions", "passed": None})
                if mode != "verify" and (not isinstance(review, dict) or set(review) != {"reason", "supported"}
                        or type(review["supported"]) is not bool or not isinstance(review["reason"], str)
                        or not review["reason"].strip() or len(review["reason"]) > 2000):
                    raise ValueError("의미 검토 JSON 오류")
                if mode != "verify" and assertions:
                    self.audit.append({"stage": "semantic_model_review", "passed": review["supported"], "reason": review["reason"]})
                if mode != "verify" and not review["supported"]:
                    self.last_failure_stage = "semantic_review"
                    feedback = [review["reason"]]
                    continue
                stored_sources = [{key: deepcopy(value) for key, value in source.items() if key not in ("text", "quote", "quotes")}
                                  for source in sources]
                quotes_by_source = {}
                for citation in result["citations"]:
                    quotes_by_source.setdefault(citation["source"], []).append(citation["quote"])
                for number, quotes in quotes_by_source.items():
                    stored_sources[number - 1]["quote"] = quotes[0]
                    if len(quotes) > 1:
                        stored_sources[number - 1]["quotes"] = quotes
                return {"content": render_answer(result), "sources": stored_sources,
                        "validation": {"number_range": True, "quotes_in_original": True,
                                       "semantic_check": "model_review_passed" if assertions else "no_factual_assertions",
                                       "attempts": attempt + 1, **verification_validation},
                        "checks": result["checks"],
                        **({"failure_stage": self.last_failure_stage} if verification_validation.get("semantic_check") in
                           ("item_review_held", "item_review_partial") else {})}
            except ValueError:
                if self.last_failure_stage is None:
                    self.last_failure_stage = "answer_parsing"
                feedback = ["JSON·필드·인용 검사를 통과하도록 제공된 근거만 사용해 다시 작성하세요."]
                self.audit.append({"stage": "parse", "passed": False})
        raise DocumentModelError("답변 인용·의미 검토 실패: 재시도 한도 도달")


def create_answer_generator(*, max_attempts=2, generation_model=None, review_model=None):
    planner = create_document_planner()
    from movie_lab.config import resolve_movies_path, resolve_gms_generation_model, resolve_gms_review_model
    from movie_lab.data import DataLoadError, load_movies
    try:
        catalog = load_movies(resolve_movies_path())
        directors = {name for row in catalog.values() for name in row.director}
    except (DataLoadError, OSError):
        # A missing catalogue disables only the narrow proposal helper.
        # Existing evidence generation and semantic review remain available.
        directors = ()
    return AnswerGenerator(planner.client, resolve_gms_generation_model(generation_model), planner.mode,
                           max_attempts=max_attempts, canonical_directors=directors,
                           review_model=resolve_gms_review_model(review_model))
