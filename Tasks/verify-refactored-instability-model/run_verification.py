#!/usr/bin/env python3

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


TASK_DIR = Path(__file__).resolve().parent
MASTER_DIR = TASK_DIR.parents[1]
MODEL_TASK_DIR = MASTER_DIR / "Tasks" / "jira-url-to-instability-model"
sys.path.insert(0, str(MODEL_TASK_DIR))

from unstable_model.config import load_config
from unstable_model.data import PROJECTS


DEFAULT_DATASETS_FILE = TASK_DIR / "datasets.json"
DEFAULT_OUTPUT_ROOT = TASK_DIR / "results"


def load_datasets(path):
    datasets_path = Path(path).resolve()
    payload = json.loads(datasets_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not payload:
        raise ValueError("The datasets file must contain a non-empty object.")

    datasets = {}
    for project, configured_path in payload.items():
        if project not in PROJECTS:
            raise ValueError(
                f"Unsupported project {project!r}; expected one of: "
                + ", ".join(PROJECTS)
            )
        if not isinstance(configured_path, str) or not configured_path.strip():
            raise ValueError(
                f"Dataset path for {project!r} must be a non-empty string."
            )
        dataset_path = Path(configured_path).expanduser()
        if not dataset_path.is_absolute():
            dataset_path = MASTER_DIR / dataset_path
        dataset_path = dataset_path.resolve()
        if not dataset_path.is_file():
            raise FileNotFoundError(
                f"Dataset for {project!r} was not found: {dataset_path}"
            )
        datasets[project] = dataset_path
    return datasets_path, datasets


def select_datasets(datasets, project):
    if project == "all":
        missing = [name for name in PROJECTS if name not in datasets]
        if missing:
            raise ValueError(
                "Project 'all' requires these missing datasets: "
                + ", ".join(missing)
            )
        return {name: datasets[name] for name in PROJECTS}
    if project not in datasets:
        raise ValueError(f"No dataset is configured for project {project!r}.")
    return {project: datasets[project]}


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as input_file:
        for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stage_datasets(datasets, data_root):
    data_root = Path(data_root)
    for project, source_path in datasets.items():
        project_dir = data_root / project
        project_dir.mkdir(parents=True, exist_ok=True)
        staged_path = project_dir / "features_labels_table_os.csv"
        if staged_path.is_symlink() or staged_path.exists():
            staged_path.unlink()
        staged_path.symlink_to(source_path)


def write_manifest(path, manifest):
    Path(path).write_text(
        json.dumps(manifest, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def build_parser():
    parser = argparse.ArgumentParser(
        description=(
            "Compare matching RF, legacy XGboost and NN families at all levels; "
            "or explicitly run the separate logistic experiment."
        )
    )
    parser.add_argument(
        "--datasets-file",
        type=Path,
        default=DEFAULT_DATASETS_FILE,
    )
    parser.add_argument(
        "--project",
        choices=["all", *PROJECTS],
        default="all",
    )
    parser.add_argument(
        "--label-threshold",
        type=int,
        choices=[5, 10, 15, 20],
        action="append",
        help="Repeat to select levels; defaults to 5,10,15,20.",
    )
    parser.add_argument("--protocol", choices=["pooled", "within-project", "leave-one-project-out"], default="pooled")
    parser.add_argument("--experiment", choices=["comparison", "logistic"], default="comparison")
    parser.add_argument("--models", nargs="+", choices=["RF", "XGboost", "NN"], default=["RF", "XGboost", "NN"])
    parser.add_argument("--comparison-config", type=Path, default=TASK_DIR / "comparison_config.json")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate and fingerprint inputs without training the model.",
    )
    return parser


def run(args):
    from model_comparison import LEVELS, load_frames, run_comparison

    levels = sorted(set(args.label_threshold or LEVELS))
    args.models = list(dict.fromkeys(args.models))
    if args.protocol != "pooled" and args.project == "all":
        raise ValueError("Within-project and held-out runs require an explicit project.")
    if args.experiment == "logistic" and args.protocol == "leave-one-project-out":
        raise ValueError("Logistic task supports pooled or within-project evaluation only.")
    output_root = args.output_root.resolve()
    if (output_root / "verification_manifest.json").exists():
        raise FileExistsError(f"Results already exist at {output_root}; choose a fresh output directory.")
    output_root.mkdir(parents=True, exist_ok=True)
    manifest_path = output_root / "verification_manifest.json"
    datasets_path, configured_datasets = load_datasets(args.datasets_file)
    selected_datasets = select_datasets(
        configured_datasets,
        "all" if args.protocol == "leave-one-project-out" else args.project,
    )
    input_details = {
        project: {
            "path": str(path),
            "size_bytes": path.stat().st_size,
            "sha256": file_sha256(path),
        }
        for project, path in selected_datasets.items()
    }
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "inputs_validated",
        "datasets_file": str(datasets_path),
        "project": args.project,
        "label_thresholds": levels,
        "models": args.models if args.experiment == "comparison" else ["Logistic"],
        "variants": ["baseline", "refactored"] if args.experiment == "comparison" else ["logistic"],
        "protocol": args.protocol,
        "experiment": args.experiment,
        "comparison_performed": False,
        "inputs": input_details,
    }
    write_manifest(manifest_path, manifest)

    staged_data_root = output_root / "input_layout"
    stage_datasets(selected_datasets, staged_data_root)
    try:
        data = load_frames(staged_data_root, selected_datasets, levels)
        if args.validate_only:
            manifest["eligible_rows"] = len(data)
            write_manifest(manifest_path, manifest)
            return manifest_path
        if args.experiment == "comparison":
            configuration = json.loads(args.comparison_config.read_text())
            manifest["comparison_config"] = configuration
            write_manifest(manifest_path, manifest)
            rows = run_comparison(
                data, output_root / "model", args.protocol, args.project,
                levels, args.models, configuration, MASTER_DIR,
            )
            manifest["comparison_performed"] = True
            manifest["result_count"] = len(rows)
            manifest["historical_pipeline_replayed"] = False
        else:
            from unstable_model.training import train_model

            model_config = load_config(MODEL_TASK_DIR / "model_config.json")
            for level in levels:
                train_model(
                    data_root=staged_data_root,
                    output_root=output_root / "model" / f"words_{level}" / "Logistic" / "logistic",
                    project=args.project,
                    threshold=level,
                    config=model_config,
                )
    except Exception as error:
        manifest["status"] = "failed"
        manifest["error"] = str(error)
        write_manifest(manifest_path, manifest)
        raise

    manifest.update({"status": "succeeded", "model_run_directory": str(output_root / "model")})
    write_manifest(manifest_path, manifest)
    return manifest_path


def main():
    args = build_parser().parse_args()
    manifest_path = run(args)
    print(f"Verification manifest: {manifest_path}")


if __name__ == "__main__":
    main()
