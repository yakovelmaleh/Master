#!/usr/bin/env python3
"""Stage-gated within-project HF experiments. No network model loading."""

import argparse
import itertools
from pathlib import Path
import resource
import time

import numpy as np

from common import (
    LEVELS, PROJECTS, REPO, TASK, artifact_hashes, check_artifact, digest,
    exclusive_lock, external_path, file_hash, model_registry, read_json, slug, write_json,
)
from data_contract import baseline_predictions, load_project
from evaluate import final_metrics, rank
from model_adapters import (
    TextBackend, load_head, predict, save_head, seed_everything, sigmoid_head,
    train_adapter, versions,
)
from model_comparison import predictions
from unstable_model.data import label_column
from unstable_model.evaluation import calculate_metrics, select_threshold
from unstable_model.features import FeatureTransformer


def validate_config(config):
    for key in ("seed", "max_length", "batch_size", "epochs", "top_families", "lora_rank"):
        if type(config[key]) is not int or config[key] < (0 if key == "seed" else 1):
            raise ValueError(f"Invalid experiment setting: {key}")
    if config["max_length"] > 1024 or config["top_families"] > 2:
        raise ValueError("Initial workflow caps sequence length at 1024 and fine-tuned families at two.")
    if config["dtype"] not in ("float32", "float16", "bfloat16"):
        raise ValueError("Unsupported dtype.")
    for key in ("learning_rates", "linear_c"):
        if not config[key] or len(config[key]) > 2 or any(
            not np.isfinite(v) or v <= 0 for v in config[key]
        ):
            raise ValueError(f"Invalid or unbounded grid: {key}")
    if not config["class_weights"] or any(v not in (None, "balanced") for v in config["class_weights"]):
        raise ValueError("Invalid class weights.")
    if not config["structured"] or any(type(v) is not bool for v in config["structured"]):
        raise ValueError("Invalid structured-feature variants.")
    if type(config["bootstrap_samples"]) is not int or config["bootstrap_samples"] < 100:
        raise ValueError("At least 100 bootstrap samples are required.")


def source_fingerprint():
    roots = [TASK, REPO / "Tasks/research-hf-instability-models",
             REPO / "Tasks/jira-url-to-instability-model/unstable_model"]
    return digest({str(path.relative_to(REPO)): file_hash(path)
                   for root in roots for path in root.rglob("*.py")
                   if "cluster_runs" not in path.parts and "__pycache__" not in path.parts})


def study_root(args):
    return external_path(args.storage) / "runs" / slug(args.run_id)


def initialize_study(args, config):
    root = study_root(args)
    values = {
        "schema": "hf-instability-v1", "config": config,
        "models": {key: model_registry()[key] for key in sorted(args.models)},
        "projects": list(PROJECTS), "reference_sha256": file_hash(TASK / "reference_contract.json"),
        "source_sha256": source_fingerprint(), "versions": versions(),
        "cache": str(external_path(args.cache)),
    }
    with exclusive_lock(root / ".study.lock"):
        path = root / "study.json"
        if path.exists() and read_json(path) != values:
            raise ValueError("Study provenance changed. Use a new run ID; do not resume with different inputs.")
        if not path.exists():
            write_json(path, values)
    return root


def structured_features(train, validation, enabled):
    if not enabled:
        return (np.empty((len(train), 0), dtype=np.float32),
                np.empty((len(validation), 0), dtype=np.float32), None)
    transformer = FeatureTransformer()
    return (transformer.fit_transform(train).astype(np.float32),
            transformer.transform(validation).astype(np.float32), transformer.to_dict())


def checkpoint_spec(args, config, level, transformer, stage):
    return {"schema": "hf-instability-v1", "project": args.project, "level": level,
            "model_key": args.model, "model": model_registry()[args.model],
            "config": config, "transformer": transformer, "stage": stage}


def predict_checkpoint(checkpoint, cache, frame):
    checkpoint = Path(checkpoint)
    spec = read_json(checkpoint / "inference.json")
    if spec["model"] != model_registry()[spec["model_key"]]:
        raise ValueError("Checkpoint base revision differs from the pinned registry.")
    transformer = spec["transformer"]
    extra = (FeatureTransformer.from_dict(transformer).transform(frame).astype(np.float32)
             if transformer is not None else np.empty((len(frame), 0), dtype=np.float32))
    backend = TextBackend(spec["model_key"], cache, spec["config"],
                          adapter=checkpoint / "adapter" if spec["stage"] == "finetune" else None)
    try:
        return predict(backend, frame.model_text, extra, load_head(checkpoint / "head.safetensors"))
    finally:
        backend.close()


