import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import numpy as np


TASK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TASK))
import common
from common import LEVELS, PROJECTS, artifact_hashes, check_artifact, digest, read_json, write_json
from data_contract import load_project, verify_frames
from evaluate import final_metrics, gates
from model_adapters import sigmoid_head
import run_experiment as runner
from bundle_artifacts import copy_tree
from check_git_artifacts import forbidden
from unstable_model.evaluation import calculate_metrics


def module_at(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


launcher = module_at("hf_submit", TASK / "cluster/submit_jobs.py")
publisher = module_at("hf_publish", TASK.parent / "publish-hf-instability-models/publish_model.py")
preparer = module_at("hf_prepare", TASK.parent / "prepare-hf-instability-models/prepare_models.py")
summary = module_at("hf_summary", TASK.parent / "create-task-summary-pr/summarize_levels.py")
packager = module_at("hf_package", TASK.parent / "create-investigation-pr/package_artifacts.py")


class ContractTests(unittest.TestCase):
    def test_all_24_historical_partitions_match(self):
        contract = read_json(TASK / "reference_contract.json")
        with tempfile.TemporaryDirectory() as directory:
            for project in PROJECTS:
                frames = load_project(project, directory)
                verify_frames(frames, contract["projects"][project])
                changed = tuple(frame.copy() for frame in frames)
                changed[0].iloc[0, changed[0].columns.get_loc("is_change_text_num_words_5")] ^= 1
                with self.assertRaisesRegex(ValueError, "label mismatch"):
                    verify_frames(changed, contract["projects"][project])

    def test_external_storage_and_identifiers(self):
        with self.assertRaises(ValueError):
            common.external_path(TASK / "cache")
        for value in ("../other", "test\n#SBATCH", "a/b", ""):
            with self.assertRaises(ValueError):
                common.slug(value)
        self.assertEqual(common.slug("hf-study-01"), "hf-study-01")

    def test_checkpoint_drift_and_symlinks_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "head.safetensors").write_text("fixture")
            initial = artifact_hashes(root)
            check_artifact(root, initial)
            (root / "head.safetensors").write_text("changed")
            with self.assertRaises(ValueError):
                check_artifact(root, initial)
            (root / "linked").symlink_to(root / "head.safetensors")
            with self.assertRaises(ValueError):
                artifact_hashes(root)

    def test_bounded_config(self):
        config = read_json(TASK / "experiment.json")
        runner.validate_config(config)
        for change in ({"max_length": 32768}, {"batch_size": 0}, {"top_families": 3},
                       {"learning_rates": [0.1, 0.2, 0.3]}, {"dtype": "automatic"}):
            with self.assertRaises(ValueError):
                runner.validate_config({**config, **change})


class MetricTests(unittest.TestCase):
    def test_constant_score_does_not_pass(self):
        metrics = calculate_metrics([0, 0, 0, 1], [.5] * 4, .5)
        self.assertEqual(metrics["auc_prc"], .625)
        self.assertFalse(gates(metrics, {"average_precision": .1})["passed"])

    def test_strict_target_and_missing_cells(self):
        metrics = {"auc_prc": .6, "average_precision": .6, "roc_auc": .7, "positive_rate": .25}
        self.assertTrue(gates(metrics, {"average_precision": .4})["passed"])
        for changed in ({"auc_prc": .5}, {"average_precision": .4}, {"roc_auc": .5}, {"auc_prc": None}):
            self.assertFalse(gates({**metrics, **changed}, {"average_precision": .4})["passed"])
        self.assertFalse(gates(metrics, {"average_precision": None})["passed"])

    def test_paired_intervals_are_repeatable_and_match_sklearn(self):
        from sklearn.metrics import auc, precision_recall_curve, average_precision_score

        y = np.array([0, 0, 1, 1] * 4)
        p = np.array([.1, .4, .4, .9] * 4)
        baseline = np.full(len(y), .5)
        a = final_metrics(y, p, baseline, .5, 120, 7)
        b = final_metrics(y, p, baseline, .5, 120, 7)
        self.assertEqual(a, b)
        precision, recall, _ = precision_recall_curve(y, p)
        self.assertAlmostEqual(a["test"]["auc_prc"], auc(recall, precision))
        self.assertAlmostEqual(a["test"]["average_precision"], average_precision_score(y, p))
        self.assertIsNotNone(a["uncertainty"]["difference_95"]["average_precision"])

    def test_head_roundtrip_formula(self):
        from scipy.special import expit

        x = np.array([[1., 2.], [3., 4.]])
        head = {"weight": np.array([[.4, -.2]]), "bias": np.array([.3])}
        np.testing.assert_allclose(sigmoid_head(x, head), expit(x @ head["weight"][0] + .3))


