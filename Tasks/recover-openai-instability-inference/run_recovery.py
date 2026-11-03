#!/usr/bin/env python3
"""Explicit plan/activation, one sealed test batch, or an amended final report."""

import argparse
from contextlib import closing
import json
import os
from pathlib import Path

from recovery import (
    CHECKS, REPORT_SCHEMA, RecoveryBackend, RecoveryLedger,
    implementation_hash,
)
from cloud_control import ControlError
from failure_evidence import error_details, record_failure
from protocol import (
    CELLS, cell_key, digest, external_path, file_hash, read_json,
    signature, slug, study_id, write_json,
)
import run_experiment as frozen


def frozen_study(root):
    study = read_json(root / "study.json")
    if signature(study["config"]) != study:
        raise ControlError("Frozen study source, packages, configuration, or data contract changed.")
    return study["config"]


def remaining_batches(root, ledger, config):
    prepared = read_json(root / "prepared.json")
    count = 0
    for cell in CELLS:
        key = cell_key(*cell)
        if ledger.artifact(study_id(root), "test-" + key) is not None:
            continue
        rows = prepared["entries"][key]["partitions"]["test"]["rows"]
        missing = sum(
            ledger.artifact(study_id(root), f"batch-test-{key}-{start}") is None
            for start in range(0, rows, config["batch_rows"])
        )
        # A completed last batch may still need receipt-based metric assembly.
        count += max(1, missing)
    return count


def require_tail_capacity(root, ledger, config):
    count = remaining_batches(root, ledger, config)
    ledger.require_capacity({
        "requests": (count + 1) * ledger.plan["session_requests"],
        "sessions": count + 1, "max_session_requests": ledger.plan["session_requests"],
    })
    return count


def amended_report(root, ledger, output):
    original = frozen.report(root, ledger, root / "recovery/frozen-report.json")
    audit = ledger.audit(root)
    if audit["pending"] or audit["seal_sha256"] != ledger.review["seal_sha256"]:
        raise ControlError("Recovery audit is unresolved or differs from the original seal.")
    value = {
        **original, "schema": REPORT_SCHEMA,
        "original_report_sha256": digest(original), "execution_recovery": audit,
        "limitations": original["limitations"] + [
            "Execution policy amended: approved HTTP-500 retries can duplicate provider charges.",
            "Unknown attempts retain their full bounds; actual costs remain incomplete.",
        ],
    }
    write_json(output, value)
    return {"complete": value["complete"], "passed": value["passed"],
            "execution_policy_amended": True, "report": str(output)}


def exclusive_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(value, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())


def approve_local(root, template, output, evidence, expires):
    """Local only: the flags on this command represent separate human approval."""
    config = frozen_study(root)
    if template["implementation_sha256"] != implementation_hash():
        raise ControlError("Recovery code changed after inspection.")
    failure = read_json(evidence)
    dispatch = failure.get("dispatch", {})
    if (failure.get("study_sha256") != template["study_sha256"]
            or any(dispatch.get(key) != template[key] for key in (
                "run", "operation", "attempt", "request_sha256"
            ))):
        raise ControlError("Private failure record differs from the inspected dispatch.")
    # The legacy error wrapper lost the status. The operator must independently
    # review the sanitized HTTP-500 log before explicitly approving this command.
    approval = {
        **template, "http_status": 500, "evidence_sha256": file_hash(evidence),
        "expires_at": expires, "checks": {key: True for key in CHECKS},
    }
    from cloud_control import unexpired
    unexpired(expires)
    if config["request_attempts"] != approval["max_attempts"]:
        raise ControlError("The original attempt ceiling cannot change.")
    exclusive_json(output, approval)
    return {"review_sha256": digest(approval), "cloud_access": False}


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("plan", "approve-local", "activate", "test", "report"))
    parser.add_argument("--storage", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--review", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--expires-at")
    parser.add_argument("--storage-inspection-approved", action="store_true")
    parser.add_argument("--accept-unknown-outcome-retries", action="store_true")
    args = parser.parse_args()
    root = external_path(args.storage) / "openai-runs" / slug(args.run_id)
    config = frozen_study(root)
    output = external_path(args.output) if args.output else root / "recovery/llm_report.json"
    review = read_json(external_path(args.review)) if args.review else None
    if args.stage in ("plan", "approve-local", "activate") and not args.output:
        parser.error("Administrative stages require an explicit private --output.")
    if args.stage == "approve-local":
        if (review is None or not args.evidence or not args.expires_at
                or not args.accept_unknown_outcome_retries):
            parser.error("Explicit consent, --review template, --evidence, and --expires-at are required.")
        print(json.dumps(approve_local(root, review, output, external_path(args.evidence), args.expires_at)))
        return
    if args.stage == "plan" and not args.storage_inspection_approved:
        parser.error("Plan consumes one bounded storage session; explicit approval is required.")
    if args.stage != "plan" and review is None:
        parser.error("Supply the separately approved private --review.")
    if args.stage in ("plan", "activate") and output.exists():
        raise ControlError("Refusing to overwrite administrative evidence.")
    status = root / "recovery/status" / (args.stage + ".json")
    write_json(status, {"status": "running", "stage": args.stage})
    backend = None
    ledger = None
    try:
        with closing(RecoveryLedger.configured()) as ledger:
            ledger.review = review
            ledger.allow_legacy = args.stage in ("plan", "activate")
            requests = 1000 if args.stage in ("plan", "activate") else ledger.plan["session_requests"]
            with ledger.session(requests=lambda: requests):
                if args.stage == "plan":
                    result = ledger.plan_review(root)
                    result["remaining_test_batches"] = require_tail_capacity(root, ledger, config)
                    exclusive_json(output, result)
                    result = {"template": str(output), "checks_default_false": True,
                              "remaining_test_batches": result["remaining_test_batches"]}
                elif args.stage == "activate":
                    remaining = require_tail_capacity(root, ledger, config)
                    result = ledger.activate(root, review)
                    result["remaining_test_batches"] = remaining
                    exclusive_json(output, result)
                else:
                    ledger.validate_review(root, review)
                    frozen.authorized(root, config, ledger)
                    frozen.sealed_cells(root, ledger)
                    if args.stage == "test":
                        backend = RecoveryBackend(ledger.allocation(study_id(root))["approval"], config)
                        backend.guard = ledger.guard_remote
                        result = frozen.evaluate(root, config, ledger, backend, "test")
                    else:
                        result = amended_report(root, ledger, output)
            write_json(status, {"status": "succeeded", "result": result})
            print(json.dumps(result, indent=2))
    except Exception as error:
        evidence = record_failure(root, "recovery-" + args.stage, error,
                                  ledger.failed_dispatch if ledger is not None else None)
        write_json(status, {"status": "failed", **error_details(error), "failure_evidence": evidence})
        raise
    finally:
        if backend is not None:
            backend.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Never expose SDK bodies, request payloads, or credentials in logs.
        detail = str(error) if isinstance(error, (ControlError, FileNotFoundError)) else type(error).__name__
        print("RECOVERY FAILED: " + detail)
        raise SystemExit(1) from None
