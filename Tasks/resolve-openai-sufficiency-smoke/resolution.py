"""Separately approved, Storage-only acceptance of the exact attempt-2 diagnostic."""

import argparse
from contextlib import closing
from datetime import datetime
import json
import math
import os
from pathlib import Path
import re
import sys

TASK = Path(__file__).resolve().parent
sys.path.insert(0, str(TASK.parent / "recover-openai-sufficiency-smoke"))
import one_shot
from cloud_control import ControlError, unexpired
from cost_control import money
from inspection_auth import InspectionStore
from inspect_failure import InspectionBudget
from ledger import SufficiencyLedger
from protocol import digest, external_path, file_hash, read_json

SCHEMA = "sufficiency-smoke-resolution-review-v1"
CHECKS = (
    "old_workers_stopped", "exact_diagnostic_accepted_without_score_selection",
    "original_unknown_and_all_reservations_retained", "known_plus_unknown_accounting_reviewed",
    "receipt_fences_and_pending_resolution_approved", "no_further_inference_authorized",
    "current_credit_and_storage_reviewed",
)


def implementation_hash():
    return digest({path.name: file_hash(path) for path in sorted(TASK.glob("*.py"))})


def evidence(root, diagnostic_review):
    original = read_json(diagnostic_review)
    context = one_shot.validate_review(root, original)
    config = context[0]
    directory = root / "jobs/diagnose-smoke"
    paths = {name: directory / (name + ".json") for name in (
        "worker-status", "diagnostic", "local-diagnostic", "response-summary",
    )}
    values = {name: read_json(path) for name, path in paths.items()}
    status, value = values["worker-status"], values["diagnostic"]
    captured, response = value["captured"], value["valid_response"]
    expected_capture = {
        "run": original["run"], "operation": "smoke-0", "attempt": 2,
        "epoch": captured["epoch"], "request_sha256": original["request_sha256"],
        "review_sha256": digest(original),
    }
    if (status.get("status") != "succeeded" or status.get("diagnostic_recorded") is not True
            or status.get("scorable_response") is not True or status.get("pending_retained") is not True
            or status.get("completes_smoke") is not False
            or value.get("schema") != "sufficiency-one-shot-diagnostic-v1"
            or value.get("phase") != "scoring" or value.get("reason") != "valid_diagnostic_response"
            or value.get("scorable_response") is not True or type(value.get("model_requests")) is not int
            or value["model_requests"] != 1 or value.get("original_outcome") != "UNKNOWN"
            or value.get("pending_retained") is not True or value.get("completes_smoke") is not False
            or value.get("authorizes_continuation") is not False
            or type(value.get("storage_requests_used")) is not int
            or not 0 <= value["storage_requests_used"] <= 100
            or captured != expected_capture or not isinstance(captured["epoch"], str) or not captured["epoch"]):
        raise ControlError("Only the exact successful one-shot diagnostic may be reviewed.")
    cloud_value = {key: item for key, item in value.items() if key != "storage_requests_used"}
    if (values["local-diagnostic"] != cloud_value
            or values["response-summary"] != {"captured": captured, "summary": value["response_summary"]}):
        raise ControlError("Local diagnostic evidence is inconsistent.")
    if (not isinstance(response, dict)
            or set(response) != {"score", "usage", "response_model", "request_id_sha256"}
            or type(response["score"]) not in (int, float) or not math.isfinite(response["score"])
            or not 0 <= response["score"] <= 1 or response["response_model"] != config["model"]
            or not isinstance(response["request_id_sha256"], str)
            or not re.fullmatch(r"[a-f0-9]{64}", response["request_id_sha256"])):
        raise ControlError("Diagnostic result or model identity is invalid.")
    usage, summary = response["usage"], value["response_summary"]
    if (set(usage) != {"input_tokens", "output_tokens"}
            or any(type(item) is not int or item < 0 for item in usage.values())
            or usage["output_tokens"] != 1 or summary != {
                "choice_count": 1, "finish_reason": summary["finish_reason"], "refused": False,
                "binary_output": True, "scored_token_count": 1, "both_class_logprobs": True,
                "invalid_class_logprobs": False, "conflicting_class_logprobs": False,
                "usage": usage, "expected_model_match": True,
            } or summary["finish_reason"] not in ("stop", "length")):
        raise ControlError("Diagnostic scoring or usage evidence is invalid.")
    return original, context, cloud_value, {name: file_hash(path) for name, path in paths.items()}


