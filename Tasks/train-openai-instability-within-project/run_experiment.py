#!/usr/bin/env python3
"""CPU orchestration of an explicitly approved, credit-bounded Azure SFT study."""

import argparse
import os
from pathlib import Path
import sys

from protocol import (
    CELLS, PILOT, PILOT_LEVEL, PILOT_PROJECT, TASK, cell_key, checked_json, config_at, digest, exclusive_lock,
    file_hash, read_json, require_unsealed, study, study_id, write_json,
)
from cost_control import Ledger, check_approval, estimate, inference_bound, money
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
    }


def authorized(root, config, ledger):
    evidence = read_json(root / "authorization.json")
    check_approval(evidence["approval"], digest(read_json(root / "study.json")), config)
    run = study_id(root)
    allocation = ledger.read()["runs"].get(run)
    if allocation is None or allocation["approval"] != evidence["approval"]:
        raise ValueError("Local approval differs from the global cost allocation.")
    if evidence["prepared_sha256"] != file_hash(root / "prepared.json"):
        raise ValueError("Prepared manifest changed after approval.")
    if ledger.read()["breached"]:
        raise ValueError("Global ledger has a cost breach.")
    return evidence


def preflight(root, config, approval, ledger, backend):
    check_approval(approval, digest(read_json(root / "study.json")), config)
    prepared = read_json(root / "prepared.json")
    if approval["scope"] == "full":
        for cell in PILOT:
            value = read_json(root / "validation" / cell_key(*cell) / "validation.json")
            checked_json(root / "validation" / cell_key(*cell) / "scores.json", value["scores_sha256"])
    value = estimate(prepared, config, approval)
    write_json(root / "cost_estimate.json", value)
    # Check affordability before contacting even a read-only cloud API.
    if money(value[approval["scope"]]) > money(config["pilot_limit_usd"] if approval["scope"] == "pilot"
                                             else config["total_limit_usd"]):
        raise ValueError("Scope is unaffordable; see cost_estimate.json. No cloud job was submitted.")
    access = backend.preflight()
    ledger.authorize(study_id(root), approval, value, config)
    evidence = {"approval": approval, "access": access, "estimate": value,
                "prepared_sha256": file_hash(root / "prepared.json")}
    write_json(root / "authorization.json", evidence)
    return evidence


def score_once(root, config, ledger, backend, deployment, operation, prompt, tokens):
    auth = authorized(root, config, ledger)["approval"]
    run = study_id(root)
    request = {"deployment": deployment, "messages": prompt, "config": config}
    previous = ledger.begin(run, operation, inference_bound(tokens, config, auth), "inference", request)
    if previous is not None:
        return previous
    result = backend.predict(deployment, prompt)
    usage = result["usage"]
    actual = (money(usage["input_tokens"]) * money(auth["rates"]["input_per_million"])
              + money(usage["output_tokens"]) * money(auth["rates"]["output_per_million"])) / 1000000
    # Earlier failed attempts may have been charged: never release their bounds.
    if result["attempts"] > 1:
        actual = None
    ledger.finish(run, operation, result, actual)
    return result


def smoke(root, config, ledger, backend):
    from unstable_model.evaluation import calculate_metrics

    require_unsealed(root)
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
    write_json(root / "smoke.json", {"study_sha256": digest(read_json(root / "study.json")),
                                   "base_deployment": authorization["approval"]["base_deployment"]})


def allowed_cells(evidence):
    return PILOT if evidence["approval"]["scope"] == "pilot" else CELLS


def train_submit(root, config, ledger, backend):
    require_unsealed(root)
    evidence = authorized(root, config, ledger)
    if read_json(root / "smoke.json")["study_sha256"] != digest(read_json(root / "study.json")):
        raise ValueError("A matching successful base-model smoke test is required.")
    run = study_id(root)
    for cell in allowed_cells(evidence):
        key = cell_key(*cell)
        path = root / "remote" / f"{key}.json"
        remote = read_json(path) if path.exists() else {}
        if remote.get("job"):
            if remote["job"]["status"] == "succeeded":
                continue
            raise ValueError("An existing job is unfinished or failed; run train-status, do not retrain.")
        partition(root, key, "train")
        filename = f"master-{run[:12]}-{key}.jsonl"
        if not remote:
            remote = {"upload_intent": filename}
            write_json(path, remote)
            file_id = backend.upload(root / "prepared" / key / "train.jsonl", filename)
        elif "training_file" not in remote:
            file_id = backend.find_upload(filename)
        else:
            file_id = remote["training_file"]
        remote["training_file"] = file_id
        write_json(path, remote)
        request = {"file": file_id, "model": config["model"], "epochs": config["epochs"]}
        previous = ledger.begin(run, "train-" + key, evidence["estimate"]["entries"][key]["train"],
                                "training", request)
        job = previous or backend.train(file_id, "master-" + digest(key + run)[:16])
        remote["job"] = job
        write_json(path, remote)
        ledger.finish(run, "train-" + key, job)
        return {"submitted_cell": key, "job_id": job["id"], "next": "train-status"}
    return {"training_complete": True, "next": "validate"}


