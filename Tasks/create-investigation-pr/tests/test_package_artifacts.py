import contextlib
import csv
import importlib.util
import io
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


spec = importlib.util.spec_from_file_location(
    "package_artifacts", Path(__file__).resolve().parents[1] / "package_artifacts.py"
)
packager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packager)


class PackageArtifactsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.results = self.root / "results"
        self.logs = self.root / "logs"
        self.results.mkdir()
        self.logs.mkdir()
        (self.logs / "job.out").write_text("Job failed: diagnostic information\n")
        self.output = self.root / "bundle"

    def sparse(self, path, size):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as stream:
            stream.truncate(size)
        return path

    def run_package(self, **kwargs):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            packager.package(self.results, self.logs, **kwargs)
        return output.getvalue()

    def test_actual_limit_and_symlink_targets(self):
        limit = packager.MAX_FILE_BYTES
        exact = self.sparse(self.results / "boundary.bin", limit)
        big = self.sparse(self.results / "raw/issues.jsonl.gz", limit + 1)
        (self.results / "large-link").symlink_to(big)
        csv_path = self.results / "features_labels_table_os.csv"
        csv_path.write_text("issue_key,label\nTEST-1,1\n")
        (self.results / "csv-link").symlink_to(csv_path)
        report = self.run_package(destination=self.output)
        self.assertEqual((self.output / "artifacts/results/boundary.bin").stat().st_size, limit)
        self.assertFalse((self.output / "artifacts/results/raw/issues.jsonl.gz").exists())
        self.assertFalse((self.output / "artifacts/results/large-link").exists())
        self.assertEqual((self.output / "artifacts/results/csv-link").read_bytes(), csv_path.read_bytes())
        self.assertFalse((self.output / "artifacts/results/csv-link").is_symlink())
        self.assertEqual(big.stat().st_size, limit + 1)
        self.assertEqual(exact.stat().st_size, limit)
        with (self.output / "OMITTED_FILES.csv").open() as stream:
            omitted = list(csv.DictReader(stream))
        self.assertEqual(len(omitted), 2)
        self.assertTrue(all(int(r["size_bytes"]) == limit + 1 for r in omitted))
        self.assertIn("2 omitted", report)
        self.assertEqual((self.output / "DATASET_STATUS.txt").read_text(), "complete\n")

    def test_oversized_dataset_is_not_reported_as_failed_creation(self):
        dataset = self.sparse(self.root / "features_labels_table_os.csv",
                              packager.MAX_FILE_BYTES + 1)
        self.run_package(destination=self.output, dataset=dataset)
        self.assertEqual((self.output / "DATASET_STATUS.txt").read_text(), "omitted_size\n")
        self.assertTrue((self.output / "artifacts/logs/job.out").is_file())

    def test_dry_run_uses_same_size_filter_without_copying(self):
        self.sparse(self.results / "big.json", packager.MAX_FILE_BYTES + 1)
        report = self.run_package()
        self.assertIn("SKIP (>90 MiB): results/big.json", report)
        self.assertIn("INCLUDE: logs/job.out", report)
        self.assertFalse(self.output.exists())

    def test_failed_run_and_optional_files(self):
        sbatch = self.root / "submit.sbatch"
        sbatch.write_text("#!/bin/bash\n")
        manifest = self.root / "submitted_jobs.tsv"
        manifest.write_text("job_id\n123\n")
        self.run_package(destination=self.output, sbatch=sbatch, manifest=manifest)
        self.assertEqual((self.output / "DATASET_STATUS.txt").read_text(), "not_created\n")
        self.assertEqual((self.output / "artifacts/submit.sbatch").read_text(), sbatch.read_text())
        self.assertEqual((self.output / "artifacts/submitted_jobs.tsv").read_text(), manifest.read_text())
        with (self.output / "OMITTED_FILES.csv").open() as stream:
            self.assertEqual(list(csv.DictReader(stream)), [])

    def test_partial_dataset_exclusion(self):
        (self.results / "features_labels_table_os.csv").write_text("small\n")
        self.sparse(self.results / "other/features_labels_table_os.csv",
                    packager.MAX_FILE_BYTES + 1)
        self.run_package(destination=self.output)
        self.assertEqual((self.output / "DATASET_STATUS.txt").read_text(), "partial_omitted_size\n")

    def test_symlink_cycle_fails_explicitly(self):
        (self.results / "cycle").symlink_to(self.results, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink cycle"):
            self.run_package(destination=self.output)

    def test_shell_dry_run_filters_before_any_git_operation(self):
        repo = self.root / "Master"
        scripts = repo / "Tasks/create-investigation-pr"
        scripts.mkdir(parents=True)
        source = Path(__file__).resolve().parents[1]
        for name in ["create_investigation_pr.sh", "package_artifacts.py"]:
            shutil.copyfile(source / name, scripts / name)
        cluster = repo / "Tasks/example/cluster_runs"
        run = cluster / "test-run/apache"
        shutil.copytree(self.results, run / "results")
        shutil.copytree(self.logs, run / "logs")
        self.sparse(run / "results/raw/issues.jsonl.gz", packager.MAX_FILE_BYTES + 1)
        self.sparse(run / "results/features_labels_table_os.csv", packager.MAX_FILE_BYTES + 1)
        (cluster / "latest_run.txt").write_text("test-run\n")
        result = subprocess.run(
            ["bash", str(scripts / "create_investigation_pr.sh"),
             "--task", "example", "--dataset", "Apache", "--dry-run"],
            text=True, capture_output=True, check=True,
        )
        self.assertIn("SKIP (>90 MiB): results/raw/issues.jsonl.gz", result.stdout)
        self.assertIn("1 included; 2 omitted", result.stdout)
        self.assertFalse((repo / ".git").exists())


if __name__ == "__main__":
    unittest.main()
