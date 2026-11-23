import copy
from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
import sys
import time
from types import SimpleNamespace as NS
import unittest
from unittest.mock import MagicMock, Mock, patch

TASK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TASK))
import one_shot as shot
import test_inspection as inspections
from test_diagnostics import fixture as response_fixture
from diagnostics import object_tree
from cloud_control import ControlError, ROOT
from protocol import BASE_METHOD, PILOT_PROJECT, PILOT_LEVEL, cell_key, digest, file_hash, read_json, write_json
from sufficiency import messages


class OneShotTests(unittest.TestCase):
    def setUp(self):
        self.fixture = inspections.InspectionTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root, self.store, self.config = self.fixture.root, self.fixture.store, self.fixture.config
        self.authorization, self.storage = self.fixture.authorization, self.fixture.storage
        self.examples = self.fixture.fixture.examples
        tokenizer = inspections.fixtures.FakeTokenizer()
        self.pair, _ = messages(
            PILOT_PROJECT, "Add a settings page.", None, tokenizer, self.config,
            self.examples[cell_key(PILOT_PROJECT, PILOT_LEVEL, "text")]["examples"],
        )
        approval = self.authorization["approval"]
        request = {"resource_id": approval["resource_id"], "model": self.config["model"],
                   "deployment": approval["base_deployment"], "method": BASE_METHOD,
                   "messages_sha256": digest(self.pair), "config_sha256": digest(self.config)}
        self.fixture.context["request_sha256"] = digest(request)
        operation, etag = self.store.get(self.fixture.opkey)
        operation.update(request=request, request_sha256=digest(request))
        attempt, attempt_etag = self.store.get(self.fixture.attemptkey)
        attempt["request_sha256"] = digest(request)
        self.store.transaction([(self.fixture.opkey, operation, etag),
                                (self.fixture.attemptkey, attempt, attempt_etag)])
        self.failure = self.root / "failures/smoke-fixture.json"
        write_json(self.root / "authorization.json", self.authorization)
        write_json(self.failure, {
            "schema": "openai-failure-evidence-v1", "stage": "smoke", "run": self.fixture.run_id,
            "study_sha256": self.fixture.context["study_sha256"],
            "dispatch": {"run": self.fixture.run_id, "operation": "smoke-0", "kind": "inference",
                         "attempt": 1, "request_sha256": digest(request)},
        })
        write_json(self.root / "status/smoke.json", {
            "status": "failed", "failure_evidence": {
                "path": str(self.failure.relative_to(self.root)), "sha256": file_hash(self.failure),
            },
        })
        self.fixture.context = shot.audit(self.root, self.failure)[-1]
        self.fixture.reset_budget()
        self.report = self.fixture.inspect()
        self.fixture.reset_budget()
        self.inspection = self.root / "jobs/inspect-failure-auth-02/inspection.json"
        write_json(self.inspection, self.report)
        write_json(self.inspection.parent / "worker-status.json", {"status": "succeeded", "inspected": True})
        self.data = (self.config, self.authorization, self.fixture.binding, self.storage,
                     self.examples, self.pair, self.fixture.context, self.report)
        for mock in (
            patch.object(shot, "binding_at", return_value=self.fixture.binding),
            patch.object(shot, "access_at", return_value=self.storage),
        ):
            mock.start()
            self.addCleanup(mock.stop)
        self.review = shot.template(self.root, self.failure, self.inspection)
        self.review.update(expires_at="2098-01-01T00:00:00Z", remaining_credit_usd="100",
                           execution_approved=True, checks={key: True for key in shot.CHECKS})
        self.directory = self.root / "jobs/diagnose-smoke"
        self.directory.mkdir(parents=True)
        response = response_fixture()
        response["model"] = self.config["model"]
        self.client = Mock()
        self.client.chat.completions.create.return_value = object_tree(response)
        credential = MagicMock()
        credential.__enter__.return_value.get_token.return_value = NS(token="PRIVATE", expires_on=time.time() + 3600)
        self.openai = NS(OpenAI=Mock(return_value=self.client),
                         APIConnectionError=type("APIConnectionError", (Exception,), {}),
                         APIStatusError=type("APIStatusError", (Exception,), {}))
        for mock in (
            patch.object(shot, "InspectionStore", return_value=self.store),
            patch.dict(sys.modules, {"azure.identity": NS(AzureCliCredential=Mock(return_value=credential)),
                                     "openai": self.openai}),
        ):
            mock.start()
            self.addCleanup(mock.stop)

    def execute(self):
        return shot.execute(self.root, self.review, self.directory)

    def test_exactly_one_request_retains_pending_money_attempt1_and_no_normal_receipt(self):
        before = copy.deepcopy(self.store.storage.rows)
        result = self.execute()
        after = self.store.storage.rows
        self.client.chat.completions.create.assert_called_once_with(
            model=self.authorization["approval"]["base_deployment"], messages=self.pair,
            temperature=1, seed=self.config["seed"], max_tokens=1, logprobs=True,
            top_logprobs=self.config["top_logprobs"],
        )
        self.assertEqual(self.openai.OpenAI.call_args.kwargs["max_retries"], 0)
        self.assertEqual(self.openai.OpenAI.call_args.kwargs["timeout"], 60)
        self.assertTrue(result["scorable_response"])
        self.assertEqual(result["model_requests"], 1)
        self.assertFalse(result["completes_smoke"])
        self.assertFalse(result["authorizes_continuation"])
        self.assertTrue(result["pending_retained"])
        self.assertLessEqual(result["storage_requests_used"], 100)
        for field in ("total", "pilot_total", "pending", "training", "quarantine", "inference_recovery"):
            self.assertEqual(after[ROOT][0][field], before[ROOT][0][field])
        self.assertEqual(after[self.fixture.attemptkey], before[self.fixture.attemptkey])
        self.assertEqual(after["run:" + self.fixture.run_id], before["run:" + self.fixture.run_id])
        self.assertEqual(after[self.fixture.opkey][0]["attempts"], 2)
        self.assertEqual(after[self.fixture.opkey][0]["status"], "dispatched")
        for key in after:
            self.assertFalse(key.startswith("receipt:"))
        self.assertFalse((self.root / "smoke.json").exists())
        self.assertFalse((self.root / "base_control.json").exists())
        self.assertEqual(read_json(self.directory / "response-summary.json")["captured"]["attempt"], 2)

    def test_second_execution_and_changed_snapshot_never_dispatch(self):
        self.execute()
        self.fixture.reset_budget()
        with self.assertRaisesRegex(ControlError, "Authority changed"):
            self.execute()
        self.client.chat.completions.create.assert_called_once()

    def test_lost_grant_commit_response_retains_attempt2_but_never_calls_model(self):
        transaction = self.store.transaction
        def lose(changes):
            transaction(changes)
            if any(key.startswith("sufficiency-smoke-grant:") for key, _, _ in changes):
                raise RuntimeError("lost commit response")
        with patch.object(self.store, "transaction", side_effect=lose):
            with self.assertRaises(RuntimeError):
                self.execute()
        self.client.chat.completions.create.assert_not_called()
        self.assertEqual(self.store.storage.rows[self.fixture.opkey][0]["attempts"], 2)
        self.assertEqual(self.store.storage.rows[ROOT][0]["pending"], [self.fixture.run_id, "smoke-0"])

    def test_sdk_429_does_not_retry_or_complete(self):
        error = self.openai.APIStatusError("PRIVATE")
        error.status_code = 429
        error.response = NS(headers={"retry-after": "0"})
        self.client.chat.completions.create.side_effect = error
        result = self.execute()
        self.assertFalse(result["scorable_response"])
        self.assertEqual(result["http_status"], 429)
        self.client.chat.completions.create.assert_called_once()
        self.assertNotIn("PRIVATE", str(read_json(self.directory / "diagnostic.json")))

    def test_timeout_remains_unknown_without_retry(self):
        self.client.chat.completions.create.side_effect = TimeoutError("PRIVATE")
        result = self.execute()
        self.assertFalse(result["scorable_response"])
        self.assertEqual(result["original_outcome"], "UNKNOWN")
        self.client.chat.completions.create.assert_called_once()

    def test_sdk_500_keeps_unknown_outcome_without_retry(self):
        error = self.openai.APIStatusError("PRIVATE")
        error.status_code = 500
        self.client.chat.completions.create.side_effect = error
        result = self.execute()
        self.assertEqual(result["http_status"], 500)
        self.assertFalse(result["scorable_response"])
        self.assertTrue(result["pending_retained"])
        self.client.chat.completions.create.assert_called_once()

    def test_changed_approval_cannot_create_review_from_old_inspection(self):
        self.storage["remaining_credit_usd"] = "99"
        with self.assertRaisesRegex(ControlError, "changed after inspection"):
            shot.template(self.root, self.failure, self.inspection)
        self.openai.OpenAI.assert_not_called()
        self.store.authenticate.assert_not_called()

    def test_late_receipt_after_grant_blocks_transport_without_clearing_pending(self):
        grant = shot.grant
        def late(ledger, review, report):
            captured = grant(ledger, review, report)
            self.store.transaction([(self.fixture.receiptkey,
                                     {"request_sha256": review["request_sha256"]}, None)])
            return captured
        with patch.object(shot, "grant", side_effect=late):
            result = self.execute()
        self.assertEqual(result["model_requests"], 0)
        self.client.chat.completions.create.assert_not_called()
        self.assertTrue(result["pending_retained"])

    def test_response_persistence_failure_prevents_scoring_without_another_request(self):
        import backend
        save = shot.exclusive_json
        def failed_write(path, value):
            if path.name == "response-summary.json":
                raise OSError("PRIVATE")
            save(path, value)
        with patch.object(shot, "exclusive_json", side_effect=failed_write), patch.object(
            backend, "positive_score"
        ) as score:
            result = self.execute()
            score.assert_not_called()
        self.assertEqual(result["reason"], "diagnostic_persistence_failed")
        self.assertFalse(result["scorable_response"])
        self.client.chat.completions.create.assert_called_once()

    def test_invalid_response_records_reason_without_score_fallback(self):
        response = self.client.chat.completions.create.return_value
        response.choices[0].logprobs.content[0].top_logprobs = []
        result = self.execute()
        self.assertFalse(result["scorable_response"])
        self.assertEqual(result["reason"], "missing_class_logprobs")
        value = read_json(self.directory / "diagnostic.json")
        self.assertIsNone(value["valid_response"])
        self.assertEqual(value["captured"]["attempt"], 2)
        self.client.chat.completions.create.assert_called_once()

    def test_lost_diagnostic_commit_does_not_create_completion_or_replay(self):
        transaction = self.store.transaction
        def lose(changes):
            transaction(changes)
            if any(key.startswith("sufficiency-smoke-diagnostic:") for key, _, _ in changes):
                raise RuntimeError("lost diagnostic commit")
        with patch.object(self.store, "transaction", side_effect=lose):
            with self.assertRaises(RuntimeError):
                self.execute()
        self.assertTrue((self.directory / "local-diagnostic.json").exists())
        self.assertFalse((self.directory / "diagnostic.json").exists())
        self.client.chat.completions.create.assert_called_once()
        self.assertEqual(self.store.storage.rows[ROOT][0]["pending"], [self.fixture.run_id, "smoke-0"])

    def test_stale_worker_cannot_persist_diagnostic(self):
        save = shot.save_diagnostic
        def stale(ledger, captured, value):
            state, etag = self.store.get(ROOT)
            state["epoch"] = "other-worker"
            self.store.transaction([(ROOT, state, etag)])
            save(ledger, captured, value)
        with patch.object(shot, "save_diagnostic", side_effect=stale):
            with self.assertRaisesRegex(ControlError, "stale"):
                self.execute()
        self.client.chat.completions.create.assert_called_once()
        self.assertFalse(any(key.startswith("sufficiency-smoke-diagnostic:") for key in self.store.storage.rows))

    def test_competing_root_update_prevents_atomic_grant(self):
        transaction = self.store.transaction
        def conflict(changes):
            if any(key.startswith("sufficiency-smoke-grant:") for key, _, _ in changes):
                state, etag = self.store.get(ROOT)
                transaction([(ROOT, state, etag)])
            transaction(changes)
        with patch.object(self.store, "transaction", side_effect=conflict):
            with self.assertRaises(ControlError):
                self.execute()
        self.client.chat.completions.create.assert_not_called()
        self.assertEqual(self.store.storage.rows[self.fixture.opkey][0]["attempts"], 1)
        self.assertFalse(any(key.startswith("sufficiency-smoke-grant:") for key in self.store.storage.rows))

    def test_expired_review_and_exhausted_credit_prevent_grant(self):
        before = copy.deepcopy(self.store.storage.rows)
        for change in ({"expires_at": "2000-01-01T00:00:00Z"}, {"remaining_credit_usd": "20"}):
            with self.subTest(change=change):
                self.review.update(change)
                self.fixture.reset_budget()
                with self.assertRaises((ControlError, ValueError)):
                    self.execute()
                self.client.chat.completions.create.assert_not_called()
                self.assertEqual(self.store.storage.rows[self.fixture.opkey], before[self.fixture.opkey])
                self.store.storage.rows = copy.deepcopy(before)
                self.review.update(expires_at="2098-01-01T00:00:00Z", remaining_credit_usd="100")

    def test_main_requires_separate_consent_and_preserves_start_marker(self):
        path = self.root.parent / "review.json"
        shot.exclusive_json(path, self.review)
        args = ["diagnose", "--root", str(self.root), "--review", str(path)]
        with patch.object(shot, "execute") as execute, redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                shot.main(args)
            execute.assert_not_called()
            execute.side_effect = RuntimeError("uncertain failure")
            with self.assertRaises(RuntimeError):
                shot.main([*args, "--execute-approved-diagnostic"])
            with self.assertRaises(FileExistsError):
                shot.main([*args, "--execute-approved-diagnostic"])
            execute.assert_called_once()


