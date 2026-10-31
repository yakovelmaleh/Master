from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext, redirect_stderr
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd

TASK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TASK))
import protocol
from protocol import CELLS, PILOT, PROJECTS, cell_key, digest, read_json, write_json
from azure_backend import AzureBackend, positive_score
from cost_control import CHECKS, check_approval, estimate, money
from cloud_control import Ledger, RetryableRejection
from fake_control import BINDING, PLAN, FakeStore, authority_fields
from failure_evidence import error_details, record_failure
from prepare_data import messages, partition, prepare
import run_experiment as runner
from bundle_artifacts import copy_tree
from unstable_model.data import CATEGORICAL_COLUMNS, NUMERIC_COLUMNS


def module_at(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


launcher = module_at("openai_launcher", TASK / "cluster/submit_jobs.py")
summary = module_at("openai_summary", TASK.parent / "create-task-summary-pr/summarize_levels.py")


class FakeTokenizer:
    name = "fixture-only"
    labels = {"0": [48], "1": [49]}

    def __init__(self, model=None):
        pass

    def encode(self, text):
        return list(text.encode())

    def decode(self, tokens):
        return bytes(tokens).decode(errors="replace")


def frame(project, split):
    rows = []
    for index in range(4):
        item = {column: float(index) for column in NUMERIC_COLUMNS}
        item.update({column: "train" if split == 0 else "unseen" for column in CATEGORICAL_COLUMNS})
        item.update({"model_text": "positive" if index % 2 else "negative",
                     "row_id": f"{project}:{split}:{index}", "issue_key": f"SECRET-{split}-{index}",
                     "source_dataset": project, "time_add_to_sprint": f"2020-0{split + 1}-01"})
        item.update({f"is_change_text_num_words_{level}": index % 2 for level in (5, 10, 15, 20)})
        rows.append(item)
    return pd.DataFrame(rows)


def loader(project, root):
    return tuple(frame(project, split) for split in range(3))


def response(score=.8, label="1", finish="length", missing=False):
    values = [NS(token="0", logprob=float(np.log(1 - score))),
              NS(token="1", logprob=float(np.log(score)))]
    token = NS(token=label, logprob=values[int(label)].logprob,
               top_logprobs=[values[int(label)]] if missing else values)
    return NS(choices=[NS(message=NS(content=label, refusal=None), finish_reason=finish,
                          logprobs=NS(content=[token]))],
              usage=NS(prompt_tokens=30, completion_tokens=1), model="fixture-model", id="response-fixture")


class FakeBackend:
    def __init__(self, config):
        self.config = config
        self.files, self.jobs, self.deployments = {}, {}, {}
        self.predict_calls = 0

    def preflight(self):
        return {"account_verified": True, "fixture": True}

    def upload(self, path, name):
        self.guard()
        value = "file-" + str(len(self.files))
        self.files[value] = name
        return value

    def find_upload(self, name):
        return next(key for key, filename in self.files.items() if filename == name)

    def train(self, file_id, suffix):
        self.guard()
        key = "job-" + str(len(self.jobs))
        value = {"id": key, "model": self.config["model"], "training_file": file_id,
                 "fine_tuned_model": "ft:" + key, "status": "queued", "trained_tokens": 100}
        self.jobs[key] = value
        return dict(value)

    def wait_file(self, file_id):
        pass

    def job(self, job_id):
        self.jobs[job_id]["status"] = "succeeded"
        return dict(self.jobs[job_id])

    def find_job(self, file_id):
        matches = [job for job in self.jobs.values() if job["training_file"] == file_id]
        if len(matches) != 1:
            raise ValueError("Unconfirmed training.")
        return self.job(matches[0]["id"])

    def get_deployment(self, name):
        return self.deployments.get(name)

    def deploy(self, name, model, owner):
        self.guard()
        self.deployments[name] = {"tags": {"master-study": owner}, "sku": {"name": "DeveloperTier"},
                                 "properties": {"model": {"name": model}, "provisioningState": "Succeeded"}}

    def ready(self, name, model, owner):
        if self.deployments[name]["properties"]["model"]["name"] != model:
            raise ValueError("Wrong model")

    def remove_deployment(self, name):
        self.guard()
        self.deployments.pop(name, None)

    def predict(self, deployment, prompt):
        self.guard()
        self.predict_calls += 1
        score = .9 if "positive" in prompt[-1]["content"] else .1
        return {"score": score, "usage": {"input_tokens": 30, "output_tokens": 1},
                "attempts": 1, "response_model": deployment, "request_id": str(self.predict_calls)}

    def delete_file(self, file_id):
        self.guard()
        self.files.pop(file_id, None)

    def delete_model(self, model):
        self.guard()

    def cancel(self, job_id):
        self.guard()
        self.jobs[job_id]["status"] = "cancelled"
        return dict(self.jobs[job_id])

    def file_exists(self, file_id):
        return file_id in self.files

    def model_exists(self, model):
        return False


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "study"
        self.config = {**read_json(TASK / "experiment.json"), "bootstrap_samples": 100}
        write_json(self.root / "study.json", {"config": self.config, "fixture": True})
        self.ledger = Ledger(FakeStore(), BINDING, PLAN, remaining_credit="100")
        self.session = self.ledger.session()
        self.session.__enter__()
        self.addCleanup(self.session.__exit__, None, None, None)
        self.backend = FakeBackend(self.config)
        self.backend.guard = self.ledger.guard_remote

    def prepared(self):
        return prepare(self.root, self.config, FakeTokenizer(), loader)

    def approval(self, scope="pilot"):
        return {
            **authority_fields(),
            "study_sha256": digest(read_json(self.root / "study.json")), "scope": scope,
            "endpoint": "https://fixture.openai.azure.com", "base_deployment": "base-fixture",
            "resource_id": "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/fixture/providers/Microsoft.CognitiveServices/accounts/fixture",
            "model": self.config["model"], "deployment_sku": "DeveloperTier",
            "credit_offer": "TEST FIXTURE, NOT AUTHORIZATION", "evidence": "mocked",
            "expires_at": "2099-01-01T00:00:00Z", "remaining_credit_usd": "100",
            "checks": {name: True for name in CHECKS},
            "rates": {"training_per_million": "1", "input_per_million": ".1", "output_per_million": ".4"},
            "rate_safety_multiplier": "1.25", "other_cost_reserve_usd": ".10",
        }

    def authorize(self, scope="pilot"):
        return runner.preflight(self.root, self.config, self.approval(scope), self.ledger, self.backend)

    def run_pilot(self):
        self.prepared()
        self.authorize()
        with patch.object(runner, "Tokenizer", FakeTokenizer):
            runner.smoke(self.root, self.config, self.ledger, self.backend)
        for _ in PILOT:
            runner.train_submit(self.root, self.config, self.ledger, self.backend)
            runner.train_status(self.root, self.config, self.ledger, self.backend)
        runner.evaluate(self.root, self.config, self.ledger, self.backend, "validation")


class FailureEvidenceTests(Fixture):
    @staticmethod
    def rejection():
        error = RuntimeError("SECRET-STORY and SECRET-TOKEN in a provider response")
        error.status_code = 400
        error.body = {"error": {
            "code": "InvalidPayload", "type": "invalid_request_error",
            "param": "method.supervised.hyperparameters.n_epochs",
            "message": "SECRET-STORY", "inner_error": {"message": "SECRET-TOKEN"},
        }}
        error.response = NS(headers={
            "Apim-Request-Id": "00000000-0000-0000-0000-000000000123",
            "authorization": "Bearer SECRET-TOKEN", "other-header": "SECRET-STORY",
        })
        return error

    def test_known_metadata_is_retained_without_messages_or_other_headers(self):
        details = error_details(self.rejection())
        self.assertEqual(details, {
            "error_type": "RuntimeError", "http_status": 400,
            "provider": {
                "code": "InvalidPayload", "type": "invalid_request_error",
                "param": "method.supervised.hyperparameters.n_epochs",
                "apim_request_id": "00000000-0000-0000-0000-000000000123",
            },
        })
        self.assertNotIn("SECRET", json.dumps(details))

    def test_unknown_fields_are_fingerprinted_and_invalid_request_ids_are_omitted(self):
        error = self.rejection()
        error.code, error.param, error.type = "SECRET-STORY", "SECRET_FIELD", "\ud800"
        error.request_id = "SECRET-TOKEN"
        error.response.headers["Apim-Request-Id"] = "SECRET-STORY\ninjected"
        details = error_details(error)
        self.assertEqual(set(details["provider"]), {"code_sha256", "param_sha256", "type_sha256"})
        self.assertNotIn("SECRET", json.dumps(details))
        error.body, error.response.headers, error.status_code = [], [], True
        self.assertIsNone(error_details(error)["http_status"])

    def test_failure_history_is_private_bound_to_dispatch_and_cannot_recover_it(self):
        self.prepared()
        self.authorize()
        run = protocol.study_id(self.root)
        request = {"file": "file-fixture", "model": self.config["model"], "epochs": 1}
        error = self.rejection()
        call = Mock(side_effect=error)
        with self.assertRaises(RuntimeError) as raised:
            self.ledger.perform(run, "train-fixture", ".01", "training", request, call)
        self.assertIs(raised.exception, error)
        before = self.ledger._root()[0]
        allocation = self.ledger.allocation(run)
        used = self.ledger.store.budget.used
        first = record_failure(self.root, "train-submit", error, self.ledger.failed_dispatch)
        # Even a cleanup failure must not discard the original dispatch error.
        second = record_failure(self.root, "train-submit", TimeoutError(), self.ledger.failed_dispatch)
        self.assertEqual(self.ledger.store.budget.used, used)
        self.assertNotEqual(first["path"], second["path"])
        self.assertEqual(protocol.file_hash(self.root / first["path"]), first["sha256"])
        for reference in (first, second):
            path = self.root / reference["path"]
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            evidence = read_json(path)
            self.assertEqual(evidence["study_sha256"], digest(read_json(self.root / "study.json")))
            self.assertEqual(evidence["dispatch"], {
                "run": run, "operation": "train-fixture", "kind": "training", "attempt": 1,
                "request_sha256": digest(request), "error": error_details(error),
            })
            self.assertNotIn("SECRET", path.read_text())
        self.assertEqual(self.ledger._root()[0], before)
        self.assertEqual(self.ledger.allocation(run), allocation)
        self.assertEqual(before["pending"], [run, "train-fixture"])
        self.assertEqual(before["training"], before["pending"])
        with self.assertRaisesRegex(ValueError, "no matching receipt"):
            self.ledger.recover_receipt(run, "train-fixture")
        with self.assertRaisesRegex(ValueError, "Unconfirmed"):
            self.ledger.perform(run, "train-fixture", ".01", "training", request, call)
        self.assertEqual(call.call_count, 1)
        self.assertEqual(self.ledger.operation(run, "train-fixture")["status"], "dispatched")

    def run_failure(self):
        stderr = io.StringIO()
        with patch.object(runner, "config_at", return_value=self.config), patch.object(
            runner, "study", return_value=self.root
        ), patch.object(runner.Ledger, "configured", return_value=self.ledger), patch.object(
            self.ledger, "session", return_value=nullcontext()
        ), patch("azure_backend.AzureBackend"), patch.object(
            runner, "authorized", return_value={"approval": self.approval()}
        ), patch.object(runner, "train_submit", side_effect=self.rejection()), patch.object(
            sys, "argv", ["runner", "train-submit", "--storage", self.temporary.name, "--run-id", "offline"]
        ), redirect_stderr(stderr), self.assertRaises(SystemExit) as raised:
            runner.main()
        self.assertEqual(raised.exception.code, 1)
        return stderr.getvalue()

    def test_runner_failure_status_links_to_redacted_evidence_without_dumping_body(self):
        stderr = self.run_failure()
        status = read_json(self.root / "status/train-submit.json")
        self.assertEqual(status["status"], "failed")
        self.assertEqual(status["http_status"], 400)
        path = self.root / status["failure_evidence"]["path"]
        self.assertEqual(status["failure_evidence"]["sha256"], protocol.file_hash(path))
        self.assertEqual(read_json(path)["error"]["provider"], status["provider"])
        self.assertNotIn("SECRET", stderr + json.dumps(status) + path.read_text())

    def test_diagnostic_write_failure_stays_failed_and_is_explicit_without_raw_error(self):
        with patch.object(runner, "record_failure", side_effect=OSError("SECRET-PATH")):
            stderr = self.run_failure()
        status = read_json(self.root / "status/train-submit.json")
        self.assertEqual(status["status"], "failed")
        self.assertEqual(status["http_status"], 400)
        self.assertNotIn("failure_evidence", status)
        self.assertIn("Failure evidence could not be persisted (OSError)", stderr)
        self.assertNotIn("SECRET", stderr)


class DataTests(Fixture):
    def test_exact_splits_and_original_feature_serialization(self):
        selected_loader = Mock(side_effect=loader)
        prepared = prepare(self.root, self.config, FakeTokenizer(), selected_loader)
        self.assertEqual([call.args[0] for call in selected_loader.call_args_list], ["Jira", "Qt"])
        expected = {f"{project}-{level}-{variant}" for project in ("Jira", "Qt")
                    for level in (5, 20) for variant in ("text", "structured")}
        self.assertEqual(set(prepared["entries"]), expected)
        for cell in CELLS:
            key = cell_key(*cell)
            for split in ("train", "validation", "test"):
                records, rows = partition(self.root, key, split)
                self.assertEqual(len(rows), 4)
                for record in records:
                    content = json.dumps(record)
                    self.assertNotIn("SECRET", content)
                    self.assertNotIn("is_change_text_num_words_", content)
                    self.assertEqual(len(record["messages"]), 3 if split == "train" else 2)
            transformer = read_json(self.root / "prepared" / cell[0] / "transformer.json")
            self.assertEqual(transformer["categories"]["project_key"], ["train"])
        path = self.root / "prepared" / cell_key(*PILOT[0]) / "test.jsonl"
        path.write_text("{}\n")
        with self.assertRaisesRegex(ValueError, "changed"):
            partition(self.root, cell_key(*PILOT[0]), "test")

    def test_empty_long_and_oversized_structured_input(self):
        prompt, _, cut = messages("", 10, None, FakeTokenizer(), self.config)
        self.assertFalse(cut)
        self.assertEqual(json.loads(prompt[-1]["content"])["original_text"], "")
        prompt, _, cut = messages("a" * 5000, 10, None, FakeTokenizer(), self.config)
        self.assertTrue(cut)
        self.assertEqual(len(json.loads(prompt[-1]["content"])["original_text"]), self.config["text_tokens"])
        with self.assertRaisesRegex(ValueError, "no rows"):
            messages("text", 10, {"feature": "a" * 20000}, FakeTokenizer(), self.config)

    def test_real_historical_reference_partitions(self):
        from data_contract import load_project, verify_frames

        reference = read_json(protocol.SHARED / "reference_contract.json")
        for project in PROJECTS:
            frames = load_project(project, self.root)
            verify_frames(frames, reference["projects"][project])
            altered = tuple(value.copy() for value in frames)
            altered[0].iloc[0, altered[0].columns.get_loc("is_change_text_num_words_5")] ^= 1
            with self.assertRaisesRegex(ValueError, "label mismatch"):
                verify_frames(altered, reference["projects"][project])


class BudgetTests(Fixture):
    def test_approval_blocks_unknown_rates_expiry_and_wrong_destination(self):
        value = self.approval()
        check_approval(value, value["study_sha256"], self.config)
        for delta in ({"expires_at": "2000-01-01T00:00:00Z"}, {"endpoint": "https://example.com"},
                      {"remaining_credit_usd": "20"}, {"checks": {}},
                      {"rates": {name: None for name in value["rates"]}}):
            with self.assertRaises(ValueError):
                check_approval({**value, **delta}, value["study_sha256"], self.config)

    def test_boundaries_protected_credit_and_unconfirmed_requests(self):
        approval = self.approval()
        with self.assertRaisesRegex(ValueError, "cost limit"):
            self.ledger.authorize("a", approval, {"pilot": "9.00001"}, self.config)
        self.ledger.authorize("a", approval, {"pilot": "9"}, self.config)
        self.assertIsNone(self.ledger.begin("a", "one", "8.99", "inference", {}))
        with self.assertRaisesRegex(ValueError, "exceed"):
            self.ledger.begin("a", "two", ".00001", "inference", {})
        self.ledger.dispatch("a", "one", 1)
        with self.assertRaisesRegex(ValueError, "Unconfirmed"):
            self.ledger.begin("a", "one", "9", "inference", {})
        self.ledger.finish("a", "one", {"score": .4}, actual="1")
        self.assertEqual(self.ledger.begin("a", "one", "9", "inference", {}), {"score": .4})
        full = self.approval("full")
        with self.assertRaisesRegex(ValueError, "cost limit"):
            self.ledger.authorize("a", full, {"full": "80.00001"}, self.config)
        self.ledger.authorize("a", full, {"full": "80"}, self.config)
        with self.assertRaisesRegex(ValueError, "Global"):
            self.ledger.authorize("b", approval, {"pilot": ".02"}, self.config)
        with self.assertRaisesRegex(ValueError, "credit|Credit"):
            self.ledger.authorize("a", {**full, "remaining_credit_usd": "99.99"}, {"full": "80"}, self.config)

    def test_reviewed_pilot_cap_preserves_prior_reservations_and_storage(self):
        previous_config = {**self.config, "pilot_limit_usd": 7}
        approval = self.approval()
        self.ledger.authorize("prior", approval, {"pilot": "6"}, previous_config)
        allocation = self.ledger.allocation("prior")
        before, _ = self.ledger._root()
        self.ledger.authorize("new", approval, {"pilot": "3.01"}, self.config)
        after, _ = self.ledger._root()
        self.assertEqual(self.ledger.allocation("prior"), allocation)
        self.assertEqual(after["pilot_total"], "8.99")
        self.assertEqual(after["total"], "8.99")
        for field in ("storage", "io_reserved", "sessions", "authority", "probe_verified"):
            self.assertEqual(after[field], before[field])
        with self.assertRaisesRegex(ValueError, r"Global pilot.*\$9"):
            self.ledger.authorize("another", approval, {"pilot": ".02"}, self.config)
        self.assertIsNone(self.ledger.allocation("another"))
        self.assertEqual(self.ledger._root()[0], after)

    def test_previous_pilot_cap_cannot_reuse_its_run_or_approval(self):
        previous_config = {**self.config, "pilot_limit_usd": 7}
        path = Path(self.temporary.name) / "previous-config.json"
        write_json(path, previous_config)
        with self.assertRaisesRegex(ValueError, "review: pilot_limit_usd"):
            protocol.config_at(path)
        previous_study = {"config": previous_config, "fixture": True}
        current_study = {"config": self.config, "fixture": True}
        storage = Path(self.temporary.name) / "previous-storage"
        previous_root = storage / "openai-runs/previous-pilot"
        write_json(previous_root / "study.json", previous_study)
        with patch.object(protocol, "signature", return_value=current_study):
            with self.assertRaisesRegex(ValueError, "new run ID"):
                protocol.study(storage, "previous-pilot", self.config)
        self.assertEqual(read_json(previous_root / "study.json"), previous_study)
        previous_approval = {**self.approval(), "study_sha256": digest(previous_study)}
        with self.assertRaisesRegex(ValueError, "current study hash"):
            check_approval(previous_approval, digest(current_study), self.config)

    def test_global_training_lock_and_usage_overrun(self):
        self.ledger.authorize("a", self.approval(), {"pilot": "3"}, self.config)
        self.ledger.authorize("b", self.approval(), {"pilot": "2"}, self.config)
        self.ledger.begin("a", "train", "1", "training", {})
        with self.assertRaisesRegex(ValueError, "cloud training"):
            self.ledger.begin("b", "train", "1", "training", {})
        self.ledger.dispatch("a", "train", 1)
        self.ledger.training_terminal("a", "train", {"status": "succeeded"})
        self.ledger.begin("b", "train", "1", "training", {})
        self.ledger.dispatch("b", "train", 1)
        with self.assertRaisesRegex(ValueError, "exceeded"):
            self.ledger.finish("b", "train", {}, actual="1.01")
        self.assertTrue(self.ledger.read()["breached"])
        self.ledger.training_terminal("b", "train", {"status": "cancelled"})
        self.assertTrue(self.ledger.read()["breached"])

    def test_concurrent_requests_cannot_both_spend_the_last_allowance(self):
        self.ledger.authorize("a", self.approval(), {"pilot": "5"}, self.config)
        self.ledger.begin("a", "initial", "4.98", "inference", {})

        def spend(name):
            try:
                self.ledger.begin("a", name, ".01", "inference", {})
                return True
            except ValueError:
                return False

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(spend, ("one", "two")))
        self.assertEqual(sum(results), 1)
        self.assertEqual(money(self.ledger.snapshot("a")["operation_bounds_usd"]), money("4.99"))

    def test_full_scope_cost_is_not_hidden_by_pilot(self):
        prepared = self.prepared()
        costs = estimate(prepared, self.config, self.approval())
        self.assertGreater(money(costs["full"]), money(costs["pilot"]))
        approval = self.approval()
        approval["rates"]["training_per_million"] = "100000"
        with self.assertRaisesRegex(ValueError, "unaffordable"):
            runner.preflight(self.root, self.config, approval, self.ledger, self.backend)
        self.assertEqual(self.backend.jobs, {})


