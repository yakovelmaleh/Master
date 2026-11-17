#!/usr/bin/env python3
"""Offline preparation or one explicitly approved stage of the sufficiency study."""

import argparse
from contextlib import ExitStack
import importlib.util
import json
import os
from pathlib import Path

from sufficiency import (
    EXPERIMENT, FROZEN, METHOD, REPORT_SCHEMA, InputLimitExceeded, approval_template, check_approval,
    demonstrations, frozen_study, messages, prepare, root_at,
)
from protocol import (
    CELLS, PILOT_LEVEL, PILOT_PROJECT, cell_key, digest, external_path, file_hash,
    read_json, study_id, write_json,
)
from prepare_data import Tokenizer, partition
from cost_control import control_requests
from failure_evidence import error_details, record_failure
from ledger import SufficiencyLedger

# The shared batch helpers intentionally resolve the original run_experiment.
spec = importlib.util.spec_from_file_location("sufficiency_runner_core", FROZEN / "run_experiment.py")
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)

STAGES = ("plan", "prepare", "preflight", "smoke", "validate", "seal", "test", "report", "reconcile")


def smoke(root, config, ledger, backend, tokenizer=None):
    from unstable_model.evaluation import calculate_metrics

    core.require_open(root, ledger)
    approval = core.authorized(root, config, ledger)["approval"]
    tokenizer = tokenizer or Tokenizer(config["model"])
    examples = demonstrations(root)[cell_key(PILOT_PROJECT, PILOT_LEVEL, "text")]["examples"]
    for i, text in enumerate(("Add a settings page.", "requirement " * config["text_tokens"])):
        # Match the original text budget even for the synthetic capability probe.
        text = tokenizer.decode(tokenizer.encode(text)[:config["text_tokens"]])
        prompt, count = messages(PILOT_PROJECT, text, None, tokenizer, config, examples)
        core.score_once(root, config, ledger, backend, approval["base_deployment"],
                        f"smoke-{i}", prompt, count)
    records, rows = partition(root, cell_key(PILOT_PROJECT, PILOT_LEVEL, "text"), "validation")
    scores = []
    for i, (record, row) in enumerate(zip(records[:20], rows[:20])):
        result = core.score_once(root, config, ledger, backend, approval["base_deployment"],
                                 f"base-control-{i}", record["messages"], row["input_tokens"])
        scores.append(result["score"])
    write_json(root / "base_control.json", {
        "experiment_schema": EXPERIMENT, "diagnostic_only": True,
        "row_ids": [row["row_id"] for row in rows[:20]], "scores": scores,
        "metrics": calculate_metrics([row["label"] for row in rows[:20]], scores, .5),
    })
    value = {"study_sha256": digest(read_json(root / "study.json")),
             "base_deployment": approval["base_deployment"]}
    ledger.record(study_id(root), "smoke", value)
    write_json(root / "smoke.json", value)


