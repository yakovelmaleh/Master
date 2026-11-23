import copy
from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

TASK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TASK))
import inspect_failure as inspection
sys.path.insert(0, str(TASK.parent / "evaluate-openai-story-sufficiency/tests"))
import test_sufficiency as fixtures
from cloud_control import ControlError, ROOT
from protocol import digest, file_hash, read_json, study_id, write_json
from renew_storage import renew


class InspectionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.SufficiencyTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root, self.config = self.fixture.root, self.fixture.config
        self.store, _, self.storage = self.fixture.renewal_fixture()
        self.store.authenticate = Mock()
        self.binding = fixtures.BINDING
        renew(self.store, self.binding, self.storage, self.root)
        self.run_id = study_id(self.root)
        request = {"fixture_request": True}
        self.context = {
            "run": self.run_id, "operation": "smoke-0", "attempt": 1,
            "request_sha256": digest(request),
            "study_sha256": digest(read_json(self.root / "study.json")),
            "failure_sha256": digest("failure"), "implementation_sha256": digest("diagnostics"),
        }
        self.authorization = {
            "approval": self.fixture.approval(),
            "prepared_sha256": file_hash(self.root / "prepared.json"),
        }
        self.operation = {
            "kind": "inference", "run": self.run_id, "name": "smoke-0", "status": "dispatched",
            "attempts": 1, "request_sha256": digest(request), "request": request,
            "epoch": "old-worker", "reserved": ".1",
        }
        self.opkey = inspection.SufficiencyLedger._key(self.run_id, "smoke-0")
        self.attemptkey = inspection.SufficiencyLedger._key(self.run_id, "smoke-0:1", "attempt")
        self.receiptkey = inspection.SufficiencyLedger._key(self.run_id, "smoke-0:1", "receipt")
        state, etag = self.store.get(ROOT)
        state.update(pending=[self.run_id, "smoke-0"], total="6", pilot_total="1")
        self.store.transaction([
            (ROOT, state, etag),
            ("run:" + self.run_id, {
                "authorization": self.authorization, "approval": self.authorization["approval"],
                "scope": "pilot", "reserved": "1", "used": ".1",
            }, None),
            (self.opkey, self.operation, None),
            (self.attemptkey, {"status": "dispatched", "epoch": "old-worker",
                              "request_sha256": digest(request)}, None),
        ])
        self.reset_budget()

    def reset_budget(self):
        self.store.budget = inspection.InspectionBudget(100)

    def inspect(self):
        return inspection.inspect(self.root, self.store, self.binding, self.storage,
                                  self.context, self.config, self.authorization)

    def test_snapshot_without_receipt_retains_every_record_except_session_bookkeeping(self):
        before = copy.deepcopy(self.store.storage.rows)
        result = self.inspect()
        after = self.store.storage.rows
        self.assertEqual(set(before), set(after))
        for key in before:
            if key != ROOT:
                self.assertEqual(before[key], after[key])
        old, new = before[ROOT][0], after[ROOT][0]
        for key in old:
            if key not in ("epoch", "sessions", "io_reserved"):
                self.assertEqual(old[key], new[key], key)
        self.assertEqual(new["sessions"], old["sessions"] + 1)
        self.assertEqual(new["io_reserved"], old["io_reserved"] + 100)
        self.assertFalse(result["receipt_present"])
        self.assertFalse(result["authorizes_inference"])
        self.assertEqual(result["model_calls"], 0)
        self.assertEqual(result["next_review"], "unresolved_attempt")
        self.assertEqual(result["historical_outcome"], "UNKNOWN")
        self.assertLessEqual(result["inspection_requests_used"], 100)
        self.assertEqual(result["inspection_requests_used"], self.store.budget.used)
        self.assertFalse(any(result["review_template"]["checks"].values()))
        self.assertFalse(result["review_template"]["execution_approved"])
        self.assertEqual(result["review_template"]["expires_at"], "")

    def test_matching_receipt_is_reported_but_not_consumed(self):
        receipt = {"request_sha256": self.context["request_sha256"],
                   "result": {"PRIVATE": "provider payload"}, "actual": ".001"}
        self.store.transaction([(self.receiptkey, receipt, None)])
        self.reset_budget()
        before = copy.deepcopy(self.store.storage.rows[self.opkey])
        result = self.inspect()
        self.assertTrue(result["receipt_present"])
        self.assertEqual(result["next_review"], "receipt_validation")
        self.assertEqual(result["historical_outcome"], "UNKNOWN")
        self.assertEqual(self.store.storage.rows[self.opkey], before)
        self.assertEqual(self.store.storage.rows[self.receiptkey][0], receipt)
        self.assertNotIn("PRIVATE", str(result))

    def test_wrong_pending_or_receipt_or_attempt_stops_without_resolution(self):
        for kind in ("pending", "receipt", "attempt", "allocation"):
            with self.subTest(kind=kind):
                original = copy.deepcopy(self.store.storage.rows)
                if kind == "pending":
                    key, change = ROOT, {"pending": [self.run_id, "different"]}
                elif kind == "attempt":
                    key, change = self.attemptkey, {"epoch": "different"}
                elif kind == "allocation":
                    key, change = "run:" + self.run_id, {"scope": "full"}
                else:
                    key, change = self.receiptkey, {"request_sha256": "wrong"}
                value, etag = self.store.get(key)
                self.store.transaction([(key, {**(value or {}), **change}, etag)])
                self.reset_budget()
                with self.assertRaises(ControlError):
                    self.inspect()
                self.assertEqual(self.store.storage.rows[self.opkey], original[self.opkey])
                self.store.storage.rows = original
                self.reset_budget()

    def test_exhausted_capacity_expired_approval_and_wrong_budget_fail_closed(self):
        for kind in ("sessions", "io_reserved", "expiry", "budget"):
            with self.subTest(kind=kind):
                original = copy.deepcopy(self.store.storage.rows)
                review = copy.deepcopy(self.storage)
                if kind in ("sessions", "io_reserved"):
                    limit = "max_sessions" if kind == "sessions" else "max_requests"
                    self.store.storage.rows[ROOT][0][kind] = self.storage["storage"][limit]
                elif kind == "expiry":
                    self.storage["expires_at"] = "2000-01-01T00:00:00Z"
                else:
                    self.store.budget = inspection.RequestBudget(1000)
                before = copy.deepcopy(self.store.storage.rows)
                with self.assertRaises((ControlError, ValueError)):
                    self.inspect()
                self.assertEqual(self.store.storage.rows, before)
                self.store.storage.rows, self.storage = original, review
                self.reset_budget()
        self.store.budget.limit = 1000000
        self.assertEqual(self.store.budget.limit, 100)
        self.store.budget.charge(100)
        with self.assertRaises(ControlError):
            self.store.budget.charge()

    def test_lost_session_commit_retains_counters_and_pending(self):
        before = copy.deepcopy(self.store.storage.rows)
        def lost_reply():
            raise RuntimeError("lost commit response")
        self.store.storage.after_commit = lost_reply
        with self.assertRaises(RuntimeError):
            self.inspect()
        after = self.store.storage.rows
        self.assertEqual(after[ROOT][0]["sessions"], before[ROOT][0]["sessions"] + 1)
        self.assertEqual(after[ROOT][0]["io_reserved"], before[ROOT][0]["io_reserved"] + 100)
        self.assertEqual(after[ROOT][0]["pending"], before[ROOT][0]["pending"])
        self.assertEqual(after[self.opkey], before[self.opkey])

    def test_late_receipt_invalidates_snapshot_without_reconciliation(self):
        get = self.store.get
        reads = 0
        def changing(key):
            nonlocal reads
            if key == self.receiptkey:
                reads += 1
                if reads == 2:
                    self.store.transaction([(key, {"request_sha256": self.context["request_sha256"]}, None)])
            return get(key)
        with patch.object(self.store, "get", side_effect=changing):
            with self.assertRaisesRegex(ControlError, "Snapshot changed"):
                self.inspect()
        self.assertEqual(self.store.storage.rows[ROOT][0]["pending"], [self.run_id, "smoke-0"])

    def test_missing_renewal_and_lost_lease_stop_without_changing_operation(self):
        key = "sufficiency-storage-renewal:" + digest(self.storage)
        renewal = self.store.storage.rows.pop(key)
        with self.assertRaisesRegex(ControlError, "renewal receipt"):
            self.inspect()
        self.store.storage.rows[key] = renewal
        self.reset_budget()
        with patch.object(self.store, "renew", side_effect=RuntimeError("lease response lost")):
            with self.assertRaisesRegex(ControlError, "renewal unconfirmed"):
                self.inspect()
        self.assertEqual(self.store.storage.rows[self.opkey][0], self.operation)
        self.assertEqual(self.store.storage.rows[ROOT][0]["pending"], [self.run_id, "smoke-0"])

    def test_root_version_change_invalidates_snapshot(self):
        get = self.store.get
        root_reads = 0
        def changing(key):
            nonlocal root_reads
            if key == ROOT:
                root_reads += 1
                if root_reads == 3:
                    value, etag = get(key)
                    self.store.transaction([(key, value, etag)])
            return get(key)
        with patch.object(self.store, "get", side_effect=changing):
            with self.assertRaisesRegex(ControlError, "Authority changed"):
                self.inspect()
        self.assertEqual(self.store.storage.rows[self.opkey][0], self.operation)

    def test_cli_requires_consent_and_retains_marker_after_failure(self):
        args = ["--root", str(self.root), "--failure", str(self.root / "failure.json")]
        with patch.object(inspection, "InspectionStore") as azure, redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                inspection.main(args)
            azure.assert_not_called()
        with patch.object(inspection, "inputs", return_value=(
            self.config, self.authorization, self.binding, self.storage, self.context,
        )), patch.object(inspection, "InspectionStore", return_value=self.store) as azure, patch.object(
            inspection, "inspect", side_effect=RuntimeError("lost reply")
        ):
            with self.assertRaises(RuntimeError):
                inspection.main([*args, "--execute-approved-inspection"])
            with self.assertRaises(FileExistsError):
                inspection.main([*args, "--execute-approved-inspection"])
            azure.assert_called_once()
        self.assertTrue((self.root / "jobs/inspect-failure/inspection.started").is_file())
        self.assertFalse((self.root / "jobs/inspect-failure/inspection.json").exists())

    def test_cli_success_writes_private_report_and_refuses_repeat(self):
        args = ["--root", str(self.root), "--failure", str(self.root / "failure.json"),
                "--execute-approved-inspection"]
        with patch.object(inspection, "inputs", return_value=(
            self.config, self.authorization, self.binding, self.storage, self.context,
        )), patch.object(inspection, "InspectionStore", return_value=self.store) as azure, redirect_stdout(io.StringIO()):
            inspection.main(args)
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                inspection.main(args)
            azure.assert_called_once()
        report = read_json(self.root / "jobs/inspect-failure/inspection.json")
        self.assertFalse(report["receipt_present"])
        self.assertEqual(report["schema"], inspection.SCHEMA)
        auth = read_json(self.root / "jobs/inspect-failure/authentication.json")
        self.assertTrue(auth["authenticated"])
        self.assertEqual(auth["storage_requests_used"], 0)
        self.store.authenticate.assert_called_once()

    def test_auth_failure_saves_safe_reason_before_any_storage_session(self):
        args = ["--root", str(self.root), "--failure", str(self.root / "failure.json"),
                "--execute-approved-inspection", "--job-label", "auth-02"]
        old = self.root / "jobs/inspect-failure/inspection.started"
        write_json(old, {"failed": True})
        before = copy.deepcopy(self.store.storage.rows)
        self.store.authenticate.side_effect = RuntimeError("PRIVATE AUTH DETAILS")
        with patch.object(inspection, "inputs", return_value=(
            self.config, self.authorization, self.binding, self.storage, self.context,
        )), patch.object(inspection, "InspectionStore", return_value=self.store), patch.object(
            inspection, "inspect"
        ) as inspect:
            with self.assertRaises(RuntimeError):
                inspection.main(args)
            inspect.assert_not_called()
            with self.assertRaises(FileExistsError):
                inspection.main(args)
        auth = read_json(self.root / "jobs/inspect-failure-auth-02/authentication.json")
        self.assertFalse(auth["authenticated"])
        self.assertEqual(auth["reason"], "authentication_failed")
        self.assertNotIn("PRIVATE", str(auth))
        self.assertEqual(self.store.storage.rows, before)
        self.assertEqual(read_json(old), {"failed": True})
        self.store.authenticate.assert_called_once()


if __name__ == "__main__":
    unittest.main()
