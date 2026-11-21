#!/usr/bin/env python3
"""Bounded storage inspection; retain uncertain renewal accounting, never call a model."""

import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

TASK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TASK))

from sufficiency import frozen_study
from renew_storage import validate
from ledger import SufficiencyLedger
from cloud_control import AzureStore, ControlError, RequestBudget, access_at, binding_at
from cost_control import money
from protocol import digest, external_path, write_json


class InspectionBudget(RequestBudget):
    """Reserve historical uncertainty without increasing this connection's I/O limit."""

    @property
    def limit(self):
        return self._limit

    @limit.setter
    def limit(self, value):
        self._limit = min(value, 100)


def inspect(root, store, binding, approval):
    config = validate(approval, binding, root)
    if not isinstance(store.budget, InspectionBudget):
        raise ControlError("Inspection requires its hard 100-request transport budget.")
    review_hash = digest(approval)
    expected_renewal = {
        "storage_renewed": True, "review_sha256": review_hash,
        "previous_storage_sha256": approval["previous_storage_sha256"],
        "storage_sha256": digest(approval["storage"]),
    }
    key = "sufficiency-renewal-recovery-accounting:" + review_hash
    accounting = {"review_sha256": review_hash, "reserved_requests": 100, "reserved_sessions": 1}
    carry = False

    def envelope():
        nonlocal carry
        previous, _ = store.get(key)
        if previous is not None and previous != accounting:
            raise ControlError("Recovery accounting differs; keep evidence and stop.")
        carry = previous is None
        return 200 if carry else 100

    store.verify_account()
    ledger = SufficiencyLedger(
        store, binding, approval["storage"], access_expires=approval["expires_at"],
        remaining_credit=approval["remaining_credit_usd"],
    )
    ledger.bind(root, config)
    with ledger.session(requests=envelope):
        state, etag = ledger._root()
        receipt, _ = store.get("sufficiency-storage-renewal:" + review_hash)
        if receipt != expected_renewal:
            raise ControlError("The exact renewal receipt must exist before inspection.")
        if carry:
            if state["sessions"] + 1 > approval["storage"]["max_sessions"]:
                raise ControlError("Insufficient session capacity for retained recovery accounting.")
            state["sessions"] += 1
            ledger._write(state, etag, [(key, accounting, None)])
        storage = money(state["storage"]["reserve_usd"])
        total = money(state["total"]) + storage
        pilot = money(state["pilot_total"]) + storage
        result = {
            "schema": "sufficiency-storage-inspection-v1",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "cloud_access": True, "model_calls": 0, "inspection_request_limit": 100,
            "recovery_requests_retained": 100, "recovery_sessions_retained": 1,
            "recovery_accounting_added": carry,
            "global_model_reserved_usd": state["total"], "storage_reserved_usd": str(storage),
            "cumulative_reserved_usd": str(total),
            "cumulative_cap_usd": str(config["total_limit_usd"]),
            "cumulative_headroom_usd": str(money(config["total_limit_usd"]) - total),
            "pilot_reserved_including_storage_usd": str(pilot),
            "pilot_cap_usd": str(config["pilot_limit_usd"]),
            "pilot_headroom_usd": str(money(config["pilot_limit_usd"]) - pilot),
            "requests_reserved": state["io_reserved"],
            "requests_remaining": state["storage"]["max_requests"] - state["io_reserved"],
            "sessions_reserved": state["sessions"],
            "sessions_remaining": state["storage"]["max_sessions"] - state["sessions"],
            "pending_operation": bool(state["pending"]), "breached": state["breached"],
            "deployment_present": bool(state["deployment"]),
            "training_quarantined": bool(state.get("quarantine")),
            "authorizes_inference": False,
        }
    result["inspection_requests_used"] = store.budget.used
    return result


def main(argv=None):
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--execute-approved-inspection", action="store_true")
    args = parser.parse_args(argv)
    if not args.execute_approved_inspection:
        parser.error("A separate, explicit 100-request storage-inspection approval is required.")
    root, output = external_path(args.root), external_path(args.output)
    if output.exists():
        parser.error("Keep the existing inspection; do not overwrite or repeat it.")
    frozen_study(root)
    binding = binding_at()
    approval = access_at(binding)
    validate(approval, binding, root)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.with_suffix(".started").open("x") as stream:
        json.dump({"review_sha256": digest(approval), "request_limit": 100}, stream)
        stream.flush()
        os.fsync(stream.fileno())
    with closing(AzureStore(binding, InspectionBudget(100))) as store:
        result = inspect(root, store, binding, approval)
    write_json(output, result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        detail = str(error) if isinstance(error, (ControlError, ValueError, FileNotFoundError)) else type(error).__name__
        print("INSPECTION STOPPED: " + detail + "; retain evidence and do not retry automatically.", file=sys.stderr)
        raise SystemExit(1) from None
