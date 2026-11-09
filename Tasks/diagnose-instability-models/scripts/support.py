"""Shared CPU-only diagnostic contracts; never import a model or train anything."""

import hashlib
from pathlib import Path
import sys

TASK = Path(__file__).resolve().parents[1]
REPO = TASK.parents[1]
HF = REPO / "Tasks/train-hf-instability-within-project"
sys.path.insert(0, str(HF))
from common import (  # noqa: E402
    LEVELS, PROJECTS, digest, exclusive_lock, external_path, file_hash,
    read_json, slug, write_json,
)
from unstable_model.data import TEXT_COLUMNS, label_column  # noqa: E402
from unstable_model.evaluation import calculate_metrics, probability_metrics  # noqa: E402

import numpy as np
import pandas as pd

REPORTS = REPO / "Tasks/sprint-data-analysis-summary/data"
COUNT = "num_different_words_all_text_sprint"
CHANGES = "num_changes_summary_description_acceptance_sprint"
FAMILIES = ("classical", "SLM1", "SLM2", "Jev")


def sha_bytes(content):
    return hashlib.sha256(content).hexdigest()


def row_hash(ids):
    return sha_bytes("\n".join(ids).encode())


def inside(root, relative):
    path = (root / relative).resolve()
    if path == root.resolve() or root.resolve() not in path.parents:
        raise ValueError(f"Artifact escapes its study: {relative}")
    return path


def metrics_match(actual, expected, tolerance):
    for key in ("auc_prc", "average_precision", "roc_auc", "row_count", "positive_count", "threshold"):
        if key not in expected:
            raise ValueError(f"Reported metric missing: {key}")
        a, b = actual[key], expected[key]
        if (a is None) != (b is None) or (
            a is not None and not np.isclose(a, b, atol=tolerance, rtol=0)
        ):
            raise ValueError(f"Metric mismatch: {key}: {a} != {b}")


def align_predictions(predictions, canonical, level):
    """Reject missing/extra/duplicate identities; never intersect away bad rows."""
    required = {"row_id", "actual_label", "instability_probability"}
    if not required.issubset(predictions):
        raise ValueError(f"Prediction columns missing: {sorted(required - set(predictions))}")
    if predictions.row_id.isna().any() or predictions.row_id.duplicated().any():
        raise ValueError("Null or duplicate prediction row identity.")
    if set(predictions.row_id) != set(canonical.row_id):
        raise ValueError("Prediction population differs from frozen partition.")
    result = predictions.set_index("row_id").loc[canonical.row_id].reset_index()
    if "source_dataset" in result and not result.source_dataset.eq(canonical.project.iloc[0]).all():
        raise ValueError("Prediction project differs.")
    if "issue_key" in result and not np.array_equal(
        result.issue_key.astype(str), canonical.issue_key.astype(str)
    ):
        raise ValueError("Prediction issue identity differs.")
    y = pd.to_numeric(result.actual_label, errors="raise").to_numpy()
    if not np.isin(y, [0, 1]).all() or not np.array_equal(y, canonical[label_column(level)]):
        raise ValueError("Prediction labels differ from frozen labels.")
    p = pd.to_numeric(result.instability_probability, errors="raise").to_numpy(float)
    if not np.isfinite(p).all() or ((p < 0) | (p > 1)).any():
        raise ValueError("Invalid instability probability; no inversion or rescaling permitted.")
    result["instability_probability"] = p
    return result


def metadata(root):
    return read_json(root / "run.json")


def emit(root, relative, stage, status, **values):
    run = metadata(root)
    write_json(root / relative, {
        "schema": "instability-diagnostics-m1-v1", "run_id": run["run_id"],
        "stage": stage, "status": status, "source_sha256": run["source_sha256"],
        "configuration_sha256": run["configuration_sha256"],
        "projects": list(PROJECTS), "levels": list(LEVELS),
        "primary_metric": "auc_prc",
        "metric_definition": "existing tie-aware trapezoidal PR integral; AP retained separately",
        "test_interpretation": "exploratory previously observed chronological holdout",
        **values,
    })


def save_table(root, relative, frame, stage):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    emit(root, relative + ".metadata.json", stage, "succeeded",
         path=str(path), sha256=file_hash(path), rows=len(frame),
         columns=list(frame.columns))


def load_table(root, relative):
    path = root / relative
    expected = read_json(root / (relative + ".metadata.json"))
    if file_hash(path) != expected["sha256"]:
        raise ValueError(f"Diagnostic input changed: {relative}")
    return pd.read_csv(path, keep_default_na=False, dtype={"row_id": str, "issue_key": str})


def quantiles(values):
    values = pd.to_numeric(pd.Series(values), errors="coerce").dropna()
    return {str(q): float(values.quantile(q)) for q in (0, .5, .9, .95, .99, 1)} if len(values) else None


def json_counts(values):
    return {str(k): int(v) for k, v in values.value_counts(dropna=False).items()}


def source_hash():
    paths = [*TASK.glob("scripts/*.py"), *TASK.glob("cluster/*"),
             HF / "reference_contract.json", HF / "common.py",
             HF / "model_adapters.py", HF / "run_experiment.py",
             REPO / "Tasks/evaluate-hf-instability-jev/jev_backend.py",
             REPO / "Tasks/evaluate-hf-instability-jev/run_evaluation.py",
             REPO / "Using_CSV_files/Load_Data_From_Jira_To_CSV/ChooseFeaturesColumns.py",
             REPO / "Using_CSV_files/Load_Data_From_Jira_To_CSV/SetUpData.py",
             REPO / "Using_CSV_files/CalculateData/prepare_data_sql.py",
             REPO / "Using_CSV_files/CalculateData/calculate_time_add_sprint.py",
             REPO / "Tasks/jira-url-to-instability-model/unstable_model/data.py",
             REPO / "Tasks/jira-url-to-instability-model/unstable_model/evaluation.py",
             REPO / "Tasks/run_cluster_task.sh"]
    return digest({str(p.relative_to(REPO)): file_hash(p) for p in paths if p.is_file()})
