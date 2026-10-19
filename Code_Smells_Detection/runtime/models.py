"""Matched binary models, validation-only selection, sealed tests and inference."""

from collections import Counter
import html
import itertools
import json
from pathlib import Path
import warnings

import joblib
import numpy as np
import pandas as pd
import sklearn

from . import collection
from .common import (
    COMPARISON, PARTITIONS, SCHEMA, digest, file_hash, immutable_json, lock,
    read_json, require_stage, verify_study, write_csv, write_json,
)
from .prepare import FEATURE_COLUMNS, frozen_frame, source_candidates
from unstable_model.data import prepare_feature_frame
from unstable_model.features import FeatureTransformer
from unstable_model.evaluation import calculate_metrics, select_threshold
from model_comparison import build_model, fit_candidate


FAMILIES = ("RF", "XGboost", "NN")
VARIANTS = ("baseline", "refactored")
ESTIMATORS = {"RF": "RandomForestClassifier", "XGboost": "GradientBoostingClassifier", "NN": "MLPClassifier"}


def model_config(path=None):
    config = read_json(path or COMPARISON / "comparison_config.json")
    if set(config["models"]) != set(FAMILIES):
        raise ValueError("This study requires exactly RF, legacy boosting and NN.")
    if not isinstance(config["seed"], int):
        raise ValueError("A fixed integer seed is required.")
    config.setdefault("bootstrap_samples", 2000)
    if not isinstance(config["bootstrap_samples"], int) or config["bootstrap_samples"] < 1:
        raise ValueError("bootstrap_samples must be positive.")
    for family, candidates in config["models"].items():
        if not candidates:
            raise ValueError("Each family needs a nonempty candidate grid.")
        for candidate in candidates:
            build_model(family, candidate, config["seed"])
    return config


def load_labels(root):
    manifest = read_json(root / "labels/manifest.json")
    catalog = read_json(root / "labels/catalog.json")
    if file_hash(root / "labels/story_labels.csv") != manifest["labels_sha256"] or digest(catalog) != manifest["catalog_sha256"]:
        raise ValueError("Frozen labels or catalog changed.")
    if (digest(read_json(root / "labels/coverage.json")) != manifest["coverage_sha256"] or
            digest(read_json(root / "labels/exclusions.json")) != manifest["exclusions_sha256"]):
        raise ValueError("Frozen coverage or reviewed exclusions changed.")
    labels = pd.read_csv(root / "labels/story_labels.csv")
    if labels.row_id.duplicated().any() or labels.empty:
        raise ValueError("Missing or duplicate label rows.")
    for source, expected in manifest["splits"].items():
        if file_hash(root / "splits" / f"{source}.json") != expected:
            raise ValueError("Label split provenance differs.")
    for language, expected in manifest["profiles"].items():
        if digest(read_json(root / "detection/profiles" / f"{language}.json")) != expected:
            raise ValueError("Detector profile changed after labeling.")
    for target in catalog:
        values = labels[target].dropna()
        if not values.isin([0, 1]).all():
            raise ValueError(f"Nonbinary target: {target}")
    return labels, catalog, manifest


def partitions(root, source, target, labels):
    frame, split = frozen_frame(root, source)
    rows = labels[(labels.source == source) & labels[target].notna()]
    if not set(rows.row_id) <= set(frame.row_id):
        raise ValueError("Labels contain rows outside frozen features.")
    merged = frame.merge(rows[["row_id", "partition", target]], on="row_id", validate="one_to_one")
    if (merged.row_id.map(split["assignment"]) != merged.partition).any():
        raise ValueError("A labeled row moved between frozen partitions.")
    if merged.empty:
        empty = merged[FEATURE_COLUMNS + ["row_id", "source", "partition"]].copy()
        empty["target"] = pd.Series(dtype=int)
        return {name: empty.copy() for name in PARTITIONS}
    data = prepare_feature_frame(merged[FEATURE_COLUMNS])
    data["row_id"] = merged.row_id.to_numpy()
    data["source"] = source
    data["partition"] = merged.partition.to_numpy()
    data["target"] = merged[target].astype(int).to_numpy()
    return {name: data[data.partition == name].copy() for name in PARTITIONS}


