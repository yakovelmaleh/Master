#!/usr/bin/env python3
"""HF Git bundles are code and allowlisted metadata, never deployable models."""

import argparse
import csv
import os
from pathlib import Path
import shutil


BLOCKED_DIRS = {"cache", "hub", "snapshots", "blobs", "checkpoint", "checkpoints",
                "adapter", "embeddings", "data", "__pycache__", ".cache", ".git"}
METADATA = {"hf_report.json", "hf_job_plan.json", "experiment.json", "profile.json",
            "candidate.json", "metrics.json", "run_metadata.json", "inference_reference.json"}
CODE_SUFFIXES = {".py", ".sh", ".json", ".md", ".txt"}
MAX_BYTES = 90 * 1024 * 1024


def allowed(path, relative, definition=False):
    if path.is_symlink() or any(part in BLOCKED_DIRS for part in relative.parts):
        return False
    if definition:
        return not any(part in {"cluster_runs", "runs", "results"} for part in relative.parts) and path.suffix in CODE_SUFFIXES
    return path.name in METADATA or path.suffix in (".out", ".err", ".sbatch")


def copy_tree(source, destination, definition=False):
    source, destination = Path(source), Path(destination)
    omissions = []
    if source.is_symlink():
        raise ValueError("HF bundle source cannot be a symlink.")
    for directory, dirs, files in os.walk(source, followlinks=False):
        for name in list(dirs):
            path = Path(directory) / name
            if name in BLOCKED_DIRS or path.is_symlink() or definition and name in {"cluster_runs", "runs", "results"}:
                dirs.remove(name)
                omissions.append((str(path.relative_to(source)), "excluded_directory"))
        for name in files:
            path = Path(directory) / name
            relative = path.relative_to(source)
            if not allowed(path, relative, definition) or path.stat().st_size > MAX_BYTES:
                omissions.append((str(relative), "not_allowlisted_or_oversized"))
                continue
            output = destination / relative
            output.parent.mkdir(parents=True, exist_ok=True)
            with path.open("rb") as stream, output.open("wb") as out:
                copied = 0
                while True:
                    chunk = stream.read(1024 * 1024)
                    if not chunk:
                        break
                    copied += len(chunk)
                    if copied > MAX_BYTES:
                        out.close()
                        output.unlink()
                        raise ValueError("Artifact exceeded the size bound while copying.")
                    out.write(chunk)
    destination.mkdir(parents=True, exist_ok=True)
    with (destination / "HF_OMITTED_FILES.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["path", "reason"])
        writer.writerows(omissions)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--definition", action="store_true")
    args = parser.parse_args()
    copy_tree(args.source, args.destination, args.definition)
