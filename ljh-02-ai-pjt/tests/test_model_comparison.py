"""Role routing and bounded comparison contracts; injected SDK only, no API."""

from copy import deepcopy
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

import httpx
from openai import BadRequestError, PermissionDeniedError

from movie_lab.answering import AnswerGenerator, create_answer_generator
from movie_lab.config import (DEFAULT_GMS_CHAT_MODEL, gms_chat_options,
                              resolve_gms_generation_model, resolve_gms_review_model)
from scripts.compare_models import (BASELINE, CANDIDATE, BudgetCompletions,
                                    ExperimentStopped, FrozenDraftGenerator, fixed_review_batch, score_fixed_review)
from tests.test_answering import fact_result, model_response, review_result, source
from tests.test_document_llm import sample_movie


class ModelComparisonTests(unittest.TestCase):
    def setUp(self):
        self.network = patch("socket.socket.connect", side_effect=AssertionError("Offline model routing tests"))
        self.network.start()
        self.addCleanup(self.network.stop)

    def test_role_settings_fall_back_without_changing_shared_default_and_factory_reuses_client(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(resolve_gms_generation_model(), BASELINE)
            self.assertEqual(resolve_gms_review_model(), BASELINE)
            os.environ["GMS_CHAT_MODEL"] = "existing-model"
            self.assertEqual(resolve_gms_generation_model(), "existing-model")
            self.assertEqual(resolve_gms_review_model(), "existing-model")
            os.environ["GMS_GENERATION_MODEL"] = CANDIDATE
            os.environ["GMS_REVIEW_MODEL"] = BASELINE
            self.assertEqual(resolve_gms_generation_model(), CANDIDATE)
            self.assertEqual(resolve_gms_review_model(), BASELINE)
            os.environ["GMS_GENERATION_MODEL"] = " "
            self.assertEqual(resolve_gms_generation_model(), "existing-model")
            self.assertEqual(resolve_gms_generation_model(CANDIDATE), CANDIDATE)
            planner = SimpleNamespace(client=MagicMock(), model="existing-model", mode="json_schema")
            with patch("movie_lab.answering.create_document_planner", return_value=planner), patch(
                    "movie_lab.data.load_movies", return_value={sample_movie().movie_id: sample_movie()}):
                configured = create_answer_generator(generation_model=CANDIDATE, max_attempts=1)
                self.assertIs(configured.client, planner.client)
                self.assertEqual(configured.model, CANDIDATE)
                self.assertEqual(configured.review_model, BASELINE)
        self.assertEqual(DEFAULT_GMS_CHAT_MODEL, BASELINE)

    def test_generation_review_models_options_and_raw_outputs_remain_separate(self):
        client = MagicMock()
        raw = fact_result()
        response1 = model_response(raw)
        response1.model = "gpt-5.4-mini-2026-03-17"
        client.chat.completions.create.side_effect = [response1, model_response(review_result())]
        generator = AnswerGenerator(client, CANDIDATE, review_model=BASELINE, max_attempts=1)
        result = generator.generate(sample_movie(), "시간 설명", [], [source()])
        generation, review = client.chat.completions.create.call_args_list
        self.assertEqual(generation.kwargs["model"], CANDIDATE)
        self.assertEqual(generation.kwargs["reasoning_effort"], "none")
        self.assertEqual(generation.kwargs["max_completion_tokens"], 1800)
        self.assertNotIn("max_tokens", generation.kwargs)
        self.assertEqual(review.kwargs["model"], BASELINE)
        self.assertEqual(review.kwargs["max_tokens"], 1800)
        self.assertNotIn("reasoning_effort", review.kwargs)
        self.assertTrue(generation.kwargs["response_format"]["json_schema"]["strict"])
        self.assertEqual(generator.request_audit[0]["parsed_output"], raw)
        self.assertEqual(json.loads(generator.request_audit[0]["raw_output"]), raw)
        self.assertNotEqual(generator.request_audit[0]["payload_sha256"], generator.request_audit[1]["payload_sha256"])
        self.assertEqual(generator.reported_models["generate_answer"], response1.model)
        self.assertEqual(generator.metrics["answer_generation"]["calls"], 1)
        self.assertEqual(generator.metrics["semantic_review"]["calls"], 1)
        self.assertEqual(result["validation"]["semantic_check"], "model_review_passed")

    def test_sdk_attempt_cap_permission_stop_and_safe_error_records(self):
        with TemporaryDirectory() as temp:
            sdk = MagicMock(return_value=model_response({}))
            budget = BudgetCompletions(sdk, Path(temp) / "calls.jsonl", limit=1)
            budget.create(**gms_chat_options(BASELINE), messages=[])
            with self.assertRaises(ExperimentStopped):
                budget.create(**gms_chat_options(BASELINE), messages=[])
            self.assertEqual(sdk.call_count, 1)
            response = httpx.Response(403, request=httpx.Request("POST", "https://example.invalid"))
            sdk = MagicMock(side_effect=PermissionDeniedError("synthetic private body", response=response, body=None))
            budget = BudgetCompletions(sdk, Path(temp) / "denied.jsonl")
            with self.assertRaises(PermissionDeniedError):
                budget.create(**gms_chat_options(CANDIDATE), messages=[])
            self.assertFalse(budget.available(CANDIDATE))
            self.assertEqual(budget.summary()["actual_chat_attempts"], 1)
            self.assertNotIn("synthetic private body", budget.path.read_text(encoding="utf-8"))
            self.assertTrue(budget.available(BASELINE))

    def test_one_explicit_parameter_repair_is_counted_and_not_repeated(self):
        response = httpx.Response(400, request=httpx.Request("POST", "https://example.invalid"))
        error = BadRequestError("synthetic error body", response=response,
                                body={"code": "unsupported_parameter", "param": "temperature"})
        with TemporaryDirectory() as temp:
            sdk = MagicMock(side_effect=[error, model_response({}), error])
            budget = BudgetCompletions(sdk, Path(temp) / "calls.jsonl")
            budget.create(**gms_chat_options(CANDIDATE), messages=[])
            self.assertEqual(sdk.call_count, 2)
            self.assertIn("temperature", sdk.call_args_list[0].kwargs)
            self.assertNotIn("temperature", sdk.call_args_list[1].kwargs)
            self.assertTrue(budget.option_repair_used)
            with self.assertRaises(BadRequestError):
                budget.create(**gms_chat_options(CANDIDATE), messages=[])
            self.assertEqual(sdk.call_count, 3)
            self.assertFalse(budget.available(CANDIDATE))
            self.assertEqual(budget.summary()["actual_chat_attempts"], 3)
            self.assertNotIn("synthetic error body", budget.path.read_text(encoding="utf-8"))

    def test_frozen_baseline_draft_runs_only_review_and_preserves_original(self):
        client = MagicMock()
        raw, sources = fact_result(), [source()]
        before = deepcopy((raw, sources))
        client.chat.completions.create.return_value = model_response(review_result())
        generator = FrozenDraftGenerator(client, BASELINE, review_model=CANDIDATE,
                                          max_attempts=1, frozen_draft=raw)
        result = generator.generate(sample_movie(), "시간 설명", [], sources)
        self.assertEqual(client.chat.completions.create.call_count, 1)
        self.assertEqual(generator.metrics["answer_generation"]["calls"], 0)
        self.assertEqual(generator.metrics["semantic_review"]["calls"], 1)
        self.assertEqual([row["role"] for row in generator.request_audit], ["review_answer"])
        self.assertEqual((raw, sources), before)
        self.assertEqual(result["validation"]["semantic_check"], "model_review_passed")
        self.assertEqual(generator.audit[0]["stage"], "frozen_generation_replay")

    def test_fixed_batch_has_four_polarity_cases_and_two_labeled_scope_challenges(self):
        case = {"movie": {"movie_id": sample_movie().movie_id, "title": sample_movie().title}, "sources": [
            source(scope="movie_metadata", document_id="meta:753091", text="감독: 김용화"),
            source(text="달은 지구의 유일한 자연위성이고 표면이 보인다.")]
        }
        payload, reference = fixed_review_batch(case)
        self.assertEqual([row["claim_id"] for row in payload["items"]], [f"c{i}" for i in range(1, 7)])
        self.assertTrue(all("proposed_verdict" not in row for row in payload["items"]))
        self.assertEqual([row["accepted"] for row in reference[:4]], [True, False, True, False])
        self.assertEqual([row["relation"] for row in reference[-2:]], ["insufficient", "insufficient"])
        self.assertTrue(payload["items"][4]["citations"][0]["document_id"].startswith("fixture:"))
        self.assertTrue(reference[-1]["mechanical_scope_would_reject"])
        incorrect_review = {"items": [{"claim_id": row["claim_id"], "evidence_relation": "contradicts",
                                        "service_reason_supported": True, "reason": "고정 잘못된 검토"}
                                       for row in reference]}
        scored = score_fixed_review(incorrect_review, reference)
        self.assertTrue(scored[3]["would_accept_after_mechanical_scope"])
        self.assertFalse(scored[3]["acceptance_matches_reference"])
        self.assertFalse(scored[-1]["would_accept_after_mechanical_scope"])


if __name__ == "__main__":
    unittest.main()
