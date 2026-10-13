import copy
import importlib.util
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd

from Code_Smells_Detection.runtime import common, detectors, evidence, models
from Code_Smells_Detection.runtime.tests.support import RuntimeCase


class ModelTests(RuntimeCase):
    def labeled_study(self):
        frame, assignment = self.frozen_study()
        profile = self.profile()
        common.write_json(self.root / "detection/profiles/java.json", profile)
        catalog = {"any_supported_smell": {"language": None, "category": "any", "smell": "any"},
                   "java.design.example": {"language": "java", "category": "design", "smell": "example"},
                   "python.design.absent": {"language": "python", "category": "design", "smell": "absent"}}
        labels = pd.DataFrame({"row_id": frame.row_id, "source": "Apache",
                               "partition": frame.row_id.map(assignment),
                               "any_supported_smell": np.arange(len(frame)) % 2,
                               "java.design.example": np.arange(len(frame)) % 2,
                               "python.design.absent": None})
        common.write_csv(self.root / "labels/story_labels.csv", labels)
        common.write_json(self.root / "labels/catalog.json", catalog)
        common.write_json(self.root / "labels/coverage.json", {"rows": []})
        common.write_json(self.root / "labels/exclusions.json", {})
        common.write_json(self.root / "labels/manifest.json", {
            "labels_sha256": common.file_hash(self.root / "labels/story_labels.csv"),
            "catalog_sha256": common.digest(catalog), "profiles": {"java": common.digest(profile)},
            "coverage_sha256": common.digest({"rows": []}), "exclusions_sha256": common.digest({}),
            "splits": {"Apache": common.file_hash(self.root / "splits/Apache.json")},
            "min_source_rows": 100,
        })
        self.succeeded("labels")
        config = self.storage / "config.json"
        common.write_json(config, {"seed": 7, "bootstrap_samples": 3, "models": {
            "RF": [{"n_estimators": 5, "max_depth": 2}],
            "XGboost": [{"n_estimators": 5, "max_depth": 2}],
            "NN": [{"hidden_layer_sizes": [4], "max_iter": 10, "alpha": .01}],
        }})
        return frame, config

    def test_all_families_share_masks_and_reject_split_changes(self):
        frame, config = self.labeled_study()
        expected = models.validate(self.root, config)
        available = [row for row in expected["matrix"] if row["status"] == "ready"]
        self.assertEqual(12, len(available))
        self.assertEqual(1, len({common.digest(row["rows"]) for row in available}))
        absent = [row for row in expected["matrix"] if row["target"].startswith("python")]
        self.assertTrue(all(row["reason"] == "empty_applicable_partition" for row in absent))
        split = common.read_json(self.root / "splits/Apache.json")
        split["assignment"][frame.row_id.iloc[0]] = "test"
        common.write_json(self.root / "splits/Apache.json", split)
        with self.assertRaisesRegex(ValueError, "provenance"):
            models.experiment(self.root)

    def test_real_classical_training_seal_test_reload_and_summary(self):
        frame, config = self.labeled_study()
        models.validate(self.root, config)
        models.train(self.root, "Apache")
        self.succeeded("train", "Apache")
        with self.assertRaises(ValueError):
            models.test(self.root, "Apache")
        models.seal(self.root)
        self.succeeded("seal")
        with self.assertRaisesRegex(ValueError, "after sealing"):
            models.train(self.root, "Apache")
        models.test(self.root, "Apache")
        self.succeeded("test", "Apache")
        report = models.report(self.root)
        self.assertEqual(18, len(report["results"]))
        self.assertEqual(12, sum(row["status"] == "succeeded" for row in report["results"]))
        self.assertEqual(120, report["retention"]["cohort"]["selected_candidates"])
        incoming, output = self.storage / "incoming.csv", self.storage / "predictions.csv"
        frame.iloc[-24:][models.FEATURE_COLUMNS].to_csv(incoming, index=False)
        models.infer(self.root, "Apache", "RF", "baseline", incoming, output)
        prediction = pd.read_csv(output)
        saved = pd.read_csv(self.root / "models/Apache/any_supported_smell/RF/baseline/test_predictions.csv")
        np.testing.assert_allclose(saved.probability, prediction[prediction.target == "any_supported_smell"].probability)
        self.assertEqual(48, len(prediction))
        spec = importlib.util.spec_from_file_location("smell_summary", common.REPO / "Tasks/create-task-summary-pr/summarize_levels.py")
        summary = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(summary)
        bundle = self.storage / "bundle"
        common.write_json(bundle / "artifacts/code_smell_report.json", report)
        summary.summarize(bundle)
        self.assertTrue((bundle / "TARGETS.csv").exists())
        self.assertFalse((bundle / "LEVELS.csv").exists())
        report["results"].pop()
        common.write_json(bundle / "artifacts/code_smell_report.json", report)
        with self.assertRaisesRegex(ValueError, "expected target"):
            summary.summarize(bundle)

    def test_label_aggregation_deduplicates_and_never_calls_absent_language_clean(self):
        frame, assignment = self.frozen_study(120)
        profile = self.profile()
        common.write_json(self.root / "detection/profiles/java.json", profile)
        fake = {"repository": "a/b", "revision": "a" * 40, "snapshot_manifest_sha256": "b" * 64,
                "files": [{"path": "src/Bad.java", "language": "java"}]}
        key = detectors.detection_key(fake, profile)
        directory = self.root / "detection/results" / key
        self.native_output(directory / "reports")
        common.write_json(directory / "result.json", {
            "key": key, "status": "succeeded", "coverage": ["src/Bad.java"], "profile_sha256": common.digest(profile),
            "reports": common.tree_manifest(directory / "reports"),
            "findings": [{"language": "java", "path": "src/Bad.java", "category": "design",
                          "smell": "Deficient Encapsulation", "entity": "Bad"}],
        })
        record = {"row_id": frame.row_id.iloc[0], "source": "Apache", "partition": "train",
                  "status": "complete", "evidence": [fake, copy.deepcopy(fake)]}
        with mock.patch.object(detectors, "evidence_records", return_value=iter([record])):
            detectors.labels(self.root)
        coverage = common.read_json(self.root / "labels/coverage.json")
        self.assertEqual(1, coverage["rows"][0]["distinct_findings"])
        labels = pd.read_csv(self.root / "labels/story_labels.csv")
        self.assertEqual(1, labels.any_supported_smell.iloc[0])

    def test_reviewed_incomplete_rows_are_excluded_without_moving_survivors(self):
        frame, assignment = self.frozen_study()
        profile = self.profile()
        common.write_json(self.root / "detection/profiles/java.json", profile)
        evidence = {"repository": "a/b", "revision": "a" * 40, "snapshot_manifest_sha256": "b" * 64,
                    "files": [{"path": "src/Clean.java", "language": "java"}]}
        key = detectors.detection_key(evidence, profile)
        directory = self.root / "detection/results" / key
        self.native_output(directory / "reports")
        common.write_json(directory / "result.json", {
            "key": key, "status": "succeeded", "profile_sha256": common.digest(profile),
            "coverage": ["src/Clean.java"], "findings": [], "reports": common.tree_manifest(directory / "reports"),
        })
        records = [{"row_id": frame.row_id.iloc[index], "source": "Apache", "partition": "train",
                    "status": "complete", "evidence": [copy.deepcopy(evidence)]} for index in range(2)]
        records[1]["evidence"][0]["revision"] = "c" * 40
        reviewed = self.storage / "reviewed.json"
        common.write_json(reviewed, {records[1]["row_id"]: "Unsupported syntax; reviewed failed detector logs"})
        with mock.patch.object(detectors, "evidence_records", side_effect=lambda *_: iter(records)):
            with self.assertRaisesRegex(ValueError, "missing/incomplete"):
                detectors.labels(self.root)
            detectors.labels(self.root, reviewed)
            labels, _, _ = models.load_labels(self.root)
            self.assertEqual([records[0]["row_id"]], labels.row_id.tolist())
            self.assertEqual([assignment[records[0]["row_id"]]], labels.partition.tolist())
            self.assertEqual([0], labels.any_supported_smell.tolist())
            with self.assertRaisesRegex(ValueError, "frozen"):
                detectors.labels(self.root)
        coverage = common.read_json(self.root / "labels/coverage.json")
        self.assertEqual("reviewed_incomplete_detection", coverage["rows"][1]["reason"])
        common.write_json(self.root / "labels/exclusions.json", {})
        with self.assertRaisesRegex(ValueError, "exclusions changed"):
            models.load_labels(self.root)

    def test_incomplete_detector_result_blocks_label_freeze(self):
        frame, assignment = self.frozen_study()
        common.write_json(self.root / "detection/profiles/java.json", self.profile())
        record = {"row_id": frame.row_id.iloc[0], "source": "Apache", "partition": "train",
                  "status": "complete", "evidence": [{
                      "repository": "a/b", "revision": "a" * 40, "snapshot_manifest_sha256": "b" * 64,
                      "files": [{"path": "src/A.java", "language": "java"}],
                  }]}
        with mock.patch.object(detectors, "evidence_records", return_value=iter([record])):
            with self.assertRaisesRegex(ValueError, "missing/incomplete"):
                detectors.labels(self.root)
        self.assertFalse((self.root / "labels/story_labels.csv").exists())