def accounting(original, diagnostic, approval):
    usage, rates = diagnostic["valid_response"]["usage"], approval["rates"]
    known = (money(usage["input_tokens"]) * money(rates["input_per_million"])
             + money(usage["output_tokens"]) * money(rates["output_per_million"])) / 1000000
    reserved = money(original["operation_reservation_retained_usd"])
    if reserved <= 0:
        raise ControlError("The original three-attempt reservation must be positive.")
    unknown = reserved / 3
    return {
        "known_actual_usd": str(known), "unknown_attempt_bound_usd": str(unknown),
        "accounted_bound_usd": str(known + unknown), "reserved_usd_retained": str(reserved),
        "unreserved_excess_usd": str(max(money(0), known + unknown - reserved)),
        "actual_complete": False, "original_outcome": "UNKNOWN",
    }


def template(root, diagnostic_review):
    original, context, diagnostic, hashes = evidence(root, diagnostic_review)
    return {
        "schema": SCHEMA, "diagnostic_review_path": str(diagnostic_review),
        "diagnostic_review_sha256": file_hash(diagnostic_review),
        "diagnostic_sha256": digest(diagnostic), "evidence_sha256": hashes,
        "captured": diagnostic["captured"], "implementation_sha256": implementation_hash(),
        "accounting": accounting(original, diagnostic, context[1]["approval"]),
        "storage_request_limit": 100, "storage_sessions": 1, "model_requests": 0,
        "remaining_credit_usd": "0", "expires_at": "", "execution_approved": False,
        "checks": {key: False for key in CHECKS},
    }


def validate_review(root, review):
    path = external_path(review["diagnostic_review_path"])
    expected = template(root, path)
    editable = {"remaining_credit_usd", "expires_at", "execution_approved", "checks"}
    if (set(review) != set(expected)
            or any(review[key] != value for key, value in expected.items() if key not in editable)
            or review["execution_approved"] is not True or set(review["checks"]) != set(CHECKS)
            or any(review["checks"][key] is not True for key in CHECKS)):
        raise ControlError("A separate exact resolution review is required.")
    unexpired(review["expires_at"])
    original, context, diagnostic, _ = evidence(root, path)
    expiry = datetime.fromisoformat(review["expires_at"].replace("Z", "+00:00"))
    if expiry > datetime.fromisoformat(original["expires_at"].replace("Z", "+00:00")):
        raise ControlError("Resolution cannot outlive the diagnostic's existing approvals.")
    if money(review["remaining_credit_usd"]) <= money(context[0]["credit_reserve_usd"]):
        raise ControlError("Current reviewed credit is required.")
    return original, context, diagnostic


def queued_review(root, path):
    validate_review(root, read_json(path))
    return {"review_path": str(path), "review_sha256": file_hash(path),
            "implementation_sha256": implementation_hash()}


def rows_at(ledger, original):
    run, name = original["run"], original["operation"]
    keys = {
        "allocation": "run:" + run, "operation": ledger._key(run, name),
        "attempt": ledger._key(run, name + ":1", "attempt"),
        "attempt2": ledger._key(run, name + ":2", "attempt"),
        "receipt1": ledger._key(run, name + ":1", "receipt"),
        "receipt2": ledger._key(run, name + ":2", "receipt"),
        "unknown": ledger._key(run, name + ":1", "sufficiency-smoke-unknown"),
        "grant": ledger._key(run, name + ":2", "sufficiency-smoke-grant"),
        "diagnostic": ledger._key(run, name + ":2", "sufficiency-smoke-diagnostic"),
        "resolution": ledger._key(run, name + ":2", "sufficiency-smoke-resolution"),
        "renewal": "sufficiency-storage-renewal:" + original["storage_approval_sha256"],
    }
    return keys, {kind: ledger.store.get(key) for kind, key in keys.items()}


