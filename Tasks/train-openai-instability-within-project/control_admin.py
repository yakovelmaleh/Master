#!/usr/bin/env python3
"""Explicit zero-use bootstrap/probe tooling. Never creates an Azure account or table."""

import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import socket
import sqlite3
import sys
import time
import uuid

from cloud_control import (
    AzureStore, Conflict, ControlError, Ledger, RequestBudget, ROOT,
    access_at, binding_at, initial_state,
)
from cost_control import CONTROL, money
from cost_control import control_envelope, control_requests
from protocol import PILOT, TASK, cell_key, digest, external_path, file_hash, read_json, write_json

PROBE_REQUEST_LIMIT = 1000


def audit(storage, control=CONTROL):
    """Read only; any paid/ambiguous old state requires a separately reviewed migration."""
    storage, control = Path(storage), Path(control)
    files = []
    database = control / "ledger.sqlite3"
    if database.exists():
        with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if tables - {"runs", "operations", "state"}:
                raise ControlError("Unknown legacy ledger schema; migration refused.")
            for name in ("runs", "operations"):
                if name in tables and connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]:
                    raise ControlError("Nonempty legacy ledger; zero-use migration refused.")
            if "state" in tables and connection.execute("SELECT 1 FROM state WHERE breached != 0").fetchone():
                raise ControlError("Legacy cost breach; migration refused.")
        files.append({"path": str(database.resolve()), "sha256": file_hash(database)})
    if (control / "deployment.json").exists():
        raise ControlError("Legacy deployment ownership exists; reconcile before migration.")
    for root in sorted((storage / "openai-runs").glob("*")):
        if not root.is_dir():
            continue
        if (root / "authorization.json").exists() or list((root / "remote").glob("*.json")):
            raise ControlError("Legacy authorization or remote intent exists; zero-use migration refused.")
        if (root / "study.json").exists():
            files.append({"path": str((root / "study.json").resolve()),
                          "sha256": file_hash(root / "study.json")})
    return {"schema": "openai-zero-use-audit-v1", "storage": str(storage.resolve()),
            "control": str(control.resolve()), "files": files, "zero_use": True}


def bootstrap(store, binding, approval, inventory):
    from azure.core.exceptions import ResourceNotFoundError

    if approval.get("migration_sha256") != digest(inventory):
        raise ControlError("Fresh zero-use inventory differs from reviewed migration evidence.")
    if approval.get("scope") != "pilot":
        raise ControlError("A zero-use bootstrap requires pilot-scope storage approval.")
    store.verify_account()
    store.budget.charge()
    if next(iter(store.table.list_entities(results_per_page=1)), None) is not None:
        raise ControlError("Bootstrap requires an empty dedicated table; never reset or adopt an existing ledger.")
    metadata = {"authority": digest(binding), "migration": digest(inventory)}
    store.budget.charge()
    try:
        properties = store.blob.get_blob_properties()
    except ResourceNotFoundError:
        store.budget.charge()
        store.blob.upload_blob(b"", overwrite=False, metadata=metadata)
    else:
        if properties.metadata != metadata:
            raise ControlError("Existing coordinator blob differs; bootstrap refused.")
    store.transaction([(ROOT, initial_state(binding, approval["storage"]), None)])
    return {"bootstrapped": True, "authority_sha256": digest(binding)}


