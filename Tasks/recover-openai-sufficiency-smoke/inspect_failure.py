"""Explicitly approved Storage-only snapshot; never resolve or replay an inference."""

import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from diagnostics import audit
from cloud_control import ControlError, RequestBudget, access_at, binding_at
from inspection_auth import InspectionStore, failure_reason
from cost_control import CONTROL, money
from ledger import SufficiencyLedger
from protocol import digest, external_path, file_hash, read_json, slug, study_id, write_json
from renew_storage import validate
from sufficiency import check_approval

SCHEMA = "sufficiency-failure-inspection-v1"
CHECKS = (
    "snapshot_reviewed", "unknown_attempt_retained", "receipt_disposition_reviewed",
    "execution_policy_amendment_approved", "possible_duplicate_charge_accepted",
)


class InspectionBudget(RequestBudget):
    @property
    def limit(self):
        return self._limit

    @limit.setter
    def limit(self, value):
        self._limit = min(value, 100)


def inputs(root, failure):
    config, model, _, _, context = audit(root, failure)
    binding = binding_at()
    storage = access_at(binding)
    validate(storage, binding, root)
    check_approval(model, context["study_sha256"], config)
    if (model["authority_sha256"] != digest(binding)
            or money(model["storage_reserve_usd"]) != money(storage["storage"]["reserve_usd"])):
        raise ControlError("Model and storage authority/reserve differ.")
    evidence = read_json(root / "authorization.json")
    return config, evidence, binding, storage, context


def queued_review(root, failure):
    _, _, _, _, context = inputs(root, failure)
    return {
        "context": context, "failure_path": str(failure),
        "model_authorization_sha256": file_hash(root / "authorization.json"),
        "storage_approval_sha256": file_hash(CONTROL / "cloud-approval.json"),
        "inspector_sha256": file_hash(Path(__file__)),
        "authentication_helper_sha256": file_hash(Path(__file__).with_name("inspection_auth.py")),
    }


