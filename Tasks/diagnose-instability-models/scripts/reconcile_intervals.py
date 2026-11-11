"""Replay both published uncertainty methods on the same saved score pairs."""

import io
from pathlib import Path

from support import (
    HF, REPORTS, align_predictions, calculate_metrics, digest, file_hash, label_column,
    metrics_match, np, pd, probability_metrics, read_json, row_hash, sha_bytes,
)
from errors import paired_interval
from evaluate import final_metrics
from evidence import git_bytes


def match_bounds(actual, expected, tolerance):
    if actual is None or expected is None:
        if actual is not expected:
            raise ValueError("Undefined versus defined confidence interval.")
    elif not np.allclose(actual, expected, atol=tolerance, rtol=0):
        raise ValueError(f"Confidence interval replay mismatch: {actual} != {expected}")


def vector_hash(values):
    return sha_bytes(np.asarray(values, dtype="<f8").tobytes())


def iid_summary(frame, threshold, samples, seed):
    result = final_metrics(
        frame.actual_label.to_numpy(), frame.model_probability.to_numpy(),
        frame.classical_probability.to_numpy(), threshold, samples, seed,
    )
    return {
        "method": "paired IID issue bootstrap", "seed": seed,
        "requested_samples": samples, "valid_samples": result["uncertainty"]["valid_samples"],
        "difference_95": result["uncertainty"]["difference_95"],
        "metrics_95": result["uncertainty"]["metrics_95"],
    }


def replay(frame, original, diagnostic, original_config, diagnostic_config, diagnostic_frame=None):
    """Fixed bridge, not a search for a favorable interval."""
    tolerance = diagnostic_config["metric_tolerance"]
    threshold = original["test"]["threshold"]
    samples, seed = original_config["bootstrap_samples"], original_config["seed"]
    if samples != original["uncertainty"]["requested_samples"]:
        raise ValueError("Original report/study bootstrap sample counts disagree.")
    original_replay = iid_summary(frame, threshold, samples, seed)
    if original_replay["valid_samples"] != original["uncertainty"]["valid_samples"]:
        raise ValueError("Original valid bootstrap count differs.")
    for metric in ("auc_prc", "average_precision", "roc_auc"):
        for key in ("difference_95", "metrics_95"):
            match_bounds(original_replay[key][metric], original["uncertainty"][key][metric], tolerance)
    diagnostic_frame = frame if diagnostic_frame is None else diagnostic_frame
    new = paired_interval(diagnostic_frame, diagnostic_config)
    match_bounds(new["interval_95"], diagnostic["uncertainty"]["interval_95"], tolerance)
    if new["valid_samples"] != diagnostic["uncertainty"]["valid_samples"]:
        raise ValueError("Diagnostic valid bootstrap count differs.")
    if (new["requested_samples"] != diagnostic["uncertainty"]["requested_samples"]
            or new["time_block_rows"] != diagnostic["uncertainty"]["time_block_rows"]):
        raise ValueError("Diagnostic bootstrap configuration differs.")
    bridge = [
        {"step": "original_method_and_configuration", **original_replay},
        {"step": "same_method_on_diagnostic_csv_representation", **iid_summary(
            diagnostic_frame, threshold, samples, seed)},
        {"step": "change_seed_only", **iid_summary(
            diagnostic_frame, threshold, samples, diagnostic_config["seed"])},
        {"step": "then_change_resample_count", **iid_summary(
            diagnostic_frame, threshold, diagnostic_config["bootstrap_samples"], diagnostic_config["seed"])},
        {"step": "then_change_sampling_to_time_blocks",
         "seed": diagnostic_config["seed"], **new},
        {"step": "time_blocks_with_original_resample_count",
         "seed": diagnostic_config["seed"],
         **paired_interval(diagnostic_frame, {**diagnostic_config, "bootstrap_samples": samples})},
    ]
    return {
        "status": "succeeded", "original_iid_reproduced": original_replay,
        "diagnostic_time_block_reproduced": new, "fixed_bridge": bridge,
        "bridge_interpretation": "Seed and finite-resample effects and sampling-unit change are all shown; effects can interact. No interval is selected based on its sign.",
    }


