import copy
from contextlib import redirect_stderr
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

TASK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TASK))
sys.path.insert(0, str(TASK.parent / "recover-openai-sufficiency-smoke/tests"))
import resolution
import test_one_shot as diagnostics
from cloud_control import ControlError, ROOT
from cost_control import money
from ledger import SufficiencyLedger
from protocol import digest, read_json, write_json


class ResolutionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = diagnostics.OneShotTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.execute()
        self.root, self.store = self.fixture.root, self.fixture.store
        self.original = self.fixture.review
        self.diagnostic_directory = self.fixture.directory
        write_json(self.diagnostic_directory / "worker-status.json", {
            "status": "succeeded", "diagnostic_recorded": True, "scorable_response": True,
            "pending_retained": True, "completes_smoke": False,
        })
        self.original_path = self.root.parent / "diagnostic-approved.json"
        write_json(self.original_path, self.original)
        self.directory = self.root / "jobs/resolve-smoke"
        self.directory.mkdir()
        self.fixture.fixture.reset_budget()
        self.store.authenticate.reset_mock()
        self.fixture.client.reset_mock()
        self.review = self.approved()
        patcher = patch.object(resolution, "InspectionStore", return_value=self.store)
        patcher.start()
        self.addCleanup(patcher.stop)

    def approved(self):
        value = resolution.template(self.root, self.original_path)
        value.update(remaining_credit_usd="100", expires_at=self.original["expires_at"],
                     execution_approved=True, checks={key: True for key in resolution.CHECKS})
        return value

    def execute(self):
        return resolution.execute(self.root, self.review, self.directory)

    def key(self, kind):
        return SufficiencyLedger._key(self.original["run"], "smoke-0:2", kind)

    def test_accepts_exact_sample_without_model_call_or_financial_release(self):
        before = copy.deepcopy(self.store.storage.rows)
        diagnostic = read_json(self.diagnostic_directory / "diagnostic.json")
        result = self.execute()
        after = self.store.storage.rows
        operation = after[self.fixture.fixture.opkey][0]
        self.assertTrue(result["resolved"])
        self.assertFalse(result["completes_smoke"])
        self.assertFalse(result["authorizes_continuation"])
        self.assertEqual(result["model_calls"], 0)
        self.assertLessEqual(result["storage_requests_used"], 100)
        self.fixture.client.chat.completions.create.assert_not_called()
        self.assertIsNone(after[ROOT][0]["pending"])
        for field in ("total", "pilot_total", "training", "quarantine", "inference_recovery"):
            self.assertEqual(after[ROOT][0][field], before[ROOT][0][field])
        for key in ("run:" + self.original["run"], self.fixture.fixture.attemptkey,
                    self.key("sufficiency-smoke-grant"), self.key("sufficiency-smoke-diagnostic")):
            self.assertEqual(after[key], before[key])
        self.assertEqual(operation["reserved"], before[self.fixture.fixture.opkey][0]["reserved"])
        self.assertEqual(operation["result"]["score"], diagnostic["valid_response"]["score"])
        self.assertEqual(operation["result"]["usage"], diagnostic["valid_response"]["usage"])
        self.assertEqual(operation["result"]["request_id_sha256"],
                         diagnostic["valid_response"]["request_id_sha256"])
        self.assertEqual(operation["result"]["unknown_attempts"], [1])
        self.assertNotIn("request_id", operation["result"])
        self.assertFalse(operation["actual_complete"])
        self.assertEqual(money(operation["unknown_attempt_bound_usd"]), money(operation["reserved"]) / 3)
        self.assertFalse((self.root / "smoke.json").exists())
        self.assertFalse((self.root / "base_control.json").exists())

    def test_normal_score_path_reuses_sample_and_fences_cannot_be_reconciled(self):
        self.execute()
        self.fixture.fixture.reset_budget()
        ledger = SufficiencyLedger(
            self.store, self.fixture.fixture.binding, self.fixture.storage["storage"],
            remaining_credit=self.fixture.storage["remaining_credit_usd"],
            access_expires=self.fixture.storage["expires_at"],
        )
        ledger.bind(self.root, self.fixture.config)
        backend = Mock()
        with ledger.session(requests=lambda: 100):
            result = diagnostics.inspections.fixtures.runner.core.score_once(
                self.root, self.fixture.config, ledger, backend,
                self.fixture.authorization["approval"]["base_deployment"],
                "smoke-0", self.fixture.pair, 100,
            )
            self.assertEqual(result["attempts"], 2)
            backend.predict.assert_not_called()
            with self.assertRaisesRegex(ControlError, "matching receipt"):
                ledger.recover_receipt(self.original["run"], "smoke-0")
        self.assertIsNone(self.store.storage.rows[ROOT][0]["pending"])

    def test_second_execution_stops_without_reapplying(self):
        self.execute()
        before = copy.deepcopy(self.store.storage.rows)
        self.fixture.fixture.reset_budget()
        with self.assertRaisesRegex(ControlError, "Authority changed"):
            self.execute()
        self.assertEqual(self.store.storage.rows, before)

    def test_late_receipt_racing_transaction_blocks_resolution_atomically(self):
        transaction = self.store.transaction
        def racing(changes):
            if any(key == self.key("sufficiency-smoke-resolution") for key, _, _ in changes):
                transaction([(self.fixture.fixture.receiptkey,
                              {"request_sha256": self.original["request_sha256"]}, None)])
            transaction(changes)
        with patch.object(self.store, "transaction", side_effect=racing):
            with self.assertRaises(ControlError):
                self.execute()
        self.assertNotIn(self.key("sufficiency-smoke-resolution"), self.store.storage.rows)
        self.assertEqual(self.store.storage.rows[self.fixture.fixture.opkey][0]["status"], "dispatched")
        self.assertEqual(self.store.storage.rows[ROOT][0]["pending"], [self.original["run"], "smoke-0"])

    def test_receipt_before_session_or_conflicting_diagnostic_blocks_resolution(self):
        before = copy.deepcopy(self.store.storage.rows)
        for kind in ("receipt", "diagnostic"):
            with self.subTest(kind=kind):
                if kind == "receipt":
                    self.store.transaction([(self.fixture.fixture.receiptkey,
                                             {"request_sha256": self.original["request_sha256"]}, None)])
                else:
                    key = self.key("sufficiency-smoke-diagnostic")
                    value, etag = self.store.get(key)
                    self.store.transaction([(key, {**value, "changed": True}, etag)])
                with self.assertRaises(ControlError):
                    self.execute()
                self.assertEqual(self.store.storage.rows[self.fixture.fixture.opkey],
                                 before[self.fixture.fixture.opkey])
                self.store.storage.rows = copy.deepcopy(before)
                self.fixture.fixture.reset_budget()

    def test_lost_commit_response_is_not_replayed(self):
        transaction = self.store.transaction
        def lose(changes):
            transaction(changes)
            if any(key == self.key("sufficiency-smoke-resolution") for key, _, _ in changes):
                raise RuntimeError("lost committed response")
        with patch.object(self.store, "transaction", side_effect=lose):
            with self.assertRaises(RuntimeError):
                self.execute()
        self.assertFalse((self.directory / "resolution.json").exists())
        self.assertIsNone(self.store.storage.rows[ROOT][0]["pending"])
        self.assertIn(self.key("sufficiency-smoke-resolution"), self.store.storage.rows)
        self.fixture.fixture.reset_budget()
        with self.assertRaises(ControlError):
            self.execute()
        self.fixture.client.chat.completions.create.assert_not_called()

    def test_local_result_write_failure_does_not_undo_or_repeat_committed_resolution(self):
        with patch.object(resolution.one_shot, "exclusive_json", side_effect=OSError("disk failure")):
            with self.assertRaises(OSError):
                self.execute()
        self.assertIsNone(self.store.storage.rows[ROOT][0]["pending"])
        self.assertIn(self.key("sufficiency-smoke-resolution"), self.store.storage.rows)
        self.fixture.fixture.reset_budget()
        with self.assertRaises(ControlError):
            self.execute()
        self.fixture.client.chat.completions.create.assert_not_called()

    def test_stale_owner_cannot_resolve(self):
        resolve = resolution.resolve
        def takeover(ledger, *args):
            state, etag = self.store.get(ROOT)
            state["epoch"] = "another-worker"
            self.store.transaction([(ROOT, state, etag)])
            return resolve(ledger, *args)
        with patch.object(resolution, "resolve", side_effect=takeover):
            with self.assertRaises(ControlError):
                self.execute()
        self.assertNotIn(self.key("sufficiency-smoke-resolution"), self.store.storage.rows)
        self.assertEqual(self.store.storage.rows[ROOT][0]["pending"], [self.original["run"], "smoke-0"])

    def replace_usage(self, tokens):
        path = self.diagnostic_directory / "diagnostic.json"
        value = read_json(path)
        value["valid_response"]["usage"]["input_tokens"] = tokens
        value["response_summary"]["usage"]["input_tokens"] = tokens
        write_json(path, value)
        cloud = {key: item for key, item in value.items() if key != "storage_requests_used"}
        write_json(self.diagnostic_directory / "local-diagnostic.json", cloud)
        write_json(self.diagnostic_directory / "response-summary.json",
                   {"captured": value["captured"], "summary": value["response_summary"]})
        key = self.key("sufficiency-smoke-diagnostic")
        _, etag = self.store.get(key)
        self.store.transaction([(key, cloud, etag)])
        self.fixture.fixture.reset_budget()

    def test_known_plus_unknown_overrun_latches_breach_without_clearing_pending(self):
        self.replace_usage(1000000000)
        self.review = self.approved()
        before = copy.deepcopy(self.store.storage.rows)
        with self.assertRaisesRegex(ControlError, "exceeded the reservation"):
            self.execute()
        after = self.store.storage.rows
        self.assertTrue(after[ROOT][0]["breached"])
        self.assertEqual(after[ROOT][0]["pending"], before[ROOT][0]["pending"])
        self.assertEqual(after[self.fixture.fixture.opkey][0]["status"], "dispatched")
        self.assertEqual(after[self.fixture.fixture.opkey][0]["reserved"],
                         before[self.fixture.fixture.opkey][0]["reserved"])
        self.assertEqual(after["run:" + self.original["run"]], before["run:" + self.original["run"]])
        value = read_json(self.directory / "resolution.json")
        self.assertFalse(value["resolved"])
        self.assertTrue(value["pending_retained"])
        self.assertGreater(money(value["accounting"]["unreserved_excess_usd"]), 0)

    def test_false_defaults_and_mutated_expired_or_unfunded_reviews_stop_before_auth(self):
        draft = resolution.template(self.root, self.original_path)
        self.assertFalse(draft["execution_approved"])
        self.assertFalse(any(draft["checks"].values()))
        for changes in (
            {"checks": draft["checks"]}, {"expires_at": "2000-01-01T00:00:00Z"},
            {"model_requests": 1}, {"remaining_credit_usd": "20"},
            {"implementation_sha256": "wrong"}, {"diagnostic_sha256": "wrong"},
        ):
            with self.subTest(changes=changes), self.assertRaises((ControlError, ValueError)):
                resolution.execute(self.root, {**self.review, **changes}, self.directory)
        self.store.authenticate.assert_not_called()

    def test_changed_or_invalid_usage_cannot_be_reapproved(self):
        self.replace_usage(-1)
        with self.assertRaisesRegex(ControlError, "usage evidence"):
            resolution.template(self.root, self.original_path)
        self.store.authenticate.assert_not_called()

    def test_main_requires_separate_consent_and_retains_start_marker_after_failure(self):
        path = self.root.parent / "resolution-approved.json"
        write_json(path, self.review)
        args = ["resolve", "--root", str(self.root), "--review", str(path)]
        with patch.object(resolution, "execute") as execute, redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                resolution.main(args)
            execute.assert_not_called()
            execute.side_effect = RuntimeError("uncertain failure")
            with self.assertRaises(RuntimeError):
                resolution.main([*args, "--execute-approved-resolution"])
            with self.assertRaises(FileExistsError):
                resolution.main([*args, "--execute-approved-resolution"])
            execute.assert_called_once()


if __name__ == "__main__":
    unittest.main()
