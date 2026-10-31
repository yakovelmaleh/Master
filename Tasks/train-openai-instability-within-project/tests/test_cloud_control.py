from copy import deepcopy
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import MagicMock, Mock, patch

from test_workflow import Fixture, TASK
import run_experiment as runner
import control_admin
from cloud_control import (
    AzureStore, Conflict, ControlError, Ledger, RequestBudget, RetryableRejection, ROOT,
    QUARANTINE_SCHEMA, SCHEMA, binding_at, encoded, storage_plan,
)
from control_admin import audit, bootstrap, contend_probe, extend_storage, hold_probe, probe
from fake_control import BINDING, PLAN, FakeStore
from protocol import BASE_METHOD, BASE_SCHEMA, digest, read_json, study_id, write_json


class QuarantineTests(Fixture):
    def pending_training(self):
        self.prepared()
        self.authorize()
        run = study_id(self.root)
        self.ledger.begin(run, "train-unknown", ".01", "training", {"file": "fixture-file"})
        self.ledger.dispatch(run, "train-unknown", 1)
        state = self.ledger._root()[0]
        operation = self.ledger.operation(run, "train-unknown")
        return {
            "schema": "training-quarantine-review-v1", "authority_sha256": digest(BINDING),
            "run": run, "operation": "train-unknown", "attempt": 1,
            "request_sha256": operation["request_sha256"],
            "state_sha256": digest(self.ledger.quarantine_state(state)),
            "allocation_sha256": digest(self.ledger.allocation(run)),
            "operation_sha256": digest(operation),
            "evidence_sha256": digest("private fixture review"), "expires_at": "2099-01-01T00:00:00Z",
            "checks": {key: True for key in ("old_workers_stopped", "private_evidence_reviewed",
                                            "full_reservation_risk_accepted", "base_only_continuation_approved")},
        }

    def base_approval(self):
        from cost_control import approval_checks

        config = read_json(TASK / "prompt_only.json")
        approval = {**self.approval(), "protocol_schema": BASE_SCHEMA, "method": BASE_METHOD,
                    "deployment_sku": config["deployment_sku"],
                    "checks": {key: True for key in approval_checks(config)}}
        return config, approval

    def test_quarantine_plan_defaults_prohibit_action_and_preserve_pending(self):
        self.pending_training()
        before = deepcopy(self.ledger.store.storage.rows)
        template = control_admin.quarantine_template(self.ledger)
        self.assertFalse(any(template["checks"].values()))
        self.assertEqual(template["observed_costs"]["training_outcome"], "UNKNOWN")
        self.assertEqual(template["observed_costs"]["old_run_reserved_usd"],
                         self.ledger.allocation(template["run"])["reserved"])
        self.assertEqual(self.ledger.store.storage.rows, before)
        with self.assertRaises((ValueError, ControlError)):
            self.ledger.quarantine_training(template)
        self.assertEqual(self.ledger.store.storage.rows, before)

    def test_explicit_quarantine_preserves_every_reservation_and_original_dispatch(self):
        review = self.pending_training()
        before = deepcopy(self.ledger.store.storage.rows)
        with patch.object(self.ledger.store, "transaction", wraps=self.ledger.store.transaction) as transaction:
            result = self.ledger.quarantine_training(review)
        self.assertEqual(transaction.call_count, 1)
        after = self.ledger.store.storage.rows
        for key in before:
            if key != ROOT:
                self.assertEqual(after[key], before[key])
        old, new = before[ROOT][0], after[ROOT][0]
        for key in old:
            if key not in ("schema", "pending"):
                self.assertEqual(new[key], old[key], key)
        self.assertIsNone(new["pending"])
        self.assertEqual(new["schema"], QUARANTINE_SCHEMA)
        self.assertNotEqual(new["schema"], SCHEMA)  # Legacy clients cannot accept the new root.
        self.assertEqual(result["outcome"], "UNKNOWN")
        self.assertEqual(self.ledger.quarantine_training(review), result)
        with self.assertRaisesRegex(ControlError, "immutable"):
            self.ledger.quarantine_training({**review, "evidence_sha256": digest("other")})
        with self.assertRaisesRegex(ControlError, "UNKNOWN"):
            self.ledger.finish(review["run"], review["operation"], {"status": "succeeded"}, terminal=True)
        self.assertEqual(self.ledger._root()[0]["training"], [review["run"], review["operation"]])

    def test_mismatched_review_expiry_and_stale_coordinator_cannot_quarantine(self):
        review = self.pending_training()
        before = deepcopy(self.ledger.store.storage.rows)
        for delta in (
            {"expires_at": "2000-01-01T00:00:00Z"}, {"authority_sha256": "wrong"},
            {"attempt": 2}, {"request_sha256": "wrong"}, {"state_sha256": "wrong"},
            {"allocation_sha256": "wrong"}, {"operation_sha256": "wrong"},
            {"checks": {}}, {"evidence_sha256": ""},
        ):
            with self.subTest(delta=delta), self.assertRaises(ControlError):
                self.ledger.quarantine_training({**review, **delta})
            self.assertEqual(self.ledger.store.storage.rows, before)
        state, etag = self.ledger._root()
        state["epoch"] = "replacement"
        self.ledger.store.transaction([(ROOT, state, etag)])
        with self.assertRaisesRegex(ControlError, "Stale"):
            self.ledger.quarantine_training(review)
        self.assertEqual(self.ledger._root()[0]["pending"], [review["run"], review["operation"]])

    def test_quarantine_allows_only_separate_base_inference_with_additive_costs(self):
        review = self.pending_training()
        state = self.ledger._root()[0]
        allocation = self.ledger.allocation(review["run"])
        config, approval = self.base_approval()
        with self.assertRaisesRegex(ControlError, "Unconfirmed"):
            self.ledger.authorize("base-run", approval, {"pilot": ".10"}, config)
        self.ledger.quarantine_training(review)
        for run in (review["run"], "new-sft"):
            with self.assertRaisesRegex(ControlError, "Quarantine"):
                self.ledger.authorize(run, self.approval(), {"pilot": ".10"}, self.config)
        with self.assertRaisesRegex(ControlError, "old allocation"):
            self.ledger.authorize(review["run"], approval, {"pilot": ".10"}, config)
        self.ledger.authorize("base-run", approval, {"pilot": ".10"}, config)
        self.assertEqual(self.ledger.allocation(review["run"]), allocation)
        from cost_control import money
        self.assertEqual(money(self.ledger._root()[0]["total"]),
                         money(state["total"]) + money(".10") - money(PLAN["reserve_usd"]))
        for run in (review["run"], "base-run"):
            for kind in ("upload", "training", "deploy", "cancel", "delete"):
                with self.subTest(run=run, kind=kind), self.assertRaises(ControlError):
                    self.ledger.begin(run, "blocked-" + kind, 0, kind, {}, recovery=True)
        request = {"model": approval["model"], "resource_id": approval["resource_id"],
                   "deployment": approval["base_deployment"], "method": BASE_METHOD}
        with self.assertRaisesRegex(ControlError, "differs"):
            self.ledger.begin("base-run", "bad-model", ".01", "inference", {**request, "model": "other"})
        self.ledger.perform("base-run", "one", ".01", "inference", request, lambda: {"score": .5})
        self.assertEqual(self.ledger._root()[0]["training"], [review["run"], review["operation"]])
        with self.assertRaisesRegex(ControlError, "pilot reservations"):
            self.ledger.authorize("too-much", approval, {"pilot": "9"}, config)
        self.assertIsNone(self.ledger.allocation("too-much"))
        with self.assertRaisesRegex(ControlError, "Quarantined"):
            self.ledger.dispatch(review["run"], review["operation"], 2)

    def test_unknown_quarantine_commit_is_recovered_idempotently_without_refund(self):
        review = self.pending_training()
        def lose_response():
            raise TimeoutError
        self.ledger.store.storage.after_commit = lose_response
        with self.assertRaises(TimeoutError):
            self.ledger.quarantine_training(review)
        state = self.ledger._root()[0]
        result = self.ledger.quarantine_training(review)
        self.assertEqual(state, self.ledger._root()[0])
        self.assertEqual(result["outcome"], "UNKNOWN")

    def test_existing_completion_receipt_requires_recovery_not_quarantine(self):
        review = self.pending_training()
        self.ledger.receipt(review["run"], review["operation"], {"id": "known-job"})
        with self.assertRaisesRegex(ControlError, "exact unresolved"):
            self.ledger.quarantine_training(review)
        self.assertIsNone(self.ledger._root()[0].get("quarantine"))
        self.assertEqual(self.ledger.recover_receipt(review["run"], review["operation"]), {"id": "known-job"})

    def test_reviewed_pilot_storage_extension_does_not_clear_quarantine_or_money(self):
        review = self.pending_training()
        self.ledger.quarantine_training(review)
        # Admin extension acquires its own lease, so release this fixture's coordinator.
        self.session.__exit__(None, None, None)
        state = self.ledger._root()[0]
        approval = {
            "scope": "pilot", "storage_extension_approved": True,
            "prompt_only_extension_approved": True, "storage": {**PLAN, "max_sessions": 101},
            "previous_storage_sha256": digest(PLAN), "run": review["run"],
            "study_sha256": self.approval()["study_sha256"], "remaining_credit_usd": "100",
        }
        with self.assertRaisesRegex(ControlError, "Pilot extension"):
            extend_storage(self.ledger.store, BINDING, {**approval, "prompt_only_extension_approved": False})
        result = extend_storage(self.ledger.store, BINDING, approval)
        after = self.ledger.store.get(ROOT)[0]
        for field in ("quarantine", "pending", "training", "total", "pilot_total"):
            self.assertEqual(after[field], state[field])
        self.assertTrue(result["storage_extended"])