def identity(root, config):
    return digest({"labels_manifest": file_hash(root / "labels/manifest.json"),
                   "config": config, "code": verify_study(root)["source_sha256"],
                   "versions": {"numpy": np.__version__, "pandas": pd.__version__, "sklearn": sklearn.__version__}})


def validate(root, config_path=None):
    require_stage(root, "labels", "all")
    config = model_config(config_path)
    labels, catalog, manifest = load_labels(root)
    study = verify_study(root)
    matrix = []
    for source in study["sources"]:
        source_count = int((labels.source == source).sum())
        for target, description in catalog.items():
            data = partitions(root, source, target, labels)
            reason = None
            if source_count < manifest["min_source_rows"]:
                reason = "fewer_than_100_fully_labeled_stories"
            elif any(data[name].empty for name in PARTITIONS):
                reason = "empty_applicable_partition"
            elif any(data[name].target.nunique() != 2 for name in ("train", "validation")):
                reason = "single_class_train_or_validation"
            for family, variant in itertools.product(FAMILIES, VARIANTS):
                matrix.append({"source": source, "target": target, **description,
                               "family": family, "estimator": ESTIMATORS[family], "variant": variant,
                               "status": "insufficient_data" if reason else "ready", "reason": reason,
                               "rows": {name: frame.row_id.tolist() for name, frame in data.items()}})
    expected = {"schema": SCHEMA, "fingerprint": identity(root, config), "config": config, "matrix": matrix}
    immutable_json(root / "models/experiment.json", expected)
    write_json(root / "models/coverage.json", dict(Counter(item["status"] for item in matrix)))
    return expected


def experiment(root):
    saved = read_json(root / "models/experiment.json")
    load_labels(root)
    if saved["fingerprint"] != identity(root, saved["config"]):
        raise ValueError("Training configuration, software or data changed.")
    return saved


def model_path(root, item):
    return root / "models" / item["source"] / item["target"] / item["family"] / item["variant"]


def predict_frame(model, transformer, frame, threshold):
    probabilities = model.predict_proba(transformer.transform(frame))[:, list(model.classes_).index(1)]
    result = frame[["row_id", "source"]].copy()
    result["actual_label"] = frame.target.to_numpy()
    result["probability"] = probabilities
    result["predicted_label"] = (probabilities >= threshold).astype(int)
    return result


def train(root, source):
    if (root / "models/sealed.json").exists():
        raise ValueError("Cannot train after sealing.")
    expected = experiment(root)
    labels, _, _ = load_labels(root)
    config = expected["config"]
    for item in expected["matrix"]:
        if item["source"] != source or item["status"] != "ready":
            continue
        destination = model_path(root, item)
        with lock(destination.with_suffix(".lock")):
            if (destination / "selected.json").exists():
                selected = read_json(destination / "selected.json")
                if selected["fingerprint"] != expected["fingerprint"]:
                    raise ValueError("Candidate belongs to a different experiment.")
                for name, value in selected["files"].items():
                    if file_hash(destination / name) != value:
                        raise ValueError("Completed candidate artifact changed.")
                continue
            data = partitions(root, source, item["target"], labels)
            if any(data[name].row_id.tolist() != item["rows"][name] for name in PARTITIONS):
                raise ValueError("Training/evaluation rows differ from planned membership.")
            transformer = FeatureTransformer()
            x = transformer.fit_transform(data["train"])
            validation_x = transformer.transform(data["validation"])
            y = data["train"].target.to_numpy()
            validation_y = data["validation"].target.to_numpy()
            candidates, best, best_score = [], None, -np.inf
            for parameters in config["models"][item["family"]]:
                model = build_model(item["family"], parameters, config["seed"])
                with warnings.catch_warnings(record=True) as caught:
                    warnings.simplefilter("always")
                    balancing = fit_candidate(model, item["family"], item["variant"], x, y, config["seed"])
                for warning in caught:
                    warnings.warn(str(warning.message), warning.category)
                probability = model.predict_proba(validation_x)[:, list(model.classes_).index(1)]
                score = calculate_metrics(validation_y, probability, .5)["auc_prc"]
                candidates.append({"parameters": parameters, "validation_auc_prc": score,
                                   "warnings": [str(w.message) for w in caught]})
                if score is not None and score > best_score:
                    best, best_score = model, score
            if best is None:
                raise ValueError("No finite validation-selected candidate.")
            probability = best.predict_proba(validation_x)[:, list(best.classes_).index(1)]
            threshold = select_threshold(validation_y, probability)
            destination.mkdir(parents=True, exist_ok=True)
            joblib.dump(best, destination / "model.joblib")
            write_json(destination / "transformer.json", transformer.to_dict())
            write_csv(destination / "validation_predictions.csv",
                      predict_frame(best, transformer, data["validation"], threshold))
            write_json(destination / "selected.json", {
                "fingerprint": expected["fingerprint"], "threshold": threshold,
                "target": item["target"], "source": source, "estimator": item["estimator"],
                "balancing": balancing, "candidates": candidates,
                "validation": calculate_metrics(validation_y, probability, threshold),
                "files": {name: file_hash(destination / name) for name in
                          ("model.joblib", "transformer.json", "validation_predictions.csv")},
            })
            print(f"Trained {source}/{item['target']}/{item['family']}/{item['variant']}", flush=True)


