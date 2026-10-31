"""One bounded base-model batch per command; no training or model management."""

import numpy as np

from protocol import BASE_METHOD, CELLS, cell_key, checked_json, digest, file_hash, read_json, study_id, write_json
from prepare_data import partition


def model_reference(approval):
    return {"model_id": approval["model"], "deployment": approval["base_deployment"],
            "method": BASE_METHOD}


def batch_scores(root, config, ledger, key, split, start, records, rows, marker):
    """Rebuild a missing private cache from exact receipts, never from paid inference."""
    from run_experiment import score_request

    run = study_id(root)
    path = root / "batches" / split / key / f"{start}.json"
    if not path.exists():
        approval = ledger.allocation(run)["approval"]
        scores = []
        for index in range(start, min(start + config["batch_rows"], len(rows))):
            operation = ledger.operation(run, f"{split}-{key}-{index}")
            request = score_request(approval, config, records[index]["messages"], approval["model"])
            if (operation is None or operation["status"] != "succeeded"
                    or operation["request_sha256"] != digest(request)):
                raise ValueError("Missing or mismatched batch receipt; never replay inference.")
            scores.append({"row_id": rows[index]["row_id"], "label": rows[index]["label"],
                           **operation["result"]})
        write_json(path, scores)
    scores = checked_json(path, marker["scores_sha256"])
    expected = rows[start:start + config["batch_rows"]]
    if (marker["start"] != start or marker["rows"] != len(expected)
            or [(s["row_id"], s["label"]) for s in scores] != [(r["row_id"], r["label"]) for r in expected]):
        raise ValueError("Batch coverage differs from the frozen partition.")
    return scores


def complete_cell(root, config, ledger, key, split, records, rows, reference, selection):
    from data_contract import baseline_predictions, load_project
    from evaluate import final_metrics
    from unstable_model.evaluation import calculate_metrics, select_threshold

    scores = []
    for start in range(0, len(rows), config["batch_rows"]):
        marker = ledger.artifact(study_id(root), f"batch-{split}-{key}-{start}")
        if marker is None:
            raise ValueError("Every batch must complete before selecting thresholds or reporting metrics.")
        scores.extend(batch_scores(root, config, ledger, key, split, start, records, rows, marker))
    labels = np.asarray([row["label"] for row in rows])
    probabilities = np.asarray([item["score"] for item in scores])
    threshold = select_threshold(labels, probabilities) if selection is None else selection["threshold"]
    directory = root / ("validation" if split == "validation" else "final") / key
    write_json(directory / "scores.json", scores)
    entry = read_json(root / "prepared.json")["entries"][key]
    value = {name: entry[name] for name in ("project", "level", "variant")}
    value.update(threshold=threshold, model_reference=reference,
                 scores_sha256=file_hash(directory / "scores.json"))
    if split == "validation":
        value["validation"] = calculate_metrics(labels, probabilities, threshold)
    else:
        _, _, test = load_project(entry["project"], root)
        if test.row_id.tolist() != [row["row_id"] for row in rows]:
            raise ValueError("Final-test rows differ from the reference contract.")
        baseline, baseline_reference = baseline_predictions(entry["project"], entry["level"], test)
        value.update(final_metrics(labels, probabilities, baseline, threshold,
                                   config["bootstrap_samples"], config["seed"]))
        value.update(baseline_reference=baseline_reference, selection_sha256=digest(selection))
    ledger.record(study_id(root), split + "-" + key, value)
    write_json(directory / ("validation.json" if split == "validation" else "metrics.json"), value)


def evaluate_batch(root, config, ledger, backend, split):
    from run_experiment import allowed_cells, authorized, require_open, score_once, sealed_cells

    if split not in ("validation", "test"):
        raise ValueError("Only validation and sealed final test are supported.")
    evidence = authorized(root, config, ledger)
    run = study_id(root)
    smoke = ledger.artifact(run, "smoke")
    if not smoke or smoke["study_sha256"] != digest(read_json(root / "study.json")):
        raise ValueError("Successful matching base-model smoke evidence is required.")
    if split == "validation":
        require_open(root, ledger)
        cells, selections = allowed_cells(evidence), None
    else:
        if evidence["approval"]["scope"] != "full":
            raise ValueError("Final test requires full-study spending approval.")
        cells, selections = CELLS, sealed_cells(root, ledger)
    reference = model_reference(evidence["approval"])
    for cell in cells:
        key = cell_key(*cell)
        selection = selections[key] if selections else None
        if selection and selection["model_reference"] != reference:
            raise ValueError("Test base model differs from the sealed selection.")
        saved = ledger.artifact(run, split + "-" + key)
        if saved is not None:
            if saved["model_reference"] != reference:
                raise ValueError("Completed cell uses a different base model.")
            directory = root / ("validation" if split == "validation" else "final") / key
            output = directory / ("validation.json" if split == "validation" else "metrics.json")
            if output.exists() and read_json(output) != saved:
                raise ValueError("Evaluation cache differs from cloud evidence.")
            write_json(output, saved)
            continue
        records, rows = partition(root, key, split)
        if len({row["label"] for row in rows}) != 2:
            raise ValueError("Both classes are required; no degenerate-cell fallback.")
        for start in range(0, len(rows), config["batch_rows"]):
            name = f"batch-{split}-{key}-{start}"
            if ledger.artifact(run, name) is not None:
                continue
            end = min(start + config["batch_rows"], len(rows))
            scores = []
            for index in range(start, end):
                result = score_once(root, config, ledger, backend, reference["deployment"],
                                    f"{split}-{key}-{index}", records[index]["messages"],
                                    rows[index]["input_tokens"], model=reference["model_id"])
                scores.append({"row_id": rows[index]["row_id"], "label": rows[index]["label"], **result})
            path = root / "batches" / split / key / f"{start}.json"
            write_json(path, scores)
            ledger.record(run, name, {"start": start, "rows": end - start,
                                     "scores_sha256": file_hash(path)})
            if end == len(rows):
                complete_cell(root, config, ledger, key, split, records, rows, reference, selection)
            return {"split": split, "cell": key, "batch_start": start, "batch_rows": end - start,
                    "cell_complete": end == len(rows),
                    "next": "Invoke the same stage explicitly for the next batch; no automatic submission."}
        # A previous command may have completed its last batch but lost metric assembly.
        complete_cell(root, config, ledger, key, split, records, rows, reference, selection)
        return {"split": split, "cell": key, "cell_complete": True, "recovered_from_receipts": True}
    return {"split": split, "scope_complete": True}
