from copy import deepcopy
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

from test_workflow import Fixture
import run_experiment as runner
from cloud_control import (
    AzureStore, Conflict, ControlError, Ledger, RequestBudget, RetryableRejection, ROOT,
    binding_at, encoded, storage_plan,
)
from control_admin import audit, bootstrap, contend_probe, extend_storage, hold_probe, probe
from fake_control import BINDING, PLAN, FakeStore
from protocol import digest, read_json, study_id, write_json


class CloudControlTests(Fixture):
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
        self.ledger.authorize("first-root", self.approval(), {"pilot": "7"}, self.config)
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
        with patch("cloud_control.AzureStore") as constructor:
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
        holder = Ledger(FakeStore(store.storage), BINDING, PLAN, remaining_credit="100")
        output = Path(self.temporary.name) / "holder.json"

        class LeaseHeld(Exception):
            status_code = 409
            error_code = "LeaseAlreadyPresent"

        contender = FakeStore(store.storage)
        def second_node(_):
            with patch.object(contender, "acquire", side_effect=LeaseHeld), patch(
                "control_admin.socket.gethostname", return_value="node-b"
            ), patch.dict(sys.modules, {"azure.core.exceptions": NS(HttpResponseError=LeaseHeld)}):
                self.assertTrue(contend_probe(contender, output)["excluded"])

        with patch("control_admin.socket.gethostname", return_value="node-a"), patch(
            "control_admin.time.sleep", side_effect=second_node
        ):
            self.assertEqual(hold_probe(holder, output), {"two_node_probe": "passed"})
        self.assertTrue(store.get(ROOT)[0]["probe_verified"])

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