def evaluate(root, config, ledger, backend, split):
    from prompt_inference import complete_cell

    if split not in ("validation", "test"):
        raise ValueError("Only validation and test are evaluation stages.")
    evidence = core.authorized(root, config, ledger)
    run = study_id(root)
    smoke_value = ledger.artifact(run, "smoke")
    if not smoke_value or smoke_value["study_sha256"] != digest(read_json(root / "study.json")):
        raise ValueError("Matching sufficiency smoke evidence is required.")
    if split == "validation":
        core.require_open(root, ledger)
        cells, selections = core.allowed_cells(evidence), None
    else:
        if evidence["approval"]["scope"] != "full":
            raise ValueError("Final test requires full-study approval.")
        cells, selections = CELLS, core.sealed_cells(root, ledger)
    examples = demonstrations(root)
    for cell in cells:
        key = cell_key(*cell)
        selection = selections[key] if selections else None
        reference = {
            "model_id": evidence["approval"]["model"], "deployment": evidence["approval"]["base_deployment"],
            "method": METHOD, "demonstrations_sha256": digest(examples[key]),
        }
        if selection and selection["model_reference"] != reference:
            raise ValueError("Model or demonstrations differ from the sealed selection.")
        saved = ledger.artifact(run, split + "-" + key)
        if saved is not None:
            if saved["model_reference"] != reference:
                raise ValueError("Completed cell uses different demonstrations.")
            directory = root / ("validation" if split == "validation" else "final") / key
            output = directory / ("validation.json" if split == "validation" else "metrics.json")
            if output.exists() and read_json(output) != saved:
                raise ValueError("Evaluation cache differs from cloud evidence.")
            write_json(output, saved)
            continue
        records, rows = partition(root, key, split)
        if len({row["label"] for row in rows}) != 2:
            raise ValueError("Both classes are required.")
        for start in range(0, len(rows), config["batch_rows"]):
            name = f"batch-{split}-{key}-{start}"
            if ledger.artifact(run, name) is not None:
                continue
            end = min(start + config["batch_rows"], len(rows))
            scores = []
            for index in range(start, end):
                result = core.score_once(root, config, ledger, backend, reference["deployment"],
                                         f"{split}-{key}-{index}", records[index]["messages"],
                                         rows[index]["input_tokens"], model=reference["model_id"])
                scores.append({"row_id": rows[index]["row_id"], "label": rows[index]["label"], **result})
            path = root / "batches" / split / key / f"{start}.json"
            write_json(path, scores)
            ledger.record(run, name, {"start": start, "rows": end - start, "scores_sha256": file_hash(path)})
            if end == len(rows):
                complete_cell(root, config, ledger, key, split, records, rows, reference, selection)
            return {"split": split, "cell": key, "batch_start": start, "batch_rows": end - start,
                    "cell_complete": end == len(rows)}
        complete_cell(root, config, ledger, key, split, records, rows, reference, selection)
        return {"split": split, "cell": key, "cell_complete": True, "recovered_from_receipts": True}
    return {"split": split, "scope_complete": True}


def report(root, ledger):
    value = core.report(root, ledger, root / "private-core-report.json")
    source = read_json(root / "study.json")["source"]
    old = read_json(Path(source["root"]) / "recovery/llm_report.json")
    previous = {cell_key(c["project"], c["level"], c["variant"]): c for c in old["cells"]}
    comparisons = []
    for cell in value["cells"]:
        if cell["status"] != "complete":
            continue
        before = previous[cell_key(cell["project"], cell["level"], cell["variant"])]
        if any(cell["test"][k] != before["test"][k] for k in ("row_count", "positive_count")):
            raise ValueError("New and previous report populations differ.")
        comparisons.append({
            "project": cell["project"], "level": cell["level"], "variant": cell["variant"],
            "previous": {k: before["test"][k] for k in ("auc_prc", "average_precision", "roc_auc")},
            "difference": {
                k: cell["test"][k] - before["test"][k]
                for k in ("auc_prc", "average_precision", "roc_auc")
            },
        })
    value.update(
        schema=REPORT_SCHEMA, experiment_schema=EXPERIMENT, method=METHOD,
        objective="story detail sufficiency as a proxy for observed K-based instability",
        exploratory=True, prior_report_sha256=source["report_sha256"],
        prompt_comparison=comparisons,
    )
    value["limitations"] = [
        item for item in value["limitations"]
        if item != "Zero-shot system/user prompting; no LLM training or fine-tuning."
    ] + [
        "Ten training demonstrations in System, target in User; no LLM training or fine-tuning.",
        "Follow-up designed after examining the previous holdout; not fresh independent confirmation.",
        "Insufficient detail is a predictor, not a manually annotated sufficiency ground truth.",
        "K is absent as explicit prompt metadata but determines training-example labels and selection.",
        "Thresholds remain validation-selected separately for each K; each cell is scored separately.",
        "Prompt-to-prompt differences are descriptive, without paired uncertainty intervals.",
        "The old HTTP-500 recovery approval does not authorize retries in this new study.",
    ]
    write_json(root / "llm_report.json", value)
    return {"complete": value["complete"], "passed": value["passed"], "exploratory": True}