def extend_storage(store, binding, approval):
    """Explicit full-scope review; no reservation, pending operation or breach is reset."""
    from cloud_control import storage_plan

    if approval.get("scope") != "full" or approval.get("storage_extension_approved") is not True:
        raise ControlError("A separate full-scope storage extension approval is required.")
    new = storage_plan(approval["storage"])
    store.verify_account()
    lease = store.acquire()
    start = time.monotonic()
    try:
        state, etag = store.get(ROOT)
        if (state is None or state.get("authority") != digest(binding)
                or state.get("schema") != binding["schema"]):
            raise ControlError("Cannot extend a missing or different authority.")
        review_key = "storage-review:" + digest(approval)
        review, _ = store.get(review_key)
        if review is not None and state["storage"] == new:
            return review
        old = state["storage"]
        if approval.get("previous_storage_sha256") != digest(old) or state["breached"]:
            raise ControlError("Storage extension requires the exact prior allowance and no unreconciled breach.")
        for key in ("max_requests", "session_requests", "max_sessions", "session_seconds",
                    "request_usd", "margin", "bootstrap_usd", "capacity_usd", "transfer_usd", "reserve_usd"):
            if money(new[key]) < money(old[key]):
                raise ControlError("Storage extensions cannot reduce prior bounds or reservations.")
        from datetime import datetime
        if datetime.fromisoformat(new["retention_until"].replace("Z", "+00:00")) < datetime.fromisoformat(
            old["retention_until"].replace("Z", "+00:00")
        ):
            raise ControlError("Storage retention cannot shrink during an extension.")
        run = approval.get("run", "")
        allocation, _ = store.get("run:" + run)
        if allocation is None or approval.get("study_sha256") != allocation["approval"]["study_sha256"]:
            raise ControlError("Storage expansion must name an authorized study.")
        for cell in PILOT:
            selection, _ = store.get(Ledger._key(run, "validation-" + cell_key(*cell), "artifact"))
            if selection is None:
                raise ControlError("Complete both pilot validations before full-scope storage expansion.")
        total = money(state["total"]) + money(new["reserve_usd"])
        if total > money("80") or total + money("20") > money(approval["remaining_credit_usd"]):
            raise ControlError("Storage extension exceeds the global cap or protected credit.")
        if (state["io_reserved"] + 100 > new["max_requests"]
                or state["sessions"] + 1 > new["max_sessions"]):
            raise ControlError("New allowance does not cover this extension's bounded I/O.")
        state.update(storage=new, storage_scope="full", epoch=uuid.uuid4().hex,
                     io_reserved=state["io_reserved"] + 100, sessions=state["sessions"] + 1)
        result = {"storage_extended": True, "storage_sha256": digest(new),
                  "previous_storage_sha256": digest(old), "run": run}
        store.renew(lease)
        if time.monotonic() - start >= 40:
            raise ControlError("Storage extension exceeded its lease-safe deadline; retry after review.")
        store.transaction([(ROOT, state, etag), (review_key, result, None)])
        return result
    finally:
        store.release(lease)


def probe(ledger):
    """Conditional batch and data/lease access probe, with no model calls."""
    with ledger.session(requests=lambda: min(PROBE_REQUEST_LIMIT, ledger.plan["session_requests"])):
        key = "probe:" + ledger.owner
        ledger.store.transaction([(key, {"value": 1}, None)])
        value, stale = ledger.store.get(key)
        ledger.store.transaction([(key, {"value": 2}, stale)])
        try:
            ledger.store.transaction([(key, value, stale), (key + ":should-not-exist", {}, None)])
        except Conflict:
            pass
        else:
            raise ControlError("Stale ETag batch unexpectedly committed.")
        if ledger.store.get(key)[0] != {"value": 2} or ledger.store.get(key + ":should-not-exist")[0] is not None:
            raise ControlError("Conditional transaction atomicity probe failed.")
        ledger.renew()
        state, etag = ledger._root()
        state["probe_atomic"] = True
        ledger._write(state, etag)
        return {"storage_probe": "passed", "authority_sha256": digest(ledger.binding)}


def hold_probe(ledger, output):
    with ledger.session(requests=lambda: min(PROBE_REQUEST_LIMIT, ledger.plan["session_requests"])):
        if not ledger._root()[0]["probe_atomic"]:
            raise ControlError("Run the conditional-transaction probe first.")
        host = socket.gethostname()
        write_json(output, {"owner": ledger.owner, "host": host})
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            ledger.check()
            contender, _ = ledger.store.get("probe-contender:" + ledger.owner)
            if contender is not None:
                if contender.get("excluded") is not True or contender.get("host") == host:
                    raise ControlError("Lease contention must succeed from a different compute node.")
                ledger.renew()
                state, etag = ledger._root()
                state["probe_verified"] = True
                ledger._write(state, etag)
                return {"two_node_probe": "passed"}
            time.sleep(1)
        raise ControlError("Second-node contention evidence was not received within the 180-second probe window.")