def inspect(root, store, binding, storage, context, config, authorization):
    validate(storage, binding, root)
    check_approval(authorization["approval"], context["study_sha256"], config)
    if (context.get("run") != study_id(root) or context.get("operation") != "smoke-0"
            or context.get("attempt") != 1
            or context["study_sha256"] != digest(read_json(root / "study.json"))
            or authorization["approval"]["authority_sha256"] != digest(binding)
            or money(authorization["approval"]["storage_reserve_usd"]) != money(storage["storage"]["reserve_usd"])):
        raise ControlError("Inspection identity or authority differs.")
    if not isinstance(store.budget, InspectionBudget):
        raise ControlError("A hard 100-request inspection budget is required.")
    store.verify_account()
    ledger = SufficiencyLedger(
        store, binding, storage["storage"], remaining_credit=storage["remaining_credit_usd"],
        access_expires=storage["expires_at"],
    )
    ledger.bind(root, config)
    run, name = context["run"], context["operation"]
    with ledger.session(requests=lambda: 100):
        state, state_etag = ledger._root()
        if state["pending"] != [run, name]:
            raise ControlError("Pending operation differs; do not infer or change its outcome.")
        keys = {
            "allocation": "run:" + run,
            "operation": ledger._key(run, name),
            "attempt": ledger._key(run, name + ":1", "attempt"),
            "receipt": ledger._key(run, name + ":1", "receipt"),
            "renewal": "sufficiency-storage-renewal:" + digest(storage),
        }
        rows = {kind: store.get(key) for kind, key in keys.items()}
        allocation, operation, attempt, receipt, renewal = (rows[kind][0] for kind in keys)
        if renewal != {
            "storage_renewed": True, "review_sha256": digest(storage),
            "previous_storage_sha256": storage["previous_storage_sha256"],
            "storage_sha256": digest(storage["storage"]),
        }:
            raise ControlError("Exact installed renewal receipt is missing or changed.")
        if (allocation is None or allocation.get("authorization") != authorization
                or allocation.get("approval") != authorization["approval"]
                or allocation.get("scope") != "pilot"):
            raise ControlError("Cloud pilot allocation differs from local authorization.")
        if (operation is None or operation.get("kind") != "inference"
                or operation.get("run") != run or operation.get("name") != name
                or operation.get("status") != "dispatched" or operation.get("attempts") != 1
                or operation.get("result") is not None
                or operation.get("request_sha256") != context["request_sha256"]
                or digest(operation.get("request")) != context["request_sha256"]
                or attempt is None or attempt.get("status") != "dispatched"
                or attempt.get("request_sha256") != context["request_sha256"]
                or not isinstance(operation.get("epoch"), str) or not operation["epoch"]
                or attempt.get("epoch") != operation.get("epoch")):
            raise ControlError("Exact failed operation/attempt identity differs.")
        if receipt is not None and receipt.get("request_sha256") != context["request_sha256"]:
            raise ControlError("Receipt request identity conflicts; stop without reconciliation.")
        # Receipts can be written without a root update; recheck every entity as well.
        ledger.renew()
        if any(store.get(key) != rows[kind] for kind, key in keys.items()):
            raise ControlError("Snapshot changed during inspection.")
        if ledger._root() != (state, state_etag):
            raise ControlError("Authority changed during inspection.")
        ledger.check()
        reserve = money(state["storage"]["reserve_usd"])
        review = {
            "schema": "sufficiency-failure-review-template-v1", **context,
            "authority_sha256": digest(binding),
            "state_sha256": digest(state), "state_etag_sha256": digest(state_etag),
            "entities": {
                kind: {"sha256": digest(value), "etag_sha256": digest(etag)}
                for kind, (value, etag) in rows.items()
            },
            "model_authorization_sha256": digest(authorization),
            "storage_approval_sha256": digest(storage),
            "training_quarantine_sha256": digest(state.get("quarantine")),
            "historical_recovery_sha256": state.get("inference_recovery"),
            "prepared_sha256": file_hash(root / "prepared.json"),
            "inspector_sha256": file_hash(Path(__file__)),
            "authentication_helper_sha256": file_hash(Path(__file__).with_name("inspection_auth.py")),
            "expires_at": "", "execution_approved": False,
            "checks": {key: False for key in CHECKS},
        }
        result = {
            "schema": SCHEMA, "captured_at": datetime.now(timezone.utc).isoformat(),
            "cloud_access": True, "model_calls": 0, "authorizes_inference": False,
            "inspection_request_limit": 100, "requests_reserved_this_session": 100,
            "sessions_reserved_this_inspection": 1,
            "pending_matches_failure": True, "attempt": 1,
            "receipt_present": receipt is not None, "historical_outcome": "UNKNOWN",
            "next_review": "receipt_validation" if receipt is not None else "unresolved_attempt",
            "breached": state["breached"], "training_quarantined": bool(state.get("quarantine")),
            "cumulative_reserved_usd": str(money(state["total"]) + reserve),
            "pilot_reserved_including_storage_usd": str(money(state["pilot_total"]) + reserve),
            "operation_reserved_usd": operation["reserved"],
            "requests_remaining": state["storage"]["max_requests"] - state["io_reserved"],
            "sessions_remaining": state["storage"]["max_sessions"] - state["sessions"],
            "review_template": review,
        }
    result["inspection_requests_used"] = store.budget.used
    return result


def main(argv=None):
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--failure", required=True, type=Path)
    parser.add_argument("--job-label", help="New evidence directory for a separately approved inspection.")
    parser.add_argument("--execute-approved-inspection", action="store_true")
    args = parser.parse_args(argv)
    if not args.execute_approved_inspection:
        parser.error("Separate consent for one 100-request Storage inspection is required.")
    root, failure = external_path(args.root), external_path(args.failure)
    config, authorization, binding, storage, context = inputs(root, failure)
    directory = root / "jobs" / ("inspect-failure" + ("-" + slug(args.job_label) if args.job_label else ""))
    output = directory / "inspection.json"
    if output.exists():
        parser.error("Inspection already exists; preserve evidence and do not repeat.")
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "inspection.started").open("x") as stream:
        json.dump({"context": context, "storage_approval_sha256": digest(storage),
                   "request_limit": 100}, stream)
        stream.flush()
        os.fsync(stream.fileno())
    with closing(InspectionStore(binding, InspectionBudget(100))) as store:
        start = time.monotonic()
        auth = {"process_timeout_seconds": 60, "scope_count": 2, "model_calls": 0}
        try:
            store.authenticate()
        except Exception as error:
            write_json(directory / "authentication.json", {
                **auth, "authenticated": False, "reason": failure_reason(error),
                "elapsed_seconds": round(time.monotonic() - start, 3),
                "storage_requests_used": store.budget.used,
            })
            raise
        write_json(directory / "authentication.json", {
            **auth, "authenticated": True, "elapsed_seconds": round(time.monotonic() - start, 3),
            "storage_requests_used": store.budget.used,
        })
        result = inspect(root, store, binding, storage, context, config, authorization)
    write_json(output, result)
    print(json.dumps({key: value for key, value in result.items() if key != "review_template"}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("FAILURE INSPECTION STOPPED; preserve evidence and do not retry.", file=sys.stderr)
        raise SystemExit(1) from None
