"""Bounded GMS role comparison using frozen recorded evidence, never reindexing.

Nothing calls a model at import time. --run explicitly enables the experiment;
all actual chat attempts, including failed requests and one optional documented
parameter repair, share the persistent 18-attempt ledger. A result/start marker
prevents accidental replay of an already started experiment.
"""

from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import re
import sys
import time
from types import SimpleNamespace

PROJECT = Path(__file__).resolve().parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from movie_lab.answering import (AnswerGenerator, RELATION_BY_VERDICT, VERIFY_REVIEW_SCHEMA,
                                 create_answer_generator, quotation_parts)
from movie_lab.config import (DEFAULT_GMS_CHAT_MODEL, resolve_gms_chat_model,
                              resolve_gms_generation_model, resolve_gms_review_model, resolve_movies_path)
from movie_lab.data import load_movies
from movie_lab.document_llm import DocumentModelError
from movie_lab.embeddings import failure_details


BASELINE, CANDIDATE = "gpt-4o-mini", "gpt-5.4-mini"
MAX_CHAT_ATTEMPTS = 18
OFFICIAL_SOURCES = [
    "https://developers.openai.com/api/docs/models/gpt-5.4-mini",
    "https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create",
]


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                      separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def load_frozen_cases(project=PROJECT):
    """Read original retrieval.sources, not post-answer shortened sources."""
    project = Path(project)
    earlier_path = project / "artifacts/review_stage4_fix/actual_cases.json"
    director_path = project / "artifacts/review_director_field/actual_case.json"
    earlier = json.loads(earlier_path.read_text(encoding="utf-8"))
    director = json.loads(director_path.read_text(encoding="utf-8"))
    records = {row["id"]: row for row in earlier["records"]}
    inputs = [
        ("Q1", records["multiple_quotes"], earlier_path, "general"),
        ("Q2", director, director_path, "verify"),
        ("Q3", records["insufficient"], earlier_path, "verify"),
    ]
    movies = load_movies(resolve_movies_path())
    cases = []
    for case_id, original, path, mode in inputs:
        sources = deepcopy(original["retrieval"]["sources"])
        if not sources or any(not isinstance(row.get("text"), str) or not row["text"] for row in sources):
            raise ValueError("동결할 검색 원문이 없습니다")
        movie = movies[original["movie_id"]]
        fixed = {"movie": asdict(movie), "question": original["question"], "mode": mode,
                 "history": [], "sources": sources}
        cases.append({"case_id": case_id, **fixed, "input_sha256": digest(fixed),
                      "recorded_evidence": str(path.relative_to(project)).replace("\\", "/"),
                      "history_note": "Same empty history for all compared roles; no new retrieval or preparation."})
    return cases, movies


class ExperimentStopped(RuntimeError):
    pass


class BudgetCompletions:
    """SDK adapter: safe attempt ledger, no hidden retries or API discovery."""
    def __init__(self, create, ledger_path, limit=MAX_CHAT_ATTEMPTS):
        self.create_sdk, self.path, self.limit = create, Path(ledger_path), limit
        self.rows, self.blocked, self.failures = [], set(), Counter()
        self.option_repair_used, self.fatal = False, False

    def available(self, model):
        return len(self.rows) < self.limit and model not in self.blocked and not self.fatal

    def _persist(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in self.rows), encoding="utf-8")

    def _one(self, kwargs, repair=None):
        model = kwargs["model"]
        if not self.available(model):
            raise ExperimentStopped("실험 호출 한도 또는 모델 중단 상태")
        row = {"attempt": len(self.rows) + 1, "model": model, "status": "started",
               "options": deepcopy({key: value for key, value in kwargs.items() if key != "messages"}),
               "request_sha256": digest(kwargs["messages"]), "sdk_retries": 0}
        if repair:
            row["compatibility_repair"] = repair
        self.rows.append(row)
        self._persist()  # Consume before transmitting, including interrupted requests.
        started = time.perf_counter()
        try:
            response = self.create_sdk(**kwargs)
            row["status"] = "response"
            reported = getattr(response, "model", None)
            if isinstance(reported, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,150}", reported):
                row["reported_model"] = reported
            return response
        except Exception as error:
            info = failure_details(error)
            row.update(status="error", error=info)
            raise
        finally:
            row["seconds"] = time.perf_counter() - started
            self._persist()

    def create(self, **kwargs):
        model = kwargs["model"]
        try:
            return self._one(kwargs)
        except ExperimentStopped:
            raise
        except Exception as error:
            status = getattr(error, "status_code", None)
            body = getattr(error, "body", None)
            detail = body.get("error", body) if isinstance(body, dict) else {}
            detail = detail if isinstance(detail, dict) else {}
            param = getattr(error, "param", None) or detail.get("param")
            # Only explicit rejected parameter names allow one repair; never
            # log the error message/body, guess auth fixes, or drop strictness.
            if (model == CANDIDATE and status == 400 and not self.option_repair_used
                    and param in ("temperature", "reasoning_effort", "max_completion_tokens")
                    and param in kwargs and self.available(model)):
                self.option_repair_used = True
                repaired = deepcopy(kwargs)
                value = repaired.pop(param)
                if param == "max_completion_tokens":
                    repaired["max_tokens"] = value
                try:
                    return self._one(repaired, {"removed": param,
                                     "replacement": "max_tokens" if param == "max_completion_tokens" else None})
                except Exception:
                    self.blocked.add(model)
                    raise
            self.failures[model] += 1
            if status == 401:
                self.fatal = True
            if status in (400, 401, 403, 404) or self.failures[model] >= 2:
                self.blocked.add(model)
            raise

    def summary(self):
        return {"limit": self.limit, "actual_chat_attempts": len(self.rows),
                "by_model": dict(Counter(row["model"] for row in self.rows)),
                "responses": sum(row["status"] == "response" for row in self.rows),
                "failures": sum(row["status"] == "error" for row in self.rows),
                "option_repair_used": self.option_repair_used, "blocked_models": sorted(self.blocked),
                "authentication_stop": self.fatal, "embedding_calls": 0, "retrieval_calls": 0}