def validate_rows(ledger, state, rows, original, context, diagnostic, review):
    config, authorization, _, _, _, _, _, inspection = context
    snapshot = inspection["review_template"]
    for kind in ("allocation", "attempt", "renewal"):
        value, etag = rows[kind]
        if snapshot["entities"][kind] != {"sha256": digest(value), "etag_sha256": digest(etag)}:
            raise ControlError("Original allocation, attempt or renewal changed.")
    captured = diagnostic["captured"]
    note, grant, operation = (rows[kind][0] for kind in ("unknown", "grant", "operation"))
    if (any(rows[kind][0] is not None for kind in ("receipt1", "receipt2", "resolution"))
            or rows["diagnostic"][0] != diagnostic
            or grant != {"captured": captured, "review": original}
            or note != {
                "outcome": "UNKNOWN", "operation_before": note["operation_before"],
                "attempt_sha256": snapshot["entities"]["attempt"]["sha256"],
                "failure_sha256": original["failure_sha256"], "review_sha256": digest(original),
            }
            or digest(note["operation_before"]) != snapshot["entities"]["operation"]["sha256"]
            or operation != {**note["operation_before"], "attempts": 2, "epoch": captured["epoch"]}
            or rows["attempt2"][0] != {
                "status": "dispatched", "epoch": captured["epoch"],
                "request_sha256": original["request_sha256"],
            }):
        raise ControlError("Diagnostic, grant, UNKNOWN or receipt state conflicts; do not resolve.")
    reserve = money(state["storage"]["reserve_usd"])
    allocation = rows["allocation"][0]
    credit = min(money(review["remaining_credit_usd"]), ledger.remaining_credit,
                 money(authorization["approval"]["remaining_credit_usd"]))
    if (state["pending"] != [original["run"], original["operation"]] or state["breached"]
            or digest(state.get("quarantine")) != snapshot["training_quarantine_sha256"]
            or state.get("inference_recovery") != snapshot["historical_recovery_sha256"]
            or money(state["total"]) + reserve != money(inspection["cumulative_reserved_usd"])
            or money(state["pilot_total"]) + reserve != money(inspection["pilot_reserved_including_storage_usd"])
            or money(state["total"]) + reserve > money(config["total_limit_usd"])
            or money(state["pilot_total"]) + reserve > money(config["pilot_limit_usd"])
            or money(state["total"]) + reserve + money(config["credit_reserve_usd"]) > credit
            or money(operation["reserved"]) != money(original["operation_reservation_retained_usd"])
            or not money(operation["reserved"]) <= money(allocation["used"]) <= money(allocation["reserved"])):
        raise ControlError("Pending state, quarantine or financial bounds prevent resolution.")