def contend_probe(store, holding):
    from azure.core.exceptions import HttpResponseError

    holder = read_json(holding)
    host = socket.gethostname()
    if holder["host"] == host:
        raise ControlError("Use a different compute node for the contender.")
    try:
        lease = store.acquire()
    except HttpResponseError as error:
        code = getattr(error, "error_code", None)
        if error.status_code != 409 or getattr(code, "value", code) != "LeaseAlreadyPresent":
            raise ControlError("Lease contention failed for a reason other than an active lease.") from None
        result = {"excluded": True, "host": host}
        store.transaction([("probe-contender:" + holder["owner"], result, None)])
        return result
    else:
        store.release(lease)
        raise ControlError("Expected a lease holder on the other node; exclusion not demonstrated.")


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("template", "cost-plan", "audit", "bootstrap", "extend",
                                         "probe", "lease-hold", "lease-contend"))
    parser.add_argument("--storage", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--holding", type=Path)
    parser.add_argument("--prepared", type=Path)
    args = parser.parse_args()
    storage, output = external_path(args.storage), external_path(args.output)
    if args.stage == "cost-plan":
        if args.prepared is None:
            parser.error("cost-plan requires --prepared for the exact eight-cell manifest")
        from protocol import config_at
        prepared, config = read_json(args.prepared), config_at(TASK / "experiment.json")
        commands = {f"{scope}-{stage}": control_requests(stage, prepared, config, scope)
                    for scope in ("pilot", "full") for stage in ("smoke", "validate", "test", "report")}
        result = {"command_request_envelopes": commands,
                  "scope_request_envelopes": {scope: control_envelope(prepared, config, scope)
                                             for scope in ("pilot", "full")},
                  "extra_command_requests": 1000,
                  "note": "Add every preflight, submit, status, seal, cleanup, probe and restart; price all envelopes and retention."}
        write_json(output, result)
        print(json.dumps(result))
        return
    if args.stage == "template":
        if output.exists():
            raise ControlError("Refusing to overwrite an existing private storage approval.")
        result = {
            "authority_sha256": digest(read_json(TASK / "control_store.json")),
            "migration_sha256": "", "expires_at": "", "remaining_credit_usd": "0",
            "scope": "pilot", "storage_extension_approved": False,
            "previous_storage_sha256": "", "run": "", "study_sha256": "",
            "live_storage_test_approved": False,
            "checks": {key: False for key in (
                "zero_use_migration_verified", "old_workers_stopped", "storage_rates_verified",
                "credit_covers_storage", "private_storage_verified", "spending_limit_enabled")},
            "storage": {"max_requests": None, "session_requests": None, "max_sessions": None,
                        "session_seconds": None, "request_usd": None, "margin": "1.25",
                        "bootstrap_usd": None, "capacity_usd": None, "transfer_usd": None, "reserve_usd": None,
                        "evidence": "", "retention_until": ""},
        }
        write_json(output, result)
        print("Private template written; defaults prohibit cloud access.")
        return
    if args.stage == "audit":
        result = audit(storage)
        write_json(output, result)
        print(json.dumps({"zero_use": True, "migration_sha256": digest(result)}))
        return
    binding = binding_at()
    approval = access_at(binding)
    if args.stage != "extend" and approval.get("live_storage_test_approved") is not True:
        raise ControlError("Explicit billable bootstrap/probe approval is required.")
    limit = (100 if args.stage in ("bootstrap", "extend")
             else min(PROBE_REQUEST_LIMIT, approval["storage"]["session_requests"]))
    store = AzureStore(binding, RequestBudget(limit))
    ledger = Ledger(store, binding, approval["storage"], access_expires=approval["expires_at"],
                    remaining_credit=approval["remaining_credit_usd"])
    try:
        if args.stage == "bootstrap":
            result = bootstrap(store, binding, approval, audit(storage))
        elif args.stage == "extend":
            result = extend_storage(store, binding, approval)
        elif args.stage == "probe":
            result = probe(ledger)
        elif args.stage == "lease-hold":
            result = hold_probe(ledger, output)
        else:
            if args.holding is None:
                raise ControlError("Supply the first node's --holding probe signal.")
            result = contend_probe(store, external_path(args.holding))
        write_json(output, result)
        print(json.dumps(result))
    finally:
        store.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        detail = str(error) if isinstance(error, (ControlError, FileNotFoundError)) else type(error).__name__
        print("CONTROL FAILED: " + detail, file=sys.stderr)
        raise SystemExit(1) from None
