#!/usr/bin/env python3
"""Local community Jev zero-shot benchmark with validation-only thresholds."""

import argparse
import importlib.metadata
import itertools
import os
from pathlib import Path
import sys
import time

from jev_backend import MODEL, PROMPT, SHARED, TASK, LocalJev, prepare
from common import (
    LEVELS, PROJECTS, digest, exclusive_lock, external_path, file_hash,
    read_json, slug, write_json,
)


def versions():
    return {name: importlib.metadata.version(name) for name in (
        "torch", "transformers", "safetensors", "huggingface-hub", "numpy", "pandas",
        "scikit-learn", "sentencepiece", "protobuf",
    )}


def protocol():
    files = [*TASK.glob("*.py"), TASK / "model.json", TASK / "requirements.txt",
             SHARED / "common.py", SHARED / "data_contract.py", SHARED / "evaluate.py",
             SHARED / "reference_contract.json", SHARED / "freeze_reference.py",
             TASK.parent / "verify-refactored-instability-model/model_comparison.py"]
    files.extend((TASK.parent / "jira-url-to-instability-model/unstable_model").glob("*.py"))
    return {"model": MODEL, "mode": "community_jev_zero_shot_native_head",
            "prompt": PROMPT, "versions": versions(), "threshold_selection": "validation_f1",
            "source_sha256": digest({str(path.relative_to(TASK.parent)): file_hash(path) for path in files}),
            "seed": 7, "bootstrap_samples": 2000}


def study(args):
    root = external_path(args.storage) / "jev-runs" / slug(args.run_id)
    current = protocol()
    with exclusive_lock(root / ".study.lock"):
        manifest = root / "study.json"
        if manifest.exists() and read_json(manifest) != current:
            raise ValueError("Jev study provenance changed; use a new run ID.")
        if not manifest.exists():
            write_json(manifest, current)
    return root


def profile(storage, cache):
    import torch
    import numpy as np

    signature = protocol()
    target = external_path(storage) / "jev-profiles" / digest(signature) / "profile.json"
    write_json(target, {"status": "running"})
    start = time.monotonic()
    try:
        if not torch.cuda.is_available():
            raise ValueError("GPU profile requires CUDA.")
        torch.cuda.reset_peak_memory_stats()
        examples = ["requirement " * 512, "Add acceptance criteria for the new requirement."]
        before = {}
        backend = LocalJev(cache)
        try:
            for level in LEVELS:
                before[str(level)] = backend.predict(examples, level)
            files = backend.files
        finally:
            backend.close()
        backend = LocalJev(cache)
        try:
            for level in LEVELS:
                np.testing.assert_allclose(before[str(level)], backend.predict(examples, level),
                                           atol=1e-6, rtol=1e-5)
        finally:
            backend.close()
        torch.cuda.synchronize()
        write_json(target, {
            "status": "succeeded", "protocol": signature, "files": files,
            "gpu": torch.cuda.get_device_name(),
            "vram_bytes": torch.cuda.get_device_properties(0).total_memory,
            "peak_reserved_bytes": torch.cuda.max_memory_reserved(),
            "peak_allocated_bytes": torch.cuda.max_memory_allocated(),
            "seconds": time.monotonic() - start,
        })
    except Exception as error:
        write_json(target, {"status": "failed", "error_type": type(error).__name__})
        raise


def require_profile(storage):
    import torch

    signature = protocol()
    path = external_path(storage) / "jev-profiles" / digest(signature) / "profile.json"
    result = read_json(path)
    if result.get("status") != "succeeded" or result["protocol"] != signature:
        raise ValueError("A matching successful Jev profile is required.")
    if not torch.cuda.is_available() or torch.cuda.get_device_name() != result["gpu"]:
        raise ValueError("GPU differs from the successfully profiled device.")
    return result


def validate(args, root, backend):
    import numpy as np
    from data_contract import load_project
    from model_comparison import predictions
    from unstable_model.data import label_column
    from unstable_model.evaluation import calculate_metrics, select_threshold

    if (root / "sealed.json").exists():
        raise ValueError("Validation cannot change after sealing.")
    _, validation, _ = load_project(args.project, root)
    for level in LEVELS:
        destination = root / "validation" / args.project / str(level)
        manifest = destination / "validation.json"
        if manifest.exists():
            if file_hash(destination / "validation_predictions.csv") != read_json(manifest)["predictions_sha256"]:
                raise ValueError("Saved validation predictions changed.")
            continue
        destination.mkdir(parents=True, exist_ok=True)
        labels = validation[label_column(level)].to_numpy()
        if len(np.unique(labels)) != 2:
            raise ValueError("Validation requires both classes.")
        probability = np.asarray(backend.predict(validation.model_text, level))
        threshold = select_threshold(labels, probability)
        predictions(destination / "validation_predictions.csv", validation, level, probability, threshold)
        write_json(manifest, {
            "project": args.project, "level": level, "threshold": threshold,
            "model": "community_jev_deberta", "stage": "validation",
            "validation": calculate_metrics(labels, probability, threshold),
            "predictions_sha256": file_hash(destination / "validation_predictions.csv"),
            "token_coverage": backend.coverage(validation.model_text),
            "checkpoint_files": backend.files,
        })


