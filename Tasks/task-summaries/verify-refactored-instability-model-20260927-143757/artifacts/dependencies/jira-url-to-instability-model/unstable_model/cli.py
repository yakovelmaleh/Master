import argparse
import json
from pathlib import Path

from .config import load_config
from .data import PROJECTS
from .training import train_model


TASK_DIR = Path(__file__).resolve().parents[1]
MASTER_DIR = TASK_DIR.parents[1]


def build_parser(config):
    parser = argparse.ArgumentParser(
        description=(
            "Train a deterministic unstable-user-story classifier using "
            "chronological splits and pre-sprint features."
        )
    )
    parser.add_argument(
        "--project",
        default=config.default_project,
        choices=["all", *PROJECTS],
        help="Dataset to train on.",
    )
    parser.add_argument(
        "--label-threshold",
        type=int,
        default=config.default_label_threshold,
        choices=[5, 10, 15, 20],
        help="Changed-word threshold defining an unstable issue.",
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        default=MASTER_DIR / "Data",
        help="Directory containing one subdirectory per project.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=TASK_DIR / "results",
        help="Directory for model artifacts and reports.",
    )
    return parser


def main():
    config = load_config(TASK_DIR / "model_config.json")
    args = build_parser(config).parse_args()
    run_dir, metrics = train_model(
        data_root=args.data_root,
        output_root=args.output_root,
        project=args.project,
        threshold=args.label_threshold,
        config=config,
    )
    result = {
        "run_directory": str(run_dir.resolve()),
        "selected_threshold": metrics["test"]["threshold"],
        "test_average_precision": metrics["test"]["average_precision"],
        "test_roc_auc": metrics["test"]["roc_auc"],
        "test_f1": metrics["test"]["f1"],
        "test_precision": metrics["test"]["precision"],
        "test_recall": metrics["test"]["recall"],
    }
    print(json.dumps(result, indent=2))
