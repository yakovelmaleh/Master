"""Separately reviewed attempt-2 diagnostics; no retry loop, receipt, or completion."""

import argparse
from contextlib import ExitStack
from datetime import datetime
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parent))
from diagnostics import REASONS, audit, response_summary
from backend import SufficiencyBackend
from cloud_control import ControlError, access_at, binding_at, unexpired
from cost_control import money
from inspection_auth import InspectionStore
from inspect_failure import InspectionBudget
from ledger import SufficiencyLedger
from protocol import digest, external_path, file_hash, read_json
from renew_storage import validate as validate_storage
from sufficiency import budget_limits, check_approval

TASK = Path(__file__).resolve().parent
SCHEMA = "sufficiency-one-shot-review-v1"
CHECKS = (
    "old_workers_stopped", "unknown_attempt_and_reservations_retained",
    "possible_duplicate_charge_accepted", "execution_policy_amendment_approved",
    "same_request_and_one_new_attempt_only", "diagnostic_only_no_completion",
    "current_credit_and_storage_reviewed",
)


def implementation_hash():
    return digest({path.name: file_hash(path) for path in sorted(TASK.glob("*.py"))})


def local_context(root, failure, inspection):
    config, model, examples, pair, context = audit(root, failure)
    binding, authorization = binding_at(), read_json(root / "authorization.json")
    storage = access_at(binding)
    validate_storage(storage, binding, root)
    check_approval(model, context["study_sha256"], config)
    if (model["authority_sha256"] != digest(binding) or model["scope"] != "pilot"
            or money(model["storage_reserve_usd"]) != money(storage["storage"]["reserve_usd"])
            or config["request_attempts"] != 3):
        raise ControlError("Exact pilot authority and original three-attempt policy required.")
    if root not in inspection.parents or inspection.name != "inspection.json":
        raise ControlError("Use the preserved inspection in this run.")
    report, status = read_json(inspection), read_json(inspection.parent / "worker-status.json")
    if (status.get("status") != "succeeded" or status.get("inspected") is not True
            or report.get("schema") != "sufficiency-failure-inspection-v1"
            or report.get("receipt_present") is not False or report.get("breached") is not False
            or report.get("pending_matches_failure") is not True or report.get("attempt") != 1
            or report.get("authorizes_inference") is not False
            or report.get("historical_outcome") != "UNKNOWN"
            or any(report["review_template"].get(key) != value for key, value in context.items())):
        raise ControlError("Inspection must identify the exact unresolved attempt without a receipt.")
    original = report["review_template"]
    if (original["authority_sha256"] != digest(binding)
            or original["model_authorization_sha256"] != digest(authorization)
            or original["storage_approval_sha256"] != digest(storage)
            or original["prepared_sha256"] != authorization["prepared_sha256"]):
        raise ControlError("Approvals or preparation changed after inspection.")
    return config, authorization, binding, storage, examples, pair, context, report


def template(root, failure, inspection):
    config, authorization, binding, storage, _, _, context, report = local_context(root, failure, inspection)
    return {
        "schema": SCHEMA, **context, "authority_sha256": digest(binding),
        "failure_path": str(failure), "inspection_path": str(inspection),
        "inspection_sha256": file_hash(inspection),
        "inspection_status_sha256": file_hash(inspection.parent / "worker-status.json"),
        "model_authorization_sha256": digest(authorization),
        "storage_approval_sha256": digest(storage),
        "diagnostic_implementation_sha256": implementation_hash(),
        "budget_limits": budget_limits(config), "target_attempt": 2,
        "max_new_model_requests": 1, "storage_request_limit": 100, "storage_sessions": 1,
        "operation_reservation_retained_usd": report["operation_reserved_usd"],
        "remaining_credit_usd": "0", "expires_at": "", "execution_approved": False,
        "checks": {key: False for key in CHECKS},
    }


