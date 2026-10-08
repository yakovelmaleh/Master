import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd


TASK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TASK))
import jev_backend as backend
import run_evaluation as runner
from common import LEVELS, PROJECTS, digest, file_hash, read_json, write_json
from data_contract import load_project


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


launcher = load_module("jev_launcher", TASK / "cluster/submit_jobs.py")
summary = load_module("jev_summary", TASK.parent / "create-task-summary-pr/summarize_levels.py")
bundle = load_module("jev_bundle", backend.SHARED / "bundle_artifacts.py")


class NativeContractTests(unittest.TestCase):
    def test_probability_is_yes_not_confidence(self):
        self.assertEqual(backend.positive_probability([{"noul": .13}]), .13)
        for result in ([], None, [None], [{"confidence": .9}], [{"noul": True}],
                       [{"noul": -1}], [{"noul": float("nan")}], [{"noul": .8}, {"noul": .2}]):
            with self.subTest(result=result), self.assertRaises(ValueError):
                backend.positive_probability(result)

    def test_fixed_native_questions_use_absolute_word_thresholds(self):
        for level in LEVELS:
            question = backend.questions(level)[0]
            self.assertEqual(question["type"], "noul")
            self.assertIn(f"at least {level} words", question["instructions"])
            self.assertIn("after sprint entry", question["instructions"])
            self.assertNotIn("%", question["instructions"])
        with self.assertRaises(ValueError):
            backend.questions(99)

    def test_native_head_and_reviewed_loader_are_in_download_allowlist(self):
        self.assertIn("head.safetensors", backend.FILES)
        self.assertIn("spm.model", backend.FILES)
        self.assertEqual(len(backend.MODEL["revision"]), 40)
        self.assertEqual(sum(name.endswith(".py") for name in backend.FILES), 4)
        self.assertTrue(all(len(value) == 64 for value in backend.MODEL["reviewed_files"].values()))

    def test_reviewed_source_drift_fails_before_import(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "typed_decisions").mkdir()
            (root / "typed_decisions/__init__.py").write_text("changed")
            with self.assertRaisesRegex(ValueError, "Reviewed upstream file changed"):
                backend.verify_reviewed_files(root)

    def test_mocked_runtime_prepare_and_cache_hashes(self):
        fake_hub = types.ModuleType("huggingface_hub")
        fake_hub.snapshot_download = MagicMock()
        with tempfile.TemporaryDirectory() as directory, patch.dict(sys.modules, {"huggingface_hub": fake_hub}):
            cache = Path(directory)
            snapshot = cache / "snapshots" / backend.MODEL["revision"]
            snapshot.mkdir(parents=True)
            for name in backend.FILES:
                path = snapshot / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("fixture")
            fake_hub.snapshot_download.return_value = str(snapshot)
            with patch.object(backend, "verify_reviewed_files") as verify:
                backend.prepare(cache)
                self.assertEqual(fake_hub.snapshot_download.call_args.kwargs["revision"], backend.MODEL["revision"])
                self.assertEqual(set(fake_hub.snapshot_download.call_args.kwargs["allow_patterns"]), set(backend.FILES))
                resolved, _ = backend.snapshot_for(cache)
                self.assertEqual(resolved, snapshot.resolve())
                (snapshot / "head.safetensors").write_text("corrupt")
                with self.assertRaisesRegex(ValueError, "Corrupt Jev snapshot"):
                    backend.snapshot_for(cache)

    def test_summary_filter_excludes_native_weights_and_source_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            source, destination = Path(directory) / "source", Path(directory) / "bundle"
            source.mkdir()
            (source / "head.safetensors").write_text("fixture")
            (source / "model.safetensors").write_text("fixture")
            (source / "hf_report.json").write_text("{}")
            (source / "snapshots").mkdir()
            (source / "snapshots/encoder.py").write_text("external code")
            bundle.copy_tree(source, destination)
            self.assertEqual(set(p.name for p in destination.iterdir()), {"hf_report.json", "HF_OMITTED_FILES.csv"})


