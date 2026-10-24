#!/usr/bin/env python3
"""CPU orchestration of an explicitly approved, credit-bounded Azure SFT study."""

import argparse
import os
from pathlib import Path
import sys
from contextlib import ExitStack

from protocol import (
    CELLS, PILOT, PILOT_LEVEL, PILOT_PROJECT, TASK, cell_key, checked_json, config_at, digest,
    file_hash, read_json, require_unsealed, study, study_id, write_json,
)
from cost_control import check_approval, control_requests, estimate, inference_bound, money
from cloud_control import Ledger, SCHEMA
from prepare_data import Tokenizer, messages, partition, prepare

TERMINAL = {"succeeded", "failed", "cancelled"}


def approval_template(root, config):
    from cost_control import CHECKS

    return {
        "study_sha256": digest(read_json(root / "study.json")), "scope": "pilot",
        "endpoint": "", "resource_id": "", "base_deployment": "",
        "model": config["model"], "deployment_sku": config["deployment_sku"],
        "credit_offer": "", "remaining_credit_usd": "0", "expires_at": "",
        "evidence": "", "checks": {name: False for name in CHECKS},
        "rates": {"training_per_million": None, "input_per_million": None, "output_per_million": None},
        "rate_safety_multiplier": "1.25", "other_cost_reserve_usd": "0",
        "control_schema": SCHEMA, "authority_sha256": "", "storage_reserve_usd": "0",
    }


def authorized(root, config, ledger):
    run = study_id(root)
    allocation = ledger.allocation(run)
    if allocation is None:
        raise ValueError("No cloud authorization for this study.")
    evidence = allocation["authorization"]
    check_approval(evidence["approval"], digest(read_json(root / "study.json")), config)
    if evidence["prepared_sha256"] != file_hash(root / "prepared.json"):
        raise ValueError("Prepared manifest changed after approval.")
    state = ledger._root()[0]
    if money(evidence["approval"]["storage_reserve_usd"]) != money(state["storage"]["reserve_usd"]):
        raise ValueError("Storage allowance changed; renew model preflight before further paid work.")
    if state["breached"]:
        raise ValueError("Global ledger has a cost breach.")
    return evidence


def require_open(root, ledger):
    require_unsealed(root)
    if ledger.artifact(study_id(root), "seal") is not None:
        raise ValueError("Training and validation cannot change after cloud sealing.")


def preflight(root, config, approval, ledger, backend):
    check_approval(approval, digest(read_json(root / "study.json")), config)
    prepared = read_json(root / "prepared.json")
    if approval["scope"] == "full":
        for cell in PILOT:
            value = read_json(root / "validation" / cell_key(*cell) / "validation.json")
            checked_json(root / "validation" / cell_key(*cell) / "scores.json", value["scores_sha256"])
            if ledger.artifact(study_id(root), "validation-" + cell_key(*cell)) != value:
                raise ValueError("Pilot validation differs from cloud evidence.")
    value = estimate(prepared, config, approval)
    write_json(root / "cost_estimate.json", value)
    # Check affordability before contacting even a read-only cloud API.
    if money(value[approval["scope"]]) > money(config["pilot_limit_usd"] if approval["scope"] == "pilot"
                                             else config["total_limit_usd"]):
        raise ValueError("Scope is unaffordable; see cost_estimate.json. No cloud job was submitted.")
    ledger.require_capacity(value["control_requests"][approval["scope"]])
    access = {**backend.preflight(), **ledger.store.verify_account()}
    evidence = {"approval": approval, "access": access, "estimate": value,
                "prepared_sha256": file_hash(root / "prepared.json")}
    ledger.authorize(study_id(root), approval, value, config, evidence)
    write_json(root / "authorization.json", evidence)
    return evidence


