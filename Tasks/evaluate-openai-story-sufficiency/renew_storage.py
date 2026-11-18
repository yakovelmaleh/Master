#!/usr/bin/env python3
"""Explicitly reviewed storage renewal; no bootstrap, model call, or reservation reset."""

import argparse
from contextlib import closing
from datetime import datetime
import json
import os
from pathlib import Path
import time
import uuid

from sufficiency import BUDGET_CHECK, EXPERIMENT, budget_limits, frozen_study
from protocol import digest, external_path, read_json, study_id, write_json
from cost_control import CONTROL, money
from cloud_control import AzureStore, ControlError, RequestBudget, ROOT, binding_at, storage_plan, unexpired
from ledger import RECOVERY_SCHEMA

REVIEW_SCHEMA = "sufficiency-storage-renewal-v1"
CHECKS = (
    "zero_use_migration_verified", "old_workers_stopped", "storage_rates_verified",
    "credit_covers_storage", "private_storage_verified", "spending_limit_enabled",
    "prior_reservations_and_quarantine_retained", "expired_retention_reviewed",
    BUDGET_CHECK,
)


def template(root, previous):
    config = frozen_study(root)
    study = read_json(root / "study.json")
    prior_report = read_json(Path(study["source"]["root"]) / "recovery/llm_report.json")
    return {
        "schema": REVIEW_SCHEMA, "experiment_schema": EXPERIMENT,
        "authority_sha256": previous["authority_sha256"],
        "historical_recovery_sha256": prior_report["execution_recovery"]["review_sha256"],
        "previous_storage_sha256": digest(previous["storage"]),
        "study_sha256": digest(study), "run": study_id(root), "scope": "full",
        "budget_limits": budget_limits(config),
        "expires_at": "", "remaining_credit_usd": "0", "storage_extension_approved": False,
        "checks": {key: False for key in CHECKS},
        "storage": {**previous["storage"], "retention_until": "", "evidence": ""},
    }


def validate(review, binding, root):
    config = frozen_study(root)
    if (review.get("schema") != REVIEW_SCHEMA or review.get("experiment_schema") != EXPERIMENT
            or review.get("authority_sha256") != digest(binding)
            or review.get("scope") != "full"
            or review.get("storage_extension_approved") is not True
            or review.get("run") != study_id(root)
            or review.get("study_sha256") != digest(read_json(root / "study.json"))
            or review.get("budget_limits") != budget_limits(config)
            or any(review.get("checks", {}).get(key) is not True for key in CHECKS)):
        raise ControlError("Separate storage-renewal review is incomplete or bound to a different study.")
    unexpired(review["expires_at"])
    storage_plan(review["storage"])
    if datetime.fromisoformat(review["expires_at"].replace("Z", "+00:00")) > datetime.fromisoformat(
        review["storage"]["retention_until"].replace("Z", "+00:00")
    ):
        raise ControlError("Access cannot outlive approved storage retention.")
    return config


def renew(store, binding, review, root):
    config = validate(review, binding, root)
    store.verify_account()
    lease = store.acquire()
    start = time.monotonic()
    try:
        state, etag = store.get(ROOT)
        if (state is None or state.get("schema") != RECOVERY_SCHEMA
                or state.get("authority") != digest(binding)):
            raise ControlError("Renewal requires the existing recovered authority; never bootstrap.")
        history_hash = review.get("historical_recovery_sha256")
        history, _ = store.get("inference-recovery:" + str(history_hash))
        if (state.get("inference_recovery") != history_hash or history is None
                or digest(history) != history_hash
                or history.get("authority_sha256") != digest(binding)
                or digest(state.get("quarantine")) != history.get("training_quarantine_sha256")
                or (state.get("quarantine") and state.get("training") != state["quarantine"]["operation"])):
            raise ControlError("Historical recovery/quarantine differs; preserve evidence and stop.")
        if state["pending"] or state["breached"] or state["deployment"]:
            raise ControlError("Pending dispatch, breach, or deployment prevents renewal.")
        key = "sufficiency-storage-renewal:" + digest(review)
        saved, _ = store.get(key)
        if saved is not None and state["storage"] == review["storage"]:
            return saved
        old, new = state["storage"], review["storage"]
        if digest(old) != review["previous_storage_sha256"]:
            raise ControlError("Prior storage allowance changed; inspect it before a new review.")
        for field in ("max_requests", "session_requests", "max_sessions", "session_seconds",
                      "request_usd", "margin", "bootstrap_usd", "capacity_usd", "transfer_usd", "reserve_usd"):
            if money(new[field]) < money(old[field]):
                raise ControlError("Renewal cannot reduce any previous bounds or reservations.")
        if datetime.fromisoformat(new["retention_until"].replace("Z", "+00:00")) < datetime.fromisoformat(
            old["retention_until"].replace("Z", "+00:00")
        ):
            raise ControlError("Retention cannot shrink.")
        total = money(state["total"]) + money(new["reserve_usd"])
        if (total > money(config["total_limit_usd"])
                or total + money(config["credit_reserve_usd"]) > money(review["remaining_credit_usd"])):
            raise ControlError("Renewal exceeds the global cap or protected credit.")
        if state["sessions"] + 1 > new["max_sessions"] or state["io_reserved"] + 100 > new["max_requests"]:
            raise ControlError("Insufficient reviewed capacity for this 100-request renewal.")
        state.update(storage=new, storage_scope="full", epoch=uuid.uuid4().hex,
                     sessions=state["sessions"] + 1, io_reserved=state["io_reserved"] + 100)
        result = {"storage_renewed": True, "review_sha256": digest(review),
                  "previous_storage_sha256": digest(old), "storage_sha256": digest(new)}
        store.renew(lease)
        if time.monotonic() - start >= 40:
            raise ControlError("Renewal exceeded its lease-safe deadline; keep evidence and stop.")
        unexpired(review["expires_at"])
        unexpired(new["retention_until"])
        store.transaction([(ROOT, state, etag), (key, result, None)])
        return result
    finally:
        store.release(lease)


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("template", "renew"))
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--review", type=Path)
    parser.add_argument("--storage-renewal-approved", action="store_true")
    args = parser.parse_args()
    root, output = external_path(args.root), external_path(args.output)
    frozen_study(root)
    if output.exists():
        parser.error("Keep existing evidence; --output must be a new private path.")
    if args.stage == "template":
        if args.review or args.storage_renewal_approved:
            parser.error("Template creation is offline, without approval flags.")
        result = template(root, read_json(CONTROL / "cloud-approval.json"))
        write_json(output, result)
        print(json.dumps({"template": str(output), "cloud_access": False, "checks_default_false": True}))
        return
    if not args.review or not args.storage_renewal_approved:
        parser.error("Renewal needs a reviewed private --review and --storage-renewal-approved.")
    review, binding = read_json(external_path(args.review)), binding_at()
    validate(review, binding, root)
    with closing(AzureStore(binding, RequestBudget(100))) as store:
        result = renew(store, binding, review, root)
    write_json(output, result)
    print(json.dumps(result))
    print("Renewal recorded. Preserve the old cloud-approval.json, then install the reviewed file there.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"STORAGE RENEWAL STOPPED: {type(error).__name__}; keep approvals and evidence.")
        raise SystemExit(1) from None
