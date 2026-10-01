#!/usr/bin/env python3
"""Copy size-bounded investigation artifacts and record every omitted file."""

import argparse
import csv
from pathlib import Path
import shutil


MAX_FILE_BYTES = 90 * 1024 * 1024
HF_BINARY_SUFFIXES = {".safetensors", ".bin", ".pt", ".pth", ".onnx", ".gguf"}
HF_MODEL_DIRS = {"checkpoint", "checkpoints", "adapter", "snapshots", "blobs", "embeddings", "cache", "hub"}


def tree_files(root, relative=Path(), ancestors=frozenset(), exclude_models=False):
    resolved = root.resolve()
    if resolved in ancestors:
        raise ValueError(f"Directory symlink cycle: {root}")
    for child in sorted(root.iterdir()):
        target = relative / child.name
        if exclude_models and (child.name in HF_MODEL_DIRS or child.is_symlink()):
            yield child, target
            continue
        if child.is_dir():
            yield from tree_files(child, target, ancestors | {resolved}, exclude_models)
        elif child.is_file():
            yield child, target
        else:
            raise ValueError(f"Unsupported or missing artifact: {child}")


def package(results, logs, destination=None, sbatch=None, manifest=None, dataset=None, exclude_models=False):
    included = []
    omitted = []

    def copy(source, target):
        size = source.stat().st_size
        if exclude_models and (source.is_symlink() or source.suffix.lower() in HF_BINARY_SUFFIXES or
                               any(p in HF_MODEL_DIRS for p in source.resolve().parts)):
            omitted.append((str(target), size, "model_artifact_not_for_git"))
            print(f"SKIP (model artifact): {target}")
            return
        if size > MAX_FILE_BYTES:
            omitted.append((str(target), size, "exceeds_90_MiB"))
            print(f"SKIP (>90 MiB): {target} ({size} bytes)")
            return
        print(f"INCLUDE: {target} ({size} bytes)")
        if destination is not None:
            output = destination / "artifacts" / target
            output.parent.mkdir(parents=True, exist_ok=True)
            # Bound the copy even if an active cluster job grows the source.
            with source.open("rb") as stream, output.open("wb") as out:
                remaining = MAX_FILE_BYTES
                while remaining:
                    chunk = stream.read(min(1024 * 1024, remaining))
                    if not chunk:
                        break
                    out.write(chunk)
                    remaining -= len(chunk)
                if stream.read(1):
                    out.close()
                    output.unlink()
                    raise ValueError(f"Artifact grew above 90 MiB while copying: {source}")
            shutil.copystat(source, output)
        included.append(target)

    for source, prefix in ((results, "results"), (logs, "logs")):
        for path, relative in tree_files(source, exclude_models=exclude_models):
            copy(path, Path(prefix) / relative)
    for source, target in (
        (sbatch, "submit.sbatch"),
        (manifest, "submitted_jobs.tsv"),
        (dataset, "dataset/features_labels_table_os.csv"),
    ):
        if source is not None:
            copy(source, Path(target))

    if destination is not None:
        destination.mkdir(parents=True, exist_ok=True)
        with (destination / "OMITTED_FILES.csv").open("w", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["artifact_path", "size_bytes", "reason"])
            writer.writerows(omitted)
        included_count = sum(p.name == "features_labels_table_os.csv" for p in included)
        omitted_count = sum(Path(p).name == "features_labels_table_os.csv" for p, _, _ in omitted)
        status = "complete" if included_count and not omitted_count else (
            "partial_omitted_size" if included_count else
            "omitted_size" if omitted_count else "not_created"
        )
        (destination / "DATASET_STATUS.txt").write_text(status + "\n")
    print(f"Artifacts: {len(included)} included; {len(omitted)} omitted.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--logs", type=Path, required=True)
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--sbatch", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--dataset", type=Path)
    parser.add_argument("--exclude-models", action="store_true")
    args = parser.parse_args()
    package(args.results, args.logs, args.destination, args.sbatch, args.manifest, args.dataset, args.exclude_models)


if __name__ == "__main__":
    main()