class FrozenDraftGenerator(AnswerGenerator):
    """Reuse the exact baseline model draft; generation here is not an API call."""
    def __init__(self, *args, frozen_draft, **kwargs):
        super().__init__(*args, **kwargs)
        self.frozen_draft = deepcopy(frozen_draft)

    def _request(self, role, schema, payload):
        if role == "generate_answer":
            self.audit.append({"stage": "frozen_generation_replay", "model_call": False,
                               "raw_draft_sha256": digest(self.frozen_draft)})
            return deepcopy(self.frozen_draft)
        return super()._request(role, schema, payload)


def compare_case(case, movies, directors, client, generation_model, review_model, *, frozen_draft=None):
    generator_type = FrozenDraftGenerator if frozen_draft is not None else AnswerGenerator
    extra = {"frozen_draft": frozen_draft} if frozen_draft is not None else {}
    generator = generator_type(client, generation_model, review_model=review_model,
                               max_attempts=1, canonical_directors=directors, **extra)
    started, result, error = time.perf_counter(), None, None
    try:
        result = generator.generate(movies[case["movie"]["movie_id"]], case["question"], deepcopy(case["history"]),
                                    deepcopy(case["sources"]), case["mode"], warnings=[])
    except DocumentModelError as failure:
        error = {"category": failure.category, "http_status": failure.http_status}
    except (ValueError, ExperimentStopped):
        error = {"category": "동결 입력 또는 실험 한도 확인 필요"}
    generation = [row for row in generator.request_audit if row["role"] == "generate_answer"]
    raw = deepcopy(frozen_draft) if frozen_draft is not None else (generation[0].get("parsed_output") if generation else None)
    return {"case_id": case["case_id"], "input_sha256": case["input_sha256"],
            "generation_model": generation_model, "review_model": review_model,
            "generation_replayed": frozen_draft is not None,
            "raw_generation": deepcopy(raw), "raw_generation_sha256": digest(raw) if raw is not None else None,
            "requests": generator.request_audit,
            "code_processing": [row for row in generator.audit if row["stage"] in
                                ("director_field_proposals", "mechanical", "unused_quotations_removed", "parse")],
            "review_audit": [row for row in generator.audit if row["stage"] in
                             ("verify_item_review", "semantic_model_review", "no_factual_assertions")],
            "final_result": result, "error": error, "failure_stage": generator.last_failure_stage,
            "seconds": time.perf_counter() - started, "stage_metrics": deepcopy(generator.metrics)}