def score_once(root, config, ledger, backend, deployment, operation, prompt, tokens, model=None):
    auth = authorized(root, config, ledger)["approval"]
    run = study_id(root)
    if model is None and deployment != auth["base_deployment"]:
        raise ValueError("Scoring requires the approved base deployment or an exact fine-tuned model identity.")
    request = {"resource_id": auth["resource_id"], "model": model or auth["model"],
               "messages_sha256": digest(prompt), "config_sha256": digest(config)}

    def actual(result):
        usage = result["usage"]
        return (money(usage["input_tokens"]) * money(auth["rates"]["input_per_million"])
                + money(usage["output_tokens"]) * money(auth["rates"]["output_per_million"])) / 1000000

    return ledger.perform(run, operation, inference_bound(tokens, config, auth), "inference", request,
                          lambda: backend.predict(deployment, prompt), actual,
                          attempts=config["request_attempts"])


def smoke(root, config, ledger, backend):
    from unstable_model.evaluation import calculate_metrics

    require_open(root, ledger)
    authorization = authorized(root, config, ledger)
    tokenizer = Tokenizer(config["model"])
    for index, text in enumerate(("Add a settings page.", "requirement " * config["text_tokens"])):
        prompt, count, _ = messages(text, PILOT_LEVEL, None, tokenizer, config)
        score_once(root, config, ledger, backend, authorization["approval"]["base_deployment"],
                   f"smoke-{index}", prompt, count)
    records, rows = partition(root, cell_key(PILOT_PROJECT, PILOT_LEVEL, "text"), "validation")
    scores = []
    for index, (record, row) in enumerate(zip(records[:20], rows[:20])):
        result = score_once(root, config, ledger, backend, authorization["approval"]["base_deployment"],
                            f"base-control-{index}", record["messages"], row["input_tokens"])
        scores.append(result["score"])
    write_json(root / "base_control.json", {
        "protocol": f"unfine-tuned text-only; first 20 {PILOT_PROJECT}/{PILOT_LEVEL} validation rows; diagnostic only",
        "row_ids": [row["row_id"] for row in rows[:20]], "scores": scores,
        "metrics": calculate_metrics([row["label"] for row in rows[:20]], scores, .5),
    })
    value = {"study_sha256": digest(read_json(root / "study.json")),
             "base_deployment": authorization["approval"]["base_deployment"]}
    ledger.record(study_id(root), "smoke", value)
    write_json(root / "smoke.json", value)


def allowed_cells(evidence):
    return PILOT if evidence["approval"]["scope"] == "pilot" else CELLS


def train_submit(root, config, ledger, backend):
    require_open(root, ledger)
    evidence = authorized(root, config, ledger)
    smoke_value = ledger.artifact(study_id(root), "smoke")
    if not smoke_value or smoke_value["study_sha256"] != digest(read_json(root / "study.json")):
        raise ValueError("A matching successful base-model smoke test is required.")
    run = study_id(root)
    for cell in allowed_cells(evidence):
        key = cell_key(*cell)
        path = root / "remote" / f"{key}.json"
        operation = ledger.operation(run, "train-" + key)
        if operation and operation.get("result"):
            if operation["result"]["status"] == "succeeded":
                continue
            raise ValueError("An existing job is unfinished or failed; run train-status, do not retrain.")
        partition(root, key, "train")
        filename = f"master-{run[:12]}-{key}.jsonl"
        uploaded = ledger.perform(
            run, "upload-" + key, 0, "upload",
            {"filename": filename, "sha256": file_hash(root / "prepared" / key / "train.jsonl")},
            lambda: {"file_id": backend.upload(root / "prepared" / key / "train.jsonl", filename)},
        )
        file_id = uploaded["file_id"]
        backend.wait_file(file_id)
        request = {"file": file_id, "model": config["model"], "epochs": config["epochs"]}
        job = ledger.perform(run, "train-" + key, evidence["estimate"]["entries"][key]["train"],
                             "training", request,
                             lambda: backend.train(file_id, "master-" + digest(key + run)[:16]))
        write_json(path, {"training_file": file_id, "job": job})
        return {"submitted_cell": key, "job_id": job["id"], "next": "train-status"}
    return {"training_complete": True, "next": "validate"}


