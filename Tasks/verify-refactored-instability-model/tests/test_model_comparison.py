import json
import subprocess
import sys
import tempfile
import unittest
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, auc, precision_recall_curve, roc_auc_score

from model_comparison import (
    LEVELS, MODEL_CLASSES, build_model, fit_candidate, load_frames,
    run_comparison, split_frames,
)
from run_verification import build_parser, run
from unstable_model.data import NUMERIC_COLUMNS, prepare_feature_frame
from unstable_model.evaluation import calculate_metrics


REPO = Path(__file__).resolve().parents[3]
SHARED = REPO / "Tasks/verify-refactored-instability-model"
CONFIG = {
    "seed": 7,
    "models": {
        "RF": [{"n_estimators": 4, "max_depth": 2}],
        "XGboost": [{"n_estimators": 4, "max_depth": 2}],
        "NN": [{"hidden_layer_sizes": [3], "max_iter": 20, "solver": "lbfgs"}],
    },
}


def dataset(project, count=60):
    rows = []
    for index in range(count):
        positive = int(index % 3 == 0)
        row = {
            "issue_key": f"{project}-{index}",
            "created": "2020-01-01",
            "time_add_to_sprint": str(pd.Timestamp("2020-01-01") + pd.Timedelta(days=index)),
            "original_summary_sprint": "changing requirement" if positive else "stable requirement",
            "original_description_sprint": "description",
            "original_acceptance_criteria_sprint": "",
            "project_key": project, "issue_type": "Story", "priority": "Major",
            **{column: float(index % 7) for column in NUMERIC_COLUMNS},
            **{f"is_change_text_num_words_{k}": positive for k in LEVELS},
        }
        rows.append(row)
    return pd.DataFrame(rows)


def prepared_data():
    frames = []
    for project in ["Apache", "Qt", "Jira"]:
        raw = dataset(project)
        frame = prepare_feature_frame(raw)
        for level in LEVELS:
            frame[f"is_change_text_num_words_{level}"] = raw[f"is_change_text_num_words_{level}"]
        frame["source_dataset"] = project
        frame["row_id"] = project + ":" + frame.issue_key
        frames.append(frame)
    return pd.concat(frames).sort_values(["time_add_to_sprint", "row_id"]).reset_index(drop=True)