def train_status(root, config, ledger, backend, cancel=False):
    run = study_id(root)
    results = {}
    for path in sorted((root / "remote").glob("*.json")):
        key, remote = path.stem, read_json(path)
        if "training_file" not in remote:
            remote["training_file"] = backend.find_upload(remote["upload_intent"])
        operation = ledger.operation(run, "train-" + key)
        if operation is None:
            write_json(path, remote)
            continue
        job = backend.job(remote["job"]["id"]) if remote.get("job") else backend.find_job(remote["training_file"])
        if job["model"] != config["model"] or job["training_file"] != remote["training_file"]:
            raise ValueError("Recovered remote training provenance differs.")
        if cancel and job["status"] not in TERMINAL:
            job = backend.cancel(job["id"])
        remote["job"] = job
        write_json(path, remote)
        if job["status"] in TERMINAL:
            actual = None
            tokens = job.get("trained_tokens")
            if tokens is not None:
                approval = ledger.read()["runs"][run]["approval"]
                actual = money(tokens) * money(approval["rates"]["training_per_million"]) / 1000000
            ledger.finish(run, "train-" + key, job, actual=actual, terminal=True)
        else:
            ledger.finish(run, "train-" + key, job)
        results[key] = job["status"]
    return results


def deploy(root, config, ledger, backend, key, model):
    run = study_id(root)
    path = ledger.directory / "deployment.json"
    record = {"run": run, "name": "master-" + digest(run + key)[:24], "model": model}
    if path.exists() and read_json(path) != record:
        raise ValueError("Another deployment is active/unconfirmed; clean up its owning study.")
    existed = path.exists()
    if not existed:
        if backend.get_deployment(record["name"]) is not None:
            raise ValueError("Refusing to adopt a deployment without an ownership manifest.")
        write_json(path, record)
        backend.deploy(record["name"], model, run)
    elif backend.get_deployment(record["name"]) is None:
        # A documented Developer expiry can recreate the exact same owned model.
        backend.deploy(record["name"], model, run)
    backend.ready(record["name"], model, run)
    return record["name"]


def remove_deployment(root, ledger, backend):
    path = ledger.directory / "deployment.json"
    if path.exists():
        record = read_json(path)
        if record["run"] != study_id(root):
            raise ValueError("Deployment belongs to a different study.")
        current = backend.get_deployment(record["name"])
        if current is not None and (
            current.get("tags", {}).get("master-study") != record["run"]
            or current["properties"]["model"]["name"] != record["model"]
        ):
            raise ValueError("Refusing to delete a deployment with different ownership.")
        backend.remove_deployment(record["name"])
        path.unlink()


def sealed_cells(root):
    seal = read_json(root / "sealed.json")
    if (seal["study_sha256"] != digest(read_json(root / "study.json")) or
            seal["prepared_sha256"] != file_hash(root / "prepared.json")):
        raise ValueError("Sealed study or data changed.")
    expected = {cell_key(*cell) for cell in CELLS}
    if set(seal["cells"]) != expected:
        raise ValueError(f"Seal requires all {len(CELLS)} approved entries.")
    for key, cell in seal["cells"].items():
        directory = root / "validation" / key
        if read_json(directory / "validation.json") != cell:
            raise ValueError("Validation selection changed after sealing.")
        checked_json(directory / "scores.json", cell["scores_sha256"])
    return seal["cells"]


def seal(root):
    if (root / "sealed.json").exists():
        sealed_cells(root)
        return
    cells = {}
    for project, level, variant in CELLS:
        key = cell_key(project, level, variant)
        directory = root / "validation" / key
        value = read_json(directory / "validation.json")
        checked_json(directory / "scores.json", value["scores_sha256"])
        if (value["project"], value["level"], value["variant"]) != (project, level, variant):
            raise ValueError("Validation cell identity differs.")
        cells[key] = value
    write_json(root / "sealed.json", {"study_sha256": digest(read_json(root / "study.json")),
                                    "prepared_sha256": file_hash(root / "prepared.json"), "cells": cells})