def seal(root):
    expected = experiment(root)
    chosen = {}
    for source in verify_study(root)["sources"]:
        require_stage(root, "train", source)
    for item in expected["matrix"]:
        if item["status"] != "ready":
            continue
        path = model_path(root, item)
        selected = read_json(path / "selected.json")
        if selected["fingerprint"] != expected["fingerprint"]:
            raise ValueError("Selection fingerprint differs.")
        for name, value in selected["files"].items():
            if file_hash(path / name) != value:
                raise ValueError("Selected artifact changed.")
        chosen[str(path.relative_to(root))] = file_hash(path / "selected.json")
    if not chosen:
        raise ValueError("No trainable targets; inspect model coverage before sealing.")
    immutable_json(root / "models/sealed.json", {"fingerprint": expected["fingerprint"], "selected": chosen})


def load_model(root, item, sealed):
    path = model_path(root, item)
    if file_hash(path / "selected.json") != sealed["selected"][str(path.relative_to(root))]:
        raise ValueError("Sealed selection changed.")
    selection = read_json(path / "selected.json")
    for name, expected in selection["files"].items():
        if file_hash(path / name) != expected:
            raise ValueError("Sealed model/transformer changed.")
    return joblib.load(path / "model.joblib"), FeatureTransformer.from_dict(read_json(path / "transformer.json")), selection


def intervals(labels, probability, threshold, seed, samples):
    rng = np.random.RandomState(seed)
    values = {name: [] for name in ("auc_prc", "average_precision", "roc_auc", "f1")}
    for _ in range(samples):
        indices = rng.randint(0, len(labels), len(labels))
        metrics = calculate_metrics(labels[indices], probability[indices], threshold)
        for name in values:
            if metrics[name] is not None:
                values[name].append(metrics[name])
    return {name: {"lower": float(np.percentile(scores, 2.5)), "upper": float(np.percentile(scores, 97.5)),
                   "valid_resamples": len(scores)} if scores else None for name, scores in values.items()}


def test(root, source):
    expected = experiment(root)
    require_stage(root, "seal", "all")
    sealed = read_json(root / "models/sealed.json")
    if sealed["fingerprint"] != expected["fingerprint"]:
        raise ValueError("Sealed experiment differs.")
    labels, _, _ = load_labels(root)
    for item in expected["matrix"]:
        if item["source"] != source or item["status"] != "ready":
            continue
        model, transformer, selected = load_model(root, item, sealed)
        frame = partitions(root, source, item["target"], labels)["test"]
        if frame.row_id.tolist() != item["rows"]["test"]:
            raise ValueError("Held-out row membership differs.")
        prediction = predict_frame(model, transformer, frame, selected["threshold"])
        y, p = prediction.actual_label.to_numpy(), prediction.probability.to_numpy()
        metrics = calculate_metrics(y, p, selected["threshold"])
        metrics["constant_score_control"] = calculate_metrics(y, np.full(len(y), .5), .5)
        metrics["confidence_intervals"] = intervals(y, p, selected["threshold"],
                                                    expected["config"]["seed"], expected["config"]["bootstrap_samples"])
        metrics["bootstrap_caveat"] = "Paired issue resampling; shared code and temporal dependence are not modeled."
        path = model_path(root, item)
        write_csv(path / "test_predictions.csv", prediction)
        immutable_json(path / "test_metrics.json", metrics)
        immutable_json(path / "tested.json", {
            "sealed_sha256": file_hash(root / "models/sealed.json"),
            "predictions_sha256": file_hash(path / "test_predictions.csv"),
            "metrics_sha256": file_hash(path / "test_metrics.json"),
        })


