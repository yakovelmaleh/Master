import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

import pandas as pd

from unstable_model.config import ModelConfig
from unstable_model.data import chronological_split
from unstable_model.evaluation import calculate_metrics, select_threshold
from unstable_model.prediction import predict_file
from unstable_model.training import train_model


class ModelTests(unittest.TestCase):
    def test_chronological_split_preserves_order(self):
        frame = pd.DataFrame(
            {
                "time_add_to_sprint": pd.date_range(
                    "2020-01-01", periods=100, freq="D"
                )
            }
        )
        train, validation, test = chronological_split(frame, 0.6, 0.2)
        self.assertEqual(len(train), 60)
        self.assertEqual(len(validation), 20)
        self.assertEqual(len(test), 20)
        self.assertLess(
            train["time_add_to_sprint"].max(),
            validation["time_add_to_sprint"].min(),
        )

    def test_threshold_and_metrics(self):
        labels = pd.Series([0, 0, 1, 1])
        probabilities = pd.Series([0.1, 0.4, 0.6, 0.9]).to_numpy()
        threshold = select_threshold(labels, probabilities)
        metrics = calculate_metrics(labels, probabilities, threshold)
        self.assertEqual(metrics["f1"], 1.0)
        self.assertEqual(metrics["confusion_matrix"], [[2, 0], [0, 2]])

    def test_threshold_falls_back_for_single_class_validation(self):
        labels = pd.Series([0, 0, 0])
        probabilities = pd.Series([0.1, 0.4, 0.8]).to_numpy()
        self.assertEqual(select_threshold(labels, probabilities), 0.5)

    def test_training_rejects_single_class_training_or_validation(self):
        for name, labels in (
            ("training", [0] * 36 + [0, 1] * 12),
            ("validation", [0, 1] * 18 + [0] * 12 + [0, 1] * 6),
        ):
            frame = pd.DataFrame({
                "is_change_text_num_words_5": labels,
                "time_add_to_sprint": pd.date_range("2020-01-01", periods=60),
            })
            with self.subTest(partition=name), patch(
                "unstable_model.training.load_dataset", return_value=frame
            ), patch("unstable_model.training.FeatureTransformer") as transformer:
                with self.assertRaisesRegex(ValueError, name + " partition must contain both"):
                    train_model(Path("."), Path("."), "Qt", 5, self.model_config())
                transformer.assert_not_called()

    def test_training_sanitizes_infinite_numeric_values(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data_root = root / "Data"
            project_dir = data_root / "Apache"
            project_dir.mkdir(parents=True)
            rows = []
            for index in range(60):
                unstable = int(index % 4 == 0)
                rows.append(
                    {
                        "issue_key": f"INF-{index}",
                        "created": "2020-01-01",
                        "time_add_to_sprint": (
                            pd.Timestamp("2020-01-01")
                            + pd.Timedelta(days=index)
                        ),
                        "original_summary_sprint": "requirement",
                        "original_description_sprint": "description",
                        "original_acceptance_criteria_sprint": "criteria",
                        "issue_type": "Story",
                        "project_key": "TEST",
                        "priority": "Major",
                        "original_story_points_sprint": (
                            float("inf") if index == 10 else 3
                        ),
                        "num_comments_before_sprint": index % 5,
                        "num_changes_text_before_sprint": unstable,
                        "num_changes_story_point_before_sprint": 0,
                        "time_until_add_to_sprint": index * 10,
                        "num_issues_cretor_prev": index,
                        "is_change_text_num_words_5": unstable,
                    }
                )
            pd.DataFrame(rows).to_csv(
                project_dir / "features_labels_table_os.csv",
                index=False,
            )
            config = self.model_config()
            run_dir, _ = train_model(
                data_root,
                root / "results",
                "Apache",
                5,
                config,
            )
            self.assertTrue((run_dir / "model.npz").is_file())

    @staticmethod
    def model_config():
        return ModelConfig(
            default_project="Apache",
            default_label_threshold=5,
            train_fraction=0.6,
            validation_fraction=0.2,
            maximum_iterations=200,
            learning_rate=0.05,
            l2_regularization=0.001,
            early_stopping_patience=20,
        )

    def test_end_to_end_training(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data_root = root / "Data"
            project_dir = data_root / "Apache"
            project_dir.mkdir(parents=True)
            rows = []
            for index in range(60):
                unstable = int(index % 4 == 0)
                rows.append(
                    {
                        "issue_key": f"TEST-{index}",
                        "created": f"2020-01-{(index % 28) + 1:02d}",
                        "time_add_to_sprint": (
                            pd.Timestamp("2020-01-01")
                            + pd.Timedelta(days=index)
                        ),
                        "original_summary_sprint": (
                            "unclear changing requirement"
                            if unstable
                            else "clear stable requirement"
                        ),
                        "original_description_sprint": "description",
                        "original_acceptance_criteria_sprint": "criteria",
                        "issue_type": "Story",
                        "project_key": "TEST",
                        "priority": "Major",
                        "original_story_points_sprint": 3,
                        "num_comments_before_sprint": index % 5,
                        "num_changes_text_before_sprint": unstable,
                        "num_changes_story_point_before_sprint": 0,
                        "time_until_add_to_sprint": index * 10,
                        "num_issues_cretor_prev": index,
                        "is_change_text_num_words_5": unstable,
                    }
                )
            pd.DataFrame(rows).to_csv(
                project_dir / "features_labels_table_os.csv",
                index=False,
            )
            config = self.model_config()
            run_dir, metrics = train_model(
                data_root,
                root / "results",
                "Apache",
                5,
                config,
            )
            self.assertTrue((run_dir / "model.npz").is_file())
            self.assertTrue((run_dir / "metrics.json").is_file())
            self.assertGreaterEqual(metrics["test"]["f1"], 0.0)
            prediction_path = root / "predictions.csv"
            row_count, _ = predict_file(
                run_dir,
                project_dir / "features_labels_table_os.csv",
                prediction_path,
            )
            self.assertEqual(row_count, 60)
            self.assertTrue(prediction_path.is_file())


if __name__ == "__main__":
    unittest.main()
