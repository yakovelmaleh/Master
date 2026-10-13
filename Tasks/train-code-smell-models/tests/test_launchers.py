import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest import mock

from Code_Smells_Detection.runtime import bundle, cluster, common
from Code_Smells_Detection.runtime.tests.support import RuntimeCase


class LauncherTests(RuntimeCase):
    def test_task_wrappers_dry_run_without_submission(self):
        self.frozen_study()
        environment = {**os.environ, "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"]}
        for kind, stage in (("prepare", "freeze"), ("detect", "labels"), ("train", "train")):
            output = subprocess.check_output([
                "bash", str(common.REPO / "Tasks/run_cluster_task.sh"), common.TASKS[kind],
                "--stage", stage, "--storage", str(self.storage), "--run-id", "test", "--dry-run",
            ], text=True, env=environment)
            self.assertIn("#SBATCH --array=0-0%1", output)
            self.assertIn("--stage " + stage, output)
            self.assertIn(str(self.root.parent.parent), output)
            subprocess.run(["bash", "-n"], input=output, text=True, check=True)

    def test_final_report_summary_bundle_dry_run(self):
        task = common.REPO / "Tasks/train-code-smell-models"
        with tempfile.TemporaryDirectory(prefix="bundle-test-", dir=task) as directory:
            metadata = Path(directory)
            target = {"language": None, "category": "any", "smell": "any"}
            cells = [{"source": "Apache", "target": "any_supported_smell", **target,
                      "family": family, "variant": variant, "status": "insufficient_data",
                      "reason": "fixture"}
                     for family in ("RF", "XGboost", "NN") for variant in ("baseline", "refactored")]
            common.write_json(metadata / "code_smell_report.json", {
                "schema": "code-smell-report-v1", "stage": "final-test",
                "sources": ["Apache"], "targets": {"any_supported_smell": target}, "results": cells,
            })
            (metadata / "private_source.py").write_text("not for review")
            (metadata / "model.joblib").write_bytes(b"not for review")
            output = subprocess.check_output([
                "bash", str(common.REPO / "Tasks/create-task-summary-pr/create_task_summary_pr.sh"),
                "--task", task.name, "--no-run", "--include", str(metadata), "--dry-run",
            ], text=True, stderr=subprocess.STDOUT)
            self.assertIn("Dry run complete", output)
            self.assertIn("TARGETS.csv", output)
            self.assertIn("TARGET_SUMMARY.md", output)
            self.assertNotIn("private_source.py", output)
            self.assertNotIn("model.joblib", output)

    def test_master_discovers_tasks_and_submission_is_bounded(self):
        listed = subprocess.check_output(["bash", str(common.REPO / "Tasks/run_cluster_task.sh"), "--list"], text=True)
        for task in common.TASKS.values():
            self.assertIn(task, listed)
        args = argparse.Namespace(kind="train", partition="main", time="1-00:00:00", mem="16G",
                                  cpus=6, mail_user="person@example.org", module="anaconda",
                                  conda_env="master-smells")
        text = cluster.render(args, [["python", "one.py"], ["python", "two.py"], ["python", "three.py"]],
                              self.storage / "run")
        self.assertIn("--array=0-2%2", text)
        self.assertIn("--mail-type=ALL", text)
        self.assertIn("logs/job-%A_%a.out", text)
        self.assertIn("logs/job-%A_%a.err", text)
        self.assertNotIn("--gres", text)
        subprocess.run(["bash", "-n"], input=text, text=True, check=True)

    def test_runtime_bundle_excludes_source_and_models_even_when_small(self):
        source = self.storage / "input"
        (source / "cache").mkdir(parents=True)
        (source / "cache/code.py").write_text("secret source")
        (source / "model.joblib").write_text("small model")
        common.write_json(source / "code_smell_report.json", {"schema": "code-smell-report-v1"})
        (source / "linked.json").symlink_to(source / "code_smell_report.json")
        copied = bundle.copy_bundle(source, self.storage / "output")
        self.assertEqual(["code_smell_report.json"], copied)
