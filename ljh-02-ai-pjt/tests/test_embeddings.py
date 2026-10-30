"""No real API calls: validate the shared embedding contract and safe evidence."""

import io
import json
import math
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx
from openai import APIConnectionError, APITimeoutError, AuthenticationError, NotFoundError

from movie_lab import embeddings as module
from scripts import check_gms_embeddings as smoke


def response(vectors, *, indexes=None, model="text-embedding-3-small"):
    indexes = indexes if indexes is not None else range(len(vectors))
    return SimpleNamespace(model=model, data=[SimpleNamespace(index=index, embedding=vector) for index, vector in zip(indexes, vectors)])


class EmbeddingTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock()
        self.client.embeddings.create.return_value = response([[0.1, 0.2, 0.3]])
        self.embedding = module.GmsEmbeddings("text-embedding-3-small", client=self.client)

    def test_document_and_query_share_model_and_actual_dimension(self):
        self.assertEqual(self.embedding.embed_documents(["문서"]), [[0.1, 0.2, 0.3]])
        self.assertEqual(self.embedding.embed_query("질문"), [0.1, 0.2, 0.3])
        self.assertEqual(self.embedding.dimensions, 3)
        self.assertEqual(self.embedding.reported_model, "text-embedding-3-small")
        self.assertEqual(self.embedding.request_count, 2)
        self.assertEqual(self.embedding.embedded_text_count, 2)
        for call in self.client.embeddings.create.call_args_list:
            self.assertEqual(call.kwargs["model"], "text-embedding-3-small")
            self.assertEqual(call.kwargs["encoding_format"], "float")
            self.assertNotIn("dimensions", call.kwargs)
            self.assertTrue(all(isinstance(value, str) for value in call.kwargs["input"]))

    def test_batches_and_response_indexes_preserve_document_order(self):
        self.embedding.batch_size = 2
        self.client.embeddings.create.side_effect = [response([[2.0], [1.0]], indexes=[1, 0]), response([[3.0]])]
        self.assertEqual(self.embedding.embed_documents(["first", "second", "third"]), [[1.0], [2.0], [3.0]])
        self.assertEqual(self.embedding.request_count, 2)
        self.assertEqual(self.embedding.embedded_text_count, 3)

    def test_invalid_or_empty_input_makes_no_request(self):
        self.assertEqual(self.embedding.embed_documents([]), [])
        for value in ([""], ["  "], [None], "text"):
            with self.subTest(value=value), self.assertRaises(module.EmbeddingValidationError):
                self.embedding.embed_documents(value)
        self.client.embeddings.create.assert_not_called()

    def test_explicit_dimensions_are_sent_and_must_match(self):
        embeddings = module.GmsEmbeddings("text-embedding-3-small", 3, client=self.client)
        embeddings.embed_query("hello")
        self.assertEqual(self.client.embeddings.create.call_args.kwargs["dimensions"], 3)
        self.client.embeddings.create.return_value = response([[1.0]])
        with self.assertRaises(module.EmbeddingValidationError):
            embeddings.embed_query("other")

    def test_malformed_vectors_counts_indexes_and_dimension_change_are_rejected(self):
        malformed = [response([]), response([[]]), response([[math.nan]]), response([[math.inf]]),
                     response([[True]]), response([["private-response"]]), response([[1.0]], indexes=[2]),
                     response([[1.0], [1.0]], indexes=[0, 0])]
        for value in malformed:
            with self.subTest(value=value):
                self.client.embeddings.create.return_value = value
                with self.assertRaises(module.EmbeddingValidationError):
                    self.embedding.embed_query("hello")
        self.client.embeddings.create.return_value = response([[1.0, 2.0]])
        self.embedding.embed_query("hello")
        self.client.embeddings.create.return_value = response([[1.0]])
        with self.assertRaises(module.EmbeddingValidationError):
            self.embedding.embed_query("hello")

    def test_client_options_local_dotenv_and_env_key_are_reused(self):
        with patch.object(module, "load_dotenv") as load, patch.dict(module.os.environ, {"GMS_KEY": "synthetic-test-key"}), patch.object(module, "OpenAI") as sdk:
            module.create_gms_embeddings("text-embedding-3-small")
        load.assert_called_once_with(dotenv_path=module.PROJECT_ROOT / ".env", override=False, verbose=False)
        self.assertEqual(sdk.call_args.kwargs, {"api_key": "synthetic-test-key", "base_url": module.GMS_BASE_URL, "max_retries": 0, "timeout": 30.0})

    def test_missing_key_and_invalid_configuration_do_not_construct_client(self):
        with patch.object(module, "OpenAI") as sdk:
            for kwargs in ({}, {"api_key": " "}, {"dimensions": 0}, {"batch_size": 0}, {"model": "bad model"}):
                with self.subTest(kwargs=kwargs), self.assertRaises(module.EmbeddingValidationError):
                    module.GmsEmbeddings(**kwargs)
            sdk.assert_not_called()

    def test_api_failure_is_not_retried_and_output_excludes_private_details(self):
        request = httpx.Request("POST", "https://example.invalid")
        error = AuthenticationError("synthetic-test-key", response=httpx.Response(401, request=request), body={"message": "synthetic-test-key"})
        self.client.embeddings.create.side_effect = error
        with self.assertRaises(AuthenticationError):
            self.embedding.embed_query("test")
        self.client.embeddings.create.assert_called_once()
        self.assertNotIn("synthetic-test-key", json.dumps(module.failure_details(error)))
        self.assertEqual(module.failure_details(error)["category"], "인증 실패")
        self.assertEqual(module.failure_details(APITimeoutError(request=request))["category"], "타임아웃")
        self.assertEqual(module.failure_details(APIConnectionError(request=request))["category"], "네트워크 연결 실패")
        unsupported = NotFoundError("private", response=httpx.Response(404, request=request), body={"code": "model_not_found"})
        self.assertEqual(module.failure_details(unsupported)["category"], "모델 미지원 또는 모델 접근 불가")

    def test_smoke_performs_one_request_prints_dimension_not_vector(self):
        with patch.object(smoke, "create_gms_embeddings", return_value=self.embedding), redirect_stdout(io.StringIO()) as output:
            code = smoke.run_check("text-embedding-3-small")
        result = json.loads(output.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(result["dimensions"], 3)
        self.assertEqual(result["request_count"], 1)
        self.assertEqual(result["text_count"], 1)
        self.assertNotIn("0.1", output.getvalue())
        self.client.embeddings.create.assert_called_once_with(model="text-embedding-3-small", input=[smoke.PROBE_TEXT], encoding_format="float")

    def test_smoke_failure_output_has_fixed_category_not_exception_text(self):
        with patch.object(smoke, "create_gms_embeddings", side_effect=ValueError("synthetic-test-key private response")), redirect_stdout(io.StringIO()) as output:
            code = smoke.run_check("text-embedding-3-small")
        self.assertEqual(code, 1)
        self.assertNotIn("synthetic-test-key", output.getvalue())
        self.assertEqual(json.loads(output.getvalue())["status"], "failure")


if __name__ == "__main__":
    unittest.main()
