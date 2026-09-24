import json
from pathlib import Path

import numpy as np
import pandas as pd


def json_default(value):
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Cannot serialize {type(value).__name__}.")


def write_json(path, value):
    with Path(path).open("w", encoding="utf-8") as output:
        json.dump(
            value,
            output,
            indent=2,
            sort_keys=True,
            default=json_default,
        )
        output.write("\n")


def write_predictions(path, frame, labels, probabilities, threshold):
    output = frame[
        ["issue_key", "project_key", "issue_type", "created", "time_add_to_sprint"]
    ].copy()
    output["actual_label"] = labels.to_numpy()
    output["instability_probability"] = probabilities
    output["predicted_label"] = (probabilities >= threshold).astype(int)
    output.to_csv(path, index=False)


def write_feature_coefficients(path, feature_names, coefficients):
    frame = pd.DataFrame(
        {
            "feature": feature_names,
            "coefficient": coefficients,
            "absolute_coefficient": abs(coefficients),
        }
    ).sort_values("absolute_coefficient", ascending=False)
    frame.to_csv(path, index=False)


def display_metric(value):
    return "N/A" if value is None else f"{value:.4f}"


def write_html_report(path, run_metadata, metrics):
    test = metrics["test"]
    confusion = test["confusion_matrix"]
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Unstable user story model report</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; max-width: 900px; margin: 40px auto; color: #24292f; }}
    table {{ border-collapse: collapse; width: 100%; margin: 16px 0 32px; }}
    th, td {{ border: 1px solid #d0d7de; padding: 8px 12px; text-align: right; }}
    th:first-child, td:first-child {{ text-align: left; }}
    code {{ background: #f6f8fa; padding: 2px 5px; }}
  </style>
</head>
<body>
  <h1>Unstable user story model</h1>
  <p>Project: <code>{run_metadata["project"]}</code>;
     label: <code>{run_metadata["label_column"]}</code>;
     selected validation threshold: <code>{test["threshold"]:.2f}</code>.</p>
  <h2>Chronological split</h2>
  <table>
    <tr><th>Partition</th><th>Rows</th><th>Positive rate</th></tr>
    <tr><td>Train</td><td>{metrics["train"]["row_count"]}</td><td>{metrics["train"]["positive_rate"]:.3f}</td></tr>
    <tr><td>Validation</td><td>{metrics["validation"]["row_count"]}</td><td>{metrics["validation"]["positive_rate"]:.3f}</td></tr>
    <tr><td>Test</td><td>{test["row_count"]}</td><td>{test["positive_rate"]:.3f}</td></tr>
  </table>
  <h2>Test metrics</h2>
  <table>
    <tr><th>Metric</th><th>Value</th></tr>
    <tr><td>AUC-PRC (trapezoidal)</td><td>{display_metric(test.get("auc_prc"))}</td></tr>
    <tr><td>Average precision</td><td>{display_metric(test["average_precision"])}</td></tr>
    <tr><td>ROC AUC</td><td>{display_metric(test["roc_auc"])}</td></tr>
    <tr><td>F1</td><td>{test["f1"]:.4f}</td></tr>
    <tr><td>Precision</td><td>{test["precision"]:.4f}</td></tr>
    <tr><td>Recall</td><td>{test["recall"]:.4f}</td></tr>
    <tr><td>Balanced accuracy</td><td>{test["balanced_accuracy"]:.4f}</td></tr>
    <tr><td>Accuracy</td><td>{test["accuracy"]:.4f}</td></tr>
  </table>
  <h2>Test confusion matrix</h2>
  <table>
    <tr><th></th><th>Predicted stable</th><th>Predicted unstable</th></tr>
    <tr><th>Actual stable</th><td>{confusion[0][0]}</td><td>{confusion[0][1]}</td></tr>
    <tr><th>Actual unstable</th><td>{confusion[1][0]}</td><td>{confusion[1][1]}</td></tr>
  </table>
</body>
</html>
"""
    Path(path).write_text(html, encoding="utf-8")


def save_model(path, model):
    np.savez_compressed(
        path,
        coefficients=model.coefficients,
        intercept=np.asarray([model.intercept]),
        iterations=np.asarray([model.iterations]),
        best_validation_loss=np.asarray([model.best_validation_loss]),
    )