class ReviewTests(unittest.TestCase):
    def test_false_default_template_and_review_binding(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary).resolve()
            root = directory / "root"
            root.mkdir()
            failure, inspection = directory / "failure.json", directory / "inspection.json"
            for path in (failure, inspection, directory / "worker-status.json"):
                shot.exclusive_json(path, {})
            context = {"run": digest("run"), "operation": "smoke-0", "attempt": 1,
                       "request_sha256": digest("request"), "study_sha256": digest("study")}
            config = {"total_limit_usd": 100, "pilot_limit_usd": 16, "credit_reserve_usd": 20}
            expiry = "2099-01-01T00:00:00Z"
            data = (config, {"approval": {"expires_at": expiry}}, {},
                    {"expires_at": expiry, "storage": {"retention_until": expiry}},
                    {}, [], context, {"operation_reserved_usd": ".002154"})
            with patch.object(shot, "local_context", return_value=data):
                draft = shot.template(root, failure, inspection)
                self.assertFalse(draft["execution_approved"])
                self.assertFalse(any(draft["checks"].values()))
                with self.assertRaises(ControlError):
                    shot.validate_review(root, draft)
                approved = {**draft, "execution_approved": True, "expires_at": "2098-01-01T00:00:00Z",
                            "remaining_credit_usd": "100", "checks": {key: True for key in shot.CHECKS}}
                self.assertEqual(shot.validate_review(root, approved), data)
                for change in (
                    {"target_attempt": 3}, {"max_new_model_requests": 2},
                    {"diagnostic_implementation_sha256": "wrong"}, {"inspection_sha256": "wrong"},
                    {"expires_at": "2100-01-01T00:00:00Z"},
                    {"checks": {**approved["checks"], shot.CHECKS[0]: False}},
                ):
                    with self.subTest(change=change), self.assertRaises(ControlError):
                        shot.validate_review(root, {**approved, **change})


if __name__ == "__main__":
    unittest.main()