class AccountVerificationTests(unittest.TestCase):
    def setUp(self):
        self.account = {
            "id": BINDING["storage_resource_id"], "kind": "StorageV2",
            "sku": {"name": "Standard_ZRS"}, "location": "israelcentral",
            "properties": {
                "accessTier": "Hot", "allowBlobPublicAccess": False,
                "allowSharedKeyAccess": False, "supportsHttpsTrafficOnly": True,
                "isHnsEnabled": False,
                "encryption": {
                    "keySource": "Microsoft.Storage",
                    "services": {
                        "blob": {"enabled": True, "keyType": "Account"},
                        "file": {"enabled": True, "keyType": "Account"},
                    },
                },
                "primaryEndpoints": {
                    "table": "https://fixture.table.core.windows.net/",
                    "blob": "https://fixture.blob.core.windows.net/",
                },
            },
        }
        self.store = object.__new__(AzureStore)
        self.store.binding = BINDING
        self.store.credential = Mock()
        self.store.credential.get_token.return_value = NS(token="offline-test-token")
        httpx = MagicMock()
        httpx.Client.return_value.__enter__.return_value.get.return_value = Mock(
            status_code=200, json=Mock(return_value=self.account)
        )
        patcher = patch.dict(sys.modules, {"httpx": httpx})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_arm_omitted_table_encryption_uses_service_default(self):
        self.assertEqual(self.store.verify_account(), {
            "storage_account_verified": True, "storage_location": "israelcentral",
        })

    def test_explicit_service_scoped_table_encryption_is_accepted(self):
        self.account["properties"]["encryption"]["services"]["table"] = {
            "keyType": "Service", "enabled": True,
        }
        self.assertTrue(self.store.verify_account()["storage_account_verified"])

    def test_explicit_invalid_table_encryption_is_not_treated_as_default(self):
        for table in (None, {}, [], {"keyType": "Account"}, {"keyType": "Unknown"},
                      {"keyType": "Service", "enabled": False},
                      {"keyType": "Service", "enabled": None}):
            with self.subTest(table=table):
                self.account["properties"]["encryption"]["services"]["table"] = table
                with self.assertRaises(ControlError):
                    self.store.verify_account()

    def test_service_default_does_not_bypass_account_policy(self):
        for field in ("allowBlobPublicAccess", "allowSharedKeyAccess"):
            with self.subTest(field=field), patch.dict(self.account["properties"], {field: True}):
                with self.assertRaises(ControlError):
                    self.store.verify_account()
        with patch.dict(self.account["properties"]["encryption"], {"keySource": "Microsoft.Keyvault"}):
            with self.assertRaises(ControlError):
                self.store.verify_account()


