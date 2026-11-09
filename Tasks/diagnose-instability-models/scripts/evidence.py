"""T1: frozen population, immutable archive, sealed predictions and provenance."""

import io
import subprocess

from support import (
    CHANGES, COUNT, FAMILIES, HF, LEVELS, PROJECTS, REPO, REPORTS,
    TEXT_COLUMNS, align_predictions, calculate_metrics, digest, emit, file_hash,
    inside, label_column, metrics_match, np, pd, read_json, row_hash,
    save_table, sha_bytes,
)
from unstable_model.data import CATEGORICAL_COLUMNS, NUMERIC_COLUMNS, load_dataset, chronological_split


def git_bytes(commit, path):
    return subprocess.check_output(
        ["git", "-C", str(REPO), "show", f"{commit}:{path}"], stderr=subprocess.PIPE
    )


def verify_population(raw, frames, expected):
    ids = raw.issue_key.astype(str)
    if raw.issue_key.isna().any() or ids.duplicated().any():
        raise ValueError("Raw dataset has missing or duplicate issue keys.")
    for split, frame in zip(("train", "validation", "test"), frames):
        part = expected["partitions"][split]
        if len(frame) != part["rows"] or row_hash(frame.row_id) != part["row_ids_sha256"]:
            raise ValueError(f"Frozen split identity mismatch: {split}")
        for k in LEVELS:
            y = frame[label_column(k)]
            if not y.isin([0, 1]).all():
                raise ValueError("Nonbinary or missing frozen labels.")
            pairs = "\n".join(f"{r}\t{int(v)}" for r, v in zip(frame.row_id, y))
            if sha_bytes(pairs.encode()) != part["labels_sha256"][str(k)]:
                raise ValueError(f"Frozen label hash mismatch: {split}/{k}")
        labels = frame[[label_column(k) for k in LEVELS]].to_numpy()
        if (np.diff(labels, axis=1) > 0).any():
            raise ValueError("Labels are not nested across K.")
        counts = pd.to_numeric(frame[COUNT], errors="coerce")
        changes = pd.to_numeric(frame[CHANGES], errors="coerce")
        available = counts.notna() & changes.notna()
        if ((counts[available] < 0) | (changes[available] < 0)).any():
            raise ValueError("Negative label-construction count.")
        for k in LEVELS:
            reconstructed = ((counts >= k) & (changes > 0)).astype(int)
            if not reconstructed[available].eq(frame.loc[available, label_column(k)]).all():
                raise ValueError(f"Stored label disagrees with implemented rule: {split}/{k}")


def population(project, reference):
    source = REPO / "Data" / project / "features_labels_table_os.csv"
    if file_hash(source) != reference["input_sha256"]:
        raise ValueError("Dataset bytes differ from frozen contract; do not regenerate splits.")
    raw = pd.read_csv(source, low_memory=False)
    if raw.issue_key.isna().any() or raw.issue_key.astype(str).duplicated().any():
        raise ValueError("Missing or duplicate raw issue key.")
    frame = load_dataset(REPO / "Data", project, 5)
    frame["row_id"] = project + ":" + frame.issue_key.astype(str)
    frame["project"] = project
    indexed = raw.assign(issue_key=raw.issue_key.astype(str)).set_index("issue_key")
    extra = [COUNT, CHANGES, *[label_column(k) for k in LEVELS[1:]]]
    for column in extra:
        frame[column] = indexed.loc[frame.issue_key.astype(str), column].to_numpy()
    frame = frame.sort_values(["time_add_to_sprint", "row_id"], kind="stable").reset_index(drop=True)
    frames = chronological_split(frame, .6, .2)
    verify_population(raw, frames, reference)
    out = []
    for split, part in zip(("train", "validation", "test"), frames):
        part = part.copy()
        part["split"] = split
        out.append(part)
    if file_hash(source) != reference["input_sha256"]:
        raise ValueError("Dataset changed while reading; do not analyze mixed inputs.")
    return pd.concat(out, ignore_index=True), {
        "path": str(source), "sha256": file_hash(source), "raw_rows": len(raw),
        "eligible_rows": len(frame), "excluded_by_existing_loader": len(raw) - len(frame),
        "status": "succeeded",
    }