def reconcile_cell(root, population, predictions, integrity, slices, project, level):
    run = read_json(root / "run.json")
    config = run["configuration"]
    canonical = population[(population.project == project) & (population.split == "test")].copy()
    canonical = canonical.sort_values("time_add_to_sprint", kind="stable").reset_index(drop=True)
    reference = read_json(HF / "reference_contract.json")
    if file_hash(HF / "reference_contract.json") != run["reference_sha256"]:
        raise ValueError("Frozen population contract changed.")
    partition = reference["projects"][project]["partitions"]["test"]
    if len(canonical) != partition["rows"] or row_hash(canonical.row_id) != partition["row_ids_sha256"]:
        raise ValueError("Diagnostic population/order differs from the original frozen test partition.")
    pairs = "\n".join(f"{r}\t{int(y)}" for r, y in zip(canonical.row_id, canonical[label_column(level)]))
    if sha_bytes(pairs.encode()) != partition["labels_sha256"][str(level)]:
        raise ValueError("Frozen test labels differ.")
    baseline = reference["projects"][project]["baseline"][str(level)]
    classical_bytes = git_bytes(reference["source_commit"], baseline["predictions_git_path"])
    if sha_bytes(classical_bytes) != baseline["predictions_sha256"]:
        raise ValueError("Original classical prediction hash mismatch.")
    check = next(c for c in integrity["cells"] if
                 (c["family"], c["project"], c["level"]) == ("SLM2", project, level))
    if check["status"] != "succeeded":
        raise ValueError("Target SLM2 cell did not pass T1.")
    report_path = REPORTS / config["reports"]["SLM2"]
    artifact_manifest = read_json(root / "manifest/artifact_manifest.json")
    report_anchor = next(a for a in artifact_manifest["artifacts"] if
                         a.get("kind") == "aggregate_report" and a.get("family") == "SLM2")
    if file_hash(report_path) != report_anchor["sha256"]:
        raise ValueError("Original report differs from the T1-hashed report.")
    report = read_json(report_path)
    original = next(c for c in report["cells"] if (c["project"], c["level"]) == (project, level))
    original_config = check["protocol"]["study"]["config"]
    if digest(check["protocol"]["study"]) != report["study_sha256"]:
        raise ValueError("Study identity differs from original report.")
    if digest(original_config) != original["artifact_reference"]["config_sha256"]:
        raise ValueError("Original study configuration differs from saved result.")
    if original["selection_sha256"] != digest(check["protocol"]["selection"]):
        raise ValueError("Sealed model selection differs from original report.")
    if original["baseline_identity"] != {key: baseline[key] for key in ("model", "variant")}:
        raise ValueError("Classical comparator identity differs.")
    native_check = next(c for c in check["checks"] if c["split"] == "test")
    native_path = Path(native_check["path"])
    native_bytes = native_path.read_bytes()
    if sha_bytes(native_bytes) != original["test_predictions_sha256"]:
        raise ValueError("Original SLM2 prediction bytes changed.")
    if sha_bytes(native_bytes) != native_check["sha256"]:
        raise ValueError("T1 neural hash anchor differs.")
    frame = canonical[["row_id", "time_add_to_sprint"]].copy()
    diagnostic_frame = frame.copy()
    originals = {
        "classical": pd.read_csv(io.BytesIO(classical_bytes)),
        "model": pd.read_csv(io.BytesIO(native_bytes)),
    }
    roundtrip_errors = {}
    for name, raw in originals.items():
        if row_hash(raw.row_id) != partition["row_ids_sha256"]:
            raise ValueError("Original CSV row order differs; do not silently change bootstrap draws.")
        aligned = align_predictions(raw, canonical, level)
        frame[name + "_probability"] = aligned.instability_probability.to_numpy()
        frame[name + "_threshold"] = baseline["metrics"]["test"]["threshold"] if name == "classical" else original["test"]["threshold"]
        normalized = predictions[
            (predictions.project == project) & (predictions.level == level)
            & (predictions.split == "test")
            & (predictions.family == ("classical" if name == "classical" else "SLM2"))
        ]
        normalized = align_predictions(normalized, canonical, level)
        expected_model = (baseline["model"] + "/" + baseline["variant"] if name == "classical"
                          else original["model"])
        if not normalized.model.eq(expected_model).all() or not np.allclose(
            normalized.threshold, frame[name + "_threshold"], atol=1e-14, rtol=0
        ):
            raise ValueError("Normalized model identity or fixed threshold differs.")
        delta = np.max(np.abs(normalized.instability_probability.to_numpy()
                              - aligned.instability_probability.to_numpy()))
        if delta > 1e-14:
            raise ValueError("Normalized diagnostic probabilities differ from original predictions.")
        roundtrip_errors[name] = float(delta)
        diagnostic_frame[name + "_probability"] = normalized.instability_probability.to_numpy()
        diagnostic_frame[name + "_threshold"] = normalized.threshold.to_numpy()
    frame["actual_label"] = canonical[label_column(level)].to_numpy()
    diagnostic_frame["actual_label"] = frame.actual_label
    diagnostic = next(c for c in slices["comparisons"] if (
        c["family"], c["project"], c["level"], c["split"], c["slice"]
    ) == ("SLM2", project, level, "test", "all"))
    for name in ("classical", "model"):
        metrics = calculate_metrics(frame.actual_label, frame[name + "_probability"],
                                    frame[name + "_threshold"].iloc[0])
        original_metrics = original["test"] if name == "model" else baseline["metrics"]["test"]
        metrics_match(metrics, original_metrics, config["metric_tolerance"])
        diagnostic_metrics = calculate_metrics(
            diagnostic_frame.actual_label, diagnostic_frame[name + "_probability"],
            diagnostic_frame[name + "_threshold"].iloc[0],
        )
        metrics_match(diagnostic_metrics, diagnostic["metrics"][name], config["metric_tolerance"])
    model_metrics = probability_metrics(frame.actual_label, frame.model_probability)
    baseline_metrics = probability_metrics(frame.actual_label, frame.classical_probability)
    delta = model_metrics["auc_prc"] - baseline_metrics["auc_prc"]
    if not np.isclose(delta, diagnostic["auc_prc_difference_model_minus_classical"],
                      rtol=0, atol=config["metric_tolerance"]):
        raise ValueError("AUC-PRC point estimates differ.")
    return {
        "project": project, "level": level, "family": "SLM2",
        "rows": len(frame), "positives": int(frame.actual_label.sum()),
        "model": original["model"], "baseline_identity": original["baseline_identity"],
        "auc_prc_difference_model_minus_classical": delta,
        "input_checks": {
            "row_order_sha256": row_hash(frame.row_id),
            "labels_sha256": partition["labels_sha256"][str(level)],
            "classical_predictions_sha256": sha_bytes(classical_bytes),
            "slm_predictions_sha256": sha_bytes(native_bytes),
            "original_report_sha256": file_hash(report_path),
            "study_sha256": report["study_sha256"],
            "selection_sha256": original["selection_sha256"],
            "source_paths": {"slm": str(native_path),
                             "classical": reference["source_commit"] + ":" + baseline["predictions_git_path"]},
            "original_probability_vector_sha256": {
                name: vector_hash(frame[name + "_probability"]) for name in ("classical", "model")
            },
            "diagnostic_probability_vector_sha256": {
                name: vector_hash(diagnostic_frame[name + "_probability"]) for name in ("classical", "model")
            },
            "csv_roundtrip_max_abs_difference": roundtrip_errors,
            "alignment": "exact full frozen test population and original row order; no filtering, truncation subset or reselection",
        },
        "original_report": original["uncertainty"],
        "diagnostic_report": diagnostic["uncertainty"],
        "configurations": {"original": original_config, "diagnostic": config},
        "metrics": {"model": model_metrics, "classical": baseline_metrics},
        "threshold_note": "Original report classical diagnostics used 0.5; T3 uses the archived validation threshold. Neither threshold enters ranking-metric bootstrap calculations.",
        **replay(frame, original, diagnostic, original_config, config, diagnostic_frame),
    }