def report(root, report_output=None):
    expected = experiment(root)
    for source in verify_study(root)["sources"]:
        require_stage(root, "test", source)
    results = []
    for item in expected["matrix"]:
        row = {key: value for key, value in item.items() if key != "rows"}
        row["test_rows_sha256"] = digest(item["rows"]["test"])
        if item["status"] == "ready":
            path = model_path(root, item)
            tested = read_json(path / "tested.json")
            if (tested["sealed_sha256"] != file_hash(root / "models/sealed.json") or
                    tested["metrics_sha256"] != file_hash(path / "test_metrics.json") or
                    tested["predictions_sha256"] != file_hash(path / "test_predictions.csv")):
                raise ValueError("Test output differs from sealed artifacts.")
            row.update(status="succeeded", metrics=read_json(path / "test_metrics.json"))
            row["test_artifacts"] = tested
        results.append(row)
    comparisons, multilabel = comparison_summaries(root, expected)
    retention = {"cohort": read_json(root / "cohort/retention.json"), "sources": {}}
    for source in verify_study(root)["sources"]:
        candidates = source_candidates(root, source)
        raw, approved = collection.load_manifest(root, source, set(candidates.issue_key))
        frozen_frame(root, source)
        decisions = read_json(root / "features" / source / "filter_decisions.json")
        retention["sources"][source] = {
            "collection": {**collection.summary(candidates, raw["records"], approved),
                           "provenance": raw.get("collection", {})},
            "preprocessing": dict(Counter(item["reason"] or "included" for item in decisions
                                          if item["reason"] != "jira_unavailable")),
            "splits": dict(Counter(read_json(root / "splits" / f"{source}.json")["assignment"].values())),
            "evidence": read_json(root / "evidence" / source / "audit.json"),
        }
    value = {"schema": "code-smell-report-v1", "stage": "final-test", "fingerprint": expected["fingerprint"],
             "sources": sorted(verify_study(root)["sources"]), "targets": read_json(root / "labels/catalog.json"),
             "complete": True, "results": results,
             "collection_complete": all(not value["collection"]["approved_unavailable"]
                                        for value in retention["sources"].values()),
             "paired_comparisons": comparisons, "multilabel": multilabel,
             "retention": retention,
             "coverage": read_json(root / "labels/coverage.json"),
             "interpretation": "Detector findings in associated files, not introduced defects or story causation. "
                               "Results are conditional on accessible, preprocessing-eligible stories. "
                               "Approved unavailable candidates have no features, partition or negative label; "
                               "missingness may be selective and creator-history counts may be incomplete."}
    write_json(root / "reports/code_smell_report.json", value)
    flat = []
    for row in results:
        metrics = row.get("metrics", {})
        flat.append({**{key: val for key, val in row.items() if key != "metrics"},
                     **{key: val for key, val in metrics.items() if not isinstance(val, (list, dict))}})
    frame = pd.DataFrame(flat)
    write_csv(root / "reports/results.csv", frame)
    collection_table = pd.DataFrame([
        {"source": source, **{name: details["collection"][name] for name in
                             ("state", "candidates", "collected_complete", "approved_unavailable", "unresolved")}}
        for source, details in retention["sources"].items()])
    (root / "reports/report.html").write_text(
        "<!doctype html><meta charset='utf-8'><h1>Story code-smell prediction</h1><p>" +
        html.escape(value["interpretation"]) + "</p><h2>Jira collection accounting</h2>" +
        collection_table.to_html(index=False, escape=True) + "<h2>Model results</h2>" +
        frame.to_html(index=False, escape=True))
    if report_output:
        write_json(report_output, value)
    return value