def train_status(root, config, ledger, backend, cancel=False):
    run = study_id(root)
    results = {}
    for cell in CELLS:
        key = cell_key(*cell)
        upload = ledger.operation(run, "upload-" + key)
        if upload is None:
            continue
        if upload["status"] == "dispatched":
            recovered = {"file_id": backend.find_upload(upload["request"]["filename"])}
            ledger.finish(run, "upload-" + key, recovered)
            upload = ledger.operation(run, "upload-" + key)
        if not upload.get("result"):
            continue
        file_id = upload["result"]["file_id"]
        operation = ledger.operation(run, "train-" + key)
        if operation is None:
            continue
        if operation["status"] == "prepared":
            if not cancel:
                results[key] = "not_submitted"
                continue
            job = {"id": None, "status": "cancelled", "model": config["model"],
                   "training_file": file_id, "fine_tuned_model": None, "trained_tokens": 0}
            ledger.cancel_prepared_training(run, "train-" + key, job)
            operation = ledger.operation(run, "train-" + key)
        previous = operation.get("result")
        if previous and previous.get("id") is None and operation["status"] == "terminal":
            job = previous
        else:
            job = backend.job(previous["id"]) if previous else backend.find_job(file_id)
        if job["model"] != config["model"] or job["training_file"] != file_id:
            raise ValueError("Recovered remote training provenance differs.")
        if cancel and job["status"] not in TERMINAL:
            ledger.finish(run, "train-" + key, job)
            job = ledger.perform(run, "cancel-" + key, 0, "cancel", {"job": job["id"]},
                                 lambda: backend.cancel(job["id"]), recovery=True)
        write_json(root / "remote" / f"{key}.json", {"training_file": file_id, "job": job})
        if job["status"] in TERMINAL:
            actual = None
            tokens = job.get("trained_tokens")
            if tokens is not None:
                approval = ledger.allocation(run)["approval"]
                actual = money(tokens) * money(approval["rates"]["training_per_million"]) / 1000000
            ledger.finish(run, "train-" + key, job, actual=actual, terminal=True)
        else:
            ledger.finish(run, "train-" + key, job)
        results[key] = job["status"]
    return results


def deploy(root, config, ledger, backend, key, model):
    run = study_id(root)
    record = ledger.claim_deployment(run, key, model, config["deployment_sku"])
    operation_name = "deploy-" + str(record["generation"])
    operation = ledger.operation(run, operation_name)
    if operation is None or operation["status"] == "prepared":
        if backend.get_deployment(record["name"]) is not None:
            raise ValueError("Refusing to adopt a deployment without an ownership manifest.")
        def create():
            backend.deploy(record["name"], model, run)
            return {"submitted": True}
        ledger.perform(run, operation_name, 0, "deploy", record, create)
    elif operation["status"] == "dispatched":
        backend.ready(record["name"], model, run)
        ledger.finish(run, operation_name, {"submitted": True})
    elif backend.get_deployment(record["name"]) is None:
        raise ValueError("Owned deployment expired/missing; run cleanup before a new deployment generation.")
    backend.ready(record["name"], model, run)
    return record["name"]


def remove_deployment(root, ledger, backend):
    record = ledger.deployment()
    if record:
        if record["run"] != study_id(root):
            raise ValueError("Deployment belongs to a different study.")
        current = backend.get_deployment(record["name"])
        if current is not None and (
            current.get("tags", {}).get("master-study") != record["run"]
            or current["properties"]["model"]["name"] != record["model"]
            or current["sku"]["name"] != record["sku"]
        ):
            raise ValueError("Refusing to delete a deployment with different ownership.")
        create_name = "deploy-" + str(record["generation"])
        creation = ledger.operation(study_id(root), create_name)
        if creation and creation["status"] == "dispatched":
            if current is None:
                raise ValueError("Unconfirmed deployment creation; absence does not prove the request failed.")
            ledger.finish(study_id(root), create_name, {"submitted": True})
        name = "remove-deployment-" + str(record["generation"])
        pending = ledger.operation(study_id(root), name)
        if pending and pending["status"] == "dispatched":
            if current is not None:
                raise ValueError("Unconfirmed deployment deletion; wait and reconcile, do not replay.")
            ledger.finish(study_id(root), name, {"removed": True})
        else:
            def remove():
                backend.remove_deployment(record["name"])
                return {"removed": True}
            ledger.perform(study_id(root), name, 0, "delete", record, remove, recovery=True)
        ledger.clear_deployment(record)