def normalized(prediction, canonical, project, level, family, model, threshold, provenance):
    result = align_predictions(prediction, canonical, level)
    if not np.isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError("Invalid existing fixed threshold.")
    if "predicted_label" in result and not np.array_equal(
        result.predicted_label, (result.instability_probability >= threshold).astype(int)
    ):
        raise ValueError("Saved threshold predictions disagree with existing fixed threshold.")
    result = result[["row_id", "actual_label", "instability_probability"]].copy()
    return result.assign(project=project, level=level, family=family, model=model,
                         split=canonical.split.iloc[0], threshold=threshold, provenance=provenance)


def classical(project, level, canonical, reference, commit, comparison, tolerance):
    cell = reference["baseline"][str(level)]
    candidates = [c for c in comparison["classical_candidates"]
                  if (c["project"], c["level"]) == (project, level)]
    if len(candidates) != 6 or {(c["model"], c["variant"]) for c in candidates} != {
        (model, variant) for model in ("RF", "XGboost", "NN") for variant in ("baseline", "refactored")
    }:
        raise ValueError("Classical pool must contain RF/boosting/NN x two variants.")
    for c in candidates:
        content = git_bytes(commit, c["git_path"])
        if sha_bytes(content) != c["sha256"] or read_json_bytes(content) != c["metrics"]:
            raise ValueError("Classical candidate report/archive mismatch.")
    selected = max(candidates, key=lambda c: (c["metrics"]["validation"]["auc_prc"],
                                             c["model"], c["variant"]))
    if (selected["model"], selected["variant"]) != (cell["model"], cell["variant"]):
        raise ValueError("Classical validation selection differs from frozen reference.")
    directory = selected["git_path"].rsplit("/", 1)[0]
    metadata_bytes = git_bytes(commit, directory + "/run_metadata.json")
    metadata = read_json_bytes(metadata_bytes)
    if (metadata["model"], metadata["variant"], metadata["project"], metadata["level"]) != (
        cell["model"], cell["variant"], project, level
    ) or metadata["test_row_ids_sha256"] != row_hash(canonical[canonical.split == "test"].row_id):
        raise ValueError("Archived classical model metadata identity differs.")
    if metadata["selection_metric"] != "validation_auc_prc" or metadata["threshold_selection"] != "validation_f1":
        raise ValueError("Archived classical model selection/threshold protocol differs.")
    object_info = subprocess.check_output(
        ["git", "-C", str(REPO), "cat-file", "--batch-check"],
        input=f"{commit}:{directory}/model.joblib\n", text=True, stderr=subprocess.PIPE
    ).strip().split()
    checkpoint = {"status": "missing"}
    if len(object_info) == 3 and object_info[1] == "blob":
        checkpoint = {"status": "archived_blob_identity_only_not_deserialized",
                      "git_blob_sha1": object_info[0], "bytes": int(object_info[2]),
                      "git_path": directory + "/model.joblib"}
    output, checks = [], []
    for split in ("validation", "test"):
        path = cell["predictions_git_path"].replace("test_predictions.csv", f"{split}_predictions.csv")
        content = git_bytes(commit, path)
        if split == "test" and sha_bytes(content) != cell["predictions_sha256"]:
            raise ValueError("Archived classical test prediction hash mismatch.")
        expected = canonical[canonical.split == split]
        prediction = pd.read_csv(io.BytesIO(content))
        threshold = cell["metrics"]["validation"]["threshold"]
        rows = normalized(prediction, expected, project, level, "classical",
                          cell["model"] + "/" + cell["variant"], threshold, f"{commit}:{path}")
        metrics = calculate_metrics(rows.actual_label, rows.instability_probability, threshold)
        metrics_match(metrics, cell["metrics"][split], tolerance)
        output.append(rows)
        checks.append({"split": split, "metrics": metrics, "sha256": sha_bytes(content),
                       "source": f"{commit}:{path}"})
    return output, {"status": "succeeded", "model": selected["model"],
                    "variant": selected["variant"], "selection": "validation_auc_prc",
                    "protocol": {"run_metadata": metadata, "metadata_sha256": sha_bytes(metadata_bytes),
                                 "checkpoint": checkpoint},
                    "probability_direction": "predict_proba class 1 = unstable; source-audited",
                    "checks": checks}


def read_json_bytes(content):
    import json
    return json.loads(content)


