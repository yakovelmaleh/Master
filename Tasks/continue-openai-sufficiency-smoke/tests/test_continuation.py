import copy
from contextlib import redirect_stderr
import io
from pathlib import Path
import sys
import time
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

TASK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TASK))
sys.path.insert(0, str(TASK.parent / "resolve-openai-sufficiency-smoke/tests"))
import continuation
import test_resolution as resolutions
from cloud_control import ControlError, ROOT
from ledger import SufficiencyLedger
from protocol import read_json, write_json


class ContinuationTests(unittest.TestCase):
    def setUp(self):
        fixtures = resolutions.diagnostics.inspections.fixtures
        loader = fixtures.source_loader
        def twenty_rows(project, root):
            train, validation, test = loader(project, root)
            validation = fixtures.pd.concat([validation] * 5, ignore_index=True)
            validation["row_id"] = [f"{project}:validation:{i}" for i in range(len(validation))]
            return train, validation, test
        patcher = patch.object(fixtures, "source_loader", side_effect=twenty_rows)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.fixture = resolutions.ResolutionTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.execute()
        self.root, self.store = self.fixture.root, self.fixture.store
        self.one = self.fixture.fixture
        self.client, self.openai = self.one.client, self.one.openai
        self.client.reset_mock()
        self.openai.OpenAI.reset_mock()
        self.store.authenticate.reset_mock()
        self.store.budget = continuation.SmokeBudget(3640)
        write_json(self.fixture.directory / "worker-status.json", {
            "status": "succeeded", "resolved": True, "model_calls": 0,
            "completes_smoke": False, "authorizes_continuation": False,
        })
        self.resolution_path = self.root.parent / "resolution-approved.json"
        write_json(self.resolution_path, self.fixture.review)
        self.review = continuation.template(self.root, self.resolution_path)
        self.review.update(
            remaining_credit_usd="100", expires_at=self.fixture.review["expires_at"],
            execution_approved=True, checks={key: True for key in continuation.CHECKS},
        )
        self.directory = self.root / "jobs/continue-smoke"
        self.directory.mkdir()
        for patcher in (
            patch.object(continuation, "InspectionStore", return_value=self.store),
            patch.object(continuation, "Tokenizer", return_value=fixtures.FakeTokenizer()),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def execute(self):
        return continuation.execute(self.root, self.review, self.directory)

    def operation(self, name):
        return self.store.storage.rows[SufficiencyLedger._key(self.review["run"], name)][0]

    def test_completes_only_remaining_predictions_with_exact_requests_and_cached_zero(self):
        before = copy.deepcopy(self.store.storage.rows)
        result = self.execute()
        self.assertEqual(result["model_requests"], 21)
        self.assertEqual(self.client.chat.completions.create.call_count, 21)
        self.assertTrue(result["smoke_complete"])
        self.assertFalse(result["authorizes_validation"])
        self.assertLessEqual(result["storage_requests_used"], 3640)
        self.assertEqual(self.openai.OpenAI.call_args.kwargs["max_retries"], 0)
        self.assertEqual(self.openai.OpenAI.call_args.kwargs["timeout"], 60)
        calls = self.client.chat.completions.create.call_args_list
        for call in calls:
            self.assertNotEqual(call.kwargs["messages"], self.one.pair)
            self.assertEqual(call.kwargs["seed"], self.one.config["seed"])
            self.assertEqual(call.kwargs["max_tokens"], 1)
            self.assertTrue(call.kwargs["logprobs"])
            self.assertEqual(call.kwargs["top_logprobs"], self.one.config["top_logprobs"])
        records, rows = continuation.partition(
            self.root, continuation.cell_key(continuation.PILOT_PROJECT, continuation.PILOT_LEVEL, "text"),
            "validation",
        )
        self.assertEqual([call.kwargs["messages"] for call in calls[1:]],
                         [record["messages"] for record in records[:20]])
        self.assertEqual(read_json(self.root / "base_control.json")["row_ids"],
                         [row["row_id"] for row in rows[:20]])
        self.assertEqual(self.store.storage.rows[self.one.fixture.opkey], before[self.one.fixture.opkey])
        for key, value in before.items():
            if key.startswith(("sufficiency-smoke-", "receipt:", "attempt:")):
                self.assertEqual(self.store.storage.rows[key], value)
        for key in ("total", "pilot_total", "training", "quarantine", "inference_recovery"):
            self.assertEqual(self.store.storage.rows[ROOT][0][key], before[ROOT][0][key])
        self.assertIsNone(self.store.storage.rows[ROOT][0]["pending"])
        self.assertTrue((self.root / "smoke.json").exists())
        self.assertEqual(read_json(self.root / "status/smoke.json")["status"], "failed")
        self.assertEqual(len(list((self.directory / "responses").glob("*.json"))), 21)

    def test_authentication_precedes_lease_and_model_token_never_refreshes(self):
        events = []
        credential = sys.modules["azure.identity"].AzureCliCredential
        token_call = credential.return_value.__enter__.return_value.get_token
        token_call.reset_mock()
        token_call.side_effect = lambda *args: (
            events.append("model-token") or NS(token="PRIVATE", expires_on=time.time() + 3600)
        )
        acquire = self.store.acquire
        def acquiring():
            events.append("lease")
            return acquire()
        with patch.object(self.store, "authenticate", side_effect=lambda: events.append("storage-tokens")), patch.object(
            self.store, "acquire", side_effect=acquiring
        ):
            self.execute()
        self.assertEqual(events, ["storage-tokens", "model-token", "lease"])
        token_call.assert_called_once()
        self.assertEqual(credential.call_args.kwargs["process_timeout"], 60)

    def test_token_expiry_stops_before_next_dispatch_without_refresh(self):
        now = time.time()
        clock = [now]
        token = NS(token="PRIVATE", expires_on=now + 3600)
        credential = sys.modules["azure.identity"].AzureCliCredential
        token_call = credential.return_value.__enter__.return_value.get_token
        token_call.reset_mock()
        token_call.return_value = token
        response = self.client.chat.completions.create.return_value
        def expire(**kwargs):
            clock[0] = token.expires_on - 100
            return response
        self.client.chat.completions.create.side_effect = expire
        with patch.object(continuation.time, "time", side_effect=lambda: clock[0]):
            with self.assertRaisesRegex(ControlError, "Model token expiring"):
                self.execute()
        self.client.chat.completions.create.assert_called_once()
        token_call.assert_called_once()
        self.assertEqual(self.operation("smoke-1")["status"], "succeeded")
        self.assertEqual(self.operation("base-control-0")["attempts"], 0)
        self.assertIsNone(self.store.storage.rows[ROOT][0]["pending"])
        self.assertFalse((self.root / "smoke.json").exists())

    def rejection(self):
        error = self.openai.APIStatusError("PRIVATE")
        error.status_code = 429
        error.response = NS(headers={"retry-after": "0"})
        return error

    def test_verified_429_uses_three_total_attempts_per_prediction_at_most(self):
        response = self.client.chat.completions.create.return_value
        self.client.chat.completions.create.side_effect = [
            item for _ in range(21) for item in (self.rejection(), self.rejection(), response)
        ]
        value = self.execute()
        self.assertEqual(value["model_requests"], 63)
        self.assertLessEqual(value["storage_requests_used"], 3640)
        self.assertTrue(all(self.operation(name)["attempts"] == 3 for name in continuation.OPERATIONS))

    def test_429_exhaustion_never_dispatches_attempt_four(self):
        self.client.chat.completions.create.side_effect = self.rejection()
        with self.assertRaisesRegex(ControlError, "retry allowance exhausted"):
            self.execute()
        self.assertEqual(self.client.chat.completions.create.call_count, 3)
        self.assertEqual(self.operation("smoke-1")["attempts"], 3)
        self.assertFalse((self.root / "smoke.json").exists())

    def test_http500_stops_after_one_call_preserving_pending_and_reason(self):
        error = self.openai.APIStatusError("PRIVATE")
        error.status_code = 500
        self.client.chat.completions.create.side_effect = error
        with self.assertRaises(Exception):
            self.execute()
        self.client.chat.completions.create.assert_called_once()
        self.assertEqual(self.store.storage.rows[ROOT][0]["pending"], [self.review["run"], "smoke-1"])
        self.assertFalse((self.root / "smoke.json").exists())
        failure = read_json(self.directory / "failure-diagnostic.json")
        self.assertEqual(failure["http_status"], 500)
        self.assertNotIn("PRIVATE", str(failure))

    def test_invalid_score_preserves_response_summary_without_fallback_or_replay(self):
        self.client.chat.completions.create.return_value.choices[0].logprobs.content[0].top_logprobs = []
        with self.assertRaises(ValueError):
            self.execute()
        self.client.chat.completions.create.assert_called_once()
        failure = read_json(self.directory / "failure-diagnostic.json")
        self.assertEqual(failure["reason"], "missing_class_logprobs")
        self.assertTrue((self.directory / "responses/smoke-1-1.json").exists())
        self.assertFalse((self.root / "smoke.json").exists())

    def test_connection_timeout_stops_without_retry(self):
        self.client.chat.completions.create.side_effect = self.openai.APIConnectionError("PRIVATE")
        with self.assertRaises(Exception):
            self.execute()
        self.client.chat.completions.create.assert_called_once()
        self.assertEqual(self.store.storage.rows[ROOT][0]["pending"], [self.review["run"], "smoke-1"])
        self.assertFalse((self.root / "smoke.json").exists())

    def test_response_write_failure_stops_before_scoring_without_retry(self):
        write = continuation.exclusive_json
        def failed(path, value):
            if path.parent.name == "responses":
                raise OSError("disk failure")
            write(path, value)
        with patch.object(continuation, "exclusive_json", side_effect=failed), patch("backend.positive_score") as score:
            with self.assertRaises(OSError):
                self.execute()
            score.assert_not_called()
        self.client.chat.completions.create.assert_called_once()
        self.assertEqual(read_json(self.directory / "failure-diagnostic.json")["reason"],
                         "diagnostic_persistence_failed")

    def test_changed_resolution_or_preexisting_progress_blocks_all_predictions(self):
        key = self.one.fixture.opkey
        value, etag = self.store.get(key)
        self.store.transaction([(key, {**value, "status": "prepared"}, etag)])
        with self.assertRaises(ControlError):
            self.execute()
        self.client.chat.completions.create.assert_not_called()

    def test_false_defaults_and_changed_scope_expiry_or_credit_prevent_authentication(self):
        draft = continuation.template(self.root, self.resolution_path)
        self.assertFalse(draft["execution_approved"])
        self.assertFalse(any(draft["checks"].values()))
        for changes in (
            {"new_predictions": 22}, {"retry_http_statuses": [429, 500]},
            {"max_new_model_requests": 64}, {"checks": draft["checks"]},
            {"expires_at": "2000-01-01T00:00:00Z"}, {"remaining_credit_usd": "20"},
        ):
            with self.subTest(changes=changes), self.assertRaises((ControlError, ValueError)):
                continuation.execute(self.root, {**self.review, **changes}, self.directory)
        self.store.authenticate.assert_not_called()
        self.openai.OpenAI.assert_not_called()

    def test_main_requires_new_consent_and_preserves_marker_after_failure(self):
        path = self.root.parent / "continuation-approved.json"
        write_json(path, self.review)
        args = ["continue", "--root", str(self.root), "--review", str(path)]
        with patch.object(continuation, "execute") as execute, redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                continuation.main(args)
            execute.assert_not_called()
            execute.side_effect = RuntimeError("uncertain failure")
            with self.assertRaises(RuntimeError):
                continuation.main([*args, "--execute-approved-continuation"])
            with self.assertRaises(FileExistsError):
                continuation.main([*args, "--execute-approved-continuation"])
            execute.assert_called_once()


if __name__ == "__main__":
    unittest.main()