class ScoringTests(unittest.TestCase):
    def test_logprob_scores_both_labels_and_not_generated_confidence(self):
        self.assertAlmostEqual(positive_score(response(.8))["score"], .8)
        self.assertAlmostEqual(positive_score(response(.2, "0"))["score"], .2)
        for value in (response(missing=True), response(finish="content_filter")):
            with self.assertRaises(ValueError):
                positive_score(value)
        bad = response()
        bad.choices[0].message.content = "confidence 0.8"
        with self.assertRaises(ValueError):
            positive_score(bad)
        bad = response()
        bad.usage = None
        with self.assertRaisesRegex(ValueError, "usage"):
            positive_score(bad)
        bad = response()
        bad.choices[0].logprobs.content[0].logprob = float("nan")
        with self.assertRaises(ValueError):
            positive_score(bad)

    def test_sdk_training_has_explicit_epochs_and_no_validation_training_rows(self):
        backend = object.__new__(AzureBackend)
        backend.guard = Mock()
        backend.client = Mock()
        backend.config = read_json(TASK / "experiment.json")
        backend.client.fine_tuning.jobs.create.return_value = NS(
            id="job", status="queued", model=backend.config["model"], training_file="file",
            fine_tuned_model=None, trained_tokens=None)
        backend.train("file", "test")
        payload = backend.client.fine_tuning.jobs.create.call_args.kwargs
        self.assertEqual(payload["method"]["supervised"]["hyperparameters"]["n_epochs"], 1)
        self.assertNotIn("validation_file", payload)
        self.assertEqual(payload["extra_body"]["trainingType"], "GlobalStandard")

    def test_deployment_uses_only_owned_developer_resources(self):
        backend = object.__new__(AzureBackend)
        backend.guard = Mock()
        backend.config = read_json(TASK / "experiment.json")
        backend.arm = Mock()
        backend.deploy("name", "ft:model", "owner")
        payload = backend.arm.call_args.args[2]
        self.assertEqual(payload["sku"], {"name": "DeveloperTier", "capacity": 50})
        self.assertEqual(payload["tags"], {"master-study": "owner"})
        self.assertEqual(payload["properties"]["model"]["name"], "ft:model")
        backend.get_deployment = Mock(return_value={
            "properties": {"model": {"name": "ft:other"}, "provisioningState": "Succeeded"},
            "tags": {"master-study": "owner"}, "sku": {"name": "DeveloperTier"}})
        with self.assertRaisesRegex(ValueError, "differs"):
            backend.ready("name", "ft:model", "owner")

    def test_deployment_readiness_rejects_missing_or_mismatched_capacity(self):
        backend = object.__new__(AzureBackend)
        backend.config = read_json(TASK / "experiment.json")
        deployment = {
            "properties": {"model": {"name": "ft:model"}, "provisioningState": "Succeeded"},
            "tags": {"master-study": "owner"}, "sku": {"name": "DeveloperTier"},
        }
        backend.get_deployment = Mock(return_value=deployment)
        for capacity in (None, 1, 49, 51, "50"):
            with self.subTest(capacity=capacity):
                deployment["sku"] = {"name": "DeveloperTier"}
                if capacity is not None:
                    deployment["sku"]["capacity"] = capacity
                with self.assertRaisesRegex(ValueError, "capacity"):
                    backend.ready("name", "ft:model", "owner")

    def test_deployment_readiness_checks_capacity_after_provisioning_completes(self):
        backend = object.__new__(AzureBackend)
        backend.config = read_json(TASK / "experiment.json")
        backend.get_deployment = Mock(side_effect=[
            {"properties": {"model": {"name": "ft:model"}, "provisioningState": "Updating"},
             "tags": {"master-study": "owner"}, "sku": {"name": "DeveloperTier", "capacity": 1}},
            {"properties": {"model": {"name": "ft:model"}, "provisioningState": "Succeeded"},
             "tags": {"master-study": "owner"}, "sku": {"name": "DeveloperTier", "capacity": 50}},
        ])
        with patch("azure_backend.time.sleep") as sleep:
            backend.ready("name", "ft:model", "owner")
        self.assertEqual(backend.get_deployment.call_count, 2)
        sleep.assert_called_once_with(15)

    def test_bounded_retry_does_not_retry_auth_errors(self):
        class ConnectionError(Exception):
            pass

        class StatusError(Exception):
            def __init__(self, status):
                self.status_code = status
                self.response = NS(headers={"retry-after": "0"})

        backend = object.__new__(AzureBackend)
        backend.guard = Mock()
        backend.config = read_json(TASK / "experiment.json")
        backend.client = Mock()
        client = backend.client.chat.completions.create
        fake_sdk = NS(APIConnectionError=ConnectionError, APIStatusError=StatusError)
        with patch.dict(sys.modules, {"openai": fake_sdk}), patch("azure_backend.time.sleep"):
            client.side_effect = [StatusError(429), response()]
            with self.assertRaises(RetryableRejection):
                backend.predict("model", [])
            self.assertEqual(client.call_count, 1)
            self.assertAlmostEqual(backend.predict("model", [])["score"], .8)
            client.reset_mock()
            client.side_effect = StatusError(401)
            with self.assertRaisesRegex(RuntimeError, "401"):
                backend.predict("model", [])
            self.assertEqual(client.call_count, 1)
            client.reset_mock()
            client.side_effect = ConnectionError()
            with self.assertRaisesRegex(RuntimeError, "no automatic replay"):
                backend.predict("model", [])
            self.assertEqual(client.call_count, 1)


