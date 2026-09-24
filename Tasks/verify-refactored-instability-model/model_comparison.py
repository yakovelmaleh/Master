"""Controlled model-family reruns, with separately labeled historical references."""

import hashlib
import json
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.utils.class_weight import compute_sample_weight

from unstable_model.artifacts import write_json
from unstable_model.data import label_column, load_dataset, chronological_split
from unstable_model.evaluation import calculate_metrics, select_threshold
from unstable_model.features import FeatureTransformer


MODEL_CLASSES = {
    "RF": RandomForestClassifier,
    # Preserve the implementation used by Utils/ml_algorithms_run_best_parameters.py.
    "XGboost": GradientBoostingClassifier,
    "NN": MLPClassifier,
}
VARIANTS = ("baseline", "refactored")
LEVELS = (5, 10, 15, 20)


def load_frames(staged_root, projects, levels):
    frames = []
    for project in projects:
        by_level = []
        for level in levels:
            frame = load_dataset(staged_root, project, level)
            frame["row_id"] = project + ":" + frame["issue_key"].astype(str)
            if frame["row_id"].duplicated().any():
                raise ValueError(f"Duplicate issue keys in {project}; cannot prove row alignment.")
            by_level.append(frame.set_index("row_id", drop=False))
        reference = by_level[0]
        for level, other in zip(levels[1:], by_level[1:]):
            if set(reference.index) != set(other.index):
                raise ValueError(f"{project}: eligible rows differ at level {level}.")
            reference[label_column(level)] = other[label_column(level)]
        reference["source_dataset"] = project
        frames.append(reference.reset_index(drop=True))
    return pd.concat(frames, ignore_index=True).sort_values(
        ["time_add_to_sprint", "row_id"], kind="stable"
    ).reset_index(drop=True)


def split_frames(data, protocol, project):
    if protocol == "within-project":
        selected = data[data.source_dataset == project]
        train, validation, test = chronological_split(selected, 0.6, 0.2)
    elif protocol == "pooled":
        train, validation, test = chronological_split(data, 0.6, 0.2)
    elif protocol == "leave-one-project-out":
        test = data[data.source_dataset == project].copy()
        training_projects = data[data.source_dataset != project]
        end = int(len(training_projects) * 0.8)
        train = training_projects.iloc[:end].copy()
        validation = training_projects.iloc[end:].copy()
    else:
        raise ValueError(f"Unknown protocol: {protocol}")
    if min(map(len, (train, validation, test))) == 0:
        raise ValueError("Empty partition; check the selected datasets and protocol.")
    return train, validation, test


def row_hash(frame):
    return hashlib.sha256("\n".join(frame.row_id).encode()).hexdigest()


def partition_info(frame, levels):
    return {
        "rows": len(frame),
        "row_ids_sha256": row_hash(frame),
        "source_counts": frame.source_dataset.value_counts().to_dict(),
        "first_sprint_entry": str(frame.time_add_to_sprint.min()),
        "last_sprint_entry": str(frame.time_add_to_sprint.max()),
        "positive_counts": {str(k): int(frame[label_column(k)].sum()) for k in levels},
    }


def build_model(name, parameters, seed):
    if name not in MODEL_CLASSES:
        raise ValueError(f"Unsupported comparison model: {name}")
    if any(k in parameters for k in ("random_state", "class_weight", "early_stopping")):
        raise ValueError("Seed, balancing and validation are controlled by the runner.")
    options = dict(parameters)
    if name == "NN" and "hidden_layer_sizes" in options:
        options["hidden_layer_sizes"] = tuple(options["hidden_layer_sizes"])
    return MODEL_CLASSES[name](random_state=seed, **options)


def fit_candidate(model, name, variant, x, y, seed):
    if variant == "baseline":
        model.fit(x, y)
        return "none"
    if name != "NN":
        model.fit(x, y, sample_weight=compute_sample_weight("balanced", y))
        return "train_only_balanced_sample_weight"
    # Historical MLP API has no sample_weight on supported Python 3.9 clusters.
    # Balance training only, using the same method as the old sample-weight NN.
    rng = np.random.RandomState(seed)
    groups = [np.flatnonzero(y == label) for label in (0, 1)]
    size = max(map(len, groups))
    indices = np.concatenate([
        np.r_[group, rng.choice(group, size - len(group), replace=True)]
        for group in groups
    ])
    rng.shuffle(indices)
    model.fit(x[indices], y[indices])
    return "train_only_random_oversampling"


def predictions(path, frame, level, probability, threshold):
    columns = ["row_id", "source_dataset", "issue_key", "time_add_to_sprint"]
    output = frame[columns].copy()
    output["actual_label"] = frame[label_column(level)].to_numpy()
    output["instability_probability"] = probability
    output["predicted_label"] = (probability >= threshold).astype(int)
    output.to_csv(path, index=False)