def fixed_review_batch(case):
    """Six labeled challenge items; proposed verdicts never enter model input.

    The irrelevant terrain sentence is an explicitly isolated fixture from the
    existing protocol test, not a newly retrieved or verified movie document.
    """
    metadata = next(row for row in case["sources"] if row.get("scope") == "movie_metadata")
    natural = next(row for row in case["sources"] if row.get("scope") == "background_unverified"
                   and "달은 지구의 유일한 자연위성" in row["text"])
    moon_quote = next(part for part in quotation_parts(natural["text"]) if "달은 지구의 유일한 자연위성" in part)
    director_quote = "감독: 김용화"
    if director_quote not in metadata["text"]:
        raise ValueError("고정 검토 감독 구절 누락")
    meta_citation = {"source": 1, "quote": director_quote, "scope": "movie_metadata",
                     "document_id": metadata["document_id"]}
    background = {"source": 2, "quote": moon_quote, "scope": "background_unverified",
                  "document_id": natural["document_id"]}
    terrain = {"source": 3, "quote": "달의 바다는 현무암과 용암 대지로 이루어진 상대적으로 어두운 지역이다.",
               "scope": "background_unverified", "document_id": "fixture:irrelevant-moon-terrain"}
    inputs, expected = [], []
    matrix = [
        ("크리스토퍼 놀란", "근거와 상충", "감독은 김용화로 표기되어 있어 주장과 상충합니다.", "contradicts", True, True),
        ("크리스토퍼 놀란", "확인됨", "메타데이터는 크리스토퍼 놀란이 감독했다고 명시합니다.", "contradicts", False, False),
        ("김용화", "확인됨", "메타데이터에 감독이 김용화라고 표기되어 있습니다.", "supports", True, True),
        ("김용화", "근거와 상충", "메타데이터의 감독은 크리스토퍼 놀란이므로 주장과 상충합니다.", "supports", False, False),
    ]
    for index, (name, proposed, reason, relation, supported, accepted) in enumerate(matrix, 1):
        inputs.append({"claim_id": f"c{index}", "user_proposition": f"이 영화의 감독은 {name}다.",
                       "service_reason": reason, "scope": "작품 속 묘사", "citations": [deepcopy(meta_citation)]})
        expected.append({"claim_id": f"c{index}", "proposed_verdict": proposed, "relation": relation,
                         "reason_supported": supported, "accepted": accepted})
    inputs.extend([
        {"claim_id": "c5", "user_proposition": "달은 지구의 자연위성이다.", "service_reason": "이 지형 구절이 자연위성 분류를 확인합니다.",
         "scope": "현실 사실", "citations": [terrain]},
        {"claim_id": "c6", "user_proposition": "이 영화에서 달이 스스로 빛나는 별로 등장한다.",
         "service_reason": "현실 자연위성 설명으로 이 영화의 해당 장면을 확인했습니다.", "scope": "작품 속 묘사", "citations": [background]},
    ])
    expected.extend([
        {"claim_id": "c5", "proposed_verdict": "확인됨", "relation": "insufficient", "reason_supported": False, "accepted": False},
        {"claim_id": "c6", "proposed_verdict": "확인됨", "relation": "insufficient", "reason_supported": False, "accepted": False,
         "mechanical_scope_would_reject": True},
    ])
    return {"selected_movie": {"movie_id": case["movie"]["movie_id"], "title": case["movie"]["title"]}, "items": inputs}, expected


def score_fixed_review(output, expected):
    """Offline scoring against the declared human reference, not a new review."""
    rows = output.get("items") if isinstance(output, dict) else None
    comparisons = []
    for truth in expected:
        matches = [row for row in rows if isinstance(row, dict) and row.get("claim_id") == truth["claim_id"]] if isinstance(rows, list) else []
        actual = matches[0] if len(matches) == 1 else None
        would_accept = bool(actual and actual.get("evidence_relation") == RELATION_BY_VERDICT.get(truth["proposed_verdict"])
                            and actual.get("service_reason_supported") is True
                            and not truth.get("mechanical_scope_would_reject"))
        comparisons.append({**truth, "actual": actual, "would_accept_after_mechanical_scope": would_accept,
                            "acceptance_matches_reference": would_accept == truth["accepted"],
                            "matches_reference": bool(actual and actual.get("evidence_relation") == truth["relation"]
                                                       and actual.get("service_reason_supported") is truth["reason_supported"])})
    return comparisons