class CloudControlTests(Fixture):
    def test_slow_startup_renews_before_work_without_extending_session_runtime(self):
        store = FakeStore()
        clock = [100]
        store.storage.clock = lambda: clock[0]
        ledger = Ledger(store, BINDING, PLAN, remaining_credit="100", clock=lambda: clock[0])
        acquire = store.acquire

        def slow_acquire():
            lease = acquire()
            clock[0] += 44
            return lease

        with patch.object(store, "acquire", side_effect=slow_acquire), patch.object(
            store, "renew", wraps=store.renew
        ) as renew, patch("cloud_control.threading.Thread"):
            with ledger.session():
                clock[0] += 20
                ledger.check()
                renew.assert_called_once_with(ledger.lease)
                self.assertEqual(ledger.session_deadline, 100 + PLAN["session_seconds"])
        self.assertIsNone(store.storage.lease)

    def test_startup_expiring_after_reservation_never_renews_or_enters_work(self):
        store = FakeStore()
        clock = [100]
        store.storage.clock = lambda: clock[0]
        ledger = Ledger(store, BINDING, PLAN, remaining_credit="100", clock=lambda: clock[0])

        def slow_commit():
            clock[0] += 51

        store.storage.after_commit = slow_commit
        with patch.object(store, "renew") as renew, patch("cloud_control.threading.Thread") as thread:
            with self.assertRaisesRegex(ControlError, "lease"):
                with ledger.session():
                    self.fail("Expired startup entered work")
            renew.assert_not_called()
            thread.assert_not_called()
        self.assertTrue(ledger.lost)
        self.assertIsNone(store.storage.lease)
        self.assertEqual(store.get(ROOT)[0]["io_reserved"], 100 + PLAN["session_requests"])

    def test_unconfirmed_startup_renewal_preserves_reservation_and_releases_lease(self):
        for late_response in (False, True):
            with self.subTest(late_response=late_response):
                store = FakeStore()
                clock = [100]
                store.storage.clock = lambda: clock[0]
                ledger = Ledger(store, BINDING, PLAN, remaining_credit="100", clock=lambda: clock[0])
                renew = store.renew

                def unconfirmed(lease):
                    if late_response:
                        renew(lease)
                        clock[0] += 51
                    else:
                        raise TimeoutError

                with patch.object(store, "renew", side_effect=unconfirmed), patch(
                    "cloud_control.threading.Thread"
                ) as thread:
                    with self.assertRaisesRegex(ControlError, "renewal|lease"):
                        with ledger.session():
                            self.fail("Unconfirmed startup entered work")
                    thread.assert_not_called()
                self.assertTrue(ledger.lost)
                self.assertIsNone(store.storage.lease)
                state = store.get(ROOT)[0]
                self.assertEqual(state["io_reserved"], 100 + PLAN["session_requests"])
                self.assertEqual(state["sessions"], 1)

    def test_second_worker_is_excluded_and_stale_epoch_cannot_write(self):
        second = Ledger(FakeStore(self.ledger.store.storage), BINDING, PLAN, remaining_credit="100")
        with self.assertRaisesRegex(Conflict, "Lease"):
            with second.session():
                self.fail("Two coordinators acquired the same lease")
        state, etag = self.ledger.store.get(ROOT)
        state["epoch"] = "replacement-owner"
        self.ledger.store.transaction([(ROOT, state, etag)])
        with self.assertRaisesRegex(ControlError, "Stale"):
            self.ledger.record("run", "selection", {})

    def test_expired_lease_is_sticky_and_never_renews_or_dispatches(self):
        self.prepared()
        self.authorize()
        self.ledger.deadline = self.ledger.clock() - 1
        with patch.object(self.ledger.store, "renew") as renew:
            with self.assertRaisesRegex(ControlError, "lease"):
                self.ledger.renew()
            renew.assert_not_called()
        self.assertTrue(self.ledger.lost)
        with self.assertRaises(ControlError):
            self.ledger.record(study_id(self.root), "smoke", {})

    def test_renewal_timeout_fences_future_calls(self):
        self.prepared()
        self.authorize()
        call = Mock(return_value={"ok": True})
        with patch.object(self.ledger.store, "renew", side_effect=TimeoutError):
            with self.assertRaisesRegex(ControlError, "renewal"):
                self.ledger.perform(study_id(self.root), "one", ".1", "inference", {}, call)
        call.assert_not_called()
        self.assertTrue(self.ledger.lost)
        self.assertEqual(self.ledger.operation(study_id(self.root), "one")["status"], "dispatched")

    def test_lost_dispatch_response_does_not_call_provider_or_repeat(self):
        self.prepared()
        self.authorize()
        run = study_id(self.root)
        self.ledger.begin(run, "one", ".1", "inference", {})

        def lose_response():
            raise TimeoutError("fixture response lost after commit")

        self.ledger.store.storage.after_commit = lose_response
        call = Mock(return_value={"ok": True})
        with self.assertRaises(TimeoutError):
            self.ledger.perform(run, "one", ".1", "inference", {}, call)
        self.assertEqual(self.ledger.operation(run, "one")["status"], "dispatched")
        with self.assertRaisesRegex(ControlError, "Unconfirmed"):
            self.ledger.perform(run, "one", ".1", "inference", {}, call)
        with self.assertRaisesRegex(ControlError, "Unconfirmed"):
            self.ledger.perform(run, "different-row", ".1", "inference", {}, call)
        call.assert_not_called()

    def test_lost_begin_response_can_resume_without_double_reservation(self):
        self.prepared()
        self.authorize()
        run = study_id(self.root)
        before = self.ledger.allocation(run)["used"]

        def lose_response():
            raise TimeoutError

        self.ledger.store.storage.after_commit = lose_response
        call = Mock(return_value={"score": .5})
        with self.assertRaises(TimeoutError):
            self.ledger.perform(run, "one", ".1", "inference", {}, call)
        self.assertEqual(self.ledger.operation(run, "one")["status"], "prepared")
        result = self.ledger.perform(run, "one", ".1", "inference", {}, call)
        self.assertEqual(result["attempts"], 1)
        self.assertEqual(call.call_count, 1)
        from cost_control import money
        self.assertEqual(money(self.ledger.allocation(run)["used"]), money(before) + money(".1"))

    def test_receipt_recovers_completion_without_repeating_provider(self):
        self.prepared()
        self.authorize()
        run = study_id(self.root)
        call = Mock(return_value={"score": .5})
        with patch.object(self.ledger, "finish", side_effect=TimeoutError):
            with self.assertRaises(TimeoutError):
                self.ledger.perform(run, "one", ".1", "inference", {}, call)
        runner.reconcile(self.root, self.config, self.ledger, self.backend)
        self.assertEqual(self.ledger.perform(run, "one", ".1", "inference", {}, call)["score"], .5)
        self.assertEqual(call.call_count, 1)

    def test_late_receipt_survives_takeover_but_stale_finish_is_fenced(self):
        self.prepared()
        self.authorize()
        run = study_id(self.root)

        def completed_after_takeover():
            state, etag = self.ledger.store.get(ROOT)
            state["epoch"] = "replacement-owner"
            self.ledger.store.transaction([(ROOT, state, etag)])
            return {"score": .5}

        with self.assertRaisesRegex(ControlError, "Stale"):
            self.ledger.perform(run, "one", ".1", "inference", {}, completed_after_takeover)
        self.assertEqual(self.ledger._root()[0]["pending"], [run, "one"])
        self.session.__exit__(None, None, None)
        replacement = Ledger(FakeStore(self.ledger.store.storage), BINDING, PLAN, remaining_credit="100")
        with replacement.session():
            self.assertEqual(replacement.recover_receipt(run, "one")["score"], .5)
            self.assertIsNone(replacement._root()[0]["pending"])

    def test_ambiguous_prediction_cannot_be_reconciled_from_absence(self):
        self.prepared()
        self.authorize()
        call = Mock(side_effect=TimeoutError)
        with self.assertRaises(TimeoutError):
            self.ledger.perform(study_id(self.root), "one", ".1", "inference", {}, call)
        with self.assertRaisesRegex(ControlError, "never replay"):
            runner.reconcile(self.root, self.config, self.ledger, self.backend)
        self.assertEqual(call.call_count, 1)

    def test_safe_throttle_retry_has_durable_attempts_and_is_bounded(self):
        self.prepared()
        self.authorize()
        run = study_id(self.root)
        call = Mock(side_effect=[RetryableRejection(0), {"score": .5}])
        with patch("cloud_control.time.sleep"):
            result = self.ledger.perform(run, "one", ".01", "inference", {}, call, attempts=3)
        self.assertEqual(result["attempts"], 2)
        self.assertEqual(self.ledger.operation(run, "one")["attempts"], 2)
        history = self.ledger.store.query(f"attempt:{run}:")
        self.assertEqual({item["status"] for item in history.values()}, {"rejected-429", "succeeded"})
        rejected = Mock(side_effect=RetryableRejection(0))
        with patch("cloud_control.time.sleep"):
            with self.assertRaisesRegex(ControlError, "exhausted"):
                self.ledger.perform(run, "two", ".01", "inference", {}, rejected, attempts=3)
            with self.assertRaisesRegex(ControlError, "exhausted"):
                self.ledger.perform(run, "two", ".01", "inference", {}, rejected, attempts=3)
        self.assertEqual(rejected.call_count, 3)

    def test_cloud_authorization_ignores_local_file_and_pins_prepared_data(self):
        self.prepared()
        self.authorize()
        (self.root / "authorization.json").unlink()
        self.assertEqual(runner.authorized(self.root, self.config, self.ledger)["approval"], self.approval())
        write_json(self.root / "authorization.json", {"approval": {"scope": "full"}})
        self.assertEqual(runner.authorized(self.root, self.config, self.ledger)["approval"]["scope"], "pilot")
        value = read_json(self.root / "prepared.json")
        value["changed"] = True
        write_json(self.root / "prepared.json", value)
        with self.assertRaisesRegex(ValueError, "Prepared"):
            runner.authorized(self.root, self.config, self.ledger)
        allocation = self.ledger.allocation(study_id(self.root))
        changed = {**allocation["authorization"], "prepared_sha256": "replacement"}
        with self.assertRaisesRegex(ControlError, "Prepared"):
            self.ledger.authorize(study_id(self.root), self.approval(), allocation["estimate"],
                                  self.config, changed)

    def test_local_smoke_file_cannot_authorize_training(self):
        self.prepared()
        self.authorize()
        write_json(self.root / "smoke.json", {"study_sha256": digest(read_json(self.root / "study.json"))})
        with self.assertRaisesRegex(ValueError, "smoke"):
            runner.train_submit(self.root, self.config, self.ledger, self.backend)
        self.assertEqual(self.backend.jobs, {})

    def test_budget_and_authority_survive_run_root_and_client_changes(self):
        self.ledger.authorize("first-root", self.approval(), {"pilot": "9"}, self.config)
        with self.assertRaisesRegex(ControlError, "Global pilot"):
            self.ledger.authorize("different-root", self.approval(), {"pilot": ".02"}, self.config)
        changed = deepcopy(BINDING)
        changed["authority_id"] = "different"
        other = Ledger(FakeStore(self.ledger.store.storage), changed, PLAN, remaining_credit="100")
        with self.assertRaisesRegex(ControlError, "authority"):
            other.read()
        with self.assertRaisesRegex(ControlError, "authority"):
            self.ledger.authorize("new", {**self.approval(), "authority_sha256": "other"},
                                  {"pilot": "1"}, self.config)
        del self.ledger.store.storage.rows[ROOT]
        with self.assertRaisesRegex(ControlError, "bootstrap"):
            self.ledger.read()

    def test_batch_conflict_is_atomic_and_oversized_records_fail(self):
        store = self.ledger.store
        store.transaction([("fixture", {"n": 1}, None)])
        _, stale = store.get("fixture")
        store.transaction([("fixture", {"n": 2}, stale)])
        with self.assertRaises(Conflict):
            store.transaction([("fixture", {"n": 3}, stale), ("other", {}, None)])
        self.assertEqual(store.get("fixture")[0], {"n": 2})
        self.assertIsNone(store.get("other")[0])
        with self.assertRaisesRegex(ControlError, "size"):
            encoded({"value": "x" * 40000})
        with self.assertRaises(ValueError):
            encoded({"value": float("nan")})

    def test_io_tail_stops_before_provider_dispatch(self):
        self.prepared()
        self.authorize()
        self.ledger.store.budget.limit = self.ledger.store.budget.used + 25
        call = Mock()
        with self.assertRaisesRegex(ControlError, "allowance|completion"):
            self.ledger.perform(study_id(self.root), "one", ".1", "inference", {}, call)
        call.assert_not_called()

    def test_zero_use_migration_refuses_any_authorization_or_nonempty_ledger(self):
        storage = Path(self.temporary.name) / "legacy"
        control = Path(self.temporary.name) / "legacy-control"
        control.mkdir()
        self.assertTrue(audit(storage, control)["zero_use"])
        with sqlite3.connect(control / "ledger.sqlite3") as connection:
            connection.execute("CREATE TABLE runs (id TEXT)")
            connection.execute("INSERT INTO runs VALUES ('prior-reservation')")
        with self.assertRaisesRegex(ControlError, "Nonempty"):
            audit(storage, control)
        (control / "ledger.sqlite3").unlink()
        write_json(storage / "openai-runs/old/authorization.json", {"scope": "pilot"})
        with self.assertRaisesRegex(ControlError, "authorization"):
            audit(storage, control)

    def test_unbound_configuration_and_offline_prepare_never_construct_storage(self):
        unbound = Path(self.temporary.name) / "unbound"
        write_json(unbound / "control_store.json", {**BINDING, "storage_resource_id": ""})
        with patch("cloud_control.TASK", unbound), patch("cloud_control.AzureStore") as constructor:
            with self.assertRaisesRegex(ControlError, "unbound"):
                binding_at()
            constructor.assert_not_called()
        with patch.object(runner, "config_at", return_value=self.config), patch.object(
            runner, "study", return_value=self.root
        ), patch.object(runner, "prepare"), patch.object(
            runner.Ledger, "configured", side_effect=AssertionError("prepare contacted Azure")
        ), patch.object(sys, "argv", ["runner", "prepare", "--storage", self.temporary.name, "--run-id", "offline"]):
            runner.main()
        self.assertEqual(read_json(self.root / "status/prepare.json")["status"], "succeeded")

    def test_storage_worksheet_requires_costed_bounded_sessions(self):
        storage_plan(PLAN)
        for key, value in (("request_usd", "0"), ("max_requests", 1000), ("margin", "1"),
                           ("retention_until", "2000-01-01T00:00:00Z"), ("reserve_usd", ".00001")):
            with self.assertRaises(ControlError):
                storage_plan({**PLAN, key: value})

    def test_scoring_transport_count_fits_the_cost_worksheet_envelope(self):
        self.prepared()
        self.authorize()
        before = self.ledger.store.budget.used
        runner.score_once(self.root, self.config, self.ledger, self.backend, "base-fixture",
                          "counted-row", [{"role": "user", "content": "test"}], 100)
        self.assertLessEqual(self.ledger.store.budget.used - before, 40)

    def test_expired_lease_takeover_preserves_unknown_dispatch(self):
        store = FakeStore()
        clock = [100]
        store.storage.clock = lambda: clock[0]
        first = Ledger(store, BINDING, PLAN, remaining_credit="100", clock=lambda: clock[0])
        second = Ledger(FakeStore(store.storage), BINDING, PLAN, remaining_credit="100", clock=lambda: clock[0])
        with self.assertRaisesRegex(Conflict, "Lease lost"):
            with first.session():
                first.authorize("run", self.approval(), {"pilot": "1"}, self.config)
                first.begin("run", "request", ".1", "inference", {})
                first.dispatch("run", "request", 1)
                clock[0] += 61
                with second.session():
                    call = Mock()
                    with self.assertRaisesRegex(ControlError, "Unconfirmed"):
                        second.perform("run", "request", ".1", "inference", {}, call)
                    with self.assertRaisesRegex(ControlError, "lease"):
                        first.finish("run", "request", {"score": .5})
                    first.receipt("run", "request", {"score": .5})
                    self.assertEqual(second.recover_receipt("run", "request")["score"], .5)
                    call.assert_not_called()

    def test_undispatched_training_can_be_cancelled_without_releasing_budget(self):
        self.prepared()
        self.authorize()
        run = study_id(self.root)
        self.ledger.begin(run, "training", ".1", "training", {})
        self.ledger.cancel_prepared_training(run, "training", {"status": "cancelled"})
        self.assertIsNone(self.ledger._root()[0]["training"])
        self.assertEqual(self.ledger.allocation(run)["used"], "0.1")
        self.assertEqual(self.ledger.operation(run, "training")["actual_usd"], "0")

    def test_preflight_requires_actual_storage_probe_evidence(self):
        state, etag = self.ledger.store.get(ROOT)
        state["probe_verified"] = False
        self.ledger.store.transaction([(ROOT, state, etag)])
        with self.assertRaisesRegex(ControlError, "two-node"):
            self.ledger.authorize("run", self.approval(), {"pilot": "1"}, self.config)

    def test_runtime_tail_keeps_intent_resumable_without_a_dispatch(self):
        self.prepared()
        self.authorize()
        self.ledger.session_deadline = self.ledger.clock() + 100
        call = Mock()
        with self.assertRaisesRegex(ControlError, "runtime"):
            self.ledger.perform(study_id(self.root), "one", ".01", "inference", {}, call)
        self.assertEqual(self.ledger.operation(study_id(self.root), "one")["status"], "prepared")
        self.assertIsNone(self.ledger._root()[0]["pending"])
        call.assert_not_called()

    def test_bootstrap_is_create_only_and_requires_matching_migration(self):
        class NotFound(Exception):
            pass

        store = FakeStore()
        store.storage.rows.clear()
        store.table = NS(list_entities=lambda **kwargs: iter(store.storage.rows))
        store.blob = Mock()
        store.blob.get_blob_properties.side_effect = NotFound
        inventory = {"zero_use": True, "fixture": True}
        approval = {"migration_sha256": digest(inventory), "storage": PLAN, "scope": "pilot"}
        modules = {"azure.core.exceptions": NS(ResourceNotFoundError=NotFound)}
        with patch.dict(sys.modules, modules):
            with self.assertRaisesRegex(ControlError, "migration"):
                bootstrap(store, BINDING, {**approval, "migration_sha256": "wrong"}, inventory)
            store.blob.upload_blob.assert_not_called()
            self.assertTrue(bootstrap(store, BINDING, approval, inventory)["bootstrapped"])
            store.blob.upload_blob.assert_called_once()
            self.assertFalse(store.blob.upload_blob.call_args.kwargs["overwrite"])
            before = store.get(ROOT)[0]
            with self.assertRaisesRegex(ControlError, "empty"):
                bootstrap(store, BINDING, approval, inventory)
            self.assertEqual(store.get(ROOT)[0], before)

    def test_probe_requires_cross_node_lease_evidence_not_just_table_access(self):
        store = FakeStore()
        store.storage.rows[ROOT][0].update(probe_verified=False, probe_atomic=False)
        first = Ledger(store, BINDING, PLAN, remaining_credit="100")
        probe(first)
        self.assertTrue(store.get(ROOT)[0]["probe_atomic"])
        self.assertFalse(store.get(ROOT)[0]["probe_verified"])
        self.assertEqual(store.get(ROOT)[0]["io_reserved"], 1100)
        self.assertEqual(store.budget.limit, 1000)
        holder = Ledger(FakeStore(store.storage), BINDING, PLAN, remaining_credit="100")
        output = Path(self.temporary.name) / "holder.json"

        class LeaseHeld(Exception):
            status_code = 409
            error_code = "LeaseAlreadyPresent"

        contender = FakeStore(store.storage)
        elapsed = [0]
        def second_node(seconds):
            elapsed[0] += seconds
            if elapsed[0] < 45:
                return
            with patch.object(contender, "acquire", side_effect=LeaseHeld), patch(
                "control_admin.socket.gethostname", return_value="node-b"
            ), patch.dict(sys.modules, {"azure.core.exceptions": NS(HttpResponseError=LeaseHeld)}):
                self.assertTrue(contend_probe(contender, output)["excluded"])

        with patch("control_admin.socket.gethostname", return_value="node-a"), patch(
            "control_admin.time.sleep", side_effect=second_node
        ), patch(
            "control_admin.time.monotonic", side_effect=lambda: elapsed[0]
        ):
            self.assertEqual(hold_probe(holder, output), {"two_node_probe": "passed"})
        self.assertTrue(store.get(ROOT)[0]["probe_verified"])
        self.assertEqual(store.get(ROOT)[0]["io_reserved"], 2100)
        self.assertEqual(holder.store.budget.limit, 1000)

    def test_probe_respects_smaller_approved_request_allowance(self):
        store = FakeStore()
        plan = {**PLAN, "session_requests": 100}
        store.storage.rows[ROOT][0]["storage"] = plan
        ledger = Ledger(store, BINDING, plan, remaining_credit="100")
        self.assertEqual(probe(ledger)["storage_probe"], "passed")
        self.assertEqual(store.get(ROOT)[0]["io_reserved"], 200)
        self.assertEqual(store.budget.limit, 100)
        self.assertLess(store.budget.used, 100)

    def test_probe_commands_enforce_transport_cap_before_cloud_access(self):
        for stage, action in (("probe", "probe"), ("lease-hold", "hold_probe"),
                              ("lease-contend", "contend_probe")):
            for approved, expected in ((PLAN["session_requests"], 1000), (100, 100)):
                with self.subTest(stage=stage, approved=approved):
                    approval = {
                        "live_storage_test_approved": True, "expires_at": PLAN["retention_until"],
                        "remaining_credit_usd": "100", "storage": {**PLAN, "session_requests": approved},
                    }
                    output = Path(self.temporary.name) / "command.json"
                    with patch.object(control_admin, "binding_at", return_value=BINDING), patch.object(
                        control_admin, "access_at", return_value=approval
                    ), patch.object(control_admin, "AzureStore") as factory, patch.object(
                        control_admin, action, return_value={}
                    ), patch("builtins.print"), patch.object(sys, "argv", [
                        "control_admin", stage, "--storage", self.temporary.name,
                        "--output", str(output), "--holding", str(output),
                    ]):
                        control_admin.main()
                    budget = factory.call_args.args[1]
                    budget.charge(expected)
                    with self.assertRaisesRegex(ControlError, "allowance exhausted"):
                        budget.charge()

    def test_missing_contender_times_out_and_releases_lease_without_marking_ready(self):
        store = FakeStore()
        store.storage.rows[ROOT][0].update(probe_verified=False, probe_atomic=True)
        holder = Ledger(store, BINDING, PLAN, remaining_credit="100")
        output = Path(self.temporary.name) / "holder-timeout.json"
        elapsed = [0]

        def advance(_):
            elapsed[0] += 60

        with patch("control_admin.time.monotonic", side_effect=lambda: elapsed[0]), patch(
            "control_admin.time.sleep", side_effect=advance
        ):
            with self.assertRaisesRegex(ControlError, "contention evidence"):
                hold_probe(holder, output)
        self.assertLessEqual(elapsed[0], 180)
        self.assertFalse(store.get(ROOT)[0]["probe_verified"])
        self.assertIsNone(store.storage.lease)

    def test_sdk_boundary_passes_conditional_etags_and_preserves_conflicts(self):
        class HttpError(Exception):
            status_code = 412

        condition = object()
        modules = {"azure.core": NS(MatchConditions=NS(IfNotModified=condition)),
                   "azure.core.exceptions": NS(HttpResponseError=HttpError)}
        store = object.__new__(AzureStore)
        store.partition = BINDING["experiment"]
        store.table = Mock()
        store.budget = RequestBudget(100)
        with patch.dict(sys.modules, modules):
            store.transaction([("root", {"n": 1}, "etag-before"), ("operation", {}, None)])
            operations = store.table.submit_transaction.call_args.args[0]
            self.assertEqual(operations[0][0], "update")
            self.assertEqual(operations[0][2]["etag"], "etag-before")
            self.assertIs(operations[0][2]["match_condition"], condition)
            self.assertEqual(operations[1][0], "create")
            store.table.submit_transaction.side_effect = HttpError
            with self.assertRaises(Conflict):
                store.transaction([("root", {"n": 2}, "stale-etag")])

    def test_explicit_storage_extension_retains_budget_and_requires_new_model_preflight(self):
        self.run_pilot()
        run = study_id(self.root)
        before = self.ledger.allocation(run)
        self.session.__exit__(None, None, None)
        new_plan = {**PLAN, "reserve_usd": ".02", "max_requests": PLAN["max_requests"] + 1000}
        approval = {"scope": "full", "storage_extension_approved": True, "storage": new_plan,
                    "previous_storage_sha256": digest(PLAN), "run": run,
                    "study_sha256": self.approval()["study_sha256"], "remaining_credit_usd": "100"}
        store = FakeStore(self.ledger.store.storage)
        result = extend_storage(store, BINDING, approval)
        self.assertTrue(result["storage_extended"])
        self.assertEqual(extend_storage(store, BINDING, approval), result)
        replacement = Ledger(FakeStore(store.storage), BINDING, new_plan, remaining_credit="100")
        with replacement.session():
            self.assertEqual(replacement.allocation(run), before)
            with self.assertRaisesRegex(ValueError, "Storage allowance changed"):
                runner.authorized(self.root, self.config, replacement)
            model_approval = {**self.approval("full"), "storage_reserve_usd": ".02"}
            runner.preflight(self.root, self.config, model_approval, replacement, self.backend)
            self.assertEqual(replacement.allocation(run)["scope"], "full")

    def test_storage_extension_cannot_skip_pilot_or_reset_a_breach(self):
        self.prepared()
        self.authorize()
        run = study_id(self.root)
        self.session.__exit__(None, None, None)
        approval = {"scope": "full", "storage_extension_approved": True,
                    "storage": {**PLAN, "reserve_usd": ".02"},
                    "previous_storage_sha256": digest(PLAN), "run": run,
                    "study_sha256": self.approval()["study_sha256"], "remaining_credit_usd": "100"}
        store = FakeStore(self.ledger.store.storage)
        with self.assertRaisesRegex(ControlError, "pilot validations"):
            extend_storage(store, BINDING, approval)
        state, etag = store.get(ROOT)
        state["breached"] = True
        store.transaction([(ROOT, state, etag)])
        with self.assertRaisesRegex(ControlError, "breach"):
            extend_storage(store, BINDING, approval)
        self.assertTrue(store.get(ROOT)[0]["breached"])


if __name__ == "__main__":
    unittest.main()