class ComparisonTests(unittest.TestCase):
    def test_all_levels_and_all_families_are_defaults(self):
        args = build_parser().parse_args([])
        self.assertIsNone(args.label_threshold)
        self.assertEqual(args.models, ["RF", "XGboost", "NN"])
        self.assertEqual(args.experiment, "comparison")

    def test_model_identities_and_no_double_weighting(self):
        for name, cls in MODEL_CLASSES.items():
            self.assertIsInstance(build_model(name, CONFIG["models"][name][0], 7), cls)
        with self.assertRaises(ValueError):
            build_model("RF", {"class_weight": "balanced"}, 7)
        self.assertEqual(MODEL_CLASSES["XGboost"].__name__, "GradientBoostingClassifier")

    def test_tied_and_untied_metrics_match_sklearn(self):
        for y, p in [
            ([0, 1, 0, 1], [.5, .5, .5, .5]),
            ([1, 0, 1, 0, 0], [.8, .8, .3, .1, .1]),
            ([0, 0, 1, 1], [.1, .4, .6, .9]),
        ]:
            y, p = np.array(y), np.array(p)
            result = calculate_metrics(y, p, .5)
            precision, recall, _ = precision_recall_curve(y, p)
            self.assertAlmostEqual(result["auc_prc"], auc(recall, precision))
            self.assertAlmostEqual(result["average_precision"], average_precision_score(y, p))
            self.assertAlmostEqual(result["roc_auc"], roc_auc_score(y, p))
        self.assertIsNone(calculate_metrics(np.zeros(4), np.ones(4) * .2, .5)["auc_prc"])
        with self.assertRaisesRegex(ValueError, "finite"):
            calculate_metrics([0, 1], [0.3, np.nan], .5)

    def test_training_weights_only_and_nn_resampling(self):
        class Recorder:
            def fit(self, x, y, **kwargs):
                self.labels = y
                self.kwargs = kwargs

        x = np.ones((4, 2))
        y = np.array([0, 0, 0, 1])
        model = Recorder()
        fit_candidate(model, "RF", "refactored", x, y, 7)
        np.testing.assert_allclose(model.kwargs["sample_weight"], [2/3, 2/3, 2/3, 2])
        fit_candidate(model, "RF", "baseline", x, y, 7)
        self.assertEqual(model.kwargs, {})
        fit_candidate(model, "NN", "refactored", x, y, 7)
        self.assertEqual(np.bincount(model.labels).tolist(), [3, 3])
        self.assertEqual(model.kwargs, {})

    def test_protocol_membership(self):
        data = prepared_data()
        for protocol in ["pooled", "within-project", "leave-one-project-out"]:
            train, val, test = split_frames(data, protocol, "Qt")
            self.assertFalse(set(train.row_id) & set(test.row_id))
            self.assertFalse(set(val.row_id) & set(test.row_id))
            if protocol == "leave-one-project-out":
                self.assertNotIn("Qt", train.source_dataset.unique())
                self.assertNotIn("Qt", val.source_dataset.unique())
                self.assertEqual(set(test.source_dataset), {"Qt"})
                self.assertEqual(len(test), 60)
            elif protocol == "within-project":
                self.assertEqual(len(train), 36)
                self.assertEqual(len(val), 12)
                self.assertEqual(len(test), 12)

    def test_real_models_all_levels_and_saved_artifacts(self):
        with tempfile.TemporaryDirectory() as directory, warnings.catch_warnings():
            warnings.simplefilter("ignore")
            root = Path(directory)
            for protocol in ["pooled", "within-project", "leave-one-project-out"]:
                out = root / protocol
                rows = run_comparison(prepared_data(), out, protocol, "Qt", LEVELS,
                                      list(MODEL_CLASSES), CONFIG, root)
                self.assertEqual(len(rows), 24)
                self.assertEqual(len({r["test_row_ids_sha256"] for r in rows}), 1)
                self.assertEqual(len(list(out.rglob("metrics.json"))), 24)
                for row in rows:
                    destination = out / f"words_{row['level']}" / row["model"] / row["variant"]
                    predicted = pd.read_csv(destination / "test_predictions.csv")
                    expected = calculate_metrics(predicted.actual_label, predicted.instability_probability.to_numpy(),
                                                 row["threshold"])
                    for metric in ["auc_prc", "average_precision", "accuracy", "roc_auc"]:
                        self.assertAlmostEqual(row[metric], expected[metric])
                    fitted = joblib.load(destination / "model.joblib")
                    self.assertIsInstance(fitted, MODEL_CLASSES[row["model"]])

    def test_runner_defaults_and_failure_manifest(self):
        with tempfile.TemporaryDirectory() as directory, warnings.catch_warnings():
            warnings.simplefilter("ignore")
            root = Path(directory)
            raw = root / "Apache.csv"
            dataset("Apache").to_csv(raw, index=False)
            datasets = root / "datasets.json"
            datasets.write_text(json.dumps({"Apache": str(raw)}))
            config = root / "config.json"
            config.write_text(json.dumps(CONFIG))
            args = build_parser().parse_args([
                "--datasets-file", str(datasets), "--project", "Apache",
                "--comparison-config", str(config), "--models", "RF",
                "--output-root", str(root / "good"),
            ])
            run(args)
            manifest = json.loads((root / "good/verification_manifest.json").read_text())
            self.assertEqual(manifest["label_thresholds"], [5, 10, 15, 20])
            self.assertEqual(manifest["result_count"], 8)
            self.assertEqual(manifest["status"], "succeeded")
            with self.assertRaises(FileExistsError):
                run(args)
            frame = dataset("Apache")
            frame["is_change_text_num_words_20"] = 0
            frame.to_csv(raw, index=False)
            args.output_root = root / "bad"
            with self.assertRaisesRegex(ValueError, "both classes"):
                run(args)
            failure = json.loads((root / "bad/verification_manifest.json").read_text())
            self.assertEqual(failure["status"], "failed")

    def test_missing_level_or_duplicate_ids_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Apache").mkdir()
            path = root / "Apache/features_labels_table_os.csv"
            dataset("Apache").drop(columns="is_change_text_num_words_20").to_csv(path, index=False)
            with self.assertRaisesRegex(ValueError, "missing columns"):
                load_frames(root, ["Apache"], LEVELS)
            frame = dataset("Apache")
            frame.loc[1, "issue_key"] = frame.loc[0, "issue_key"]
            frame.to_csv(path, index=False)
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                load_frames(root, ["Apache"], LEVELS)
            frame = dataset("Apache")
            frame["is_change_text_num_words_5"] = frame["is_change_text_num_words_5"].astype(float)
            frame.loc[1, "is_change_text_num_words_5"] = 0.5
            frame.to_csv(path, index=False)
            with self.assertRaisesRegex(ValueError, "non-binary"):
                load_frames(root, ["Apache"], LEVELS)


