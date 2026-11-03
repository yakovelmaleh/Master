import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

TASK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TASK))
spec = importlib.util.spec_from_file_location("recovery_job_launcher", TASK / "cluster/submit_jobs.py")
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)

from recovery import CHECKS, REPORT_SCHEMA, REVIEW_SCHEMA, implementation_hash
from protocol import digest, file_hash, read_json, study_id, write_json


class LauncherTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name).resolve()
        self.storage = self.home / "master-openai"
        self.root = self.storage / "openai-runs/fixture"
        self.config = {"batch_rows": 400}
        write_json(self.root / "study.json", {"config": self.config, "fixture": True})
        write_json(self.root / "prepared.json", {
            "entries": {"fixture": {"partitions": {"test": {"rows": 800}}}},
        })
        write_json(self.root / "sealed.json", {"fixture": "immutable seal"})
        write_json(self.root / "authorization.json", {"approval": {"scope": "full"}})
        self.review_path = self.home / ".local/state/master-openai/recovery-approved-fixture.json"
        self.review = {
            "schema": REVIEW_SCHEMA, "run": study_id(self.root),
            "study_sha256": digest(read_json(self.root / "study.json")),
            "prepared_sha256": file_hash(self.root / "prepared.json"),
            "seal_sha256": digest(read_json(self.root / "sealed.json")),
            "implementation_sha256": implementation_hash(), "remaining_test_batches": 2,
            "expires_at": "2099-01-01T00:00:00Z", "checks": {key: True for key in CHECKS},
        }
        write_json(self.review_path, self.review)
        self.review_hash = digest(self.review)
        write_json(self.root / "recovery/status/activate.json", {
            "status": "succeeded", "result": {
                "activated": True, "review_sha256": self.review_hash, "remaining_test_batches": 2,
            },
        })
        self.directory, self.manifest = launcher.paths(self.root, self.review_hash)
        self.args = SimpleNamespace(
            storage=self.storage, run_id="fixture", review=None,
            partition="main", time="2-00:00:00", mail_user="fixture@example.invalid", dry_run=False,
        )
        for item in (
            patch.object(Path, "home", return_value=self.home),
            patch.object(launcher, "frozen_study", return_value=self.config),
            patch.object(launcher, "check_approval"),
        ):
            item.start()
            self.addCleanup(item.stop)

    def submit(self):
        with patch.object(launcher.subprocess, "check_output", side_effect=["", "987654\n"]), patch("builtins.print"):
            return launcher.submit(self.args)

    def provider_process(self, command, **kwargs):
        stage = command[3]
        self.calls.append(stage)
        if self.fail_stage == stage:
            raise subprocess.CalledProcessError(1, command)
        if stage == "test":
            write_json(self.root / "recovery/status/test.json", {
                "status": "succeeded", "result": {"batch_rows": 400, "cell": "fixture"},
            })
        else:
            write_json(self.root / "recovery/llm_report.json", {
                "schema": REPORT_SCHEMA, "complete": True, "passed": False,
                "cells": [{} for _ in range(8)],
                "execution_recovery": {"review_sha256": self.review_hash},
            })

    def run_job(self, fail_stage=None):
        self.calls, self.fail_stage = [], fail_stage
        with patch.dict(os.environ, {"SLURM_JOB_ID": "987654"}), patch.object(
            launcher.subprocess, "run", side_effect=self.provider_process
        ):
            launcher.run_job(self.manifest)

    def test_submit_renders_all_mail_and_prevents_duplicate_submission(self):
        self.assertEqual(self.submit(), "987654")
        script = self.directory / "submit.sbatch"
        text = script.read_text()
        self.assertIn("#SBATCH --mail-type=ALL\n", text)
        self.assertIn("#SBATCH --mail-user=fixture@example.invalid\n", text)
        self.assertIn("#SBATCH --no-requeue\n", text)
        subprocess.run(["bash", "-n", str(script)], check=True)
        self.assertEqual(read_json(self.manifest)["status"], "submitted")
        with patch.object(launcher.subprocess, "check_output") as scheduler:
            with self.assertRaisesRegex(ValueError, "submission is already recorded"):
                launcher.submit(self.args)
            scheduler.assert_not_called()

    def test_legacy_partial_paste_marker_blocks_even_with_empty_queue(self):
        (self.root / "recovery/resume-20261103.started").write_text("123\n")
        with patch.object(launcher.subprocess, "check_output") as scheduler:
            with self.assertRaisesRegex(ValueError, "already started"):
                launcher.submit(self.args)
            scheduler.assert_not_called()

    def test_active_job_or_queue_failure_never_submits(self):
        for response in ("master-openai-recovery\n", subprocess.CalledProcessError(1, "squeue")):
            with self.subTest(response=response), patch.object(
                launcher.subprocess, "check_output", side_effect=[response]
            ) as scheduler:
                with self.assertRaises((ValueError, subprocess.CalledProcessError)):
                    launcher.submit(self.args)
                self.assertEqual(scheduler.call_count, 1)
                self.assertFalse(self.manifest.exists())

    def test_lost_sbatch_response_keeps_intent_and_blocks_resubmission(self):
        with patch.object(launcher.subprocess, "check_output", side_effect=[
            "", subprocess.CalledProcessError(1, "sbatch")
        ]):
            with self.assertRaises(subprocess.CalledProcessError):
                launcher.submit(self.args)
        self.assertEqual(read_json(self.manifest)["status"], "submission_unconfirmed")
        with patch.object(launcher.subprocess, "check_output") as scheduler:
            with self.assertRaisesRegex(ValueError, "already recorded"):
                launcher.submit(self.args)
            scheduler.assert_not_called()

    def test_exact_hash_selection_never_picks_latest_unrelated_review(self):
        write_json(self.review_path.with_name("recovery-approved-newer.json"),
                   {**self.review, "expires_at": "2100-01-01T00:00:00Z"})
        result = launcher.context(self.storage, "fixture")
        self.assertEqual(result[1], self.review_path)
        write_json(self.review_path.with_name("recovery-approved-copy.json"), self.review)
        with self.assertRaisesRegex(ValueError, "unique"):
            launcher.context(self.storage, "fixture")
        self.assertEqual(launcher.context(self.storage, "fixture", self.review_path)[2], self.review_hash)

    def test_expired_or_mismatched_review_blocks_before_scheduler_access(self):
        with patch.object(launcher.subprocess, "check_output") as scheduler:
            self.args.review = self.review_path.with_name("recovery-approved-wrong.json")
            write_json(self.args.review, {**self.review, "expires_at": "2100-01-01T00:00:00Z"})
            with self.assertRaisesRegex(ValueError, "differs"):
                launcher.submit(self.args)
            self.args.review = None
            self.review["expires_at"] = "2000-01-01T00:00:00Z"
            write_json(self.review_path, self.review)
            status_path = self.root / "recovery/status/activate.json"
            status = read_json(status_path)
            status["result"]["review_sha256"] = digest(self.review)
            write_json(status_path, status)
            with self.assertRaises(launcher.ControlError):
                launcher.submit(self.args)
            scheduler.assert_not_called()

    def test_worker_runs_exact_count_report_and_accepts_failed_performance_gates(self):
        self.submit()
        self.run_job()
        self.assertEqual(self.calls, ["test", "test", "report"])
        status = read_json(self.directory / "worker-status.json")
        self.assertEqual(status["status"], "succeeded")
        self.assertFalse(status["passed"])
        with self.assertRaisesRegex(ValueError, "already started"):
            self.run_job()
        self.assertEqual(self.calls, [])

    def test_worker_stops_at_first_error_without_retry_or_report(self):
        self.submit()
        with self.assertRaises(subprocess.CalledProcessError):
            self.run_job("test")
        self.assertEqual(self.calls, ["test"])
        self.assertEqual(read_json(self.directory / "worker-status.json")["status"], "failed")
        self.assertTrue(list((self.root / "recovery").glob("*.started")))

    def test_worker_rejects_report_with_wrong_review(self):
        self.submit()
        original = self.provider_process

        def wrong_report(command, **kwargs):
            original(command, **kwargs)
            if command[3] == "report":
                path = self.root / "recovery/llm_report.json"
                report = read_json(path)
                report["execution_recovery"]["review_sha256"] = "another review"
                write_json(path, report)

        with patch.object(self, "provider_process", side_effect=wrong_report):
            with self.assertRaisesRegex(ValueError, "incomplete or belongs"):
                self.run_job()
        status = read_json(self.directory / "worker-status.json")
        self.assertEqual(status["status"], "failed")
        self.assertEqual(status["completed_test_batches"], 2)

    def test_worker_can_start_after_submission_response_was_lost(self):
        self.submit()
        plan = read_json(self.manifest)
        plan.pop("job_id")
        plan["status"] = "submission_unconfirmed"
        write_json(self.manifest, plan)
        self.run_job()
        self.assertEqual(self.calls, ["test", "test", "report"])

    def test_mutated_script_or_job_identity_stops_before_work(self):
        self.submit()
        with patch.dict(os.environ, {"SLURM_JOB_ID": "111"}), self.assertRaisesRegex(ValueError, "identity"):
            launcher.run_job(self.manifest)
        (self.directory / "submit.sbatch").write_text("changed")
        with self.assertRaisesRegex(ValueError, "evidence or launcher changed"):
            self.run_job()
        self.assertEqual(self.calls, [])

    def test_dry_run_and_invalid_directives_do_not_submit(self):
        self.args.dry_run = True
        with patch.object(launcher.subprocess, "check_output") as scheduler, patch("builtins.print"):
            launcher.submit(self.args)
            scheduler.assert_not_called()
        self.assertFalse(self.manifest.exists())
        self.args.mail_user = "fixture@example.invalid\n#SBATCH --time=7-00:00:00"
        with self.assertRaisesRegex(ValueError, "directive"):
            launcher.submit(self.args)


if __name__ == "__main__":
    unittest.main()