def candidate_result(destination, spec, probability, validation, level, parameters):
    threshold = select_threshold(validation[label_column(level)].to_numpy(), probability)
    checkpoint = destination / "checkpoint"
    write_json(checkpoint / "inference.json", spec)
    (checkpoint / "README.md").write_text(
        f"# Within-project instability classifier\n\n"
        f"Base: `{spec['model']['id']}` at `{spec['model']['revision']}`.\n\n"
        f"Project: {spec['project']}; unstable level: {level}; stage: {spec['stage']}.\n\n"
        "Use Master Tasks/train-hf-instability-within-project/predict.py; this is not a "
        "standalone Transformers pipeline. The base model and tokenizer are downloaded "
        "separately at their pinned revision. Inputs must be the original pre-sprint fields.\n\n"
        "Retrospective public-Jira benchmark; pretraining contamination is possible. "
        "No claim of meeting the research target is made by publishing this checkpoint.\n"
    )
    predictions(destination / "validation_predictions.csv", validation, level, probability, threshold)
    result = {
        "stage": spec["stage"], "project": spec["project"], "level": level,
        "model": spec["model_key"], "parameters": parameters, "threshold": threshold,
        "validation": calculate_metrics(validation[label_column(level)].to_numpy(), probability, threshold),
        "checkpoint_files": artifact_hashes(checkpoint),
        "validation_predictions_sha256": file_hash(destination / "validation_predictions.csv"),
    }
    write_json(destination / "candidate.json", result)
    return result


def prior_candidate(destination):
    path = destination / "candidate.json"
    if not path.exists():
        return None
    result = read_json(path)
    check_artifact(destination / "checkpoint", result["checkpoint_files"])
    if file_hash(destination / "validation_predictions.csv") != result["validation_predictions_sha256"]:
        raise ValueError("Validation predictions changed.")
    return result


def frozen(args, config, root):
    from sklearn.linear_model import LogisticRegression

    train, validation, _ = load_project(args.project, root)
    backend = TextBackend(args.model, args.cache, config)
    try:
        write_json(root / "length_reports" / f"{args.project}-{args.model}.json",
                   {"train": backend.length_report(train.model_text)})
        train_embeddings = backend.embeddings(train.model_text, args.storage)
        val_embeddings = backend.embeddings(validation.model_text, args.storage)
        for level, structured, weight, c in itertools.product(
            LEVELS, config["structured"], config["class_weights"], config["linear_c"]
        ):
            parameters = {"structured": structured, "class_weight": weight, "C": c}
            destination = root / "frozen" / args.project / args.model / str(level) / digest(parameters)[:16]
            if prior_candidate(destination):
                continue
            extra_train, extra_val, transformer = structured_features(train, validation, structured)
            features = np.concatenate([train_embeddings, extra_train], axis=1)
            head = LogisticRegression(C=c, class_weight=weight, random_state=config["seed"], max_iter=2000)
            head.fit(features, train[label_column(level)])
            checkpoint = destination / "checkpoint"
            checkpoint.mkdir(parents=True, exist_ok=True)
            save_head(checkpoint / "head.safetensors", head.coef_, head.intercept_)
            val_features = np.concatenate([val_embeddings, extra_val], axis=1)
            probability = sigmoid_head(val_features, load_head(checkpoint / "head.safetensors"))
            np.testing.assert_allclose(probability, head.predict_proba(val_features)[:, 1], atol=1e-6, rtol=1e-5)
            candidate_result(destination, checkpoint_spec(args, config, level, transformer, "frozen"),
                             probability, validation, level, parameters)
    finally:
        backend.close()


def candidates(root, project, level, stages):
    values = []
    for stage in stages:
        for path in sorted((root / stage / project).glob(f"*/{level}/*/candidate.json")):
            value = prior_candidate(path.parent)
            values.append((value, path.parent))
    return values