def reconciliation_markdown(results):
    lines = [
        "# Confidence interval reconciliation", "",
        "Delta is SLM2 minus the validation-selected classical model in **AUC-PRC**, not AP.",
        "Both results are retained. No method is selected for having a favorable sign.", "",
    ]
    for result in results:
        lines += [f"## {result['project']}, K={result['level']}", ""]
        if result["status"] != "succeeded":
            lines += [f"**Blocked:** {result['reason']}", ""]
            continue
        lines += [
            f"Rows: {result['rows']}; positives: {result['positives']}; "
            f"unchanged point difference: {result['auc_prc_difference_model_minus_classical']:+.9f}.",
            "Exact source CSV hashes, frozen row/label order, model/comparator identity and config were checked.",
            "Original and diagnostic intervals replayed within the existing metric tolerance.", "",
            "| Replay | Samples | Seed | 95% delta AUC-PRC interval |",
            "|---|---:|---:|---|",
        ]
        for item in result["fixed_bridge"]:
            interval = item.get("interval_95") if "interval_95" in item else item["difference_95"]["auc_prc"]
            lines.append(f"| {item['step']} | {item['requested_samples']} | {item['seed']} | {interval} |")
        lines += ["", "AP/ROC intervals, valid draw counts and full fingerprints are retained in JSON.", ""]
    lines += [
        "## Why intervals differ", "",
        "The original procedure samples individual issues independently with replacement. "
        "The diagnostic procedure samples contiguous 20-row chronological blocks, concatenates "
        "them and trims to the original sample size; blocks do not wrap. It changes the resampling "
        "distribution and retains within-block dependence. Edge rows also have different inclusion "
        "weights under this non-circular construction. Seeds and draw counts differ as recorded.",
        "The fixed bridge separates successive configuration changes descriptively; their effects "
        "can interact and are not an additive causal attribution. Block intervals need not be wider.",
        "CSV representation differences are measured and replayed separately in the bridge; "
        "there is no score inversion, recalibration or filtering. Label, model, comparator and metric "
        "are not changed. Bootstrap intervals "
        "do not refit models or account for model-selection uncertainty. Sparse positives and "
        "finite draws limit stability. All comparisons are exploratory, unadjusted for multiplicity, "
        "and use an already observed holdout; a zero-crossing change is not fresh confirmation.",
        "AUC-PRC and AP are different metrics: original IntelDAOS K=5 has a positive AUC-PRC lower "
        "bound while its AP difference interval includes zero. Never substitute one for the other.",
    ]
    return "\n".join(lines) + "\n"