def comparison_summaries(root, expected):
    comparisons, multilabel = [], []
    ready = [item for item in expected["matrix"] if item["status"] == "ready"]
    for source, target in sorted({(item["source"], item["target"]) for item in ready}):
        items = [item for item in ready if (item["source"], item["target"]) == (source, target)]
        for left, right in itertools.combinations(items, 2):
            a = pd.read_csv(model_path(root, left) / "test_predictions.csv")
            b = pd.read_csv(model_path(root, right) / "test_predictions.csv")
            if a.row_id.tolist() != b.row_id.tolist() or not np.array_equal(a.actual_label, b.actual_label):
                raise ValueError("Paired comparison rows/labels differ.")
            rng = np.random.RandomState(expected["config"]["seed"])
            differences = []
            y, pa, pb = a.actual_label.to_numpy(), a.probability.to_numpy(), b.probability.to_numpy()
            for _ in range(expected["config"]["bootstrap_samples"]):
                index = rng.randint(0, len(y), len(y))
                ma = calculate_metrics(y[index], pa[index], .5)["average_precision"]
                mb = calculate_metrics(y[index], pb[index], .5)["average_precision"]
                if ma is not None and mb is not None:
                    differences.append(ma - mb)
            comparisons.append({
                "source": source, "target": target,
                "left": [left["family"], left["variant"]], "right": [right["family"], right["variant"]],
                "test_row_ids_sha256": digest(a.row_id.tolist()),
                "ap_difference_95_interval": [float(np.percentile(differences, 2.5)),
                                              float(np.percentile(differences, 97.5))] if differences else None,
                "valid_resamples": len(differences),
            })
    groups = {(item["source"], item["language"], item["family"], item["variant"])
              for item in ready if item["language"] is not None}
    for source, language, family, variant in sorted(groups):
        items = [item for item in ready if (item["source"], item["language"], item["family"], item["variant"])
                 == (source, language, family, variant)]
        predictions = [pd.read_csv(model_path(root, item) / "test_predictions.csv") for item in items]
        common_rows = set(predictions[0].row_id).intersection(*(set(frame.row_id) for frame in predictions[1:]))
        ordered = [row for row in predictions[0].row_id if row in common_rows]
        if not ordered:
            continue
        truth = np.column_stack([frame.set_index("row_id").loc[ordered].actual_label for frame in predictions])
        predicted = np.column_stack([frame.set_index("row_id").loc[ordered].predicted_label for frame in predictions])
        from unstable_model.evaluation import binary_metrics
        micro = binary_metrics(truth.ravel(), predicted.ravel())
        multilabel.append({
            "source": source, "language": language, "family": family, "variant": variant,
            "targets": [item["target"] for item in items], "test_row_ids_sha256": digest(ordered),
            "rows": len(ordered), "micro_f1": micro["f1"],
            "macro_f1": float(np.mean([binary_metrics(truth[:, i], predicted[:, i])["f1"]
                                       for i in range(truth.shape[1])])),
            "hamming_loss": float(np.mean(truth != predicted)),
            "subset_accuracy": float(np.mean(np.all(truth == predicted, axis=1))),
            "omitted_targets": [item["target"] for item in expected["matrix"]
                                if (item["source"], item["language"], item["family"], item["variant"])
                                == (source, language, family, variant) and item["status"] != "ready"],
        })
    return comparisons, multilabel


def infer(root, source, family, variant, input_csv, output_csv):
    expected = experiment(root)
    sealed = read_json(root / "models/sealed.json")
    if source not in verify_study(root)["sources"] or family not in FAMILIES or variant not in VARIANTS:
        raise ValueError("Unknown source, family or variant.")
    incoming = pd.read_csv(input_csv, keep_default_na=False)
    if set(incoming.columns) != set(FEATURE_COLUMNS):
        raise ValueError("Inference requires exactly the documented pre-sprint feature columns.")
    frame = prepare_feature_frame(incoming)
    if frame.time_add_to_sprint.isna().any() or frame.issue_key.duplicated().any():
        raise ValueError("Invalid timestamps or duplicate inference keys.")
    outputs = []
    for item in expected["matrix"]:
        if (item["source"], item["family"], item["variant"], item["status"]) != (source, family, variant, "ready"):
            continue
        model, transformer, selected = load_model(root, item, sealed)
        probabilities = model.predict_proba(transformer.transform(frame))[:, list(model.classes_).index(1)]
        for key, probability in zip(frame.issue_key, probabilities):
            outputs.append({"issue_key": key, "target": item["target"], "language": item["language"],
                            "probability": float(probability), "threshold": selected["threshold"],
                            "predicted_label": int(probability >= selected["threshold"])})
    if not outputs:
        raise ValueError("No supported trained targets for the requested source/model.")
    write_csv(output_csv, pd.DataFrame(outputs))