def historical_references(repo, projects, levels, models):
    rows = []
    sources = []
    for project in projects:
        for level in levels:
            path = repo / "Models/results_best_para" / project / (
                f"results_groups_{project}_is_change_text_num_words_{level}.csv"
            )
            if not path.is_file():
                sources.append({"path": str(path), "status": "missing"})
                continue
            sources.append({
                "path": str(path.relative_to(repo)),
                "status": "available",
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            })
            results = pd.read_csv(path)
            for _, row in results[results.Model.isin(models)].iterrows():
                rows.append({
                    "project": project, "level": level, "model": row.Model,
                    "estimator_class": MODEL_CLASSES[row.Model].__name__,
                    "variant": "published_historical_reference",
                    "directly_comparable": False,
                    "auc_prc": row.area_under_pre_recall_curve,
                    "average_precision": row.avg_precision,
                    "accuracy": row.accuracy,
                    "roc_auc": row.area_under_roc_curve,
                })
    return rows, sources


def run_comparison(data, output, protocol, project, levels, models, config, repo):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    train, validation, test = split_frames(data, protocol, project)
    for level in levels:
        for name, frame in (("train", train), ("validation", validation)):
            if frame[label_column(level)].nunique() != 2:
                raise ValueError(f"{name} needs both classes at unstable level {level}.")
    transformer = FeatureTransformer()
    x_train = transformer.fit_transform(train)
    x_val = transformer.transform(validation)
    x_test = transformer.transform(test)
    write_json(output / "feature_transformer.json", transformer.to_dict())
    split = {
        "protocol": protocol,
        "project": project,
        "feature_policy": "same_pre_sprint_transform_for_both_variants",
        "historical_pipeline_replayed": False,
        "baseline_definition": "unweighted model-family rerun, not the published old pipeline",
        "test_weights": "none",
        "selection_metric": "validation_auc_prc",
        "versions": {"sklearn": sklearn.__version__, "numpy": np.__version__, "pandas": pd.__version__},
        "partitions": {
            name: partition_info(frame, levels)
            for name, frame in (("train", train), ("validation", validation), ("test", test))
        },
    }
    write_json(output / "split_manifest.json", split)
    for name, frame in (("train", train), ("validation", validation), ("test", test)):
        frame[["row_id", "source_dataset", "issue_key"] + [label_column(k) for k in levels]].to_csv(
            output / f"{name}_rows.csv", index=False
        )
    historical, sources = historical_references(repo, sorted(data.source_dataset.unique()), levels, models)
    pd.DataFrame(historical, columns=[
        "project", "level", "model", "estimator_class", "variant", "directly_comparable",
        "auc_prc", "average_precision", "accuracy", "roc_auc",
    ]).to_csv(output / "historical_reference.csv", index=False)
    write_json(output / "historical_sources.json", sources)
    rows = []
    seed = config["seed"]
    for level in levels:
        y_train = train[label_column(level)].to_numpy()
        y_val = validation[label_column(level)].to_numpy()
        y_test = test[label_column(level)].to_numpy()
        for name in models:
            for variant in VARIANTS:
                destination = output / f"words_{level}" / name / variant
                destination.mkdir(parents=True, exist_ok=True)
                candidates = []
                best = None
                best_score = -np.inf
                for parameters in config["models"][name]:
                    candidate = build_model(name, parameters, seed)
                    with warnings.catch_warnings(record=True) as caught:
                        warnings.simplefilter("always")
                        balancing = fit_candidate(candidate, name, variant, x_train, y_train, seed)
                    for warning in caught:
                        warnings.warn(str(warning.message), warning.category)
                    probability = candidate.predict_proba(x_val)[:, 1]
                    score = calculate_metrics(y_val, probability, 0.5)["auc_prc"]
                    candidates.append({
                        "parameters": candidate.get_params(),
                        "validation_auc_prc": score,
                        "warnings": [str(w.message) for w in caught],
                    })
                    if score > best_score:
                        best = candidate
                        best_score = score
                if best is None:
                    raise ValueError(f"No valid candidates for {name}/{variant}/{level}.")
                val_probability = best.predict_proba(x_val)[:, 1]
                threshold = select_threshold(y_val, val_probability)
                test_probability = best.predict_proba(x_test)[:, 1]
                metrics = {
                    "validation": calculate_metrics(y_val, val_probability, threshold),
                    "test": calculate_metrics(y_test, test_probability, threshold),
                }
                metadata = {
                    "model": name, "estimator_class": type(best).__name__,
                    "variant": variant, "level": level, "protocol": protocol,
                    "project": project, "balancing": balancing,
                    "test_weights": "none", "seed": seed,
                    "selection_metric": "validation_auc_prc",
                    "threshold_selection": "validation_f1",
                    "test_row_ids_sha256": row_hash(test),
                    "parameters": best.get_params(), "candidates": candidates,
                }
                write_json(destination / "metrics.json", metrics)
                write_json(destination / "run_metadata.json", metadata)
                predictions(destination / "validation_predictions.csv", validation, level, val_probability, threshold)
                predictions(destination / "test_predictions.csv", test, level, test_probability, threshold)
                joblib.dump(best, destination / "model.joblib")
                rows.append({
                    "project": project, "protocol": protocol, "level": level,
                    "model": name, "estimator_class": type(best).__name__,
                    "variant": variant, "test_row_ids_sha256": row_hash(test),
                    **metrics["test"],
                })
                pd.DataFrame(rows).to_csv(output / "comparison_results.csv", index=False)
    return rows