def run_fixed_review(case, client, model):
    payload, expected = fixed_review_batch(case)
    schema = deepcopy(VERIFY_REVIEW_SCHEMA)
    schema["properties"]["items"]["items"]["properties"]["claim_id"]["enum"] = [item["claim_id"] for item in payload["items"]]
    generator = AnswerGenerator(client, BASELINE, review_model=model, max_attempts=1)
    output, error = None, None
    try:
        output = generator._request("review_verify", schema, payload)
    except DocumentModelError as failure:
        error = {"category": failure.category, "http_status": failure.http_status}
    except (ValueError, ExperimentStopped):
        error = {"category": "검토 JSON 또는 호출 한도 오류"}
    comparisons = score_fixed_review(output, expected)
    return {"model": model, "input_sha256": digest(payload), "payload": payload,
            "fixture_note": "Controlled review challenge; c5 is an isolated protocol fixture, c6 deliberately violates evidence scope. Not live retrieval.",
            "requests": generator.request_audit, "output": output, "error": error, "reference_comparison": comparisons}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="실제 GMS 비교를 한 번 실행")
    parser.add_argument("--output-dir", default="artifacts/review_upgrade/models")
    args = parser.parse_args()
    output = Path(args.output_dir)
    if not output.is_absolute():
        output = PROJECT / output
    started_path, result_path = output / "experiment_started.json", output / "comparison.json"
    if started_path.exists() or result_path.exists():
        print(json.dumps({"status": "stopped", "reason": "기존 실험 기록이 있어 자동 재실행을 차단했습니다"}, ensure_ascii=False))
        return 2
    cases, movies = load_frozen_cases()
    write_json(output / "frozen_inputs.json", {"cases": cases, "official_documentation": OFFICIAL_SOURCES,
               "note": "Official model documentation does not establish GMS support. No retrieval/embedding calls."})
    if not args.run:
        print(json.dumps({"mode": "prepare-only", "cases": len(cases), "chat_calls": 0}, ensure_ascii=False))
        return 0
    write_json(started_path, {"chat_attempt_limit": MAX_CHAT_ATTEMPTS, "baseline": BASELINE, "candidate": CANDIDATE})
    # This existing factory alone loads the key. No key inspection, new key,
    # environment override, direct OpenAI endpoint, or model-list request.
    base = create_answer_generator(max_attempts=1, generation_model=BASELINE, review_model=BASELINE)
    ledger = BudgetCompletions(base.client.chat.completions.create, output / "chat_attempts.jsonl")
    client = SimpleNamespace(chat=SimpleNamespace(completions=ledger))
    directors = {name for movie in movies.values() for name in movie.director}
    defaults_before = {"chat": resolve_gms_chat_model(), "generation": resolve_gms_generation_model(), "review": resolve_gms_review_model()}
    report = {"baseline": BASELINE, "candidate": CANDIDATE, "sdk_retries": 0, "max_generation_attempts": 1,
              "comparison_conditions": {"same_frozen_inputs": True, "new_retrieval": False, "new_embedding": False,
                                        "sampling": "temperature=0", "output_cap": 1800,
                                        "candidate_reasoning": "none", "strict_json_schema_requested": True},
              "defaults_before": defaults_before, "generation_role": [], "review_role": [], "fixed_review": []}
    baselines = {}
    for case in cases:
        for model in (BASELINE, CANDIDATE):
            if not ledger.available(model) or not ledger.available(BASELINE):
                report["generation_role"].append({"case_id": case["case_id"], "generation_model": model,
                                                  "status": "skipped_model_or_budget_stopped"})
                continue
            record = compare_case(case, movies, directors, client, model, BASELINE)
            report["generation_role"].append(record)
            if model == BASELINE:
                baselines[case["case_id"]] = record
            write_json(result_path, {**report, "calls": ledger.summary(), "incomplete": True})
    for case in cases:
        raw = baselines.get(case["case_id"], {}).get("raw_generation")
        if raw is None or not ledger.available(CANDIDATE):
            report["review_role"].append({"case_id": case["case_id"], "review_model": CANDIDATE,
                                          "status": "skipped_no_baseline_draft_or_model_stopped"})
            continue
        report["review_role"].append(compare_case(case, movies, directors, client, BASELINE, CANDIDATE, frozen_draft=raw))
        write_json(result_path, {**report, "calls": ledger.summary(), "incomplete": True})
    for model in (BASELINE, CANDIDATE):
        if ledger.available(model):
            report["fixed_review"].append(run_fixed_review(cases[1], client, model))
        else:
            report["fixed_review"].append({"model": model, "status": "skipped_model_or_budget_stopped"})
    defaults_after = {"chat": resolve_gms_chat_model(), "generation": resolve_gms_generation_model(), "review": resolve_gms_review_model()}
    compared = report["generation_role"] + report["review_role"] + report["fixed_review"]
    complete = all(not row.get("error") and not str(row.get("status", "")).startswith("skipped") for row in compared)
    report.update(calls=ledger.summary(), defaults_after=defaults_after,
                  defaults_unchanged=defaults_before == defaults_after,
                  code_default_unchanged=DEFAULT_GMS_CHAT_MODEL == BASELINE,
                  run_finished=True, comparison_complete=complete, incomplete=not complete,
                  note="One small experiment, not a broad accuracy/cost/latency ranking.")
    write_json(result_path, report)
    print(json.dumps({"output": str(result_path.relative_to(PROJECT)).replace("\\", "/"), "calls": report["calls"],
                      "defaults_unchanged": report["defaults_unchanged"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(json.dumps({"status": "stopped", "error": failure_details(error)}, ensure_ascii=False))
        raise SystemExit(1) from None