def discover(roots, manifest):
    studies = {}
    for base in roots:
        manifest.append({"path": str(base), "kind": "search_root",
                         "status": "available" if base.is_dir() else "missing"})
        paths = {base / "study.json"}
        for container in ("runs", "jev-runs"):
            paths.update(base.glob(f"{container}/*/study.json"))
        for path in sorted(paths):
            if not path.is_file():
                continue
            try:
                value = read_json(path)
                matches = studies.setdefault(digest(value), [])
                if path.parent.resolve() not in matches:
                    matches.append(path.parent.resolve())
                manifest.append({"path": str(path), "kind": "study", "sha256": file_hash(path),
                                 "identity": digest(value), "status": "available"})
            except (ValueError, OSError) as exc:
                manifest.append({"path": str(path), "kind": "study", "status": "failed",
                                 "reason": str(exc)})
        # Inventory candidate history/coverage files without reading story content.
        for pattern in ("**/*history*.jsonl", "**/*changelog*.json", "**/length_reports/*.json",
                        "**/changes_summary_os.csv", "**/changes_description_os.csv",
                        "**/changes_criteria_os.csv", "**/changes_sprint_os.csv", "**/sprints_os.csv"):
            for path in sorted(base.glob(pattern)) if base.is_dir() else []:
                manifest.append({"path": str(path), "kind": "history_or_coverage",
                                 "sha256": file_hash(path), "bytes": path.stat().st_size,
                                 "status": "available_not_automatically_interpreted"})
    return studies


def neural(family, root, report, project, level, canonical, tolerance):
    study = read_json(root / "study.json")
    seal = read_json(root / "sealed.json")
    if digest(study) != report["study_sha256"] or seal["study_sha256"] != digest(study):
        raise ValueError("Study or seal identity differs from original report.")
    selections = seal["cells"] if family == "Jev" else seal["selections"]
    keys = [(s["project"], s["level"]) for s in selections]
    if len(keys) != 24 or set(keys) != {(p, k) for p in PROJECTS for k in LEVELS}:
        raise ValueError("Seal must contain exactly 24 unique project/K selections.")
    selected = next(s for s in selections if (s["project"], s["level"]) == (project, level))
    expected = next(c for c in report["cells"] if (c["project"], c["level"]) == (project, level))
    final = root / "final" / project / str(level)
    result = read_json(final / "metrics.json")
    if result != expected or result["selection_sha256"] != digest(selected):
        raise ValueError("Final metrics differ from report or sealed selection.")
    if result["model"] != selected["model"] or result["checkpoint_files"] != selected["checkpoint_files"]:
        raise ValueError("Model or checkpoint identity differs from seal.")
    checkpoint_status = "unavailable_native_weights_not_required_for_saved_score_analysis"
    protocol = {"study": study, "selection": selected,
                "checkpoint_status": checkpoint_status,
                "provenance_files": {str(p): file_hash(p) for p in (
                    root / "study.json", root / "sealed.json", final / "metrics.json"
                )}}
    if family != "Jev":
        if study["reference_sha256"] != file_hash(HF / "reference_contract.json"):
            raise ValueError("Study used another reference population contract.")
        directory = inside(root, selected["directory"])
        inference = read_json(directory / "checkpoint/inference.json")
        if inference["model"] != study["models"][selected["model"]]:
            raise ValueError("Selected base model/revision differs from study.")
        if "artifact_reference" in result and (
            result["artifact_reference"]["base"] != inference["model"]
            or result["artifact_reference"]["config_sha256"] != digest(inference["config"])
        ):
            raise ValueError("Final base identity or configuration differs from selected inference.")
        if (inference["project"], inference["level"], inference["model_key"]) != (
            project, level, selected["model"]
        ):
            raise ValueError("Inference identity differs from selected cell.")
        unavailable = []
        for name, expected_hash in selected["checkpoint_files"].items():
            path = inside(directory / "checkpoint", name)
            if not path.is_file():
                unavailable.append(name)
            elif file_hash(path) != expected_hash:
                raise ValueError(f"Checkpoint hash mismatch: {name}")
        protocol["checkpoint_status"] = "verified" if not unavailable else "missing_files"
        protocol["missing_checkpoint_files"] = unavailable
        protocol["inference"] = inference
        val_path = directory / "validation_predictions.csv"
        val_hash = selected["validation_predictions_sha256"]
    else:
        if study["model"]["identity"] != report["model_identity"]:
            raise ValueError("Native Jev identity differs from original report.")
        val_path = root / "validation" / project / str(level) / "validation_predictions.csv"
        val_hash = selected["predictions_sha256"]
    output, checks = [], []
    for split, path, expected_hash, reported in (
        ("validation", val_path, val_hash, selected["validation"]),
        ("test", final / "test_predictions.csv", result["test_predictions_sha256"], result["test"]),
    ):
        content = path.read_bytes()
        if sha_bytes(content) != expected_hash:
            raise ValueError(f"Saved {split} prediction hash mismatch.")
        prediction = pd.read_csv(io.BytesIO(content))
        threshold = selected["threshold"]
        rows = normalized(prediction, canonical[canonical.split == split], project, level,
                          family, selected["model"], threshold, str(path))
        metrics = calculate_metrics(rows.actual_label, rows.instability_probability, threshold)
        metrics_match(metrics, reported, tolerance)
        output.append(rows)
        checks.append({"split": split, "metrics": metrics, "path": str(path), "sha256": sha_bytes(content)})
    if result["test"]["threshold"] != selected["threshold"]:
        raise ValueError("Test threshold differs from sealed validation threshold.")
    protocol["token_coverage"] = result.get("token_coverage", {
        "status": "unavailable_per_row", "note": "Train length reports cannot identify test truncation."
    })
    return output, {"status": "succeeded", "checks": checks, "protocol": protocol,
                    "probability_direction": (
                        "native noul is positive probability; source-audited"
                        if family == "Jev" else "sigmoid head / predict_proba class 1; source-audited"
                    )}