class PromptOnlyTests(Fixture):
    def setUp(self):
        super().setUp()
        self.config = {**protocol.config_at(TASK / "prompt_only.json"),
                       "bootstrap_samples": 100, "batch_rows": 2}
        write_json(self.root / "study.json", {"config": self.config, "fixture": True})
        self.backend.config = self.config
        for name in ("upload", "train", "deploy", "remove_deployment", "delete_file", "delete_model", "cancel"):
            setattr(self.backend, name, Mock(side_effect=AssertionError("Prompt-only called " + name)))

    def approval(self, scope="pilot"):
        from cost_control import approval_checks

        value = super().approval(scope)
        value.update(protocol_schema=protocol.BASE_SCHEMA, method=protocol.BASE_METHOD,
                     deployment_sku=self.config["deployment_sku"],
                     checks={key: True for key in approval_checks(self.config)})
        del value["rates"]["training_per_million"]
        return value

    def start(self):
        self.prepared()
        self.authorize()
        with patch.object(runner, "Tokenizer", FakeTokenizer):
            runner.smoke(self.root, self.config, self.ledger, self.backend)

    def finish_split(self, split):
        for _ in range(32):
            before = self.backend.predict_calls
            result = runner.evaluate(self.root, self.config, self.ledger, self.backend, split)
            self.assertLessEqual(self.backend.predict_calls - before, self.config["batch_rows"])
            if result.get("scope_complete"):
                return
        self.fail("Batch iteration did not complete")

    def test_prompt_only_approvals_and_costs_do_not_require_training(self):
        prepared = self.prepared()
        approval = self.approval()
        check_approval(approval, approval["study_sha256"], self.config)
        costs = estimate(prepared, self.config, approval)
        self.assertTrue(all(set(value) == {"validation", "test"} for value in costs["entries"].values()))
        legacy = {**read_json(TASK / "experiment.json"), "bootstrap_samples": 100}
        sft_approval = {**approval, "rates": {**approval["rates"], "training_per_million": "1"}}
        old = estimate(prepared, legacy, sft_approval)
        training = sum(money(entry["train"]) for entry in old["entries"].values())
        self.assertEqual(money(old["full"]) - money(costs["full"]), training)
        for delta in ({"method": "sft"}, {"protocol_schema": "openai-instability-v2"},
                      {"base_deployment": ""}, {"checks": {}},
                      {"expires_at": "2000-01-01T00:00:00Z"},
                      {"rates": {"input_per_million": None, "output_per_million": ".4"}}):
            with self.subTest(delta=delta), self.assertRaises(ValueError):
                check_approval({**approval, **delta}, approval["study_sha256"], self.config)
        template = runner.approval_template(self.root, self.config)
        self.assertNotIn("training_per_million", template["rates"])
        self.assertFalse(any(template["checks"].values()))

    def test_no_assistant_examples_and_all_partition_rows_are_preserved(self):
        self.prepared()
        for cell in CELLS:
            for split in ("train", "validation", "test"):
                records, rows = partition(self.root, cell_key(*cell), split)
                expected = frame(cell[0], ("train", "validation", "test").index(split))
                self.assertEqual([row["row_id"] for row in rows], expected.row_id.tolist())
                for record in records:
                    self.assertEqual([m["role"] for m in record["messages"]], ["system", "user"])
                    self.assertEqual(record["messages"][0]["content"], protocol.PROMPT)

    def test_eight_cell_batched_workflow_seal_restoration_and_summary(self):
        self.start()
        with self.assertRaisesRegex(ValueError, "full-study"):
            runner.evaluate(self.root, self.config, self.ledger, self.backend, "test")
        self.finish_split("validation")
        with self.assertRaises(FileNotFoundError):
            runner.seal(self.root, self.ledger)
        self.authorize("full")
        with self.assertRaisesRegex(ValueError, "selection seal"):
            runner.evaluate(self.root, self.config, self.ledger, self.backend, "test")
        self.finish_split("validation")
        runner.seal(self.root, self.ledger)
        with self.assertRaisesRegex(ValueError, "sealing"):
            runner.evaluate(self.root, self.config, self.ledger, self.backend, "validation")
        with patch("data_contract.load_project", loader), patch(
            "data_contract.baseline_predictions", return_value=(np.full(4, .5), {"fixture": True})
        ):
            self.finish_split("test")
        self.assertEqual(self.backend.predict_calls, 6 + 32 + 32)
        self.assertTrue(all(op["kind"] == "inference" for op in self.ledger.operations(protocol.study_id(self.root))))
        output = Path(self.temporary.name) / "bundle/artifacts/results/llm_report.json"
        result = runner.report(self.root, self.ledger, output)
        self.assertTrue(result["complete"])
        self.assertEqual(result["schema"], "openai-instability-prompt-report-v1")
        self.assertEqual(len(result["cells"]), 8)
        for cell in result["cells"]:
            self.assertNotIn("job_id", cell["model_reference"])
            self.assertEqual(cell["model_reference"]["method"], protocol.BASE_METHOD)
            key = cell_key(cell["project"], cell["level"], cell["variant"])
            self.assertEqual(read_json(self.root / "final" / key / "metrics.json")["threshold"],
                             read_json(self.root / "validation" / key / "validation.json")["threshold"])
            for relative in (f"validation/{key}/scores.json", f"final/{key}/scores.json",
                             f"final/{key}/metrics.json"):
                (self.root / relative).unlink()
        restored = runner.report(self.root, self.ledger, output)
        self.assertEqual(result["cells"], restored["cells"])
        self.assertEqual(self.backend.predict_calls, 70)
        summary.summarize(output.parents[2])
        text = (output.parents[2] / "RESULTS.csv").read_text()
        self.assertIn("openai_prompt_text", text)
        self.assertEqual(len(text.splitlines()), 9)
        bundled = Path(self.temporary.name) / "export"
        copy_tree(self.root, bundled)
        self.assertFalse((bundled / "batches").exists())

    def test_partial_batch_receipt_recovery_never_replays_a_completed_request(self):
        self.start()
        run = protocol.study_id(self.root)
        before = self.backend.predict_calls
        with patch.object(self.ledger, "finish", side_effect=TimeoutError):
            with self.assertRaises(TimeoutError):
                runner.evaluate(self.root, self.config, self.ledger, self.backend, "validation")
        self.assertEqual(self.backend.predict_calls, before + 1)
        with self.assertRaisesRegex(ValueError, "Unconfirmed"):
            runner.evaluate(self.root, self.config, self.ledger, self.backend, "validation")
        runner.reconcile(self.root, self.config, self.ledger, self.backend)
        runner.evaluate(self.root, self.config, self.ledger, self.backend, "validation")
        self.assertEqual(self.backend.predict_calls, before + 2)
        key = cell_key(*PILOT[0])
        (self.root / "batches/validation" / key / "0.json").unlink()
        runner.evaluate(self.root, self.config, self.ledger, self.backend, "validation")
        self.assertEqual(self.backend.predict_calls, before + 4)
        saved = self.ledger.artifact(run, "validation-" + key)
        self.assertEqual(len(read_json(self.root / "validation" / key / "scores.json")), 4)
        self.assertTrue(saved)

    def test_unknown_prediction_is_not_replayed_or_skipped(self):
        self.start()
        before = self.backend.predict_calls
        with patch.object(self.backend, "predict", side_effect=TimeoutError):
            with self.assertRaises(TimeoutError):
                runner.evaluate(self.root, self.config, self.ledger, self.backend, "validation")
        with self.assertRaisesRegex(ValueError, "no matching receipt"):
            runner.reconcile(self.root, self.config, self.ledger, self.backend)
        with self.assertRaisesRegex(ValueError, "Unconfirmed"):
            runner.evaluate(self.root, self.config, self.ledger, self.backend, "validation")
        self.assertEqual(self.backend.predict_calls, before)

    def test_control_envelope_covers_batches_and_reconstruction(self):
        from cost_control import control_envelope, control_requests

        prepared = self.prepared()
        for scope in ("pilot", "full"):
            envelope = control_envelope(prepared, self.config, scope)
            expected_batches = 4 if scope == "pilot" else 32
            self.assertEqual(envelope["sessions"], expected_batches + (2 if scope == "pilot" else 3))
        self.start()
        before = self.ledger.store.budget.used
        runner.evaluate(self.root, self.config, self.ledger, self.backend, "validation")
        self.assertLess(self.ledger.store.budget.used - before,
                        control_requests("validate", prepared, self.config, "pilot"))
        with patch.dict(self.ledger.plan, {"session_requests": 100}):
            with self.assertRaisesRegex(ValueError, "Storage allowance"):
                self.ledger.require_capacity(control_envelope(prepared, self.config, "pilot"))

    def test_training_stages_and_model_mutations_fail_before_remote_access(self):
        for call in (
            lambda: runner.train_submit(self.root, self.config, self.ledger, self.backend),
            lambda: runner.train_status(self.root, self.config, self.ledger, self.backend),
            lambda: runner.cleanup(self.root, self.config, self.ledger, self.backend),
            lambda: runner.deploy(self.root, self.config, self.ledger, self.backend, "cell", "model"),
        ):
            with self.assertRaisesRegex(ValueError, "Prompt-only"):
                call()
        backend = object.__new__(AzureBackend)
        backend.config = self.config
        backend.guard = Mock()
        backend.client = Mock()
        backend.http = Mock()
        for call in (
            lambda: backend.upload(Path("not-opened"), "file"), lambda: backend.train("file", "suffix"),
            lambda: backend.cancel("job"), lambda: backend.delete_file("file"),
            lambda: backend.delete_model("model"), lambda: backend.deploy("base", "model", "run"),
            lambda: backend.remove_deployment("base"),
        ):
            with self.assertRaisesRegex(ValueError, "Prompt-only"):
                call()
        self.assertFalse(backend.guard.called)
        self.assertFalse(backend.client.mock_calls)
        self.assertFalse(backend.http.mock_calls)

    def test_backend_requires_exact_base_and_system_user_messages(self):
        backend = object.__new__(AzureBackend)
        backend.config, backend.approval = self.config, self.approval()
        backend.guard, backend.client = Mock(), Mock()
        prompt, _, _ = messages("text", 20, None, FakeTokenizer(), self.config)
        result = response()
        result.model = self.config["model"]
        backend.client.chat.completions.create.return_value = result
        fake_sdk = NS(APIConnectionError=type("ConnectionError", (Exception,), {}),
                      APIStatusError=type("StatusError", (Exception,), {}))
        with patch.dict(sys.modules, {"openai": fake_sdk}):
            backend.predict("base-fixture", prompt)
            payload = backend.client.chat.completions.create.call_args.kwargs
            self.assertEqual(payload["messages"], prompt)
            self.assertTrue(payload["logprobs"])
            self.assertEqual(payload["max_tokens"], 1)
            for deployment, bad in (("other", prompt), ("base-fixture", prompt[1:]),
                                    ("base-fixture", prompt + [{"role": "assistant", "content": "1"}])):
                with self.assertRaisesRegex(ValueError, "Prompt-only"):
                    backend.predict(deployment, bad)
            result.model = "different-snapshot"
            with self.assertRaisesRegex(ValueError, "different base model"):
                backend.predict("base-fixture", prompt)