def main(argv=None):
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=STAGES)
    parser.add_argument("--storage", default=str(Path.home() / "master-openai"))
    parser.add_argument("--run-id", default="openai-sufficiency-01")
    parser.add_argument("--source-run", type=Path)
    parser.add_argument("--approval", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--execute-approved-stage", action="store_true")
    args = parser.parse_args(argv)
    if args.stage == "plan":
        from input_plan import plan, summary

        if args.approval or args.execute_approved_stage:
            parser.error("Sizing is offline and cannot use execution approval flags.")
        storage = external_path(args.storage)
        output = external_path(args.output or storage / "openai-sufficiency-input-plan.json")
        if output.exists():
            parser.error("Keep the existing plan; select a new --output path.")
        source = args.source_run or storage / "openai-runs/openai-prompt-01"
        value = plan(source)
        write_json(output, value)
        print(json.dumps({**summary(value), "report": str(output)}, indent=2))
        return
    if args.output:
        parser.error("--output is only available for offline plan.")
    if args.stage == "prepare":
        if args.approval or args.execute_approved_stage:
            parser.error("Preparation is offline and cannot use an execution approval.")
        source = args.source_run or external_path(args.storage) / "openai-runs/openai-prompt-01"
        root = prepare(args.storage, args.run_id, source)
        path = root / "approval.template.json"
        if not path.exists():
            write_json(path, approval_template(root))
        print(json.dumps({"prepared": True, "cloud_access": False, "root": str(root),
                          "study_sha256": digest(read_json(root / "study.json"))}))
        return
    if not args.execute_approved_stage:
        parser.error("This stage needs renewed approvals and explicit --execute-approved-stage.")
    if args.source_run or (args.approval and args.stage != "preflight"):
        parser.error("--source-run is plan/prepare-only; --approval is preflight-only.")
    root = root_at(args.storage, args.run_id)
    config = frozen_study(root)
    examples = demonstrations(root)
    approval = None
    if args.stage == "preflight":
        if not args.approval:
            parser.error("Supply the separately reviewed private --approval.")
        approval = read_json(external_path(args.approval))
    else:
        approval = read_json(root / "authorization.json")["approval"]
    check_approval(approval, digest(read_json(root / "study.json")), config)
    ledger = None
    status_path = root / "status" / f"{args.stage}.json"
    write_json(status_path, {"status": "running", "stage": args.stage})
    try:
        with ExitStack() as stack:
            ledger = SufficiencyLedger.configured()
            ledger.bind(root, config)
            stack.callback(ledger.close)
            stack.enter_context(ledger.session(requests=lambda: control_requests(
                args.stage, read_json(root / "prepared.json"), config, approval["scope"],
            )))
            if args.stage == "report":
                core.authorized(root, config, ledger)
                result = report(root, ledger)
            elif args.stage == "seal":
                core.authorized(root, config, ledger)
                core.seal(root, ledger)
                result = {"sealed": True}
            elif args.stage == "reconcile":
                result = core.reconcile(root, config, ledger, None)
            else:
                from backend import SufficiencyBackend

                if args.stage != "preflight":
                    approval = core.authorized(root, config, ledger)["approval"]
                backend = SufficiencyBackend(approval, config, examples)
                stack.callback(backend.close)
                backend.guard = ledger.guard_remote
                if args.stage == "preflight":
                    core.preflight(root, config, approval, ledger, backend)
                    result = {"authorized_scope": approval["scope"]}
                elif args.stage == "smoke":
                    smoke(root, config, ledger, backend)
                    result = {"smoke": "succeeded"}
                else:
                    result = evaluate(root, config, ledger, backend,
                                      "validation" if args.stage == "validate" else "test")
        write_json(status_path, {"status": "succeeded", "result": result})
        print(json.dumps(result, indent=2))
    except Exception as error:
        evidence = record_failure(root, args.stage, error,
                                  ledger.failed_dispatch if ledger is not None else None)
        write_json(status_path, {"status": "failed", **error_details(error), "failure_evidence": evidence})
        raise


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        detail = str(error) if isinstance(error, InputLimitExceeded) else type(error).__name__
        print(f"SUFFICIENCY STOPPED: {detail}; keep private evidence and reservations.")
        raise SystemExit(1) from None