def restore_scores(root, ledger, split, key, selection, operations=None):
    directory = root / ("validation" if split == "validation" else "final") / key
    path = directory / "scores.json"
    if not path.exists():
        run = study_id(root)
        allocation = ledger.allocation(run)
        config = read_json(root / "study.json")["config"]
        records, rows = partition(root, key, split)
        operations = operations if operations is not None else {
            item["name"]: item for item in ledger.operations(run)}
        scores = []
        for index, (record, row) in enumerate(zip(records, rows)):
            saved = operations.get(f"{split}-{key}-{index}")
            request = {"resource_id": allocation["approval"]["resource_id"],
                       "model": selection["model_reference"]["model_id"],
                       "messages_sha256": digest(record["messages"]), "config_sha256": digest(config)}
            if (saved is None or saved["status"] != "succeeded"
                    or saved["request_sha256"] != digest(request)):
                raise ValueError("Missing or mismatched cloud score; never reconstruct it by a paid replay.")
            scores.append({"row_id": row["row_id"], "label": row["label"], **saved["result"]})
        write_json(path, scores)
    checked_json(path, selection["scores_sha256"])


def sealed_cells(root, ledger):
    seal = ledger.artifact(study_id(root), "seal")
    if seal is None:
        raise ValueError("No cloud selection seal.")
    if (root / "sealed.json").exists() and read_json(root / "sealed.json") != seal:
        raise ValueError("Local selection changed after cloud sealing.")
    write_json(root / "sealed.json", seal)
    if (seal["study_sha256"] != digest(read_json(root / "study.json")) or
            seal["prepared_sha256"] != file_hash(root / "prepared.json")):
        raise ValueError("Sealed study or data changed.")
    expected = {cell_key(*cell) for cell in CELLS}
    if set(seal["cells"]) != expected:
        raise ValueError(f"Seal requires all {len(CELLS)} approved entries.")
    operations = None
    for key, cell in seal["cells"].items():
        directory = root / "validation" / key
        if not (directory / "validation.json").exists():
            write_json(directory / "validation.json", cell)
        if read_json(directory / "validation.json") != cell:
            raise ValueError("Validation selection changed after sealing.")
        if not (directory / "scores.json").exists() and operations is None:
            operations = {item["name"]: item for item in ledger.operations(study_id(root))}
        restore_scores(root, ledger, "validation", key, cell, operations)
    return seal["cells"]


def seal(root, ledger):
    if ledger.artifact(study_id(root), "seal") is not None:
        sealed_cells(root, ledger)
        return
    cells = {}
    for project, level, variant in CELLS:
        key = cell_key(project, level, variant)
        directory = root / "validation" / key
        value = read_json(directory / "validation.json")
        if ledger.artifact(study_id(root), "validation-" + key) != value:
            raise ValueError("Validation selection differs from cloud completion evidence.")
        checked_json(directory / "scores.json", value["scores_sha256"])
        if (value["project"], value["level"], value["variant"]) != (project, level, variant):
            raise ValueError("Validation cell identity differs.")
        cells[key] = value
    value = {"study_sha256": digest(read_json(root / "study.json")),
             "prepared_sha256": file_hash(root / "prepared.json"), "cells": cells}
    ledger.record(study_id(root), "seal", value)
    write_json(root / "sealed.json", value)