class LauncherTests(unittest.TestCase):
    def test_every_stage_through_master_launcher(self):
        with tempfile.TemporaryDirectory() as directory:
            for stage in ("setup", "prepare", "profile", "validate", "seal", "test", "report"):
                with self.subTest(stage=stage):
                    command = [
                        "bash", str(TASK.parent / "run_cluster_task.sh"), TASK.name,
                        "--stage", stage, "--partition", "main", "--cache", directory + "/cache",
                        "--storage", directory + "/storage", "--dry-run",
                    ]
                    gpu = stage in ("profile", "validate", "test")
                    if gpu:
                        command.extend(["--gres", "gpu:rtx_3090:1"])
                    result = subprocess.run(command, check=True, text=True, capture_output=True)
                    self.assertIn("#SBATCH --mail-user=yakovelm@post.bgu.ac.il", result.stdout)
                    self.assertIn("#SBATCH --mail-type=ALL", result.stdout)
                    self.assertEqual("#SBATCH --gres=" in result.stdout, gpu)
                    self.assertIn("--array=0-5%2" if stage in ("validate", "test") else "--array=0-0%1",
                                  result.stdout)
                    if stage == "setup":
                        self.assertIn("python -m pip install", result.stdout)
                        self.assertIn("&& python -m pip check", result.stdout)
                    else:
                        self.assertIn("python -u", result.stdout)
                    subprocess.run(["bash", "-n"], input=result.stdout, text=True, check=True)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_gpu_missing_fails_before_submission(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([
                sys.executable, str(TASK / "cluster/submit_jobs.py"), "--stage", "profile",
                "--partition", "main", "--cache", directory + "/cache",
                "--storage", directory + "/storage", "--dry-run",
            ], text=True, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("require exactly one", result.stderr)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_existing_hf_job_blocks_even_setup(self):
        with tempfile.TemporaryDirectory() as directory:
            argv = ["submit", "--stage", "setup", "--partition", "main", "--cache", directory + "/cache",
                    "--storage", directory + "/storage"]
            with patch.object(sys, "argv", argv), patch.object(launcher, "exclusive_lock") as lock, \
                    patch.object(launcher.subprocess, "check_output", return_value="master-hf-train\n") as command:
                lock.return_value.__enter__.return_value = None
                with self.assertRaisesRegex(ValueError, "Another Master HF"):
                    launcher.main()
                self.assertEqual(command.call_count, 1)


class EvaluationTests(unittest.TestCase):
    @staticmethod
    def frames(project, root):
        parts = []
        for stage in ("train", "validation", "test"):
            labels = np.array([0, 0, 1] * 6)
            parts.append(pd.DataFrame({
                "row_id": [f"{project}:{stage}-{i}" for i in range(len(labels))],
                "issue_key": [f"{stage}-{i}" for i in range(len(labels))],
                "source_dataset": project, "time_add_to_sprint": "2020-01-01",
                "model_text": np.where(labels, "ambiguous", "stable"),
                **{f"is_change_text_num_words_{level}": labels for level in LEVELS},
            }))
        return tuple(parts)

    def test_full_mocked_24_cell_workflow_and_seal(self):
        import data_contract

        class FakeModel:
            files = {"head.safetensors": "fixture-hash"}

            def predict(self, texts, level):
                return [.9 if value == "ambiguous" else .1 for value in texts]

            def coverage(self, texts):
                return {"rows": len(texts), "truncated_rows": 0}

        signature = {"mode": "test-fixture", "bootstrap_samples": 100, "seed": 7}
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(runner, "protocol", return_value=signature), \
                patch.object(data_contract, "load_project", side_effect=self.frames), \
                patch.object(data_contract, "baseline_predictions",
                             side_effect=lambda p, k, f: (np.full(len(f), .5),
                                                         {"model": "RF", "variant": "baseline"})):
            args = argparse.Namespace(storage=directory, cache=directory + "/cache", run_id="study")
            root = runner.study(args)
            with self.assertRaisesRegex(ValueError, "Validation incomplete"):
                runner.seal(root)
            for project in PROJECTS:
                args.project = project
                runner.validate(args, root, FakeModel())
                runner.validate(args, root, FakeModel())
                write_json(root / "status" / f"validate-{project}.json", {"status": "succeeded"})
            runner.seal(root)
            with self.assertRaisesRegex(ValueError, "cannot change"):
                runner.validate(args, root, FakeModel())
            output = Path(directory) / "bundle/artifacts/cluster-run/results/hf_report.json"
            runner.report(root, output)
            self.assertFalse(read_json(output)["all_24_passed"])
            for project in PROJECTS:
                args.project = project
                runner.test(args, root, FakeModel())
                runner.test(args, root, FakeModel())
            runner.report(root, output)
            result = read_json(output)
            self.assertEqual(len(result["cells"]), 24)
            self.assertTrue(result["all_24_passed"])
            summary.summarize(Path(directory) / "bundle")
            self.assertIn("0 of 24", (Path(directory) / "bundle/LEVEL_SUMMARY.md").read_text())
            changed = root / "final/Apache/5/test_predictions.csv"
            changed.write_text("changed")
            with self.assertRaisesRegex(ValueError, "Final result changed"):
                runner.report(root, output)

    def test_source_and_environment_changes_reject_resume(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(runner, "protocol", return_value={"version": 1}) as signature:
            args = argparse.Namespace(storage=directory, run_id="study")
            runner.study(args)
            signature.return_value = {"version": 2}
            with self.assertRaisesRegex(ValueError, "provenance changed"):
                runner.study(args)


if __name__ == "__main__":
    unittest.main()