def validate_review(root, review):
    failure, inspection = external_path(review["failure_path"]), external_path(review["inspection_path"])
    expected = template(root, failure, inspection)
    editable = {"remaining_credit_usd", "expires_at", "execution_approved", "checks"}
    if (set(review) != set(expected)
            or any(review[key] != value for key, value in expected.items() if key not in editable)
            or review["execution_approved"] is not True
            or set(review["checks"]) != set(CHECKS)
            or any(review["checks"][key] is not True for key in CHECKS)):
        raise ControlError("Exact, separately approved one-shot review is required.")
    unexpired(review["expires_at"])
    data = local_context(root, failure, inspection)
    config, authorization, _, storage = data[:4]
    expiry = datetime.fromisoformat(review["expires_at"].replace("Z", "+00:00"))
    if any(expiry > datetime.fromisoformat(value.replace("Z", "+00:00")) for value in (
        authorization["approval"]["expires_at"], storage["expires_at"], storage["storage"]["retention_until"],
    )):
        raise ControlError("Diagnostic approval cannot outlive existing approvals.")
    if money(review["remaining_credit_usd"]) <= money(config["credit_reserve_usd"]):
        raise ControlError("Current reviewed credit is required.")
    return data


def queued_review(root, path):
    review = read_json(path)
    validate_review(root, review)
    return {"review_path": str(path), "review_sha256": file_hash(path),
            "implementation_sha256": implementation_hash()}


def snapshot_rows(ledger, report):
    context = report["review_template"]
    run, name = context["run"], context["operation"]
    keys = {
        "allocation": "run:" + run, "operation": ledger._key(run, name),
        "attempt": ledger._key(run, name + ":1", "attempt"),
        "receipt": ledger._key(run, name + ":1", "receipt"),
        "renewal": "sufficiency-storage-renewal:" + context["storage_approval_sha256"],
    }
    rows = {kind: ledger.store.get(key) for kind, key in keys.items()}
    for kind, (value, etag) in rows.items():
        if context["entities"][kind] != {"sha256": digest(value), "etag_sha256": digest(etag)}:
            raise ControlError("Inspection snapshot changed; no new model request allowed.")
    if rows["receipt"][0] is not None:
        raise ControlError("A receipt exists; review reconciliation instead of making another request.")
    return keys, rows


def session_envelope(ledger, report):
    state, etag = ledger._root()
    expected = report["review_template"]
    if digest(state) != expected["state_sha256"] or digest(etag) != expected["state_etag_sha256"]:
        raise ControlError("Authority changed after inspection; no one-shot grant may be created.")
    snapshot_rows(ledger, report)
    return 100


def grant(ledger, review, report):
    unexpired(review["expires_at"])
    ledger.renew()
    state, etag = ledger._root()
    keys, rows = snapshot_rows(ledger, report)
    allocation, operation, attempt = (rows[key][0] for key in ("allocation", "operation", "attempt"))
    run, name = review["run"], review["operation"]
    config = ledger.config
    storage = money(state["storage"]["reserve_usd"])
    credit = min(ledger.remaining_credit, money(review["remaining_credit_usd"]),
                 money(allocation["approval"]["remaining_credit_usd"]))
    if (state["breached"] or state["pending"] != [run, name] or state["epoch"] != ledger.owner
            or operation["status"] != "dispatched" or operation["attempts"] != 1
            or operation["request_sha256"] != review["request_sha256"]
            or attempt["status"] != "dispatched"
            or money(operation["reserved"]) != money(review["operation_reservation_retained_usd"])
            or money(operation["reserved"]) <= 0
            or money(allocation["used"]) < money(operation["reserved"])
            or money(allocation["used"]) > money(allocation["reserved"])
            or money(state["total"]) + storage > money(config["total_limit_usd"])
            or money(state["pilot_total"]) + storage > money(config["pilot_limit_usd"])
            or money(state["total"]) + storage + money(config["credit_reserve_usd"]) > credit):
        raise ControlError("Pending identity or financial bounds prevent a diagnostic grant.")
    ledger.store.budget.require_tail(40)
    captured = {"run": run, "operation": name, "attempt": 2, "epoch": ledger.owner,
                "request_sha256": review["request_sha256"], "review_sha256": digest(review)}
    before = dict(operation)
    operation = {**operation, "attempts": 2, "epoch": ledger.owner}
    ledger._write(state, etag, [
        (keys["operation"], operation, rows["operation"][1]),
        (ledger._key(run, name + ":2", "attempt"),
         {"status": "dispatched", "epoch": ledger.owner, "request_sha256": review["request_sha256"]}, None),
        (ledger._key(run, name + ":1", "sufficiency-smoke-unknown"),
         {"outcome": "UNKNOWN", "operation_before": before, "attempt_sha256": digest(attempt),
          "failure_sha256": review["failure_sha256"], "review_sha256": digest(review)}, None),
        (ledger._key(run, name + ":2", "sufficiency-smoke-grant"),
         {"captured": captured, "review": review}, None),
    ])
    ledger.active = (run, name)
    return captured


