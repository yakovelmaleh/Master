import math

import numpy as np
import pandas as pd


def select_threshold(labels, probabilities):
    if len(set(labels)) < 2:
        return 0.5
    candidates = np.linspace(0.05, 0.95, 91)
    scores = [
        binary_metrics(labels, probabilities >= threshold)["f1"]
        for threshold in candidates
    ]
    return float(candidates[int(np.argmax(scores))])


def probability_metrics(labels, probabilities):
    labels = np.asarray(labels, dtype=int)
    probabilities = np.asarray(probabilities, dtype=float)
    positive_count = int(labels.sum())
    negative_count = len(labels) - positive_count
    if positive_count == 0 or negative_count == 0:
        return {"average_precision": None, "roc_auc": None}

    order = np.argsort(-probabilities, kind="mergesort")
    sorted_labels = labels[order]
    cumulative_positives = np.cumsum(sorted_labels)
    ranks = np.arange(1, len(labels) + 1)
    precision_at_rank = cumulative_positives / ranks
    average_precision = float(
        np.sum(precision_at_rank * sorted_labels) / positive_count
    )

    probability_ranks = np.asarray(
        pd.Series(probabilities).rank(method="average")
    )
    positive_rank_sum = float(probability_ranks[labels == 1].sum())
    roc_auc = (
        positive_rank_sum - positive_count * (positive_count + 1) / 2
    ) / (positive_count * negative_count)
    return {
        "average_precision": average_precision,
        "roc_auc": float(roc_auc),
    }


def binary_metrics(labels, predictions):
    labels = np.asarray(labels, dtype=int)
    predictions = np.asarray(predictions, dtype=int)
    true_negative = int(np.sum((labels == 0) & (predictions == 0)))
    false_positive = int(np.sum((labels == 0) & (predictions == 1)))
    false_negative = int(np.sum((labels == 1) & (predictions == 0)))
    true_positive = int(np.sum((labels == 1) & (predictions == 1)))
    precision_denominator = true_positive + false_positive
    recall_denominator = true_positive + false_negative
    specificity_denominator = true_negative + false_positive
    precision = (
        true_positive / precision_denominator
        if precision_denominator
        else 0.0
    )
    recall = (
        true_positive / recall_denominator if recall_denominator else 0.0
    )
    specificity = (
        true_negative / specificity_denominator
        if specificity_denominator
        else 0.0
    )
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0
    )
    return {
        "accuracy": float(np.mean(labels == predictions)),
        "balanced_accuracy": float((recall + specificity) / 2),
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "confusion_matrix": [
            [true_negative, false_positive],
            [false_negative, true_positive],
        ],
    }


def clean_metric(value):
    if value is None or math.isnan(value):
        return None
    return float(value)


def calculate_metrics(labels, probabilities, threshold):
    predictions = (probabilities >= threshold).astype(int)
    binary = binary_metrics(labels, predictions)
    probability = probability_metrics(labels, probabilities)
    return {
        "threshold": float(threshold),
        "row_count": int(len(labels)),
        "positive_count": int(np.sum(labels)),
        "positive_rate": float(np.mean(labels)),
        **binary,
        "average_precision": clean_metric(
            probability["average_precision"]
        ),
        "roc_auc": clean_metric(probability["roc_auc"]),
    }