class LauncherTests(unittest.TestCase):
    def args(self, **changes):
        values = dict(kind="train", stage="frozen", gres="gpu:a100:1", partition="gpu",
                      time="1-00:00:00", mem="32G", cpus=6, mail_user=None,
                      module="anaconda", conda_env="master-hf")
        return argparse.Namespace(**{**values, **changes})

    def test_gpu_array_limit_and_shell_syntax(self):
        text = launcher.render(self.args(), Path("/cluster/logs/run"),
                               [["python", "/path with spaces/runner.py"]] * 6, {})
        self.assertIn("--array=0-5%2", text)
        self.assertIn("--gres=gpu:a100:1", text)
        self.assertIn("HF_HUB_OFFLINE=1", text)
        subprocess.run(["bash", "-n"], input=text, text=True, check=True)

    def test_profile_is_one_job_and_no_gpu_defaults(self):
        with self.assertRaises(ValueError):
            launcher.render(self.args(kind="research", stage="profile"), Path("/logs"), [["python"]] * 2, {})
        for gres in (None, "gpu:a100:2", "gpu:a100:1\n#SBATCH"):
            with self.assertRaises(ValueError):
                launcher.render(self.args(gres=gres), Path("/logs"), [["python"]], {})

    def test_publishing_requests_gpu_for_reload(self):
        with self.assertRaises(ValueError):
            launcher.render(self.args(kind="publish", stage=None, gres=None), Path("/logs"), [["python"]], {})

    def test_all_task_launchers_default_mail_and_allow_override(self):
        with tempfile.TemporaryDirectory() as directory:
            stages = {
                "research": ["--stage", "probe"],
                "prepare": [],
                "train": ["--stage", "frozen", "--run-id", "mail-test", "--gres", "gpu:a100:1"],
                "publish": ["--checkpoint", directory + "/checkpoint", "--hf-repo", "example/model",
                            "--approve-export", "--gres", "gpu:a100:1"],
            }
            for kind, task in launcher.TASKS.items():
                for recipient in (None, "other@example.invalid"):
                    with self.subTest(kind=kind, recipient=recipient):
                        command = [
                            "bash", str(TASK.parent / "run_cluster_task.sh"), task,
                            "--partition", "main", "--storage", directory + "/storage",
                            "--cache", directory + "/cache", "--dry-run", *stages[kind],
                        ]
                        if recipient is not None:
                            command.extend(["--mail-user", recipient])
                        result = subprocess.run(command, text=True, capture_output=True, check=True)
                        expected = recipient or "yakovelm@post.bgu.ac.il"
                        self.assertIn(f"#SBATCH --mail-user={expected}\n", result.stdout)
                        self.assertIn("#SBATCH --mail-type=ALL\n", result.stdout)
                        self.assertEqual(result.stdout.count("#SBATCH --mail-user="), 1)
                        subprocess.run(["bash", "-n"], input=result.stdout, text=True, check=True)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_dry_run_has_no_side_effects_and_master_discovers_tasks(self):
        with tempfile.TemporaryDirectory() as directory:
            command = [
                sys.executable, str(TASK / "cluster/submit_jobs.py"), "train",
                "--stage", "frozen", "--run-id", "dry-test", "--partition", "gpu",
                "--gres", "gpu:a100:1", "--storage", directory + "/storage",
                "--cache", directory + "/cache", "--dry-run",
            ]
            result = subprocess.run(command, text=True, capture_output=True, check=True)
            self.assertIn("--array=0-11%2", result.stdout)
            self.assertEqual(list(Path(directory).iterdir()), [])
        result = subprocess.check_output(["bash", str(TASK.parent / "run_cluster_task.sh"), "--list"], text=True)
        for task in launcher.TASKS.values():
            self.assertIn(task, result)


