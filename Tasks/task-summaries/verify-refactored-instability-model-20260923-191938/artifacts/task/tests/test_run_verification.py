import json
import tempfile
import unittest
from pathlib import Path

from run_verification import load_datasets, select_datasets, stage_datasets


class VerificationTaskTests(unittest.TestCase):
    def test_load_select_and_stage_explicit_datasets(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            datasets = {}
            for project in (
                "Apache",
                "Hyperledger",
                "IntelDAOS",
                "Jira",
                "MariaDB",
                "Qt",
            ):
                path = root / f"{project}.csv"
                path.write_text("issue_key\nDEMO-1\n", encoding="utf-8")
                datasets[project] = str(path)

            config_path = root / "datasets.json"
            config_path.write_text(
                json.dumps(datasets),
                encoding="utf-8",
            )

            resolved_config, loaded = load_datasets(config_path)
            selected = select_datasets(loaded, "all")
            staged_root = root / "staged"
            stage_datasets(selected, staged_root)

            self.assertEqual(resolved_config, config_path.resolve())
            self.assertEqual(set(selected), set(datasets))
            for project, original_path in selected.items():
                staged_path = (
                    staged_root
                    / project
                    / "features_labels_table_os.csv"
                )
                self.assertTrue(staged_path.is_symlink())
                self.assertEqual(staged_path.resolve(), original_path)

    def test_all_requires_every_supported_dataset(self):
        with self.assertRaisesRegex(ValueError, "missing datasets"):
            select_datasets({"Apache": Path("apache.csv")}, "all")


if __name__ == "__main__":
    unittest.main()
