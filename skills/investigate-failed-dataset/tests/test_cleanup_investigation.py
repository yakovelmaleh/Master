import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "cleanup_investigation.py"
)
SPEC = importlib.util.spec_from_file_location(
    "cleanup_investigation",
    SCRIPT_PATH,
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class CleanupInvestigationTests(unittest.TestCase):
    def create_master_repository(self, root):
        repository = root / "Master"
        repository.mkdir()
        subprocess.run(
            ["git", "init", "-q", str(repository)],
            check=True,
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(repository),
                "remote",
                "add",
                "origin",
                "https://github.com/yakovelmaleh/Master.git",
            ],
            check=True,
        )
        launcher = repository / "Tasks" / "run_cluster_task.sh"
        launcher.parent.mkdir()
        launcher.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
        return repository

    def test_resolves_only_selected_dataset_directory(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            repository = self.create_master_repository(
                Path(temporary_directory)
            )
            dataset_path = (
                repository
                / "Tasks"
                / "jira-url-to-instability-model"
                / "cluster_runs"
                / "20260917-204018"
                / "mariadb"
            )
            dataset_path.mkdir(parents=True)

            root = MODULE.repository_root(repository)
            resolved = MODULE.expected_dataset_path(
                root,
                "jira-url-to-instability-model",
                "20260917-204018",
                "MariaDB",
            )

            self.assertEqual(resolved, dataset_path.resolve())

    def test_rejects_non_master_repository(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            repository = Path(temporary_directory) / "Other"
            repository.mkdir()
            subprocess.run(
                ["git", "init", "-q", str(repository)],
                check=True,
            )
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(repository),
                    "remote",
                    "add",
                    "origin",
                    "https://github.com/yakovelmaleh/Other.git",
                ],
                check=True,
            )

            with self.assertRaisesRegex(ValueError, "only in a repository"):
                MODULE.repository_root(repository)

    def test_accepts_github_ssh_remote(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            repository = self.create_master_repository(
                Path(temporary_directory)
            )
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(repository),
                    "remote",
                    "set-url",
                    "origin",
                    "git@github.com:yakovelmaleh/Master.git",
                ],
                check=True,
            )

            self.assertEqual(
                MODULE.repository_root(repository),
                repository.resolve(),
            )

    def test_temporary_path_requires_expected_prefix(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary_directory:
            with self.assertRaisesRegex(ValueError, "must start"):
                MODULE.validate_temporary_path(temporary_directory)


if __name__ == "__main__":
    unittest.main()