class BundleTests(unittest.TestCase):
    def test_only_allowlisted_metadata_not_weights_or_links(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, destination = root / "source", root / "bundle"
            source.mkdir()
            (source / "hf_report.json").write_text("{}")
            (source / "tiny.safetensors").write_text("not large")
            (source / "issues.jsonl").write_text("raw issue")
            (source / "checkpoint").mkdir()
            (source / "checkpoint/head.json").write_text("weights disguised as metadata")
            (source / "metrics.json").symlink_to(source / "tiny.safetensors")
            copy_tree(source, destination)
            self.assertTrue((destination / "hf_report.json").exists())
            self.assertEqual(set(p.name for p in destination.iterdir()), {"hf_report.json", "HF_OMITTED_FILES.csv"})

    def test_legacy_packaging_unchanged_hf_small_weights_excluded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            results, logs = root / "results", root / "logs"
            results.mkdir()
            logs.mkdir()
            (results / "tiny.safetensors").write_text("fixture")
            packager.package(results, logs, root / "legacy")
            self.assertTrue((root / "legacy/artifacts/results/tiny.safetensors").exists())
            (results / "metrics.json").symlink_to(results / "tiny.safetensors")
            packager.package(results, logs, root / "hf", exclude_models=True)
            self.assertFalse((root / "hf/artifacts/results/tiny.safetensors").exists())
            self.assertFalse((root / "hf/artifacts/results/metrics.json").exists())
            self.assertIn("model_artifact_not_for_git", (root / "hf/OMITTED_FILES.csv").read_text())

    def test_staged_artifact_guard(self):
        for path in ("Tasks/new/model.safetensors", "Tasks/new/adapter_model.bin",
                     "Tasks/train-hf-instability-within-project/cluster_runs/run/metrics.json"):
            self.assertTrue(forbidden(path))
        self.assertFalse(forbidden("Tasks/research-hf-instability-models/models.json"))

    def test_hf_summary_has_all_cells_without_fake_joblib(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cells = [{"project": project, "level": level, "model": "modernbert",
                      "test": {"auc_prc": .4}, "checkpoint_files": {"head.safetensors": "hash"},
                      "test_predictions_sha256": "hash"} for project in PROJECTS for level in LEVELS]
            path = root / "artifacts/cluster-run/results/hf_report.json"
            write_json(path, {"schema": "hf-instability-report-v1", "stage": "final-test", "cells": cells})
            summary.summarize(root)
            self.assertIn("0 of 24", (root / "LEVEL_SUMMARY.md").read_text())
            cells.pop()
            write_json(path, {"schema": "hf-instability-report-v1", "stage": "final-test", "cells": cells})
            with self.assertRaises(ValueError):
                summary.summarize(root)


class PublishingTests(unittest.TestCase):
    def test_public_destination_rejected_before_upload(self):
        api = MagicMock()
        api.repo_info.return_value.private = False
        with self.assertRaises(ValueError):
            publisher.ensure_private(api, "owner/model")
        api.upload_folder.assert_not_called()
        api.create_repo.assert_called_once_with(repo_id="owner/model", private=True, exist_ok=True, repo_type="model")

    def test_private_destination_and_forbidden_export(self):
        api = MagicMock()
        api.repo_info.return_value.private = True
        api.repo_info.return_value.sha = "fixed-commit"
        self.assertEqual(publisher.ensure_private(api, "owner/model"), "fixed-commit")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "head.safetensors").write_text("fixture")
            (root / "inference.json").write_text("{}")
            publisher.export_files(root)
            (root / "raw_issues.jsonl").write_text("private content")
            with self.assertRaises(ValueError):
                publisher.export_files(root)


class PreparationTests(unittest.TestCase):
    def test_mocked_pinned_runtime_download_and_offline_check(self):
        import types

        fake = types.ModuleType("huggingface_hub")
        fake.HfApi = MagicMock()
        fake.HfApi.return_value.model_info.return_value.siblings = []
        fake.snapshot_download = MagicMock()
        with tempfile.TemporaryDirectory() as directory, patch.dict(sys.modules, {"huggingface_hub": fake}):
            cache = Path(directory)
            revision = common.model_registry()["modernbert"]["revision"]
            snapshot = cache / "snapshots" / revision
            snapshot.mkdir(parents=True)
            (snapshot / "config.json").write_text("{}")
            (snapshot / "model.safetensors").write_text("test fixture, not model weights")
            fake.snapshot_download.return_value = str(snapshot)
            preparer.prepare(cache, ["modernbert"])
            self.assertEqual(fake.snapshot_download.call_args.kwargs["revision"], revision)
            self.assertFalse(fake.snapshot_download.call_args.kwargs["local_files_only"])
            self.assertTrue((cache / "ready/modernbert.json").exists())
            preparer.prepare(cache, ["modernbert"], offline=True)
            self.assertTrue(fake.snapshot_download.call_args.kwargs["local_files_only"])
            (snapshot / "model.safetensors.index.json").write_text(
                json.dumps({"weight_map": {"a": "missing.safetensors"}}))
            with self.assertRaisesRegex(ValueError, "Missing weight shards"):
                preparer.prepare(cache, ["modernbert"], offline=True)


class WorkflowTests(unittest.TestCase):
    def test_mocked_runtime_through_all_24_final_cells(self):
        import pandas as pd

        class FakeBackend:
            def __init__(self, *args, **kwargs):
                pass

            def embeddings(self, texts, storage):
                return np.asarray([[1., 0.] if text == "stable" else [0., 1.] for text in texts],
                                  dtype=np.float32)

            def length_report(self, texts):
                return {"rows": len(texts), "truncated_rows": 0}

            def close(self):
                pass

        def frames(project, storage):
            output = []
            for partition in ("train", "validation", "test"):
                rows = 30 if partition == "train" else 12
                y = np.arange(rows) % 3 == 0
                frame = pd.DataFrame({
                    "row_id": [f"{project}:{partition}-{i}" for i in range(rows)],
                    "source_dataset": project, "issue_key": [f"{partition}-{i}" for i in range(rows)],
                    "time_add_to_sprint": "2020-01-01", "model_text": np.where(y, "changes", "stable"),
                    **{f"is_change_text_num_words_{k}": y.astype(int) for k in LEVELS},
                })
                output.append(frame)
            return tuple(output)

        def save(path, weight, bias):
            with Path(path).open("wb") as stream:
                np.savez(stream, weight=weight, bias=bias)

        def load(path):
            with np.load(path, allow_pickle=False) as value:
                return {key: value[key] for key in value.files}

        def prediction(path, cache, frame):
            return sigmoid_head(FakeBackend().embeddings(frame.model_text, cache),
                                load(Path(path) / "head.safetensors"))

        config = {**read_json(TASK / "experiment.json"), "structured": [False],
                  "linear_c": [1.], "class_weights": [None], "bootstrap_samples": 100}
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(runner, "versions", return_value={"test": "mock"}), \
                patch.object(runner, "load_project", side_effect=frames), \
                patch.object(runner, "TextBackend", FakeBackend), \
                patch.object(runner, "save_head", side_effect=save), \
                patch.object(runner, "load_head", side_effect=load), \
                patch.object(runner, "predict_checkpoint", side_effect=prediction), \
                patch.object(runner, "baseline_predictions",
                             side_effect=lambda p, k, f: (np.full(len(f), .5),
                                                         {"model": "RF", "variant": "baseline"})):
            args = argparse.Namespace(storage=directory, cache=directory + "/cache", run_id="test",
                                      models=["modernbert"], model="modernbert")
            root = runner.initialize_study(args, config)
            for project in PROJECTS:
                args.project = project
                runner.frozen(args, config, root)
                runner.frozen(args, config, root)
                for stage in ("frozen", "finetune"):
                    write_json(root / "status" / f"{stage}-{project}-modernbert.json", {"status": "succeeded"})
            runner.seal(root)
            for project in PROJECTS:
                args.project = project
                runner.test_selected(args, config, root)
                runner.test_selected(args, config, root)
            runner.report(root, root / "hf_report.json")
            report = read_json(root / "hf_report.json")
            self.assertEqual(len(report["cells"]), 24)
            self.assertTrue(report["all_24_passed"])
            with self.assertRaisesRegex(ValueError, "provenance changed"):
                runner.initialize_study(args, {**config, "seed": 999})


@unittest.skipUnless(importlib.util.find_spec("torch") and importlib.util.find_spec("transformers"),
                     "Requires isolated HF dependencies; no pretrained downloads are used")
class TinyModelTests(unittest.TestCase):
    def test_pooling_padding_and_empty_rows(self):
        import torch
        from model_adapters import pool

        hidden = torch.tensor([[[1., 0.], [0., 1.], [9., 9.]]])
        mask = torch.tensor([[1, 1, 0]])
        torch.testing.assert_close(pool(hidden, mask, "last"), torch.tensor([[0., 1.]]))
        torch.testing.assert_close(pool(hidden, mask, "mean"),
                                   torch.tensor([[2 ** -.5, 2 ** -.5]]))
        with self.assertRaises(ValueError):
            pool(hidden, torch.zeros_like(mask), "mean")

    def test_random_modernbert_forward_backward_and_adapter_roundtrip(self):
        import torch
        from transformers import AutoModel, ModernBertConfig
        from peft import LoraConfig, get_peft_model, PeftModel
        from model_adapters import pool

        config = ModernBertConfig(vocab_size=64, hidden_size=16, intermediate_size=32,
                                 num_hidden_layers=2, num_attention_heads=2,
                                 max_position_embeddings=64, local_attention=16, reference_compile=False)
        torch.manual_seed(7)
        base = AutoModel.from_config(config, attn_implementation="eager")
        pristine = {k: v.clone() for k, v in base.state_dict().items()}
        model = get_peft_model(base, LoraConfig(r=2, lora_alpha=4, target_modules=["Wqkv", "Wo"]))
        inputs = {"input_ids": torch.tensor([[1, 2, 3, 4], [4, 3, 2, 1]]),
                  "attention_mask": torch.ones(2, 4, dtype=torch.long)}
        model.train()
        pool(model(**inputs).last_hidden_state, inputs["attention_mask"], "mean").sum().backward()
        self.assertTrue(any(p.grad is not None for p in model.parameters() if p.requires_grad))
        model.eval()
        expected = model(**inputs).last_hidden_state.detach()
        with tempfile.TemporaryDirectory() as directory:
            model.save_pretrained(directory)
            other = AutoModel.from_config(config, attn_implementation="eager")
            other.load_state_dict(pristine)
            loaded = PeftModel.from_pretrained(other, directory).eval()
            torch.testing.assert_close(expected, loaded(**inputs).last_hidden_state)


if __name__ == "__main__":
    unittest.main()
