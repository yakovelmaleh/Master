"""Selection and final success criteria, with explicit degenerate-score controls."""

import numpy as np

from unstable_model.evaluation import calculate_metrics, probability_metrics


def eligible(metrics):
    return (
        metrics.get("average_precision") is not None
        and metrics.get("roc_auc") is not None
        and metrics["average_precision"] > metrics["positive_rate"]
        and metrics["roc_auc"] > 0.5
    )


def rank(metrics):
    return (eligible(metrics), metrics["auc_prc"], metrics["average_precision"])


def gates(metrics, baseline):
    required = ("auc_prc", "average_precision", "roc_auc", "positive_rate")
    if any(metrics.get(k) is None or not np.isfinite(metrics[k]) for k in required):
        return {"valid": False, "passed": False}
    baseline_ap = baseline.get("average_precision")
    checks = {
        "valid": baseline_ap is not None and bool(np.isfinite(baseline_ap)),
        "auc_prc_above_half": metrics["auc_prc"] > 0.5,
        "ap_above_prevalence": metrics["average_precision"] > metrics["positive_rate"],
        "ap_above_baseline": baseline_ap is not None and metrics["average_precision"] > baseline_ap,
        "roc_above_half": metrics["roc_auc"] > 0.5,
    }
    return {**checks, "passed": all(checks.values())}


def final_metrics(labels, probabilities, baseline_probabilities, threshold, samples, seed):
    metrics = calculate_metrics(labels, probabilities, threshold)
    baseline = calculate_metrics(labels, baseline_probabilities, 0.5)
    constant = calculate_metrics(labels, np.full(len(labels), 0.5), 0.5)
    rng = np.random.RandomState(seed)
    intervals = {name: [] for name in ("auc_prc", "average_precision", "roc_auc")}
    deltas = {name: [] for name in intervals}
    for _ in range(samples):
        indices = rng.randint(0, len(labels), len(labels))
        if len(np.unique(labels[indices])) != 2:
            continue
        current = probability_metrics(labels[indices], probabilities[indices])
        control = probability_metrics(labels[indices], baseline_probabilities[indices])
        for name in intervals:
            intervals[name].append(current[name])
            deltas[name].append(current[name] - control[name])
    valid = len(intervals["auc_prc"])

    def bounds(values):
        return np.percentile(values, [2.5, 97.5]).tolist() if valid >= 100 else None

    return {
        "test": metrics, "baseline": baseline, "constant_score": constant,
        "gates": gates(metrics, baseline),
        "uncertainty": {
            "method": "paired issue bootstrap; does not model temporal dependence",
            "requested_samples": samples, "valid_samples": valid,
            "metrics_95": {k: bounds(v) for k, v in intervals.items()},
            "difference_95": {k: bounds(v) for k, v in deltas.items()},
        },
    }
