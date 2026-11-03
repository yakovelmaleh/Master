from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

TASK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TASK))
sys.path.insert(0, str(TASK.parent / "train-openai-instability-within-project/tests"))

import numpy as np
from test_workflow import Fixture, FakeTokenizer, loader
from fake_control import BINDING, PLAN, FakeStore
from recovery import CHECKS, RECOVERY_SCHEMA, RecoveryLedger, UncertainHTTP500
from run_recovery import amended_report, remaining_batches
from cloud_control import ControlError, Ledger, ROOT, QUARANTINE_SCHEMA
from cost_control import approval_checks, money
from protocol import BASE_METHOD, BASE_SCHEMA, CELLS, digest, read_json, study_id, write_json
from prepare_data import partition
import run_experiment as runner


class RecoveryTests(Fixture):
    def approval(self, scope="full"):
        value = super().approval(scope)
        value.update(protocol_schema=BASE_SCHEMA, method=BASE_METHOD,
                     deployment_sku=self.config["deployment_sku"],
                     checks={key: True for key in approval_checks(self.config)})
        del value["rates"]["training_per_million"]
        return value

    def setUp(self):
        super().setUp()
        self.config = {**read_json(TASK.parent / "train-openai-instability-within-project/prompt_only.json"),
                       "bootstrap_samples": 100, "batch_rows": 2}
        write_json(self.root / "study.json", {"config": self.config, "fixture": True})
        self.backend.config = self.config
        self.prepared()
        self.authorize("pilot")
        with patch.object(runner, "Tokenizer", FakeTokenizer):
            runner.smoke(self.root, self.config, self.ledger, self.backend)
        for _ in range(4):
            runner.evaluate(self.root, self.config, self.ledger, self.backend, "validation")
        self.authorize("full")
        for _ in range(12):
            runner.evaluate(self.root, self.config, self.ledger, self.backend, "validation")
        runner.seal(self.root, self.ledger)
        self.run = study_id(self.root)
        self.name = "test-Jira-5-text-1"
        self.records, self.rows = partition(self.root, "Jira-5-text", "test")
        self.score(0, self.ledger)
        with patch.object(self.backend, "predict", side_effect=RuntimeError("HTTP500 fixture")):
            with self.assertRaises(RuntimeError):
                self.score(1, self.ledger)
        # Retain a synthetic prior training quarantine throughout the recovery.
        state, etag = self.ledger._root()
        state.update(schema=QUARANTINE_SCHEMA, training=["old-run", "training"],
                     quarantine={"operation": ["old-run", "training"], "outcome": "UNKNOWN"})
        self.ledger.store.transaction([(ROOT, state, etag)])
        self.before = deepcopy(self.ledger._root()[0])
        self.allocation_before = deepcopy(self.ledger.allocation(self.run))
        store = self.ledger.store
        self.session.__exit__(None, None, None)
        self.recovery = RecoveryLedger(FakeStore(store.storage), BINDING, PLAN, remaining_credit="100")
        self.recovery.allow_legacy = True
        session = self.recovery.session()
        session.__enter__()
        self.addCleanup(session.__exit__, None, None, None)
        self.review = self.recovery.plan_review(self.root)
        self.review.update(
            checks={key: True for key in CHECKS}, http_status=500,
            evidence_sha256=digest("private reviewed HTTP500 evidence"),
            expires_at="2098-01-01T00:00:00Z",
        )
        self.backend.guard = self.recovery.guard_remote
        sleep = patch("recovery.time.sleep")
        sleep.start()
        self.addCleanup(sleep.stop)

    def score(self, index, ledger=None):
        return runner.score_once(
            self.root, self.config, ledger or self.recovery, self.backend,
            self.approval()["base_deployment"], f"test-Jira-5-text-{index}",
            self.records[index]["messages"], self.rows[index]["input_tokens"],
            model=self.config["model"],
        )

    def activate(self):
        return self.recovery.activate(self.root, self.review)

    def test_activation_fences_old_clients_and_retains_all_money_and_pending(self):
        original_op = self.recovery.operation(self.run, self.name)
        self.activate()
        state = self.recovery._root()[0]
        self.assertEqual(state["schema"], RECOVERY_SCHEMA)
        for key in ("total", "pilot_total", "pending", "quarantine", "training", "storage"):
            self.assertEqual(state[key], self.before[key])
        self.assertEqual(self.recovery.allocation(self.run), self.allocation_before)
        self.assertEqual(self.recovery.operation(self.run, self.name), original_op)
        with self.assertRaisesRegex(ControlError, "mismatched cloud authority"):
            self.ledger._root()
        self.assertEqual(self.activate()["review_sha256"], digest(self.review))

    def test_review_mismatch_and_expiry_do_not_change_authority(self):
        before = deepcopy(self.recovery.store.storage.rows)
        for delta in (
            {"checks": {}}, {"http_status": 503}, {"attempt": 2},
            {"request_sha256": "wrong"}, {"seal_sha256": "wrong"},
            {"implementation_sha256": "wrong"}, {"expires_at": "2000-01-01T00:00:00Z"},
            {"expires_at": "2100-01-01T00:00:00Z"},
        ):
            with self.subTest(delta=delta), self.assertRaises((ValueError, ControlError)):
                self.recovery.activate(self.root, {**self.review, **delta})
            self.assertEqual(self.recovery.store.storage.rows, before)

    def test_lost_activation_response_is_idempotent(self):
        def lose_response():
            raise TimeoutError
        self.recovery.store.storage.after_commit = lose_response
        with self.assertRaises(TimeoutError):
            self.activate()
        rows = deepcopy(self.recovery.store.storage.rows)
        self.activate()
        self.assertEqual(self.recovery.store.storage.rows, rows)

    def test_retry_reuses_completed_rows_and_keeps_original_unknown_attempt(self):
        self.activate()
        before = self.backend.predict_calls
        self.score(0)
        result = self.score(1)
        self.assertEqual(self.backend.predict_calls, before + 1)
        self.assertEqual(result["attempts"], 2)
        self.score(1)
        self.assertEqual(self.backend.predict_calls, before + 1)
        original, _ = self.recovery.store.get(self.recovery._key(self.run, self.name + ":1", "attempt"))
        self.assertEqual(original["status"], "dispatched")
        self.assertEqual(self.recovery.allocation(self.run), self.allocation_before)
        self.assertEqual(self.recovery._root()[0]["total"], self.before["total"])
        self.assertIsNone(self.recovery._root()[0]["pending"])

    def test_three_total_attempts_exhaust_without_refund_or_fourth_call(self):
        self.activate()
        error = UncertainHTTP500({"http_status": 500})
        calls = Mock(side_effect=error)
        with patch.object(self.backend, "predict", calls):
            with self.assertRaisesRegex(ControlError, "No approved unused"):
                self.score(1)
            self.assertEqual(calls.call_count, 2)
            with self.assertRaises(ControlError):
                self.score(1)
            self.assertEqual(calls.call_count, 2)
        self.assertEqual(self.recovery.operation(self.run, self.name)["attempts"], 3)
        self.assertEqual(self.recovery._root()[0]["pending"], [self.run, self.name])
        self.assertEqual(self.recovery.allocation(self.run), self.allocation_before)

    def test_non500_failure_is_never_retried(self):
        self.activate()
        with patch.object(self.backend, "predict", side_effect=TimeoutError) as call:
            with self.assertRaises(TimeoutError):
                self.score(1)
            with self.assertRaises(ControlError):
                self.score(1)
            self.assertEqual(call.call_count, 1)
        self.assertEqual(self.recovery.operation(self.run, self.name)["attempts"], 2)

    def test_receipt_recovery_after_lost_finish_never_calls_provider_again(self):
        self.activate()
        with patch.object(self.recovery, "finish", side_effect=TimeoutError):
            with self.assertRaises(TimeoutError):
                self.score(1)
        before = self.backend.predict_calls
        result = self.score(1)
        self.assertEqual(result["attempts"], 2)
        self.assertEqual(self.backend.predict_calls, before)

    def test_lost_retry_transition_response_does_not_duplicate_dispatch(self):
        self.activate()
        def lose_response():
            raise TimeoutError
        self.recovery.store.storage.after_commit = lose_response
        before = self.backend.predict_calls
        with self.assertRaises(TimeoutError):
            self.score(1)
        self.assertEqual(self.backend.predict_calls, before)
        self.score(1)
        self.assertEqual(self.backend.predict_calls, before + 1)
        self.assertEqual(self.recovery.operation(self.run, self.name)["attempts"], 2)

    def test_late_old_receipt_cannot_be_attributed_to_new_attempt(self):
        self.activate()
        first, _ = self.recovery.store.get(self.recovery._key(self.run, self.name + ":1", "attempt"))
        self.recovery.retry_unknown(self.run, self.name)
        self.recovery.dispatch(self.run, self.name, 3)
        old = RecoveryLedger(self.recovery.store, BINDING, PLAN, remaining_credit="100")
        old.review = self.review
        old.captured = (self.run, self.name, 1, first["request_sha256"], first["epoch"])
        old.receipt(self.run, self.name, {"score": .1}, ".00001")
        receipt1, _ = self.recovery.store.get(self.recovery._key(self.run, self.name + ":1", "receipt"))
        receipt2, _ = self.recovery.store.get(self.recovery._key(self.run, self.name + ":2", "receipt"))
        self.assertIsNotNone(receipt1)
        self.assertIsNone(receipt2)
        with self.assertRaisesRegex(ControlError, "stale attempt"):
            old.finish(self.run, self.name, {"score": .1}, ".00001")

    def test_stale_epoch_cannot_release_pending_or_dispatch(self):
        self.activate()
        state, etag = self.recovery._root()
        state["epoch"] = "new-owner"
        self.recovery.store.transaction([(ROOT, state, etag)])
        before = self.backend.predict_calls
        with self.assertRaisesRegex(ControlError, "Stale"):
            self.score(1)
        self.assertEqual(self.backend.predict_calls, before)
        self.assertEqual(self.recovery._root()[0]["pending"], [self.run, self.name])

    def test_receipt_arriving_before_retry_prevents_replacement(self):
        self.activate()
        op = self.recovery.operation(self.run, self.name)
        attempt, _ = self.recovery.store.get(self.recovery._key(self.run, self.name + ":1", "attempt"))
        self.recovery.captured = (self.run, self.name, 1, op["request_sha256"], attempt["epoch"])
        self.recovery.receipt(self.run, self.name, {"score": .7, "attempts": 1}, ".000001")
        before = self.backend.predict_calls
        self.assertEqual(self.score(1)["attempts"], 1)
        self.assertEqual(self.backend.predict_calls, before)

    def test_expired_review_and_breach_stop_before_retry(self):
        self.activate()
        before = self.backend.predict_calls
        with patch("recovery.unexpired", side_effect=ControlError("expired")):
            with self.assertRaisesRegex(ControlError, "expired"):
                self.score(1)
        state, etag = self.recovery._root()
        state["breached"] = True
        self.recovery.store.transaction([(ROOT, state, etag)])
        with self.assertRaises((ControlError, ValueError)):
            self.score(1)
        self.assertEqual(self.backend.predict_calls, before)

    def test_new_row_500_retries_fit_a_reviewed_batch_envelope(self):
        self.activate()
        self.score(1)
        predict = self.backend.predict
        calls = 0

        def transient(deployment, messages):
            nonlocal calls
            calls += 1
            if calls < 3:
                self.backend.guard()
                raise UncertainHTTP500({"http_status": 500})
            return predict(deployment, messages)

        before = self.recovery.store.budget.used
        with patch.object(self.backend, "predict", side_effect=transient):
            self.assertEqual(self.score(2)["attempts"], 3)
        per_row = self.recovery.store.budget.used - before
        # Existing full-study reconstruction/metric envelope is 25,760 requests.
        self.assertLessEqual(per_row * 400 + 25760, 80000, per_row)
        self.assertEqual(calls, 3)

    def test_unknown_attempt_cost_is_included_in_atomic_breach_check(self):
        self.activate()
        self.recovery.retry_unknown(self.run, self.name)
        self.recovery.dispatch(self.run, self.name, 3)
        reserved = money(self.recovery.operation(self.run, self.name)["reserved"])
        known = reserved * money(".9")
        result = {"score": .5, "attempts": 2}
        self.recovery.receipt(self.run, self.name, result, known)
        with self.assertRaisesRegex(ControlError, "unknown-attempt bounds"):
            self.recovery.finish(self.run, self.name, result, known)
        op = self.recovery.operation(self.run, self.name)
        self.assertEqual(money(op["actual_usd"]), known)
        self.assertGreater(money(op["accounted_bound_usd"]), reserved)
        self.assertTrue(self.recovery._root()[0]["breached"])
        self.assertIsNone(self.recovery._root()[0]["pending"])

    def test_completed_workflow_preserves_seal_and_reports_policy_amendment(self):
        self.activate()
        seal_before = read_json(self.root / "sealed.json")
        before = self.backend.predict_calls
        self.assertEqual(remaining_batches(self.root, self.recovery, self.config), 16)
        with patch("data_contract.load_project", loader), patch(
            "data_contract.baseline_predictions", return_value=(np.full(4, .5), {"fixture": True})
        ):
            for _ in range(16):
                runner.evaluate(self.root, self.config, self.recovery, self.backend, "test")
        self.assertEqual(self.backend.predict_calls - before, 31)
        self.assertEqual(read_json(self.root / "sealed.json"), seal_before)
        path = self.root / "recovery/llm_report.json"
        result = amended_report(self.root, self.recovery, path)
        report = read_json(path)
        self.assertTrue(result["complete"])
        self.assertEqual(len(report["cells"]), len(CELLS))
        self.assertTrue(report["execution_recovery"]["execution_policy_amended"])
        self.assertEqual(len(report["execution_recovery"]["unknown_attempts"]), 1)
        self.assertFalse(report["execution_recovery"]["actual_cost_complete"])


if __name__ == "__main__":
    unittest.main()