def evaluate(root, config, ledger, backend, split):
    import numpy as np
    from data_contract import baseline_predictions, load_project
    from evaluate import final_metrics
    from unstable_model.evaluation import calculate_metrics, select_threshold

    evidence = authorized(root, config, ledger)
    if split == "validation":
        require_open(root, ledger)
        cells = allowed_cells(evidence)
        selected = None
    else:
        if evidence["approval"]["scope"] != "full":
            raise ValueError("Final test requires full-study spending approval.")
        selected, cells = sealed_cells(root, ledger), CELLS
    for project, level, variant in cells:
        key = cell_key(project, level, variant)
        directory = root / ("validation" if split == "validation" else "final") / key
        output = directory / ("validation.json" if split == "validation" else "metrics.json")
        if output.exists():
            previous = read_json(output)
            saved = ledger.artifact(study_id(root), split + "-" + key)
            if saved is not None:
                if saved != previous:
                    raise ValueError("Evaluation cache differs from cloud evidence.")
                restore_scores(root, ledger, split, key, saved)
                continue
        job = ledger.operation(study_id(root), "train-" + key)["result"]
        if job["status"] != "succeeded" or not job["fine_tuned_model"]:
            raise ValueError("Training must succeed before evaluation.")
        model = job["fine_tuned_model"]
        if selected and selected[key]["model_reference"] != {"model_id": model, "job_id": job["id"]}:
            raise ValueError("Test model differs from the sealed fine-tune.")
        records, rows = partition(root, key, split)
        labels = np.asarray([row["label"] for row in rows])
        if len(np.unique(labels)) != 2:
            raise ValueError("Both classes are required; no degenerate-cell fallback.")
        name = None
        scores = []
        for index, (record, row) in enumerate(zip(records, rows)):
            operation_name = f"{split}-{key}-{index}"
            prior = ledger.operation(study_id(root), operation_name)
            if name is None and (prior is None or prior["status"] == "prepared"):
                name = deploy(root, config, ledger, backend, key, model)
            result = score_once(root, config, ledger, backend, name, operation_name,
                                record["messages"], row["input_tokens"], model=model)
            scores.append({"row_id": row["row_id"], "label": row["label"], **result})
        # Cleanup remains explicit if inference fails; its owning manifest survives.
        active = ledger.deployment()
        if active and active["run"] == study_id(root) and active["key"] == key:
            remove_deployment(root, ledger, backend)
        probabilities = np.asarray([item["score"] for item in scores])
        threshold = select_threshold(labels, probabilities) if selected is None else selected[key]["threshold"]
        write_json(directory / "scores.json", scores)
        value = {"project": project, "level": level, "variant": variant, "threshold": threshold,
                 "model_reference": {"model_id": model, "job_id": job["id"]},
                 "scores_sha256": file_hash(directory / "scores.json")}
        if split == "validation":
            value["validation"] = calculate_metrics(labels, probabilities, threshold)
        else:
            _, _, test = load_project(project, root)
            if test.row_id.tolist() != [row["row_id"] for row in rows]:
                raise ValueError("Final-test rows differ from the reference contract.")
            baseline, reference = baseline_predictions(project, level, test)
            value.update(final_metrics(labels, probabilities, baseline, threshold, config["bootstrap_samples"], config["seed"]))
            value["baseline_reference"] = reference
            value["selection_sha256"] = digest(selected[key])
        write_json(output, value)
        ledger.record(study_id(root), split + "-" + key, value)


def report(root, ledger, output):
    if read_json(root / "study.json")["config"]["schema"] != "openai-instability-v2":
        raise ValueError("Reporting an older study requires its original protocol version.")
    entries = []
    selections = sealed_cells(root, ledger) if ledger.artifact(study_id(root), "seal") is not None else None
    operations = None
    for project, level, variant in CELLS:
        key = cell_key(project, level, variant)
        path = root / "final" / key / "metrics.json"
        cell = {"project": project, "level": level, "variant": variant, "status": "missing"}
        saved = ledger.artifact(study_id(root), "test-" + key)
        if saved is not None and not path.exists():
            write_json(path, saved)
        if path.exists():
            value = read_json(path)
            if ledger.artifact(study_id(root), "test-" + key) != value:
                raise ValueError("Test result differs from cloud completion evidence.")
            if not (path.parent / "scores.json").exists() and operations is None:
                operations = {item["name"]: item for item in ledger.operations(study_id(root))}
            restore_scores(root, ledger, "test", key, value, operations)
            if selections is None:
                raise ValueError("Final-test results exist without a selection seal.")
            selection = selections[key]
            if value["selection_sha256"] != digest(selection):
                raise ValueError("Test result selection changed.")
            cell.update(value)
            cell["status"] = "complete"
        entries.append(cell)
    complete = all(cell["status"] == "complete" for cell in entries)
    result = {
        "schema": "openai-instability-report-v2", "stage": "final-test", "cells": entries,
        "complete": complete, "passed": complete and all(c["gates"]["passed"] for c in entries),
        "study_sha256": digest(read_json(root / "study.json")),
        "costs": ledger.snapshot(study_id(root)) if ledger.allocation(study_id(root)) else {"authorized": False},
        "limitations": ["Scope is Jira and Qt at levels 5 and 20, both variants; not the six-project study.",
                        "Retrospective reused holdout; possible pretraining exposure.",
                        "Conditional label-token scores are not calibrated event probabilities.",
                        "Issue bootstrap does not model temporal dependence.",
                        "Missing comparators are not estimated; hosted weights are not exported."],
    }
    write_json(output, result)
    return result