def require_frozen_complete(root, study):
    for project in PROJECTS:
        for name in study["models"]:
            status = root / "status" / f"frozen-{project}-{name}.json"
            if not status.exists() or read_json(status)["status"] != "succeeded":
                raise ValueError(f"Frozen stage incomplete: {project}/{name}")


def top_families(root, project, level, count):
    best = {}
    for result, _ in candidates(root, project, level, ("frozen",)):
        name = result["model"]
        if name not in best or rank(result["validation"]) > rank(best[name]["validation"]):
            best[name] = result
    return sorted(best, key=lambda name: (rank(best[name]["validation"]), name), reverse=True)[:count]


def finetune(args, config, root):
    require_frozen_complete(root, read_json(root / "study.json"))
    train, validation, _ = load_project(args.project, root)
    for level in LEVELS:
        if args.model not in top_families(root, args.project, level, config["top_families"]):
            continue
        choices = [r for r, _ in candidates(root, args.project, level, ("frozen",)) if r["model"] == args.model]
        winner = max(choices, key=lambda item: rank(item["validation"]))
        structured = winner["parameters"]["structured"]
        extra_train, extra_val, transformer = structured_features(train, validation, structured)
        for rate, weight in itertools.product(config["learning_rates"], config["class_weights"]):
            parameters = {"learning_rate": rate, "class_weight": weight, "structured": structured}
            destination = root / "finetune" / args.project / args.model / str(level) / digest(parameters)[:16]
            if prior_candidate(destination):
                continue
            seed_everything(config["seed"])
            backend = TextBackend(args.model, args.cache, config, training=True)
            checkpoint = destination / "checkpoint"
            try:
                train_adapter(backend, train.model_text, extra_train,
                              train[label_column(level)].to_numpy(), config, checkpoint, rate, weight)
                probability = predict(backend, validation.model_text, extra_val,
                                      load_head(checkpoint / "head.safetensors"))
                spec = checkpoint_spec(args, config, level, transformer, "finetune")
                write_json(checkpoint / "inference.json", spec)
            finally:
                backend.close()
            reloaded = predict_checkpoint(checkpoint, args.cache, validation)
            np.testing.assert_allclose(probability, reloaded, atol=1e-5, rtol=1e-4)
            candidate_result(destination, spec, reloaded, validation, level, parameters)


def seal(root):
    study = read_json(root / "study.json")
    require_frozen_complete(root, study)
    for project in PROJECTS:
        for name in study["models"]:
            status = root / "status" / f"finetune-{project}-{name}.json"
            if not status.exists() or read_json(status)["status"] != "succeeded":
                raise ValueError(f"Fine-tuning stage incomplete: {project}/{name}")
    selections = []
    for project, level in itertools.product(PROJECTS, LEVELS):
        options = candidates(root, project, level, ("frozen", "finetune"))
        if not options:
            raise ValueError(f"No candidates for {project}/{level}")
        winner, path = max(options, key=lambda item: (rank(item[0]["validation"]), str(item[1])))
        selections.append({**winner, "directory": str(path.relative_to(root))})
    value = {"study_sha256": digest(study), "selections": selections,
             "selection_policy": "validation quality gates, then trapezoidal PR area, then AP"}
    with exclusive_lock(root / ".study.lock"):
        if (root / "sealed.json").exists() and read_json(root / "sealed.json") != value:
            raise ValueError("Selection is already sealed; use a new exploratory run.")
        write_json(root / "sealed.json", value)