class DiagnosticBackend(SufficiencyBackend):
    def __init__(self, client, approval, config, examples, guard, save_response):
        self.approval, self.config = approval, config
        self.systems = {entry["system"]: (entry["project"], entry["variant"]) for entry in examples.values()}
        self.phase, self.calls, self.summary, self.http_status = "input", 0, None, None

        def guarded():
            self.phase = "guard"
            guard()

        def create(**kwargs):
            if self.calls:
                raise ControlError("Only one model request is allowed.")
            self.phase = "sdk"
            self.calls += 1
            try:
                response = client.chat.completions.create(**kwargs)
            except Exception as error:
                status = getattr(error, "status_code", None)
                self.http_status = status if type(status) is int and 100 <= status <= 599 else None
                raise
            self.phase = "response_summary"
            self.summary = response_summary(response, config["model"])
            self.phase = "diagnostic_write"
            save_response(self.summary)
            self.phase = "scoring"
            return response

        self.guard = guarded
        self.client = NS(chat=NS(completions=NS(create=create)))


def capture(backend, pair):
    result = None
    try:
        result = backend.predict(backend.approval["base_deployment"], pair)
        reason = "valid_diagnostic_response"
    except Exception as error:
        reason = ("diagnostic_persistence_failed" if backend.phase == "diagnostic_write" else
                  REASONS.get(str(error), "unclassified_error") if backend.phase == "scoring"
                  else "unclassified_error")
    return {
        "phase": "model_check" if reason == "model_mismatch" else backend.phase,
        "reason": reason, "model_requests": backend.calls, "http_status": backend.http_status,
        "response_summary": backend.summary, "scorable_response": result is not None,
        "valid_response": None if result is None else {
            "score": result["score"], "usage": result["usage"], "response_model": result["response_model"],
            "request_id_sha256": digest(result["request_id"]),
        },
    }


def save_diagnostic(ledger, captured, value):
    ledger.renew()
    state, etag = ledger._root()
    run, name = captured["run"], captured["operation"]
    operation = ledger.operation(run, name)
    attempt, _ = ledger.store.get(ledger._key(run, name + ":2", "attempt"))
    saved_grant, _ = ledger.store.get(ledger._key(run, name + ":2", "sufficiency-smoke-grant"))
    if (state["pending"] != [run, name] or state["epoch"] != captured["epoch"]
            or operation["status"] != "dispatched" or operation["attempts"] != 2
            or operation["epoch"] != captured["epoch"]
            or operation["request_sha256"] != captured["request_sha256"]
            or attempt["epoch"] != captured["epoch"] or attempt["status"] != "dispatched"
            or attempt["request_sha256"] != captured["request_sha256"]
            or saved_grant["captured"] != captured
            or digest(saved_grant["review"]) != captured["review_sha256"]):
        raise ControlError("A stale diagnostic cannot record another attempt's result.")
    ledger._write(state, etag, [
        (ledger._key(run, name + ":2", "sufficiency-smoke-diagnostic"), value, None),
    ])


def exclusive_json(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())


