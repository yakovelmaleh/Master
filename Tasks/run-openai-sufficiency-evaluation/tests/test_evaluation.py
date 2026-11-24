import copy
from contextlib import redirect_stderr
import io
from pathlib import Path
import sys
import time
from types import SimpleNamespace as NS
import unittest
from unittest.mock import MagicMock, Mock, patch

TASK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TASK))
sys.path.insert(0, str(TASK.parent / "evaluate-openai-story-sufficiency/tests"))
import evaluation
import test_sufficiency as fixtures
from cloud_control import ControlError, ROOT, RequestBudget
from cost_control import estimate, money
from ledger import SufficiencyLedger
from protocol import read_json, write_json


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.SufficiencyTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root, self.config = self.fixture.root, self.fixture.config
        self.store, _, self.storage = self.fixture.renewal_fixture()
        fixtures.renew(self.store, fixtures.BINDING, self.storage, self.root)
        ledger = SufficiencyLedger(self.store, fixtures.BINDING, self.storage["storage"],
                                  remaining_credit="100", access_expires=self.storage["expires_at"])
        ledger.bind(self.root, self.config)
        backend = fixtures.FakeBackend(self.config)
        backend.guard = ledger.guard_remote
        with ledger.session(requests=lambda: 1000):
            fixtures.runner.core.preflight(self.root, self.config, self.fixture.approval(), ledger, backend)
            fixtures.runner.smoke(self.root, self.config, ledger, backend, fixtures.FakeTokenizer())
        self.store.authenticate = Mock()
        self.store.credential = Mock()
        self.store.credential.get_token.return_value = NS(token="PRIVATE")
        self.client, self.http = Mock(), Mock()
        response = fixtures.response()
        response.model = self.config["model"]
        self.client.chat.completions.create.return_value = response
        self.openai = NS(OpenAI=Mock(return_value=self.client),
                         APIConnectionError=type("APIConnectionError", (Exception,), {}),
                         APIStatusError=type("APIStatusError", (Exception,), {}))
        self.credential = MagicMock()
        self.credential.__enter__.return_value.get_token.return_value = NS(
            token="PRIVATE", expires_on=time.time() + 3600,
        )
        self.identity = NS(AzureCliCredential=Mock(return_value=self.credential))
        def metadata(method, url, **kwargs):
            self.assertEqual(method, "GET")
            value = (
                {"properties": {"model": {"name": self.config["model"][:-11],
                                         "version": self.config["model"][-10:]},
                                "provisioningState": "Succeeded"},
                 "sku": {"name": self.config["deployment_sku"]}}
                if "/deployments/" in url else
                {"properties": {"endpoint": fixtures.BINDING["endpoint"]}, "location": "fixture"}
            )
            return NS(is_success=True, status_code=200, content=b"{}", json=lambda: value)
        self.http.request.side_effect = metadata
        for patcher in (
            patch.object(evaluation, "binding_at", return_value=fixtures.BINDING),
            patch.object(evaluation, "access_at", return_value=self.storage),
            patch.object(evaluation, "InspectionStore", return_value=self.store),
            patch.dict(sys.modules, {"azure.identity": self.identity, "openai": self.openai,
                                     "httpx": NS(Client=Mock(return_value=self.http))}),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def approved(self, stage, label, approval=None):
        review = evaluation.template(self.root, stage, label, approval)
        review.update(remaining_credit_usd="100", expires_at="2098-01-01T00:00:00Z",
                      execution_approved=True, checks={key: True for key in evaluation.CHECKS})
        return review

    def execute(self, review, suffix=""):
        directory = self.root / "jobs" / (f"eval-{review['stage']}-{review['job_label']}" + suffix)
        directory.mkdir(parents=True)
        self.store.budget = RequestBudget(review["storage_request_limit"])
        return evaluation.execute(self.root, review, directory)

    def job(self, stage, label, approval=None):
        return self.execute(self.approved(stage, label, approval))

    def full_preflight(self):
        self.job("validate", "pilot-1")
        self.job("validate", "pilot-2")
        path = self.root.parent / "full-model.json"
        write_json(path, self.fixture.approval("full"))
        return self.job("preflight", "full", path)

    def test_pilot_job_is_one_cell_batch_with_identical_requests_and_no_expansion(self):
        before = copy.deepcopy(self.store.storage.rows)
        result = self.job("validate", "pilot-1")
        self.assertEqual(result["scope"], "pilot")
        self.assertEqual(result["result"]["batch_rows"], 4)
        self.assertEqual(result["model_requests"], 4)
        self.assertFalse(result["authorizes_next_job"])
        key = result["result"]["cell"]
        self.assertIn(key, {fixtures.cell_key(*cell) for cell in fixtures.PILOT})
        records, _ = fixtures.partition(self.root, key, "validation")
        self.assertEqual([call.kwargs["messages"] for call in self.client.chat.completions.create.call_args_list],
                         [record["messages"] for record in records])
        for call in self.client.chat.completions.create.call_args_list:
            self.assertEqual(call.kwargs["max_tokens"], 1)
            self.assertEqual(call.kwargs["seed"], self.config["seed"])
            self.assertEqual(call.kwargs["top_logprobs"], self.config["top_logprobs"])
        self.assertEqual(self.openai.OpenAI.call_args.kwargs["max_retries"], 0)
        self.assertEqual(self.store.storage.rows[ROOT][0]["total"], before[ROOT][0]["total"])
        self.assertEqual(self.store.storage.rows[ROOT][0]["quarantine"], before[ROOT][0]["quarantine"])
        self.assertLessEqual(result["storage_requests_used"], self.approved("validate", "next")["storage_request_limit"])

    def test_full_workflow_preserves_pilot_expansion_seal_and_final_test_gates(self):
        self.full_preflight()
        self.client.models.list.assert_called_once()
        self.assertEqual(self.http.request.call_count, 2)
        self.client.chat.completions.create.reset_mock()
        with self.assertRaisesRegex(ValueError, "selection seal"):
            self.job("test", "unsealed")
        self.client.chat.completions.create.assert_not_called()
        for i in range(len(fixtures.CELLS) - len(fixtures.PILOT)):
            self.job("validate", "full-" + str(i))
        self.openai.OpenAI.reset_mock()
        self.assertTrue(self.job("seal", "seal-1")["result"]["sealed"])
        self.openai.OpenAI.assert_not_called()
        with self.assertRaises(ValueError):
            self.job("validate", "after-seal")
        with patch("data_contract.load_project", side_effect=fixtures.loader), patch(
            "data_contract.baseline_predictions",
            return_value=(fixtures.np.asarray([.1, .9, .1, .9]), {"fixture": True}),
        ):
            for i in range(len(fixtures.CELLS)):
                self.job("test", "test-" + str(i))
        self.openai.OpenAI.reset_mock()
        report = self.job("report", "report-1")
        self.assertTrue(report["result"]["complete"])
        self.assertEqual(report["model_requests"], 0)
        self.openai.OpenAI.assert_not_called()
        self.assertEqual(len(read_json(self.root / "llm_report.json")["cells"]), len(fixtures.CELLS))

    def test_pilot_cannot_seal_or_test_and_full_preflight_requires_completed_pilot(self):
        for stage in ("seal", "test"):
            with self.subTest(stage=stage), self.assertRaises(ControlError):
                self.approved(stage, "forbidden")
        path = self.root.parent / "full-model.json"
        write_json(path, self.fixture.approval("full"))
        before = copy.deepcopy(self.store.storage.rows["run:" + fixtures.study_id(self.root)])
        with self.assertRaises(FileNotFoundError):
            self.job("preflight", "premature", path)
        self.assertEqual(self.store.storage.rows["run:" + fixtures.study_id(self.root)], before)
        self.client.models.list.assert_not_called()
        self.client.chat.completions.create.assert_not_called()

    def test_expansion_respects_current_job_credit_not_only_older_approval_balance(self):
        self.job("validate", "pilot-1")
        self.job("validate", "pilot-2")
        full = self.fixture.approval("full")
        path = self.root.parent / "full-model.json"
        write_json(path, full)
        review = self.approved("preflight", "limited-credit", path)
        state = self.store.storage.rows[ROOT][0]
        allocation_key = "run:" + fixtures.study_id(self.root)
        before = copy.deepcopy(self.store.storage.rows[allocation_key])
        current = money(state["total"]) + money(state["storage"]["reserve_usd"]) + 20
        future = money(state["total"]) - money(before[0]["reserved"]) + money(
            estimate(read_json(self.root / "prepared.json"), self.config, full)["full"]
        ) + 20
        self.assertGreater(future, current)
        review["remaining_credit_usd"] = str((current + future) / 2)
        with self.assertRaisesRegex(ControlError, "Credit cannot cover"):
            self.execute(review)
        self.assertEqual(self.store.storage.rows[allocation_key], before)

    def test_authentication_is_before_lease_and_model_token_is_acquired_once(self):
        events = []
        token_call = self.credential.__enter__.return_value.get_token
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
            self.job("validate", "auth")
        self.assertEqual(events, ["storage-tokens", "model-token", "lease"])
        token_call.assert_called_once()
        self.assertEqual(self.identity.AzureCliCredential.call_args.kwargs["process_timeout"], 60)

    def test_job_label_is_consumed_even_if_local_path_or_review_changes(self):
        review = self.approved("validate", "once")
        self.execute(review)
        self.client.chat.completions.create.reset_mock()
        changed = {**review, "remaining_credit_usd": "99"}
        with self.assertRaisesRegex(ControlError, "already consumed"):
            self.execute(changed, "-copied")
        self.client.chat.completions.create.assert_not_called()

    def test_expiring_model_token_stops_before_durable_dispatch_without_refresh(self):
        token = self.credential.__enter__.return_value.get_token.return_value
        dispatch = evaluation.EvaluationLedger.dispatch
        def expiring(ledger, *args):
            token.expires_on = time.time() + 100
            return dispatch(ledger, *args)
        with patch.object(evaluation.EvaluationLedger, "dispatch", expiring), self.assertRaisesRegex(
            ControlError, "no refresh"
        ):
            self.job("validate", "expired-token")
        self.client.chat.completions.create.assert_not_called()
        self.credential.__enter__.return_value.get_token.assert_called_once()
        self.assertIsNone(self.store.storage.rows[ROOT][0]["pending"])

    def test_lost_grant_commit_response_prevents_model_dispatch(self):
        transaction = self.store.transaction
        def lose(changes):
            transaction(changes)
            if any(key.startswith("sufficiency-evaluation-job:") for key, _, _ in changes):
                raise RuntimeError("lost commit response")
        with patch.object(self.store, "transaction", side_effect=lose), self.assertRaises(RuntimeError):
            self.job("validate", "lost")
        self.client.chat.completions.create.assert_not_called()
        self.assertTrue(any(key.startswith("sufficiency-evaluation-job:") for key in self.store.storage.rows))

    def test_lost_finish_response_stops_and_later_review_reuses_committed_score(self):
        transaction = self.store.transaction
        def lose(changes):
            transaction(changes)
            if any(value.get("status") == "succeeded" for _, value, _ in changes):
                raise RuntimeError("lost finish response")
        with patch.object(self.store, "transaction", side_effect=lose), self.assertRaises(RuntimeError):
            self.job("validate", "lost-finish")
        self.client.chat.completions.create.assert_called_once()
        self.assertIsNone(self.store.storage.rows[ROOT][0]["pending"])
        self.client.chat.completions.create.reset_mock()
        self.assertEqual(self.job("validate", "reviewed-next")["model_requests"], 3)
        self.assertEqual(self.client.chat.completions.create.call_count, 3)

    def test_scoring_failure_saves_summary_but_never_retries_or_fills_missing_class(self):
        response = self.client.chat.completions.create.return_value
        response.choices[0].logprobs.content[0].top_logprobs.clear()
        with self.assertRaises(ValueError):
            self.job("validate", "bad-score")
        self.client.chat.completions.create.assert_called_once()
        directory = self.root / "jobs/eval-validate-bad-score"
        self.assertEqual(len(list((directory / "responses").glob("*.json"))), 1)
        self.assertEqual(read_json(directory / "failure-diagnostic.json")["phase"], "scoring")
        self.assertIsNotNone(self.store.storage.rows[ROOT][0]["pending"])

    def test_verified_429_cannot_exceed_three_total_attempts(self):
        rejection = self.openai.APIStatusError("PRIVATE")
        rejection.status_code = 429
        rejection.response = NS(headers={"retry-after": "0"})
        self.client.chat.completions.create.side_effect = rejection
        with self.assertRaises(ControlError):
            self.job("validate", "exhausted-429")
        self.assertEqual(self.client.chat.completions.create.call_count, 3)

    def test_verified_429_retries_but_http500_does_not(self):
        response = self.client.chat.completions.create.return_value
        rejection = self.openai.APIStatusError("PRIVATE")
        rejection.status_code = 429
        rejection.response = NS(headers={"retry-after": "0"})
        self.client.chat.completions.create.side_effect = [rejection, response, response, response, response]
        self.assertEqual(self.job("validate", "retry-429")["model_requests"], 5)
        self.client.chat.completions.create.reset_mock()
        failure = self.openai.APIStatusError("PRIVATE")
        failure.status_code = 500
        self.client.chat.completions.create.side_effect = failure
        with self.assertRaises(Exception):
            self.job("validate", "stop-500")
        self.client.chat.completions.create.assert_called_once()
        self.assertIsNotNone(self.store.storage.rows[ROOT][0]["pending"])
        report = read_json(self.root / "jobs/eval-validate-stop-500/failure-diagnostic.json")
        self.assertEqual(report["http_status"], 500)
        self.assertNotIn("PRIVATE", str(report))

    def test_out_of_split_operation_is_rejected_before_provider_request(self):
        def invalid(root, config, ledger, backend, split):
            ledger.begin(fixtures.study_id(root), "test-Jira-20-text-0", 0, "inference", {})
        with patch.object(evaluation.runner, "evaluate", side_effect=invalid), self.assertRaises(ControlError):
            self.job("validate", "wrong-split")
        self.client.chat.completions.create.assert_not_called()

    def test_false_defaults_changed_limits_expiry_and_queued_stage_fail_closed(self):
        draft = evaluation.template(self.root, "validate", "review")
        self.assertFalse(draft["execution_approved"])
        self.assertFalse(any(draft["checks"].values()))
        review = self.approved("validate", "review")
        for changes in ({"max_model_requests": 1201}, {"retry_http_statuses": [429, 500]},
                        {"expires_at": "2000-01-01T00:00:00Z"}, {"remaining_credit_usd": "20"}):
            with self.subTest(changes=changes), self.assertRaises((ControlError, ValueError)):
                evaluation.validate_review(self.root, {**review, **changes})
        path = self.root.parent / "review.json"
        write_json(path, review)
        with self.assertRaises(ControlError):
            evaluation.queued_review(self.root, path, "test", "review")
        with patch.object(evaluation, "diagnostic_implementation_hash", return_value="changed"), self.assertRaises(
            ControlError
        ):
            evaluation.validate_review(self.root, review)
        self.store.authenticate.assert_not_called()

    def test_cli_separate_consent_and_start_marker_prevent_reentry(self):
        path = self.root.parent / "review.json"
        write_json(path, self.approved("validate", "cli"))
        args = ["execute", "--root", str(self.root), "--review", str(path)]
        with patch.object(evaluation, "execute") as execute, redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                evaluation.main(args)
            execute.assert_not_called()
            execute.side_effect = RuntimeError("uncertain failure")
            with self.assertRaises(RuntimeError):
                evaluation.main([*args, "--execute-approved-evaluation"])
            with self.assertRaises(FileExistsError):
                evaluation.main([*args, "--execute-approved-evaluation"])
            execute.assert_called_once()


if __name__ == "__main__":
    unittest.main()