class LauncherTests(unittest.TestCase):
    def test_job_matrix_and_project_filter(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "raw.csv"
            raw.write_text("issue_key\nTEST-1\n")
            configured = root / "datasets.json"
            configured.write_text(json.dumps({
                p: str(raw) for p in ["Apache", "Qt", "Jira", "MariaDB", "Hyperledger", "IntelDAOS"]
            }))
            for name, protocol, count in [
                ("verify-refactored-instability-model", "pooled", 4),
                ("validate-refactored-model-per-dataset", "within-project", 24),
                ("compare-models-leave-one-project-out", "leave-one-project-out", 24),
                ("evaluate-logistic-instability-model", "pooled", 4),
            ]:
                task = root / name
                task.mkdir()
                command = [sys.executable, str(SHARED / "cluster/submit_jobs.py"),
                           "--task-dir", str(task), "--protocol", protocol,
                           "--datasets-file", str(configured), "--run-id", "test", "--dry-run"]
                subprocess.run(command, check=True, capture_output=True, text=True)
                plan = json.loads((task / "cluster_runs/test/job_plan.json").read_text())
                self.assertEqual(len(plan["jobs"]), count)
                self.assertEqual(plan["levels"], [5, 10, 15, 20])
                for job in plan["jobs"]:
                    script = task / "cluster_runs/test" / job["sbatch"]
                    subprocess.run(["bash", "-n", str(script)], check=True)
                    self.assertIn(f"--label-threshold {job['level']}", script.read_text())
                if protocol != "pooled":
                    narrowed = [x if x != "test" else "qt-only" for x in command] + ["--only", "Qt"]
                    subprocess.run(narrowed, check=True, capture_output=True, text=True)
                    plan = json.loads((task / "cluster_runs/qt-only/job_plan.json").read_text())
                    self.assertEqual(len(plan["jobs"]), 4)
                    self.assertEqual({j["project"] for j in plan["jobs"]}, {"Qt"})
                duplicate = subprocess.run(command, capture_output=True, text=True)
                self.assertNotEqual(duplicate.returncode, 0)

    def test_partial_submission_failure_is_persisted(self):
        with tempfile.TemporaryDirectory() as directory:
            import os

            root = Path(directory)
            task = root / "validate-refactored-model-per-dataset"
            task.mkdir()
            raw = root / "raw.csv"
            raw.write_text("test\n")
            config = task / "datasets.json"
            config.write_text(json.dumps({"Qt": str(raw)}))
            binary = root / "bin"
            binary.mkdir()
            counter = root / "called"
            sbatch = binary / "sbatch"
            sbatch.write_text(
                f"#!/bin/bash\nif [ -f '{counter}' ]; then exit 1; fi\n"
                f"touch '{counter}'\necho 12345\n"
            )
            sbatch.chmod(0o755)
            command = [
                sys.executable, str(SHARED / "cluster/submit_jobs.py"), "--task-dir", str(task),
                "--protocol", "within-project", "--datasets-file", str(config), "--run-id", "partial",
            ]
            result = subprocess.run(command, capture_output=True, text=True,
                                    env={**os.environ, "PATH": str(binary) + os.pathsep + os.environ["PATH"]})
            self.assertNotEqual(result.returncode, 0)
            plan = json.loads((task / "cluster_runs/partial/job_plan.json").read_text())
            self.assertEqual([j["job_id"] for j in plan["jobs"]],
                             ["12345", "SUBMISSION-FAILED", "PENDING", "PENDING"])
            self.assertIn("submission_error", plan)

    def test_invalid_project_fails_before_any_submission(self):
        with tempfile.TemporaryDirectory() as directory:
            task = Path(directory) / "validate-refactored-model-per-dataset"
            task.mkdir()
            raw = task / "raw.csv"
            raw.write_text("test\n")
            config = task / "datasets.json"
            config.write_text(json.dumps({"Apache": str(raw)}))
            result = subprocess.run([
                sys.executable, str(SHARED / "cluster/submit_jobs.py"), "--task-dir", str(task),
                "--protocol", "within-project", "--datasets-file", str(config),
                "--only", "Apache", "--only", "Qt", "--dry-run",
            ], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((task / "cluster_runs").exists())


if __name__ == "__main__":
    unittest.main()