def execute(root, review, directory):
    config, authorization, binding, storage, examples, pair, _, report = validate_review(root, review)
    from azure.identity import AzureCliCredential
    from openai import OpenAI

    with ExitStack() as stack:
        store = InspectionStore(binding, InspectionBudget(100))
        stack.callback(store.close)
        store.authenticate()
        with AzureCliCredential(process_timeout=60) as credential:
            token = credential.get_token("https://cognitiveservices.azure.com/.default")
        if token.expires_on <= time.time() + 300:
            raise ControlError("Model token lifetime too short; no lease or inference requested.")

        def cached_model_token():
            if token.expires_on <= time.time() + 120:
                raise ControlError("Model token expiring; do not refresh during the lease.")
            return token.token

        store.verify_account()
        ledger = SufficiencyLedger(store, binding, storage["storage"],
                                   remaining_credit=storage["remaining_credit_usd"],
                                   access_expires=storage["expires_at"])
        ledger.bind(root, config)
        client = OpenAI(base_url=authorization["approval"]["endpoint"].rstrip("/") + "/openai/v1/",
                        api_key=cached_model_token, max_retries=0, timeout=60)
        stack.callback(client.close)
        with ledger.session(requests=lambda: session_envelope(ledger, report)):
            captured = grant(ledger, review, report)

            def guard():
                unexpired(review["expires_at"])
                ledger.store.budget.require_tail(25)
                ledger.guard_remote()
                if any(store.get(ledger._key(review["run"], "smoke-0:" + str(number), "receipt"))[0]
                       is not None for number in (1, 2)):
                    raise ControlError("A late receipt appeared; no diagnostic request may be sent.")

            backend = DiagnosticBackend(
                client, authorization["approval"], config, examples, guard,
                lambda summary: exclusive_json(directory / "response-summary.json",
                                                {"captured": captured, "summary": summary}),
            )
            value = {"schema": "sufficiency-one-shot-diagnostic-v1", "captured": captured,
                     "original_outcome": "UNKNOWN", "pending_retained": True,
                     "completes_smoke": False, "authorizes_continuation": False, **capture(backend, pair)}
            exclusive_json(directory / "local-diagnostic.json", value)
            save_diagnostic(ledger, captured, value)
    value["storage_requests_used"] = store.budget.used
    exclusive_json(directory / "diagnostic.json", value)
    return {key: value[key] for key in (
        "schema", "original_outcome", "pending_retained", "completes_smoke", "authorizes_continuation",
        "model_requests", "scorable_response", "reason", "http_status", "storage_requests_used",
    )}


def main(argv=None):
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("template", "diagnose"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--failure", type=Path)
    parser.add_argument("--inspection", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--review", type=Path)
    parser.add_argument("--execute-approved-diagnostic", action="store_true")
    args = parser.parse_args(argv)
    root = external_path(args.root)
    if args.stage == "template":
        if not (args.failure and args.inspection and args.output) or args.review or args.execute_approved_diagnostic:
            parser.error("Offline template requires --failure, --inspection, --output only.")
        output = external_path(args.output)
        if output == root or root in output.parents:
            parser.error("Write the private review outside the preserved run.")
        value = template(root, external_path(args.failure), external_path(args.inspection))
        exclusive_json(output, value)
        print(json.dumps({"cloud_access": False, "checks_default_false": True}))
        return
    if not args.review or not args.execute_approved_diagnostic or args.failure or args.inspection or args.output:
        parser.error("One-shot execution requires its private --review and explicit consent only.")
    review = read_json(external_path(args.review))
    validate_review(root, review)
    directory = root / "jobs/diagnose-smoke"
    directory.mkdir(parents=True, exist_ok=True)
    exclusive_json(directory / "diagnostic.started", {"review_sha256": digest(review)})
    print(json.dumps(execute(root, review, directory), indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("ONE-SHOT DIAGNOSTIC STOPPED; preserve pending state and do not retry.", file=sys.stderr)
        raise SystemExit(1) from None
