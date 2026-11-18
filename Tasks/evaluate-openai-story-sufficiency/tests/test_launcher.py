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
        self.directory = self.storage / "openai-sufficiency-runs/openai-sufficiency-03/jobs/prepare"
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


if __name__ == "__main__":
    unittest.main()