def evaluate(root, config, ledger, backend, split):
    import numpy as np
    from data_contract import baseline_predictions, load_project
    from evaluate import final_metrics
    from unstable_model.evaluation import calculate_metrics, select_threshold

    evidence = authorized(root, config, ledger)
    if split == "validation":
        require_unsealed(root)
        cells = allowed_cells(evidence)
        selected = None
    else:
        if evidence["approval"]["scope"] != "full":
            raise ValueError("Final test requires full-study spending approval.")
        selected, cells = sealed_cells(root), CELLS
    for project, level, variant in cells:
        key = cell_key(project, level, variant)
        directory = root / ("validation" if split == "validation" else "final") / key
        output = directory / ("validation.json" if split == "validation" else "metrics.json")
        if output.exists():
            previous = read_json(output)
            checked_json(directory / "scores.json", previous["scores_sha256"])
            continue
        remote = read_json(root / "remote" / f"{key}.json")
        job = remote["job"]
        if job["status"] != "succeeded" or not job["fine_tuned_model"]:
            raise ValueError("Training must succeed before evaluation.")
        model = job["fine_tuned_model"]
        if selected and selected[key]["model_reference"] != {"model_id": model, "job_id": job["id"]}:
            raise ValueError("Test model differs from the sealed fine-tune.")
        records, rows = partition(root, key, split)
        labels = np.asarray([row["label"] for row in rows])
        if len(np.unique(labels)) != 2:
            raise ValueError("Both classes are required; no degenerate-cell fallback.")
        name = deploy(root, config, ledger, backend, key, model)
        scores = []
        for index, (record, row) in enumerate(zip(records, rows)):
            result = score_once(root, config, ledger, backend, name, f"{split}-{key}-{index}",
                                record["messages"], row["input_tokens"])
            scores.append({"row_id": row["row_id"], "label": row["label"], **result})
        # Cleanup remains explicit if inference fails; its owning manifest survives.
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


def report(root, ledger, output):
    if read_json(root / "study.json")["config"]["schema"] != "openai-instability-v2":
        raise ValueError("Reporting an older study requires its original protocol version.")
    entries = []
    selections = sealed_cells(root) if (root / "sealed.json").exists() else None
    for project, level, variant in CELLS:
        key = cell_key(project, level, variant)
        path = root / "final" / key / "metrics.json"
        cell = {"project": project, "level": level, "variant": variant, "status": "missing"}
        if path.exists():
            value = read_json(path)
            checked_json(path.parent / "scores.json", value["scores_sha256"])
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
        "costs": ledger.snapshot(study_id(root)) if study_id(root) in ledger.read()["runs"] else {"authorized": False},
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
    for path in (root / "remote").glob("*.json"):
        value = read_json(path)
        if "training_file" in value and not value.get("file_deleted"):
            backend.delete_file(value["training_file"])
            value["file_deleted"] = True
            write_json(path, value)
        model = value.get("job", {}).get("fine_tuned_model")
        if delete_models and model and not value.get("model_deleted"):
            backend.delete_model(model)
            value["model_deleted"] = True
            write_json(path, value)
    write_json(root / "cleanup.json", {"deployments_removed": True, "uploads_removed": True,
                                     "models_retained": not delete_models})


STAGES = ("prepare", "preflight", "smoke", "train-submit", "train-status", "validate",
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
    ledger = Ledger()
    if args.stage in ("train-status", "cancel", "cleanup", "report"):
        from protocol import external_path, slug

        root = external_path(args.storage) / "openai-runs" / slug(args.run_id)
        config = read_json(root / "study.json")["config"]
    else:
        config = config_at(args.config)
        root = study(args.storage, args.run_id, config)
    status = root / "status" / f"{args.stage}.json"
    backend = None
    with exclusive_lock(ledger.directory / ".execution.lock"):
        write_json(status, {"status": "running", "stage": args.stage})
        try:
            if args.stage == "prepare":
                prepare(root, config)
                write_json(root / "approval.template.json", approval_template(root, config))
                result = {"study_sha256": digest(read_json(root / "study.json")), "next": "preflight"}
            elif args.stage == "seal":
                seal(root)
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
                elif args.stage in ("cancel", "cleanup", "train-status"):
                    # Recovery must remain possible after credit approval expires.
                    approval = ledger.read()["runs"][study_id(root)]["approval"]
                else:
                    approval = authorized(root, config, ledger)["approval"]
                backend = AzureBackend(approval, config)
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
