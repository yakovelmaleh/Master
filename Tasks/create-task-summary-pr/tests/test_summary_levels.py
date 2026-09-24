import csv
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


TASK = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("summarize_levels", TASK / "summarize_levels.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def make_run(run, level, succeeded=True):
    directory = run / f"qt/words_{level}/results"
    model = directory / f"model/words_{level}/RF/baseline"
    model.mkdir(parents=True)
    (run / "job_plan.json").write_text(json.dumps({
        "jobs": [{"project": "Qt", "level": level, "models": ["RF"],
                  "variants": ["baseline", "refactored"], "results": f"qt/words_{level}/results"}]
    }))
    (directory / "verification_manifest.json").write_text(json.dumps({
        "status": "succeeded" if succeeded else "failed"
    }))
    (model / "metrics.json").write_text(json.dumps({
        "test": {"auc_prc": 0.2, "average_precision": 0.21, "accuracy": 0.8, "roc_auc": 0.7}
    }))
    (model / "run_metadata.json").write_text("{}")
    for name in ["test_predictions.csv", "validation_predictions.csv", "model.joblib"]:
        (model / name).write_text("fixture\n")
    logs = directory.parent / "logs"
    logs.mkdir()
    (logs / "job-123.out").write_text("test log\n")


class SummaryTests(unittest.TestCase):
    def test_grouped_job_reports_missing_levels_and_failed_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory)
            root = bundle / "artifacts/cluster-run"
            results = root / "qt/results"
            model = results / "model/words_5/RF/baseline"
            model.mkdir(parents=True)
            (root / "job_plan.json").write_text(json.dumps({
                "jobs": [{
                    "project": "Qt", "levels": [5, 10, 15, 20],
                    "models": ["RF"], "variants": ["baseline"],
                    "results": "qt/results",
                }],
            }))
            manifest = results / "verification_manifest.json"
            manifest.write_text(json.dumps({"status": "succeeded"}))
            (model / "metrics.json").write_text(json.dumps({"test": {"auc_prc": 0.2}}))
            for name in ["run_metadata.json", "test_predictions.csv",
                         "validation_predictions.csv", "model.joblib"]:
                (model / name).write_text("{}")
            module.summarize(bundle)
            with (bundle / "LEVELS.csv").open() as stream:
                coverage = list(csv.DictReader(stream))
            self.assertEqual(len(coverage), 4)
            self.assertEqual(coverage[0]["coverage"], "complete")
            self.assertTrue(all(row["missing_files"] == "metrics.json" for row in coverage[1:]))
            manifest.write_text(json.dumps({"status": "failed"}))
            module.summarize(bundle)
            with (bundle / "LEVELS.csv").open() as stream:
                coverage = list(csv.DictReader(stream))
            self.assertTrue(all(row["coverage"] == "incomplete" for row in coverage))
            with (bundle / "RESULTS.csv").open() as stream:
                self.assertEqual(len(list(csv.DictReader(stream))), 1)

    def test_all_levels_and_missing_variants_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for level in [5, 10, 15, 20]:
                make_run(root / f"artifacts/cluster-runs/k{level}", level)
            module.summarize(root)
            with (root / "LEVELS.csv").open() as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 8)
            self.assertEqual({r["level"] for r in rows}, {"5", "10", "15", "20"})
            self.assertEqual(sum(r["coverage"] == "incomplete" for r in rows), 4)
            with (root / "RESULTS.csv").open() as stream:
                metrics = list(csv.DictReader(stream))
            self.assertEqual(len(metrics), 4)
            self.assertEqual(metrics[0]["auc_prc"], "0.2")
            self.assertEqual(metrics[0]["average_precision"], "0.21")

    def test_shell_collects_multiple_runs_and_logs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "Master"
            task = root / "Tasks/create-task-summary-pr"
            task.mkdir(parents=True)
            for name in ["create_task_summary_pr.sh", "summarize_levels.py"]:
                shutil.copy2(TASK / name, task / name)
            selected = root / "Tasks/demo"
            selected.mkdir()
            (selected / "README.md").write_text("Test task\n")
            for level in [5, 10, 15, 20]:
                make_run(selected / f"cluster_runs/k{level}", level)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "remote", "add", "origin",
                            "https://github.com/yakovelmaleh/Master.git"], check=True)
            subprocess.run(["git", "-C", str(root), "add", "Tasks"], check=True)
            subprocess.run(["git", "-C", str(root), "-c", "user.name=Test", "-c",
                            "user.email=test@example.invalid", "commit", "-qm", "fixture"], check=True)
            command = ["bash", str(task / "create_task_summary_pr.sh"), "--task", "demo", "--dry-run"]
            for level in [5, 10, 15, 20]:
                command.extend(["--run-id", f"k{level}"])
            result = subprocess.run(command, check=True, capture_output=True, text=True)
            for level in [5, 10, 15, 20]:
                self.assertIn(f"artifacts/cluster-runs/k{level}/qt/words_{level}/logs/job-123.out", result.stdout)
                self.assertIn(f"words_{level}/RF/baseline/metrics.json", result.stdout)
            self.assertIn("LEVELS.csv", result.stdout)
            self.assertIn("RESULTS.csv", result.stdout)
            self.assertIn("Standard levels absent: none", result.stdout)


if __name__ == "__main__":
    unittest.main()
