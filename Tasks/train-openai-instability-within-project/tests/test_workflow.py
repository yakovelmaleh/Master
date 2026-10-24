from concurrent.futures import ThreadPoolExecutor
import importlib.util
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
            self.ledger.authorize("a", approval, {"pilot": "7.00001"}, self.config)
        self.ledger.authorize("a", approval, {"pilot": "7"}, self.config)
        self.assertIsNone(self.ledger.begin("a", "one", "6.99", "inference", {}))
        with self.assertRaisesRegex(ValueError, "exceed"):
            self.ledger.begin("a", "two", ".00001", "inference", {})
        self.ledger.dispatch("a", "one", 1)
        with self.assertRaisesRegex(ValueError, "Unconfirmed"):
            self.ledger.begin("a", "one", "7", "inference", {})
        self.ledger.finish("a", "one", {"score": .4}, actual="1")
        self.assertEqual(self.ledger.begin("a", "one", "7", "inference", {}), {"score": .4})
        full = self.approval("full")
        with self.assertRaisesRegex(ValueError, "cost limit"):
            self.ledger.authorize("a", full, {"full": "80.00001"}, self.config)
        self.ledger.authorize("a", full, {"full": "80"}, self.config)
        with self.assertRaisesRegex(ValueError, "Global"):
            self.ledger.authorize("b", approval, {"pilot": ".02"}, self.config)
        with self.assertRaisesRegex(ValueError, "credit|Credit"):
            self.ledger.authorize("a", {**full, "remaining_credit_usd": "99.99"}, {"full": "80"}, self.config)

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
        self.assertEqual(payload["sku"]["name"], "DeveloperTier")
        self.assertEqual(payload["tags"], {"master-study": "owner"})
        self.assertEqual(payload["properties"]["model"]["name"], "ft:model")
        backend.get_deployment = Mock(return_value={
            "properties": {"model": {"name": "ft:other"}, "provisioningState": "Succeeded"},
            "tags": {"master-study": "owner"}, "sku": {"name": "DeveloperTier"}})
        with self.assertRaisesRegex(ValueError, "differs"):
            backend.ready("name", "ft:model", "owner")

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
        for directory in ("prepared", "remote", "logs"):
            (source / directory).mkdir(parents=True)
            (source / directory / "secret.jsonl").write_text("private payload")
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