def cleanup(root, config, ledger, backend, delete_models=False):
    statuses = train_status(root, config, ledger, backend)
    if any(status not in TERMINAL for status in statuses.values()):
        raise ValueError("Cancel active Azure training first; SLURM exit is not cancellation.")
    remove_deployment(root, ledger, backend)
    run = study_id(root)
    for cell in CELLS:
        key = cell_key(*cell)
        upload = ledger.operation(run, "upload-" + key)
        if upload and upload.get("result"):
            file_id = upload["result"]["file_id"]
            def remove_file():
                backend.delete_file(file_id)
                return {"removed": True}
            ledger.perform(run, "delete-file-" + key, 0, "delete", {"file_id": file_id},
                           remove_file, recovery=True)
        training = ledger.operation(run, "train-" + key)
        model = training.get("result", {}).get("fine_tuned_model") if training else None
        if delete_models and model:
            def remove_model():
                backend.delete_model(model)
                return {"removed": True}
            ledger.perform(run, "delete-model-" + key, 0, "delete", {"model": model},
                           remove_model, recovery=True)
    write_json(root / "cleanup.json", {"deployments_removed": True, "uploads_removed": True,
                                     "models_retained": not delete_models})


def reconcile(root, config, ledger, backend):
    run = study_id(root)
    pending = ledger._root()[0]["pending"]
    if pending is None:
        return train_status(root, config, ledger, backend)
    if pending[0] != run:
        raise ValueError("Pending dispatch belongs to another study; use its recovery command.")
    name = pending[1]
    operation = ledger.operation(run, name)
    if operation["kind"] in ("training", "upload"):
        return train_status(root, config, ledger, backend)
    if operation["kind"] == "cancel":
        job = backend.job(operation["request"]["job"])
        if job["status"] not in TERMINAL:
            raise ValueError("Cancellation outcome is not terminal; wait, never replay it.")
        ledger.finish(run, name, job)
        return train_status(root, config, ledger, backend)
    if operation["kind"] == "deploy":
        record = operation["request"]
        backend.ready(record["name"], record["model"], record["run"])
        ledger.finish(run, name, {"submitted": True})
    elif operation["kind"] == "delete":
        request = operation["request"]
        if "file_id" in request:
            exists = backend.file_exists(request["file_id"])
        elif "name" in request:
            exists = backend.get_deployment(request["name"]) is not None
        else:
            exists = backend.model_exists(request["model"])
        if exists:
            raise ValueError("Deletion outcome unconfirmed; wait, never replay it.")
        ledger.finish(run, name, {"removed": True})
    else:
        ledger.recover_receipt(run, name)
    return {"reconciled": name}