def test_selected(args, config, root):
    sealed = read_json(root / "sealed.json")
    if sealed["study_sha256"] != digest(read_json(root / "study.json")):
        raise ValueError("Sealed study changed.")
    _, validation, test = load_project(args.project, root)
    for selected in sealed["selections"]:
        if selected["project"] != args.project or selected["model"] != args.model:
            continue
        level = selected["level"]
        destination = root / "final" / args.project / str(level)
        with exclusive_lock(destination / ".test.lock"):
            completed = destination / "metrics.json"
            checkpoint = root / selected["directory"] / "checkpoint"
            check_artifact(checkpoint, selected["checkpoint_files"])
            if completed.exists():
                if read_json(completed)["selection_sha256"] != digest(selected):
                    raise ValueError("Final evaluation selection changed.")
                if file_hash(destination / "test_predictions.csv") != read_json(completed)["test_predictions_sha256"]:
                    raise ValueError("Saved test predictions changed.")
                continue
            # Reload equivalence is checked on validation before touching the final test.
            import pandas as pd

            validation_path = root / selected["directory"] / "validation_predictions.csv"
            if file_hash(validation_path) != selected["validation_predictions_sha256"]:
                raise ValueError("Selected validation predictions changed.")
            saved = pd.read_csv(validation_path)
            if saved.row_id.tolist() != validation.row_id.tolist():
                raise ValueError("Validation prediction order changed.")
            reloaded = predict_checkpoint(checkpoint, args.cache, validation)
            np.testing.assert_allclose(saved.instability_probability, reloaded, atol=1e-5, rtol=1e-4)
            probability = predict_checkpoint(checkpoint, args.cache, test)
            baseline_probability, baseline = baseline_predictions(args.project, level, test)
            result = final_metrics(
                test[label_column(level)].to_numpy(), probability, baseline_probability,
                selected["threshold"], config["bootstrap_samples"], config["seed"],
            )
            predictions(destination / "test_predictions.csv", test, level, probability, selected["threshold"])
            write_json(completed, {
                **result, "project": args.project, "level": level, "model": args.model,
                "stage": "final-test", "selection_sha256": digest(selected),
                "checkpoint_files": selected["checkpoint_files"],
                "artifact_reference": {
                    "study_relative_checkpoint": str(checkpoint.relative_to(root)),
                    "base": model_registry()[args.model], "config_sha256": digest(config),
                    "source_sha256": source_fingerprint(),
                },
                "baseline_identity": {"model": baseline["model"], "variant": baseline["variant"]},
                "test_predictions_sha256": file_hash(destination / "test_predictions.csv"),
            })


def report(root, output):
    study = read_json(root / "study.json")
    sealed = read_json(root / "sealed.json")
    if sealed["study_sha256"] != digest(study):
        raise ValueError("Cannot report a changed sealed study.")
    selections = {(cell["project"], cell["level"]): cell for cell in sealed["selections"]}
    rows = []
    for project, level in itertools.product(PROJECTS, LEVELS):
        path = root / "final" / project / str(level) / "metrics.json"
        if path.exists():
            result = read_json(path)
            if result["selection_sha256"] != digest(selections[project, level]):
                raise ValueError("Final result does not match sealed selection.")
            if file_hash(path.parent / "test_predictions.csv") != result["test_predictions_sha256"]:
                raise ValueError("Final prediction file changed.")
            rows.append(result)
        else:
            rows.append({"project": project, "level": level, "status": "missing", "gates": {"passed": False}})
    macros = {}
    for level in LEVELS:
        cells = [row for row in rows if row["level"] == level and "test" in row]
        macros[str(level)] = {
            "completed_projects": len(cells),
            **{metric: float(np.mean([row["test"][metric] for row in cells]))
               if len(cells) == len(PROJECTS) and all(row["test"][metric] is not None for row in cells)
               else None for metric in ("auc_prc", "average_precision", "roc_auc")},
        }
    write_json(output, {"schema": "hf-instability-report-v1", "stage": "final-test",
                        "study_sha256": digest(study), "cells": rows,
                        "macro_by_level_secondary": macros,
                        "all_24_passed": all(row["gates"]["passed"] for row in rows),
                        "retrospective_holdout": True})


