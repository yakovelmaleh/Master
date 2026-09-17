#!/usr/bin/env python3

import argparse
import re
import shutil
import subprocess
from pathlib import Path


SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]+$")


def repository_root(path):
    candidate = Path(path).expanduser().resolve()
    result = subprocess.run(
        ["git", "-C", str(candidate), "rev-parse", "--show-toplevel"],
        check=True,
        capture_output=True,
        text=True,
    )
    root = Path(result.stdout.strip()).resolve()
    if root.name != "Master":
        raise ValueError(
            f"This cleanup helper works only in a repository named Master: {root}"
        )
    if not (root / "Tasks" / "run_cluster_task.sh").is_file():
        raise ValueError(f"Master task launcher was not found under: {root}")
    remote = subprocess.run(
        ["git", "-C", str(root), "remote", "get-url", "origin"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    normalized_remote = remote.rstrip("/")
    if normalized_remote.endswith(".git"):
        normalized_remote = normalized_remote[:-4]
    if normalized_remote.startswith("git@github.com:"):
        normalized_remote = normalized_remote.replace(
            "git@github.com:",
            "https://github.com/",
            1,
        )
    if not normalized_remote.endswith("github.com/yakovelmaleh/Master"):
        raise ValueError(
            "This cleanup helper only supports the "
            f"yakovelmaleh/Master repository; origin is {remote!r}."
        )
    return root


def validate_name(value, label):
    if not SAFE_NAME.fullmatch(value):
        raise ValueError(
            f"{label} may contain only letters, numbers, dots, underscores, "
            "and dashes."
        )
    return value


def dataset_slug(value):
    slug = re.sub(r"[^a-z0-9._-]+", "-", value.casefold()).strip("-")
    if not slug:
        raise ValueError("Dataset name does not produce a valid directory slug.")
    return slug


def expected_dataset_path(root, task, run_id, dataset):
    task = validate_name(task, "Task")
    run_id = validate_name(run_id, "Run ID")
    cluster_root = (root / "Tasks" / task / "cluster_runs").resolve()
    if not cluster_root.is_dir():
        raise FileNotFoundError(
            f"Task cluster results directory was not found: {cluster_root}"
        )
    target = (cluster_root / run_id / dataset_slug(dataset)).resolve()
    if cluster_root not in target.parents:
        raise ValueError("Resolved dataset path escaped the cluster results root.")
    if not target.is_dir():
        raise FileNotFoundError(f"Dataset run directory was not found: {target}")
    return target


def validate_temporary_path(path):
    target = Path(path).expanduser().resolve()
    temporary_root = Path("/tmp").resolve()
    if temporary_root not in target.parents:
        raise ValueError(f"Temporary path is not below /tmp: {target}")
    if not target.name.startswith("master-investigation."):
        raise ValueError(
            "Temporary path name must start with 'master-investigation.': "
            f"{target}"
        )
    if not target.is_dir():
        raise FileNotFoundError(f"Temporary path was not found: {target}")
    return target


def remove_directory(path):
    shutil.rmtree(path)


def build_parser():
    parser = argparse.ArgumentParser(
        description=(
            "Safely remove one Master cluster dataset run and optional "
            "investigation temporary directories."
        )
    )
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--dataset", required=True)
    parser.add_argument(
        "--confirm-delete",
        required=True,
        help="Must exactly match the resolved dataset run directory.",
    )
    parser.add_argument(
        "--temporary-path",
        action="append",
        default=[],
        help="Optional /tmp/master-investigation.* directory; repeat as needed.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and print paths without deleting them.",
    )
    return parser


def main():
    args = build_parser().parse_args()
    root = repository_root(args.repo_root)
    dataset_path = expected_dataset_path(
        root,
        args.task,
        args.run_id,
        args.dataset,
    )
    confirmation = str(Path(args.confirm_delete).expanduser().resolve())
    if confirmation != str(dataset_path):
        raise ValueError(
            "--confirm-delete must exactly match the resolved dataset path:\n"
            f"{dataset_path}"
        )
    temporary_paths = [
        validate_temporary_path(path) for path in args.temporary_path
    ]

    print(f"Dataset run directory: {dataset_path}")
    for temporary_path in temporary_paths:
        print(f"Temporary investigation directory: {temporary_path}")

    if args.dry_run:
        print("Dry run complete. Nothing was deleted.")
        return

    remove_directory(dataset_path)
    for temporary_path in temporary_paths:
        remove_directory(temporary_path)
    print("Confirmed investigation files were deleted.")


if __name__ == "__main__":
    main()
