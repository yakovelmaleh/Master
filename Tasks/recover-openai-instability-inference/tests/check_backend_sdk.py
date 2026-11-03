"""Actual pinned OpenAI SDK against memory-only HTTP; no Azure access."""

import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
import openai

from recovery import RecoveryBackend, UncertainHTTP500
from azure_backend import ProviderError
from cloud_control import RetryableRejection
from protocol import PROMPT, read_json


class BackendSDKTests(unittest.TestCase):
    def backend(self, handler):
        self.assertEqual(openai.__version__, "2.6.1")
        backend = object.__new__(RecoveryBackend)
        backend.config = read_json(
            Path(__file__).resolve().parents[2] / "train-openai-instability-within-project/prompt_only.json"
        )
        backend.approval = {"base_deployment": "fixture"}
        backend.guard = Mock()
        client = httpx.Client(transport=httpx.MockTransport(handler))
        backend.client = openai.OpenAI(
            api_key="offline-fixture", base_url="https://fixture.openai.azure.com/openai/v1/",
            max_retries=0, http_client=client,
        )
        self.addCleanup(backend.client.close)
        return backend

    def predict(self, backend):
        return backend.predict("fixture", [
            {"role": "system", "content": PROMPT}, {"role": "user", "content": '{"text":"fixture"}'},
        ])

    def test_only_500_becomes_a_durably_retryable_unknown(self):
        for status, expected in ((500, UncertainHTTP500), (400, ProviderError),
                                 (503, ProviderError), (429, RetryableRejection)):
            calls = []

            def handler(request):
                calls.append(request)
                return httpx.Response(
                    status, json={"error": {"code": "server_error", "message": "SECRET-FIXTURE"}},
                    headers={"x-request-id": "req_0123456789abcdef"},
                )

            backend = self.backend(handler)
            with self.subTest(status=status), self.assertRaises(expected) as raised:
                self.predict(backend)
            self.assertEqual(len(calls), 1)
            self.assertNotIn("SECRET-FIXTURE", str(raised.exception))
            if status == 500:
                self.assertEqual(raised.exception.details["http_status"], 500)
                self.assertNotIn("SECRET-FIXTURE", json.dumps(raised.exception.details))
            elif status != 429:
                self.assertNotIsInstance(raised.exception, UncertainHTTP500)

    def test_connection_timeout_remains_blocked(self):
        calls = []

        def handler(request):
            calls.append(request)
            raise httpx.ReadTimeout("private fixture failure", request=request)

        with self.assertRaises(ProviderError) as raised:
            self.predict(self.backend(handler))
        self.assertNotIsInstance(raised.exception, UncertainHTTP500)
        self.assertEqual(len(calls), 1)

    def test_success_uses_unchanged_payload_and_class_scores(self):
        payloads = []

        def handler(request):
            payloads.append(json.loads(request.content))
            return httpx.Response(200, json={
                "id": "chatcmpl-fixture", "object": "chat.completion", "created": 1,
                "model": "gpt-4.1-mini-2025-04-14",
                "choices": [{"index": 0, "finish_reason": "length",
                             "message": {"role": "assistant", "content": "1"},
                             "logprobs": {"content": [{
                                 "token": "1", "logprob": -0.2, "bytes": [49],
                                 "top_logprobs": [
                                     {"token": "0", "logprob": -2, "bytes": [48]},
                                     {"token": "1", "logprob": -0.2, "bytes": [49]},
                                 ],
                             }]}}],
                "usage": {"prompt_tokens": 30, "completion_tokens": 1, "total_tokens": 31},
            })

        result = self.predict(self.backend(handler))
        self.assertGreater(result["score"], .8)
        self.assertEqual(len(payloads), 1)
        self.assertEqual(payloads[0], {
            "model": "fixture", "messages": [
                {"role": "system", "content": PROMPT},
                {"role": "user", "content": '{"text":"fixture"}'},
            ],
            "temperature": 1, "seed": 7, "max_tokens": 1,
            "logprobs": True, "top_logprobs": 20,
        })


if __name__ == "__main__":
    unittest.main()