STAGES = ("prepare", "preflight", "smoke", "train-submit", "train-status", "reconcile", "validate",
          "seal", "test", "report", "cancel", "cleanup")


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=STAGES)
    parser.add_argument("--config", type=Path, default=TASK / "experiment.json")
    parser.add_argument("--storage", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--approval", type=Path)
    parser.add_argument("--report-output", type=Path)
    parser.add_argument("--delete-models", action="store_true")
    args = parser.parse_args()
    if args.delete_models and args.stage != "cleanup":
        parser.error("--delete-models is valid only for cleanup")
    if args.approval and args.stage != "preflight":
        parser.error("--approval is valid only for preflight")
    if args.stage in ("train-status", "cancel", "cleanup", "report", "reconcile"):
        from protocol import external_path, slug

        root = external_path(args.storage) / "openai-runs" / slug(args.run_id)
        config = read_json(root / "study.json")["config"]
        if config.get("control_schema") != SCHEMA:
            raise ValueError("Legacy study needs its original recovery code; do not migrate paid state implicitly.")
    else:
        config = config_at(args.config)
        root = study(args.storage, args.run_id, config)
    status = root / "status" / f"{args.stage}.json"
    backend = None
    write_json(status, {"status": "running", "stage": args.stage})
    try:
        with ExitStack() as stack:
            ledger = None if args.stage == "prepare" else Ledger.configured()
            if ledger is not None:
                stack.callback(ledger.close)
                def requests():
                    allocation = ledger.allocation(study_id(root))
                    return control_requests(
                        args.stage, read_json(root / "prepared.json"), config,
                        allocation["scope"] if allocation else "pilot",
                    )
                stack.enter_context(ledger.session(requests=requests))
            if args.stage == "prepare":
                prepare(root, config)
                write_json(root / "approval.template.json", approval_template(root, config))
                result = {"study_sha256": digest(read_json(root / "study.json")), "next": "preflight"}
            elif args.stage == "seal":
                authorized(root, config, ledger)
                seal(root, ledger)
                result = {"sealed": True}
            elif args.stage == "report":
                result = report(root, ledger, args.report_output or root / "llm_report.json")
                result = {"complete": result["complete"], "passed": result["passed"]}
            else:
                from azure_backend import AzureBackend

                if args.stage == "preflight":
                    if args.approval is None:
                        raise ValueError("Supply reviewed external --approval; template defaults prohibit spending.")
                    from protocol import external_path

                    approval = read_json(external_path(args.approval))
                    check_approval(approval, digest(read_json(root / "study.json")), config)
                elif args.stage in ("cancel", "cleanup", "train-status", "reconcile"):
                    # Recovery must remain possible after credit approval expires.
                    approval = ledger.allocation(study_id(root))["approval"]
                else:
                    approval = authorized(root, config, ledger)["approval"]
                backend = AzureBackend(approval, config)
                backend.guard = ledger.guard_remote
                if args.stage == "preflight":
                    preflight(root, config, approval, ledger, backend)
                    result = {"authorized_scope": approval["scope"]}
                elif args.stage == "smoke":
                    smoke(root, config, ledger, backend)
                    result = {"smoke": "succeeded"}
                elif args.stage == "train-submit":
                    result = train_submit(root, config, ledger, backend)
                elif args.stage in ("train-status", "cancel"):
                    result = train_status(root, config, ledger, backend, args.stage == "cancel")
                elif args.stage == "reconcile":
                    result = reconcile(root, config, ledger, backend)
                elif args.stage in ("validate", "test"):
                    evaluate(root, config, ledger, backend, "validation" if args.stage == "validate" else "test")
                    result = {"evaluated": args.stage}
                else:
                    cleanup(root, config, ledger, backend, args.delete_models)
                    result = {"cleanup": "succeeded"}
        write_json(status, {"status": "succeeded", "result": result})
        print(result)
    except Exception as error:
        from azure_backend import ProviderError

        write_json(status, {"status": "failed", "stage": args.stage, "error_type": type(error).__name__,
                            "http_status": getattr(error, "status_code", None)})
        # SDK exceptions can contain raw story text. Never emit their body.
        detail = str(error) if isinstance(error, (ValueError, FileNotFoundError, ProviderError)) else type(error).__name__
        print(f"FAILED {args.stage}: {detail}. See {status}; reconcile remote state before retrying.",
              file=sys.stderr)
        raise SystemExit(1) from None
    finally:
        if backend is not None:
            backend.close()


if __name__ == "__main__":
    main()