def profile(args, config):
    import torch

    if not torch.cuda.is_available():
        raise ValueError("A real allocated CUDA GPU is required for the cluster profile.")
    seed_everything(config["seed"])
    torch.cuda.reset_peak_memory_stats()
    start = time.monotonic()
    backend = TextBackend(args.model, args.cache, config, training=True)
    destination = external_path(args.storage) / "profiles" / args.model / digest(config)
    destination.mkdir(parents=True, exist_ok=True)
    try:
        # Force maximum-length activations rather than profiling only short Jira examples.
        texts = ["requirement " * config["max_length"]] * (2 * config["batch_size"])
        profile_config = {**config, "epochs": 1}
        train_adapter(backend, texts, np.empty((len(texts), 0), dtype=np.float32),
                      np.arange(len(texts)) % 2, profile_config, destination / "checkpoint",
                      config["learning_rates"][0], None)
        probability = predict(backend, texts, np.empty((len(texts), 0), dtype=np.float32),
                              load_head(destination / "checkpoint/head.safetensors"))
    finally:
        backend.close()
    loaded = TextBackend(args.model, args.cache, config, adapter=destination / "checkpoint/adapter")
    try:
        np.testing.assert_allclose(
            probability, predict(loaded, texts, np.empty((len(texts), 0), dtype=np.float32),
                                 load_head(destination / "checkpoint/head.safetensors")),
            atol=1e-5, rtol=1e-4,
        )
    finally:
        loaded.close()
    torch.cuda.synchronize()
    write_json(destination / "profile.json", {
        "status": "succeeded", "model": model_registry()[args.model], "config": config,
        "source_sha256": source_fingerprint(), "versions": versions(),
        "gpu": torch.cuda.get_device_name(), "vram_bytes": torch.cuda.get_device_properties(0).total_memory,
        "peak_allocated_bytes": torch.cuda.max_memory_allocated(),
        "peak_reserved_bytes": torch.cuda.max_memory_reserved(),
        "host_maxrss_platform_units": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "seconds": time.monotonic() - start,
    })


def require_profile(args, config):
    import torch

    path = external_path(args.storage) / "profiles" / args.model / digest(config) / "profile.json"
    value = read_json(path)
    if (value["status"] != "succeeded" or value["config"] != config
            or value["model"] != model_registry()[args.model] or value["versions"] != versions()
            or value["source_sha256"] != source_fingerprint()):
        raise ValueError("A matching successful GPU profile is required.")
    if not torch.cuda.is_available() or torch.cuda.get_device_name() != value["gpu"]:
        raise ValueError("GPU differs from the profiled hardware; profile this device first.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("profile", "frozen", "finetune", "seal", "test", "report"))
    parser.add_argument("--storage", required=True)
    parser.add_argument("--cache", required=True)
    parser.add_argument("--run-id", default="profile")
    parser.add_argument("--models", nargs="+", choices=sorted(model_registry()), default=["modernbert", "qwen_embedding"])
    parser.add_argument("--model", choices=sorted(model_registry()), default="modernbert")
    parser.add_argument("--project", choices=PROJECTS, default="Apache")
    parser.add_argument("--config", type=Path, default=TASK / "experiment.json")
    parser.add_argument("--report-output", type=Path)
    args = parser.parse_args()
    config = read_json(args.config)
    validate_config(config)
    if args.stage not in ("seal", "report") and args.model not in args.models:
        raise ValueError("--model must belong to this study's --models.")
    if args.stage == "profile":
        path = external_path(args.storage) / "profiles" / args.model / digest(config) / "profile.json"
        write_json(path, {"status": "running"})
        try:
            profile(args, config)
        except Exception as error:
            write_json(path, {"status": "failed", "error_type": type(error).__name__})
            raise
        return
    root = initialize_study(args, config)
    if args.stage == "seal":
        seal(root)
        return
    if args.stage == "report":
        if args.report_output is None:
            raise ValueError("--report-output is required.")
        report(root, args.report_output)
        return
    require_profile(args, config)
    if args.stage in ("frozen", "finetune") and (root / "sealed.json").exists():
        raise ValueError("Cannot train after selection is sealed.")
    if args.stage == "frozen" and (root / "finetune_started.json").exists():
        raise ValueError("Cannot change frozen candidates after fine-tuning starts.")
    if args.stage == "finetune":
        require_frozen_complete(root, read_json(root / "study.json"))
        write_json(root / "finetune_started.json", {"study_sha256": digest(read_json(root / "study.json"))})
    status = root / "status" / f"{args.stage}-{args.project}-{args.model}.json"
    with exclusive_lock(status.with_suffix(".lock")):
        write_json(status, {"status": "running"})
        try:
            seed_everything(config["seed"])
            {"frozen": frozen, "finetune": finetune, "test": test_selected}[args.stage](args, config, root)
        except Exception as error:
            write_json(status, {"status": "failed", "error_type": type(error).__name__})
            raise
        write_json(status, {"status": "succeeded"})


if __name__ == "__main__":
    main()