def inventory(root, roots, config, histories=None):
    reference = read_json(HF / "reference_contract.json")
    comparison_path = REPORTS / "classical-best-comparison-20261029.json"
    comparison = read_json(comparison_path)
    manifest = [{"path": str(HF / "reference_contract.json"), "sha256": file_hash(HF / "reference_contract.json"),
                 "kind": "frozen_contract", "status": "available"},
                {"path": str(comparison_path), "sha256": file_hash(comparison_path),
                 "kind": "comparison_report", "status": "available"}]
    studies = discover(roots, manifest)
    reports, report_errors = {}, {}
    for family, name in config["reports"].items():
        path = REPORTS / name
        try:
            if file_hash(path) != comparison["reports_sha256"][family]:
                raise ValueError("Report hash differs from comparison evidence.")
            report = read_json(path)
            keys = [(c["project"], c["level"]) for c in report["cells"]]
            if len(keys) != 24 or set(keys) != {(p, k) for p in PROJECTS for k in LEVELS}:
                raise ValueError("Report cell identities incomplete or duplicated.")
            reports[family] = report
            manifest.append({"path": str(path), "sha256": file_hash(path), "kind": "aggregate_report",
                             "family": family, "study_sha256": report["study_sha256"],
                             "status": "available_not_row_evidence"})
        except (OSError, ValueError, KeyError) as exc:
            report_errors[family] = str(exc)
            manifest.append({"path": str(path), "kind": "aggregate_report", "family": family,
                             "status": "blocked", "reason": str(exc)})
    datasets, predictions, checks, populations = [], [], [], []
    for project in PROJECTS:
        try:
            frame, info = population(project, reference["projects"][project])
            datasets.append(frame)
            manifest.append({"project": project, "kind": "dataset", **info})
            populations.append({"project": project, **info})
        except (OSError, ValueError, KeyError) as exc:
            failed = {"project": project, "status": "blocked", "reason": str(exc)}
            populations.append(failed)
            manifest.append({"kind": "dataset", **failed})
            continue
        for k in LEVELS:
            for family in FAMILIES:
                try:
                    if family == "classical":
                        if comparison["source_commit"] != reference["source_commit"]:
                            raise ValueError("Classical comparison/archive commit differs.")
                        rows, details = classical(project, k, frame, reference["projects"][project],
                                                  reference["source_commit"], comparison,
                                                  config["metric_tolerance"])
                    else:
                        if family in report_errors:
                            raise ValueError(report_errors[family])
                        choices = studies.get(reports[family]["study_sha256"], [])
                        if len(choices) != 1:
                            raise ValueError(f"Need exactly one matching sealed study, found {len(choices)}.")
                        rows, details = neural(family, choices[0], reports[family], project, k,
                                               frame, config["metric_tolerance"])
                    predictions.extend(rows)
                    checks.append({"project": project, "level": k, "family": family, **details})
                except (OSError, ValueError, KeyError, StopIteration, subprocess.CalledProcessError) as exc:
                    checks.append({"project": project, "level": k, "family": family,
                                   "status": "blocked", "reason": str(exc)})
    dataset = pd.concat(datasets, ignore_index=True) if datasets else pd.DataFrame(columns=[
        "row_id", "issue_key", "project", "split", "time_add_to_sprint", COUNT, CHANGES,
        *TEXT_COLUMNS, "model_text", *[label_column(k) for k in LEVELS],
    ])
    prediction = pd.concat(predictions, ignore_index=True) if predictions else pd.DataFrame(
        columns=["row_id", "actual_label", "instability_probability", "project", "level",
                 "family", "model", "split", "threshold", "provenance"])
    save_table(root, "manifest/population.csv", dataset, "T1")
    save_table(root, "manifest/predictions.csv", prediction, "T1")
    status = "succeeded" if len(checks) == 96 and all(
        c["status"] == "succeeded" for c in checks
    ) and len(datasets) == 6 else "blocked"
    if histories:
        manifest.append({"kind": "normalized_histories", "path": str(histories),
                         "sha256": file_hash(histories), "status": "available_pending_validation"})
    wins = {}
    for family, report in reports.items():
        wins[family] = sum(
            c["test"]["auc_prc"] > reference["projects"][c["project"]]["baseline"][str(c["level"])]["metrics"]["test"]["auc_prc"]
            for c in report["cells"]
        )
    emit(root, "manifest/artifact_manifest.json", "T1", status, artifacts=manifest,
         search_scope=[str(p) for p in roots], histories=str(histories) if histories else None,
         history_status="supplied_pending_validation" if histories else "unavailable",
         required_studies=[{
             "family": family, "study_sha256": report["study_sha256"],
             "matching_roots": [str(p) for p in studies.get(report["study_sha256"], [])],
             "required": ["study.json", "sealed.json", "final/<project>/<K>/metrics.json",
                          "final/<project>/<K>/test_predictions.csv",
                          "selected validation_predictions.csv and checkpoint/inference.json (HF)",
                          "validation/<project>/<K>/validation_predictions.csv (Jev)"],
         } for family, report in reports.items()],
         datasets=populations)
    emit(root, "manifest/integrity_checks.json", "T1", status, cells=checks, populations=populations,
         verified_cells=sum(c["status"] == "succeeded" for c in checks),
         expected_cells=96, aggregate_only_auc_prc_wins= wins,
         aggregate_warning="Report arithmetic only; not row-level reproduction for blocked cells.")
    emit(root, "manifest/comparison_contract.json", "T1", status,
         labels={str(k): f"{COUNT} >= {k} AND {CHANGES} > 0" for k in LEVELS},
         alignment="exact project+row_id population; order ignored; mismatch blocks entire cell",
         splits="frozen chronological 60/20/20; existing tie ordering; no regeneration",
         selection="classical max(validation AUC-PRC, model, variant); SLM original sealed selection",
         thresholds="existing validation-selected thresholds only; no threshold fitting",
         family_protocols={
             "classical": "pre-sprint structured fields + lexical summary features; RF/legacy GradientBoosting/NN; train-only preprocessing; validation AUC-PRC selection",
             "SLM1": "ModernBERT/Qwen embeddings; frozen heads and adapters; optional structured features; validation quality gates then AUC-PRC/AP",
             "SLM2": "Phi/Gemma/Qwen3.5; same sealed HF workflow, per-study budgets/configs recorded in cell protocol",
             "Jev": "community native zero-shot DeBERTa; original text + fixed K prompt; validation F1 threshold; no task-specific training",
         },
         input_fields={
             "original_text": TEXT_COLUMNS, "structured_numeric": NUMERIC_COLUMNS,
             "structured_categorical": CATEGORICAL_COLUMNS,
             "classical_text_transform": "unstable_model.features.text_features: length/unique words, punctuation/newlines, URL/code/TODO/please/acceptance indicators",
             "selected_SLM_structured_fields": "Exact fitted transformer or null in each verified cell protocol.inference; do not assume the structured variant won.",
             "budget_and_selection": "Original per-study config and selected parameters are recorded in verified neural cell protocols, not made equal retrospectively.",
         },
         input_timing="Only original_*_sprint text and existing pre-sprint metadata were model inputs; future fields used only for label audit.",
         unavailable="Temporal feature correctness and snapshot construction require raw histories; source inspection alone is not empirical verification.",
         constant_control="Preserve constant-score AUC-PRC=(1+prevalence)/2, AP=prevalence.",
         cells=checks)
    return status