class WorkflowTests(Fixture):
    def test_mocked_eight_entry_workflow_and_summary(self):
        self.run_pilot()
        self.assertEqual({path.stem for path in (self.root / "remote").glob("*.json")},
                         {"Jira-20-text", "Jira-20-structured"})
        self.assertIn("Jira/20", read_json(self.root / "base_control.json")["protocol"])
        self.assertFalse((self.root / "final").exists())
        with self.assertRaises(FileNotFoundError):
            runner.seal(self.root, self.ledger)
        self.authorize("full")
        for _ in range(6):
            runner.train_submit(self.root, self.config, self.ledger, self.backend)
            runner.train_status(self.root, self.config, self.ledger, self.backend)
        self.assertEqual(len(self.backend.jobs), 8)
        runner.evaluate(self.root, self.config, self.ledger, self.backend, "validation")
        runner.seal(self.root, self.ledger)
        with self.assertRaisesRegex(ValueError, "sealing"):
            runner.train_submit(self.root, self.config, self.ledger, self.backend)
        with patch("data_contract.load_project", loader), patch(
            "data_contract.baseline_predictions", return_value=(np.full(4, .5), {"fixture": True})
        ):
            runner.evaluate(self.root, self.config, self.ledger, self.backend, "test")
        calls = self.backend.predict_calls
        runner.evaluate(self.root, self.config, self.ledger, self.backend, "test")
        self.assertEqual(self.backend.predict_calls, calls)
        output = Path(self.temporary.name) / "bundle/artifacts/results/llm_report.json"
        result = runner.report(self.root, self.ledger, output)
        self.assertTrue(result["complete"])
        self.assertTrue(result["passed"])
        self.assertEqual(result["schema"], "openai-instability-report-v2")
        self.assertEqual(len(result["cells"]), 8)
        summary.summarize(output.parents[2])
        self.assertEqual(len((output.parents[2] / "RESULTS.csv").read_text().splitlines()), 9)
        runner.cleanup(self.root, self.config, self.ledger, self.backend)
        self.assertEqual(self.backend.files, {})
        self.assertEqual(self.backend.deployments, {})
        for cell in CELLS:
            key = cell_key(*cell)
            for relative in (f"remote/{key}.json", f"validation/{key}/validation.json",
                             f"validation/{key}/scores.json", f"final/{key}/metrics.json",
                             f"final/{key}/scores.json"):
                (self.root / relative).unlink()
        (self.root / "authorization.json").unlink()
        (self.root / "sealed.json").unlink()
        restored = runner.report(self.root, self.ledger, output)
        self.assertEqual(restored["cells"], result["cells"])
        self.assertEqual(self.backend.predict_calls, calls)
        selection_path = self.root / "validation" / cell_key(*PILOT[0]) / "validation.json"
        value = read_json(selection_path)
        value["threshold"] = .99
        write_json(selection_path, value)
        with self.assertRaisesRegex(ValueError, "selection changed"):
            runner.sealed_cells(self.root, self.ledger)

    def test_training_timeout_reconciles_without_resubmission(self):
        self.prepared()
        self.authorize()
        self.ledger.record(protocol.study_id(self.root), "smoke",
                           {"study_sha256": digest(read_json(self.root / "study.json"))})
        real_train = self.backend.train

        def timeout(file_id, suffix):
            real_train(file_id, suffix)
            raise TimeoutError("fixture ambiguous response")

        with patch.object(self.backend, "train", side_effect=timeout):
            with self.assertRaises(TimeoutError):
                runner.train_submit(self.root, self.config, self.ledger, self.backend)
        with self.assertRaisesRegex(ValueError, "Unconfirmed"):
            runner.train_submit(self.root, self.config, self.ledger, self.backend)
        runner.train_status(self.root, self.config, self.ledger, self.backend)
        self.assertEqual(len(self.backend.jobs), 1)
        runner.train_submit(self.root, self.config, self.ledger, self.backend)
        self.assertEqual(len(self.backend.jobs), 2)

    def test_interrupted_prediction_keeps_completed_rows_and_blocks_uncertain_row(self):
        self.run_pilot()
        deployment = self.approval()["base_deployment"]
        prompt = [{"role": "user", "content": "test"}]
        first = runner.score_once(self.root, self.config, self.ledger, self.backend, deployment, "row-a", prompt, 100)
        calls = self.backend.predict_calls
        self.assertEqual(first, runner.score_once(self.root, self.config, self.ledger, self.backend, deployment, "row-a", prompt, 100))
        self.assertEqual(calls, self.backend.predict_calls)
        with patch.object(self.backend, "predict", side_effect=TimeoutError):
            with self.assertRaises(TimeoutError):
                runner.score_once(self.root, self.config, self.ledger, self.backend, deployment, "row-b", prompt, 100)
        with self.assertRaisesRegex(ValueError, "Unconfirmed"):
            runner.score_once(self.root, self.config, self.ledger, self.backend, deployment, "row-b", prompt, 100)

    def test_deployment_expiry_requires_cleanup_and_does_not_adopt_others(self):
        self.prepared()
        self.authorize()
        name = runner.deploy(self.root, self.config, self.ledger, self.backend, "key", "ft:one")
        self.backend.deployments.clear()
        with self.assertRaisesRegex(ValueError, "expired"):
            runner.deploy(self.root, self.config, self.ledger, self.backend, "key", "ft:one")
        runner.remove_deployment(self.root, self.ledger, self.backend)
        new_name = runner.deploy(self.root, self.config, self.ledger, self.backend, "key", "ft:one")
        self.assertNotEqual(name, new_name)
        with self.assertRaisesRegex(ValueError, "Another"):
            runner.deploy(self.root, self.config, self.ledger, self.backend, "other", "ft:two")
        self.backend.deployments[new_name]["tags"]["master-study"] = "unrelated"
        with self.assertRaisesRegex(ValueError, "ownership"):
            runner.remove_deployment(self.root, self.ledger, self.backend)

    def test_missing_report_entries_remain_explicit(self):
        value = runner.report(self.root, self.ledger, self.root / "llm_report.json")
        self.assertEqual(len(value["cells"]), 8)
        self.assertFalse(value["complete"])
        self.assertFalse(value["passed"])

    def test_old_configuration_and_run_cannot_be_reinterpreted_as_reduced_scope(self):
        old_config = {**self.config, "schema": "openai-instability-v1", "pilot_limit_usd": 5}
        path = Path(self.temporary.name) / "old-config.json"
        write_json(path, old_config)
        with self.assertRaisesRegex(ValueError, "new run ID"):
            protocol.config_at(path)
        old_study = {"config": old_config, "fixture": True}
        storage = Path(self.temporary.name) / "legacy-storage"
        old_root = storage / "openai-runs/legacy-study"
        write_json(old_root / "study.json", old_study)
        with patch.object(protocol, "signature", return_value={"config": self.config, "fixture": True}):
            with self.assertRaisesRegex(ValueError, "new run ID"):
                protocol.study(storage, "legacy-study", self.config)
        with self.assertRaisesRegex(ValueError, "original protocol"):
            runner.report(old_root, self.ledger, old_root / "llm_report.json")
        self.assertEqual(read_json(old_root / "study.json"), old_study)
        self.assertFalse((old_root / "llm_report.json").exists())