def resolve(ledger, original, context, diagnostic, review, previous_rows):
    unexpired(review["expires_at"])
    ledger.renew()
    state, etag = ledger._root()
    keys, rows = rows_at(ledger, original)
    if state["epoch"] != ledger.owner or rows != previous_rows:
        raise ControlError("Resolution snapshot changed or ownership was lost.")
    validate_rows(ledger, state, rows, original, context, diagnostic, review)
    ledger.store.budget.require_tail(20)
    costs = accounting(original, diagnostic, context[1]["approval"])
    breached = money(costs["unreserved_excess_usd"]) > 0
    result = {**diagnostic["valid_response"], "attempts": 2,
              "unknown_attempts": [1], "actual_complete": False,
              "resolution_review_sha256": digest(review)}
    operation = {**rows["operation"][0], "actual_usd": costs["known_actual_usd"],
                 "unknown_attempt_bound_usd": costs["unknown_attempt_bound_usd"],
                 "accounted_bound_usd": costs["accounted_bound_usd"],
                 "unreserved_excess_usd": costs["unreserved_excess_usd"], "actual_complete": False}
    value = {
        "schema": "sufficiency-smoke-resolution-v1", "captured": diagnostic["captured"],
        "review_sha256": digest(review), "diagnostic_sha256": digest(diagnostic),
        "accounting": costs, "breached": breached, "resolved": not breached,
        "pending_retained": breached, "completes_smoke": False, "authorizes_continuation": False,
        "model_calls": 0, "resolution_epoch": ledger.owner,
    }
    changes = [
        (keys["resolution"], {"review": review, "value": value}, None),
        (keys["operation"], operation, rows["operation"][1]),
    ]
    # Create-only fences atomically reject receipts racing the final snapshot.
    # They deliberately cannot be consumed by the historical receipt reconciler.
    for number in (1, 2):
        changes.append((keys["receipt" + str(number)], {
            "schema": "sufficiency-smoke-receipt-fence-v1", "request_sha256": None,
            "blocked_request_sha256": original["request_sha256"], "attempt": number,
            "resolution_review_sha256": digest(review),
        }, None))
    if breached:
        state["breached"] = True
    else:
        operation.update(status="succeeded", result=result)
        changes.append((keys["attempt2"], {
            **rows["attempt2"][0], "status": "succeeded", "result_sha256": digest(result),
        }, rows["attempt2"][1]))
        state["pending"] = None
    ledger._write(state, etag, changes)
    return value


def execute(root, review, directory):
    original, context, diagnostic = validate_review(root, review)
    config, _, binding, storage = context[:4]
    with closing(InspectionStore(binding, InspectionBudget(100))) as store:
        store.authenticate()
        store.verify_account()
        ledger = SufficiencyLedger(store, binding, storage["storage"],
                                   remaining_credit=storage["remaining_credit_usd"],
                                   access_expires=storage["expires_at"])
        ledger.bind(root, config)
        snapshot = {}

        def envelope():
            state, _ = ledger._root()
            if state["epoch"] != diagnostic["captured"]["epoch"]:
                raise ControlError("Authority changed after the diagnostic; new review is required.")
            _, rows = rows_at(ledger, original)
            validate_rows(ledger, state, rows, original, context, diagnostic, review)
            snapshot.update(rows)
            return 100

        with ledger.session(requests=envelope):
            value = resolve(ledger, original, context, diagnostic, review, snapshot)
    value["storage_requests_used"] = store.budget.used
    one_shot.exclusive_json(directory / "resolution.json", value)
    if value["breached"]:
        raise ControlError("Known plus UNKNOWN bound exceeded the reservation; pending and breach retained.")
    return value


def main(argv=None):
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("template", "resolve"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--diagnostic-review", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--review", type=Path)
    parser.add_argument("--execute-approved-resolution", action="store_true")
    args = parser.parse_args(argv)
    root = external_path(args.root)
    if args.stage == "template":
        if not args.diagnostic_review or not args.output or args.review or args.execute_approved_resolution:
            parser.error("Offline template requires --diagnostic-review and --output only.")
        output = external_path(args.output)
        if output == root or root in output.parents:
            parser.error("Write the private template outside the preserved run.")
        one_shot.exclusive_json(output, template(root, external_path(args.diagnostic_review)))
        print(json.dumps({"cloud_access": False, "checks_default_false": True}))
        return
    if not args.review or not args.execute_approved_resolution or args.diagnostic_review or args.output:
        parser.error("Resolution requires its separate --review and --execute-approved-resolution.")
    review = read_json(external_path(args.review))
    validate_review(root, review)
    directory = root / "jobs/resolve-smoke"
    directory.mkdir(parents=True, exist_ok=True)
    one_shot.exclusive_json(directory / "resolution.started", {"review_sha256": digest(review)})
    result = execute(root, review, directory)
    print(json.dumps({key: result[key] for key in (
        "resolved", "breached", "model_calls", "pending_retained", "completes_smoke",
        "authorizes_continuation", "storage_requests_used",
    )}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("RESOLUTION STOPPED; preserve evidence and do not retry.", file=sys.stderr)
        raise SystemExit(1) from None