def seal(root):
    cells = []
    for project, level in itertools.product(PROJECTS, LEVELS):
        status = root / "status" / f"validate-{project}.json"
        if not status.exists() or read_json(status)["status"] != "succeeded":
            raise ValueError(f"Validation incomplete: {project}")
        directory = root / "validation" / project / str(level)
        cell = read_json(directory / "validation.json")
        if file_hash(directory / "validation_predictions.csv") != cell["predictions_sha256"]:
            raise ValueError("Validation predictions changed before sealing.")
        cells.append(cell)
    value = {"study_sha256": digest(read_json(root / "study.json")), "cells": cells}
    with exclusive_lock(root / ".study.lock"):
        if (root / "sealed.json").exists() and read_json(root / "sealed.json") != value:
            raise ValueError("Cannot modify an existing seal.")
        write_json(root / "sealed.json", value)


def sealed_cells(root):
    value = read_json(root / "sealed.json")
    if value["study_sha256"] != digest(read_json(root / "study.json")):
        raise ValueError("Sealed study changed.")
    cells = {(cell["project"], cell["level"]): cell for cell in value["cells"]}
    if len(value["cells"]) != 24 or set(cells) != set(itertools.product(PROJECTS, LEVELS)):
        raise ValueError("Seal requires exactly all 24 cells.")
    return cells


def test(args, root, backend):
    import numpy as np
    import pandas as pd
    from data_contract import load_project, baseline_predictions
    from evaluate import final_metrics
    from model_comparison import predictions
    from unstable_model.data import label_column

    selected = sealed_cells(root)
    _, validation, data = load_project(args.project, root)
    for level in LEVELS:
        cell = selected[args.project, level]
        if cell["checkpoint_files"] != backend.files:
            raise ValueError("Native model artifacts changed since validation.")
        destination = root / "final" / args.project / str(level)
        path = destination / "metrics.json"
        if path.exists():
            previous = read_json(path)
            if (previous["selection_sha256"] != digest(cell) or
                    previous["test_predictions_sha256"] != file_hash(destination / "test_predictions.csv")):
                raise ValueError("Saved test result changed.")
            continue
        val_path = root / "validation" / args.project / str(level) / "validation_predictions.csv"
        if file_hash(val_path) != cell["predictions_sha256"]:
            raise ValueError("Selected validation predictions changed.")
        val_predictions = pd.read_csv(val_path)
        if val_predictions.row_id.tolist() != validation.row_id.tolist():
            raise ValueError("Validation row order changed.")
        np.testing.assert_allclose(
            backend.predict(validation.model_text.iloc[:8], level),
            val_predictions.instability_probability.iloc[:8], atol=1e-6, rtol=1e-5,
        )
        baseline, baseline_identity = baseline_predictions(args.project, level, data)
        probability = np.asarray(backend.predict(data.model_text, level))
        result = final_metrics(data[label_column(level)].to_numpy(), probability, baseline,
                               cell["threshold"], protocol()["bootstrap_samples"], protocol()["seed"])
        destination.mkdir(parents=True, exist_ok=True)
        predictions(destination / "test_predictions.csv", data, level, probability, cell["threshold"])
        write_json(path, {
            **result, "project": args.project, "level": level, "stage": "final-test",
            "model": "community_jev_deberta", "mode": "zero_shot_with_validation_threshold",
            "selection_sha256": digest(cell), "checkpoint_files": backend.files,
            "artifact_reference": MODEL,
            "token_coverage": backend.coverage(data.model_text),
            "baseline_identity": {key: baseline_identity[key] for key in ("model", "variant")},
            "test_predictions_sha256": file_hash(destination / "test_predictions.csv"),
        })


def report(root, output):
    selected = sealed_cells(root)
    cells = []
    for project, level in itertools.product(PROJECTS, LEVELS):
        path = root / "final" / project / str(level) / "metrics.json"
        if not path.exists():
            cells.append({"project": project, "level": level, "status": "missing", "gates": {"passed": False}})
            continue
        cell = read_json(path)
        if (cell["selection_sha256"] != digest(selected[project, level]) or
                cell["test_predictions_sha256"] != file_hash(path.parent / "test_predictions.csv")):
            raise ValueError("Final result changed.")
        cells.append(cell)
    write_json(output, {
        "schema": "hf-instability-report-v1", "stage": "final-test", "cells": cells,
        "all_24_passed": all(cell["gates"]["passed"] for cell in cells),
        "study_sha256": digest(read_json(root / "study.json")),
        "model_identity": MODEL["identity"], "mode": "zero_shot_with_validation_threshold",
        "retrospective_holdout": True, "prompt_tuned_on_test": False,
    })


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("prepare", "profile", "validate", "seal", "test", "report"))
    parser.add_argument("--cache", required=True)
    parser.add_argument("--storage", required=True)
    parser.add_argument("--run-id", default="jev-study-01")
    parser.add_argument("--project", choices=PROJECTS, default="Apache")
    parser.add_argument("--report-output", type=Path)
    args = parser.parse_args()
    if args.stage == "prepare":
        prepare(args.cache)
        return
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    if args.stage == "profile":
        profile(args.storage, args.cache)
        return
    root = study(args)
    if args.stage == "seal":
        seal(root)
        return
    if args.stage == "report":
        if args.report_output is None:
            raise ValueError("--report-output is required.")
        report(root, args.report_output)
        return
    profile_result = require_profile(args.storage)
    status = root / "status" / f"{args.stage}-{args.project}.json"
    with exclusive_lock(status.with_suffix(".lock")):
        write_json(status, {"status": "running"})
        try:
            backend = LocalJev(args.cache)
            try:
                if backend.files != profile_result["files"]:
                    raise ValueError("Snapshot differs from the successful profile.")
                {"validate": validate, "test": test}[args.stage](args, root, backend)
            finally:
                backend.close()
        except Exception as error:
            write_json(status, {"status": "failed", "error_type": type(error).__name__})
            raise
        write_json(status, {"status": "succeeded"})


if __name__ == "__main__":
    main()