class LauncherAndBundleTests(Fixture):
    def test_storage_probe_waits_for_slow_holder_and_reports_missing_readiness(self):
        root = Path(self.temporary.name)
        shell = root / "probe-fixture.sh"
        calls = root / "srun-calls"
        shell.write_text("""
ticks=0
scontrol() { printf 'node-a\\nnode-b\\n'; }
srun() {
  for argument in "$@"; do
    case "$argument" in
      probe|lease-hold|lease-contend)
        if [[ "$argument" == lease-contend && ! -f "$directory/holder.json" ]]; then
          echo 'Contender started before holder readiness.' >&2
          return 1
        fi
        printf '%s\\n' "$argument" >> "$FIXTURE_CALLS"
        return 0
        ;;
    esac
  done
  return 1
}
sleep() {
  ticks=$((ticks + 1))
  if [[ "$ticks" -eq "$FIXTURE_READY_AFTER" ]]; then
    printf '{}\\n' > "$directory/holder.json"
  fi
}
""")
        for ready_after, success in ((45, True), (-1, False)):
            with self.subTest(ready_after=ready_after):
                calls.write_text("")
                result = subprocess.run(
                    ["bash", str(TASK / "cluster/check_cloud_control.sbatch"),
                     str(root), sys.executable],
                    env={**os.environ, "BASH_ENV": str(shell),
                         "SLURM_SUBMIT_DIR": str(TASK.parents[1]),
                         "SLURM_JOB_ID": "fixture", "SLURM_JOB_NODELIST": "fixture",
                         "FIXTURE_CALLS": str(calls), "FIXTURE_READY_AFTER": str(ready_after)},
                    capture_output=True, text=True, timeout=10,
                )
                self.assertEqual(result.returncode == 0, success, result.stderr)
                self.assertEqual("CLOUD_CONTROL_PROBE_PASSED" in result.stdout, success)
                self.assertEqual("lease-contend" in calls.read_text().splitlines(), success)
                if not success:
                    self.assertIn("lease-holder readiness timed out", result.stderr)

    def test_setup_creates_only_absent_environment_and_stops_on_failed_inventory(self):
        directory = Path(self.temporary.name) / "bin"
        directory.mkdir()
        (directory / "python").symlink_to(sys.executable)
        (directory / "activate").write_text("return 0\n")
        (directory / "module").write_text("#!/usr/bin/env bash\nexit 0\n")
        (directory / "module").chmod(0o700)
        (directory / "conda").write_text(
            '#!/usr/bin/env bash\nset -eu\n'
            'case "$1" in\n'
            'env) printf "%s\\n" "$FIXTURE_ENV_JSON";;\n'
            'create) printf "created\\n" >> "$FIXTURE_MARKER";;\n'
            '*) exit 2;;\nesac\n'
        )
        (directory / "conda").chmod(0o700)
        args = NS(stage="setup", partition="main", time="01:00:00", mem="8G",
                  mail_user="test@example.invalid", conda_env="master-openai")
        text = launcher.render(args, Path(self.temporary.name) / "job", [["true"]])
        marker = Path(self.temporary.name) / "created"
        env = {**os.environ, "PATH": str(directory) + ":" + os.environ["PATH"],
               "FIXTURE_MARKER": str(marker)}
        for listing, created, success in (
            ('{"envs": []}', True, True),
            ('{"envs": ["/conda/envs/master-openai"]}', False, True),
            ("invalid inventory", False, False),
        ):
            if marker.exists():
                marker.unlink()
            result = subprocess.run(["bash"], input=text, text=True, capture_output=True,
                                    env={**env, "FIXTURE_ENV_JSON": listing})
            self.assertEqual(result.returncode == 0, success, result.stderr)
            self.assertEqual(marker.exists(), created)

    def test_cpu_dry_run_all_stages_and_master_discovery(self):
        for stage in launcher.STAGES:
            args = ["bash", str(TASK.parent / "run_cluster_task.sh"), TASK.name, "--stage", stage,
                    "--storage", self.temporary.name, "--partition", "main", "--dry-run"]
            if stage == "preflight":
                args += ["--approval", self.temporary.name + "/approval.json"]
            result = subprocess.run(args, text=True, capture_output=True, check=True)
            self.assertNotIn("--gres", result.stdout)
            self.assertIn("--mail-type=ALL", result.stdout)
            self.assertEqual("conda create --yes" in result.stdout, stage == "setup")
            if stage == "setup":
                self.assertIn('if [[ "$environment_state" == absent ]]', result.stdout)
                self.assertIn("conda env list --json", result.stdout)
            subprocess.run(["bash", "-n"], input=result.stdout, text=True, check=True)
        result = subprocess.run(["bash", str(TASK.parent / "run_cluster_task.sh"), "--list"],
                                text=True, capture_output=True, check=True)
        self.assertIn(TASK.name, result.stdout)

    def test_bundle_excludes_payloads_logs_credentials_and_symlinks(self):
        source = Path(self.temporary.name) / "source"
        for directory in ("prepared", "remote", "logs", "failures"):
            (source / directory).mkdir(parents=True)
            (source / directory / "secret.jsonl").write_text("private payload")
        write_json(source / "failures/llm_report.json",
                   {"schema": "openai-instability-report-v2", "private": "diagnostics"})
        (source / "approval.json").write_text("private config")
        (source / "train.jsonl").write_text("training data")
        (source / "linked").symlink_to(source / "prepared", target_is_directory=True)
        destination = Path(self.temporary.name) / "bundle"
        for schema in ("openai-instability-report-v1", "openai-instability-report-v2"):
            write_json(source / "llm_report.json", {"schema": schema})
            copy_tree(source, destination)
            self.assertEqual(read_json(destination / "llm_report.json")["schema"], schema)
            self.assertEqual({p.name for p in destination.iterdir()}, {"llm_report.json", "LLM_OMITTED_FILES.json"})
        write_json(source / "llm_report.json", {"schema": "unreviewed-scope"})
        with self.assertRaisesRegex(ValueError, "explicit LLM report schema"):
            copy_tree(source, destination)
        with self.assertRaisesRegex(ValueError, "symlink"):
            copy_tree(source / "linked", destination)


if __name__ == "__main__":
    unittest.main()
