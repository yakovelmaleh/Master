from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

TASK = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("sufficiency_launcher", TASK / "cluster/submit_jobs.py")
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


class LauncherTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.storage = Path(temporary.name).resolve()
        self.study = {"config": {"max_input_tokens": 10240}, "fixture": True}
        for mock in (
            patch.object(launcher, "signature", return_value=self.study),
            patch.object(launcher.Path, "home", return_value=self.storage),
        ):
            mock.start()
            self.addCleanup(mock.stop)
        self.args = ["--storage", str(self.storage)]
        self.directory = self.storage / "openai-sufficiency-runs/openai-sufficiency-04/jobs/prepare"
        self.manifest = self.directory / "submission.json"

    def submit(self):
        with patch.object(launcher.subprocess, "check_output", side_effect=["", "123;cluster\n"]) as calls:
            with redirect_stdout(io.StringIO()):
                launcher.main(self.args)
        self.assertEqual([call.args[0][0] for call in calls.call_args_list], ["squeue", "sbatch"])
        return launcher.read_json(self.manifest)

    def test_dry_run_and_master_discovery_do_not_submit(self):
        output = io.StringIO()
        with patch.object(launcher.subprocess, "check_output") as calls, redirect_stdout(output):
            launcher.main([*self.args, "--dry-run"])
        calls.assert_not_called()
        self.assertFalse(self.manifest.exists())
        script = output.getvalue()
        self.assertIn("#SBATCH --mail-type=ALL", script)
        self.assertIn("#SBATCH --no-requeue", script)
        self.assertNotIn("--gres", script)
        subprocess.run(["bash", "-n"], input=script, text=True, check=True)
        listed = subprocess.check_output(["bash", str(TASK.parent / "run_cluster_task.sh"), "--list"], text=True)
        self.assertIn(TASK.name, listed.splitlines())
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            launcher.main([*self.args, "--stage", "preflight"])

    def test_records_intent_and_blocks_duplicate_or_active_jobs(self):
        plan = self.submit()
        self.assertEqual(plan["status"], "submitted")
        self.assertEqual(plan["job_id"], "123")
        with patch.object(launcher.subprocess, "check_output") as calls:
            with self.assertRaisesRegex(ValueError, "already recorded"):
                launcher.main(self.args)
            calls.assert_not_called()
        with patch.object(launcher.subprocess, "check_output", return_value="master-openai-other\n") as calls:
            with self.assertRaisesRegex(ValueError, "already active"):
                launcher.main([*self.args, "--run-id", "other"])
            self.assertEqual(calls.call_count, 1)

    def test_master_pull_dispatches_to_the_new_launcher(self):
        binaries = self.storage / "bin"
        interpreter = self.storage / ".conda/envs/master-openai/bin/python"
        binaries.mkdir()
        interpreter.parent.mkdir(parents=True)
        git = binaries / "git"
        git.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$HOME/git-args"\n')
        interpreter.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
        git.chmod(0o700)
        interpreter.chmod(0o700)
        with patch.dict(launcher.os.environ, {
            "HOME": str(self.storage),
            "PATH": str(binaries) + launcher.os.pathsep + launcher.os.environ["PATH"],
        }):
            output = subprocess.check_output([
                "bash", str(TASK.parent / "run_cluster_task.sh"),
                "--pull", TASK.name, "--stage", "prepare", "--dry-run",
            ], text=True)
        self.assertEqual((self.storage / "git-args").read_text().splitlines(),
                         ["-C", str(TASK.parent.parent), "pull", "--ff-only"])
        self.assertEqual(output.splitlines(), [
            str(TASK / "cluster/submit_jobs.py"), "--stage", "prepare", "--dry-run",
        ])

    def test_lost_submission_response_preserves_intent(self):
        with patch.object(launcher.subprocess, "check_output", side_effect=["", RuntimeError("lost reply")]):
            with self.assertRaises(RuntimeError):
                launcher.main(self.args)
        self.assertEqual(launcher.read_json(self.manifest)["status"], "submission_unconfirmed")
        with patch.object(launcher.subprocess, "check_output") as calls, self.assertRaises(ValueError):
            launcher.main(self.args)
        calls.assert_not_called()

    def test_inspection_requires_consent_and_dispatches_only_the_bounded_helper(self):
        root = self.directory.parent.parent
        launcher.write_json(root / "study.json", self.study)
        launcher.write_json(root / "prepared.json", {})
        args = [*self.args, "--stage", "inspect-storage"]
        with patch.object(launcher.subprocess, "check_output") as commands, redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                launcher.main(args)
            commands.assert_not_called()
        with patch.object(launcher.subprocess, "check_output", side_effect=["", "456"]), redirect_stdout(io.StringIO()):
            launcher.main([*args, "--execute-approved-inspection"])
        directory = root / "jobs/inspect-storage"
        self.assertIn("AzureCliCredential", (directory / "submit.sbatch").read_text())

        def inspected(command, check):
            self.assertTrue(check)
            self.assertEqual(command[2], str(TASK / "cluster/inspect_storage.py"))
            self.assertIn("--execute-approved-inspection", command)
            launcher.write_json(directory / "inspection.json", {
                "schema": "sufficiency-storage-inspection-v1", "authorizes_inference": False,
                "model_calls": 0, "inspection_request_limit": 100, "inspection_requests_used": 20,
            })

        with patch.dict(launcher.os.environ, {"SLURM_JOB_ID": "456"}), patch.object(
            launcher.subprocess, "run", side_effect=inspected
        ) as run, redirect_stdout(io.StringIO()):
            original_hash = launcher.file_hash
            with patch.object(launcher, "file_hash", side_effect=lambda p: (
                "changed" if Path(p) == TASK / "cluster/inspect_storage.py" else original_hash(p)
            )):
                with self.assertRaisesRegex(ValueError, "inspection implementation changed"):
                    launcher.run_job(directory / "submission.json")
                run.assert_not_called()
            launcher.run_job(directory / "submission.json")
            run.assert_called_once()
        self.assertTrue(launcher.read_json(directory / "worker-status.json")["inspected"])

    def test_worker_runs_only_preparation_and_blocks_reentry(self):
        self.submit()
        root = self.directory.parent.parent

        def prepared(command, check):
            self.assertTrue(check)
            self.assertEqual(command[3], "prepare")
            self.assertNotIn("--execute-approved-stage", command)
            launcher.write_json(root / "study.json", self.study)
            launcher.write_json(root / "prepared.json", {})
            launcher.write_json(root / "approval.template.json", {})

        with patch.dict(launcher.os.environ, {"SLURM_JOB_ID": "123"}), patch.object(
            launcher.subprocess, "run", side_effect=prepared
        ) as run, redirect_stdout(io.StringIO()):
            launcher.run_job(self.manifest)
            self.assertEqual(launcher.read_json(self.directory / "worker-status.json")["status"], "succeeded")
            with self.assertRaises(FileExistsError):
                launcher.run_job(self.manifest)
            self.assertEqual(run.call_count, 1)

    def test_worker_refuses_changed_provenance_and_records_preparation_failure(self):
        self.submit()
        with patch.dict(launcher.os.environ, {"SLURM_JOB_ID": "123"}), patch.object(
            launcher.subprocess, "run"
        ) as run:
            with patch.object(launcher, "signature", return_value={"changed": True}):
                with self.assertRaisesRegex(ValueError, "provenance changed"):
                    launcher.run_job(self.manifest)
            run.assert_not_called()
            run.side_effect = subprocess.CalledProcessError(1, ["prepare"])
            with self.assertRaises(subprocess.CalledProcessError):
                launcher.run_job(self.manifest)
        self.assertEqual(launcher.read_json(self.directory / "worker-status.json")["status"], "failed")
        self.assertTrue((self.directory / "worker.started").exists())

    def model_fixture(self, scope="pilot"):
        self.root = self.directory.parent.parent
        self.control = self.storage / "control"
        self.approval = self.control / "model-approval.json"
        self.storage_approval = self.control / "cloud-approval.json"
        launcher.write_json(self.root / "study.json", self.study)
        launcher.write_json(self.root / "prepared.json", {})
        approval = {"scope": scope, "authority_sha256": "authority", "storage_reserve_usd": "5.30"}
        launcher.write_json(self.approval, approval)
        launcher.write_json(self.root / "authorization.json", {"approval": approval})
        launcher.write_json(self.storage_approval, {
            "authority_sha256": "authority", "storage": {"reserve_usd": "5.30"},
        })
        for mock in (
            patch.object(launcher, "CONTROL", self.control),
            patch.object(launcher, "check_approval"),
            patch.object(launcher, "validate_storage"),
            patch.object(launcher, "binding_at", return_value={}),
        ):
            mock.start()
            self.addCleanup(mock.stop)

    def submit_model(self, stage, label=None):
        args = [*self.args, "--stage", stage, "--execute-approved-stage"]
        if stage == "preflight":
            args += ["--approval", str(self.approval)]
        if label is not None:
            args += ["--job-label", label]
        with patch.object(launcher.subprocess, "check_output", side_effect=["", "123"]), redirect_stdout(io.StringIO()):
            launcher.main(args)
        return launcher.job_directory(self.root, stage, label)

    def test_model_stages_require_separate_consent_and_correct_flags(self):
        with patch.object(launcher.subprocess, "check_output") as calls, redirect_stderr(io.StringIO()):
            for stage in launcher.MODEL_STAGES:
                with self.subTest(stage=stage), self.assertRaises(SystemExit):
                    launcher.main([*self.args, "--stage", stage])
            for flags in (
                ["--stage", "preflight", "--execute-approved-stage"],
                ["--stage", "smoke", "--execute-approved-stage", "--approval", "/unused"],
                ["--stage", "prepare", "--execute-approved-stage"],
                ["--stage", "inspect-storage", "--job-label", "again"],
                ["--stage", "smoke", "--execute-approved-stage", "--execute-approved-inspection"],
            ):
                with self.subTest(flags=flags), self.assertRaises(SystemExit):
                    launcher.main([*self.args, *flags])
            calls.assert_not_called()

    def test_model_stages_dispatch_once_and_keep_job_local_results(self):
        self.model_fixture(scope="full")
        for stage in launcher.MODEL_STAGES:
            with self.subTest(stage=stage):
                directory = self.submit_model(stage)
                script = (directory / "submit.sbatch").read_text()
                self.assertIn("AzureCliCredential", script)
                subprocess.run(["bash", "-n"], input=script, text=True, check=True)

                def completed(command, check):
                    self.assertTrue(check)
                    self.assertEqual(command[2:4], [str(TASK / "run_experiment.py"), stage])
                    self.assertIn("--execute-approved-stage", command)
                    self.assertEqual("--approval" in command, stage == "preflight")
                    self.assertNotIn("--execute-approved-inspection", command)
                    launcher.write_json(self.root / "status" / f"{stage}.json", {
                        "status": "succeeded", "result": {"fixture": stage},
                    })

                with patch.dict(launcher.os.environ, {"SLURM_JOB_ID": "123"}), patch.object(
                    launcher.subprocess, "run", side_effect=completed
                ) as run, redirect_stdout(io.StringIO()):
                    launcher.run_job(directory / "submission.json")
                    run.assert_called_once()
                self.assertEqual(launcher.read_json(directory / "result.json")["result"], {"fixture": stage})
                self.assertEqual(launcher.read_json(directory / "worker-status.json")["status"], "succeeded")

    def test_model_jobs_recheck_approvals_and_prepared_hash_before_dispatch(self):
        self.model_fixture()
        directory = self.submit_model("validate", "01")
        manifest = directory / "submission.json"
        with patch.dict(launcher.os.environ, {"SLURM_JOB_ID": "123"}), patch.object(
            launcher.subprocess, "run"
        ) as run:
            for path in (self.root / "authorization.json", self.storage_approval, self.root / "prepared.json"):
                original = launcher.read_json(path)
                launcher.write_json(path, {**original, "changed": True})
                with self.subTest(path=path), self.assertRaisesRegex(ValueError, "Queued model/storage"):
                    launcher.run_job(manifest)
                launcher.write_json(path, original)
            with patch.object(launcher, "check_approval", side_effect=ValueError("expired")):
                with self.assertRaisesRegex(ValueError, "expired"):
                    launcher.run_job(manifest)
            plan = launcher.read_json(manifest)
            launcher.write_json(manifest, {**plan, "model_stage_approved": False})
            with self.assertRaisesRegex(ValueError, "explicit model-stage"):
                launcher.run_job(manifest)
            run.assert_not_called()
        self.assertFalse((directory / "worker.started").exists())

    def test_model_reviews_reject_mismatch_before_submission(self):
        self.model_fixture()
        for mutation in (
            {"authority_sha256": "different"}, {"storage_reserve_usd": "4.00"},
        ):
            approval = launcher.read_json(self.approval)
            launcher.write_json(self.approval, {**approval, **mutation})
            with patch.object(launcher.subprocess, "check_output") as calls:
                with self.assertRaisesRegex(ValueError, "approvals differ"):
                    launcher.main([*self.args, "--stage", "preflight", "--approval", str(self.approval),
                                   "--execute-approved-stage"])
                calls.assert_not_called()
            launcher.write_json(self.approval, approval)
        for stage in ("seal", "test"):
            with self.subTest(stage=stage), self.assertRaisesRegex(ValueError, "full-study"):
                self.submit_model(stage)
        with patch.object(launcher, "check_approval", side_effect=ValueError("unapproved")):
            with self.assertRaisesRegex(ValueError, "unapproved"):
                self.submit_model("smoke")
        with patch.object(launcher, "validate_storage", side_effect=ValueError("expired storage")):
            with self.assertRaisesRegex(ValueError, "expired storage"):
                self.submit_model("smoke")

    def test_named_batch_failure_keeps_markers_and_never_retries(self):
        self.model_fixture()
        directory = self.submit_model("validate", "01")
        with self.assertRaisesRegex(ValueError, "already recorded"):
            self.submit_model("validate", "01")
        with patch.dict(launcher.os.environ, {"SLURM_JOB_ID": "123"}), patch.object(
            launcher.subprocess, "run", side_effect=subprocess.CalledProcessError(1, ["validate"])
        ) as run:
            with self.assertRaises(subprocess.CalledProcessError):
                launcher.run_job(directory / "submission.json")
            with self.assertRaises(FileExistsError):
                launcher.run_job(directory / "submission.json")
            run.assert_called_once()
        self.assertEqual(launcher.read_json(directory / "worker-status.json")["status"], "failed")
        self.assertTrue((directory / "worker.started").is_file())
        self.assertFalse((directory / "result.json").exists())


if __name__ == "__main__":
    unittest.main()
