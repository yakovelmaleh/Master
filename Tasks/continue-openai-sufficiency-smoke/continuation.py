"""Separately reviewed continuation of the 21 remaining sufficiency smoke predictions."""

import argparse
from contextlib import ExitStack
from datetime import datetime
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace as NS

TASK = Path(__file__).resolve().parent
sys.path.insert(0, str(TASK.parent / "resolve-openai-sufficiency-smoke"))
import resolution
from backend import SufficiencyBackend
from cloud_control import ControlError, RequestBudget, RetryableRejection, unexpired
from cost_control import control_requests, money
from diagnostics import REASONS, response_summary
from inspection_auth import InspectionStore
from ledger import SufficiencyLedger
from one_shot import exclusive_json
from prepare_data import Tokenizer, partition
from protocol import PILOT_LEVEL, PILOT_PROJECT, cell_key, digest, external_path, file_hash, read_json

spec = importlib.util.spec_from_file_location(
    "sufficiency_continuation_core", TASK.parent / "evaluate-openai-story-sufficiency/run_experiment.py",
)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)

SCHEMA = "sufficiency-smoke-continuation-review-v1"
OPERATIONS = ("smoke-1", *(f"base-control-{i}" for i in range(20)))
REQUEST_LIMIT = 3640
CHECKS = (
    "old_workers_stopped", "exact_resolved_sample_reused",
    "remaining_21_predictions_only", "verified_429_only_three_attempt_policy",
    "unknown_and_all_reservations_retained", "current_credit_and_storage_reviewed",
    "no_validation_or_test_authorized",
)


def implementation_hash():
    return digest({path.name: file_hash(path) for path in sorted(TASK.glob("*.py"))})


def inputs(root, path):
    review = read_json(path)
    original, context, diagnostic = resolution.validate_review(root, review)
    directory = root / "jobs/resolve-smoke"
    status, value = read_json(directory / "worker-status.json"), read_json(directory / "resolution.json")
    expected = {
        "schema": "sufficiency-smoke-resolution-v1", "captured": diagnostic["captured"],
        "review_sha256": digest(review), "diagnostic_sha256": digest(diagnostic),
        "accounting": review["accounting"], "breached": False, "resolved": True,
        "pending_retained": False, "completes_smoke": False, "authorizes_continuation": False,
        "model_calls": 0, "resolution_epoch": value["resolution_epoch"],
    }
    if (status.get("status") != "succeeded" or status.get("resolved") is not True
            or status.get("model_calls") != 0 or status.get("completes_smoke") is not False
            or status.get("authorizes_continuation") is not False
            or {key: item for key, item in value.items() if key != "storage_requests_used"} != expected
            or type(value.get("storage_requests_used")) is not int
            or not 0 <= value["storage_requests_used"] <= 100
            or not isinstance(value["resolution_epoch"], str) or not value["resolution_epoch"]):
        raise ControlError("The exact successful Storage-only resolution is required.")
    if any((root / name).exists() for name in ("smoke.json", "base_control.json")):
        raise ControlError("Smoke output already exists; preserve evidence rather than rerunning.")
    if control_requests("smoke", read_json(root / "prepared.json"), context[0], "pilot") != REQUEST_LIMIT:
        raise ControlError("The original smoke request envelope changed.")
    return review, original, context, diagnostic, expected


def template(root, resolution_review):
    _, original, context, _, value = inputs(root, resolution_review)
    directory = root / "jobs/resolve-smoke"
    return {
        "schema": SCHEMA, "resolution_review_path": str(resolution_review),
        "resolution_review_sha256": file_hash(resolution_review),
        "resolution_sha256": file_hash(directory / "resolution.json"),
        "resolution_status_sha256": file_hash(directory / "worker-status.json"),
        "implementation_sha256": implementation_hash(), "run": original["run"],
        "study_sha256": original["study_sha256"], "resolution_epoch": value["resolution_epoch"],
        "new_predictions": 21, "max_attempts_per_prediction": context[0]["request_attempts"],
        "max_new_model_requests": 63, "retry_http_statuses": [429],
        "storage_request_limit": REQUEST_LIMIT, "storage_sessions": 1,
        "remaining_credit_usd": "0", "expires_at": "", "execution_approved": False,
        "checks": {key: False for key in CHECKS},
    }


def validate_review(root, review):
    path = external_path(review["resolution_review_path"])
    expected = template(root, path)
    editable = {"remaining_credit_usd", "expires_at", "execution_approved", "checks"}
    if (set(review) != set(expected)
            or any(review[key] != value for key, value in expected.items() if key not in editable)
            or review["execution_approved"] is not True or set(review["checks"]) != set(CHECKS)
            or any(review["checks"][key] is not True for key in CHECKS)):
        raise ControlError("Exact separate smoke-continuation approval is required.")
    unexpired(review["expires_at"])
    data = inputs(root, path)
    expiry = datetime.fromisoformat(review["expires_at"].replace("Z", "+00:00"))
    if expiry > datetime.fromisoformat(data[0]["expires_at"].replace("Z", "+00:00")):
        raise ControlError("Continuation cannot outlive the existing approvals.")
    if money(review["remaining_credit_usd"]) <= money(data[2][0]["credit_reserve_usd"]):
        raise ControlError("Current reviewed credit is required.")
    return data


def queued_review(root, path):
    validate_review(root, read_json(path))
    return {"review_path": str(path), "review_sha256": file_hash(path),
            "implementation_sha256": implementation_hash()}


class SmokeBudget(RequestBudget):
    @property
    def limit(self):
        return self._limit

    @limit.setter
    def limit(self, value):
        self._limit = min(value, REQUEST_LIMIT)


class SmokeLedger(SufficiencyLedger):
    def begin(self, run, name, amount, kind, request, recovery=False):
        if recovery or kind != "inference" or name not in ("smoke-0", *OPERATIONS):
            raise ControlError("Only the reviewed smoke operations are allowed.")
        if name == "smoke-0" and self.operation(run, name) != self.resolved_operation:
            raise ControlError("The accepted smoke-0 result changed; it must never be replayed.")
        return super().begin(run, name, amount, kind, request, recovery)

    def dispatch(self, run, name, attempts):
        if name not in OPERATIONS or attempts != 3:
            raise ControlError("Only remaining smoke predictions may dispatch, with three total attempts.")
        unexpired(self.continuation_review["expires_at"])
        self.check_model_token()
        return super().dispatch(run, name, attempts)

    def record(self, run, name, value):
        if name != "smoke":
            raise ControlError("Continuation cannot record validation, test or seal artifacts.")
        return super().record(run, name, value)


def resolved_snapshot(ledger, data, review):
    resolution_review, original, context, diagnostic, resolved = data
    state, _ = ledger._root()
    _, rows = resolution.rows_at(ledger, original)
    snapshot = context[-1]["review_template"]
    for kind in ("allocation", "attempt", "renewal"):
        value, etag = rows[kind]
        if snapshot["entities"][kind] != {"sha256": digest(value), "etag_sha256": digest(etag)}:
            raise ControlError("Original allocation, attempt or renewal changed.")
    note, captured = rows["unknown"][0], diagnostic["captured"]
    result = {**diagnostic["valid_response"], "attempts": 2, "unknown_attempts": [1],
              "actual_complete": False, "resolution_review_sha256": digest(resolution_review)}
    costs = resolved["accounting"]
    expected_op = {
        **note["operation_before"], "attempts": 2, "epoch": captured["epoch"],
        "actual_usd": costs["known_actual_usd"], "unknown_attempt_bound_usd": costs["unknown_attempt_bound_usd"],
        "accounted_bound_usd": costs["accounted_bound_usd"], "unreserved_excess_usd": "0",
        "actual_complete": False, "status": "succeeded", "result": result,
    }
    if (digest(note["operation_before"]) != snapshot["entities"]["operation"]["sha256"]
            or note != {"outcome": "UNKNOWN", "operation_before": note["operation_before"],
                        "attempt_sha256": snapshot["entities"]["attempt"]["sha256"],
                        "failure_sha256": original["failure_sha256"], "review_sha256": digest(original)}
            or rows["grant"][0] != {"captured": captured, "review": original}
            or rows["diagnostic"][0] != diagnostic
            or rows["resolution"][0] != {"review": resolution_review, "value": resolved}
            or rows["operation"][0] != expected_op
            or rows["attempt2"][0] != {"status": "succeeded", "epoch": captured["epoch"],
                                      "request_sha256": original["request_sha256"],
                                      "result_sha256": digest(result)}):
        raise ControlError("The accepted diagnostic or its resolution changed.")
    for number in (1, 2):
        if rows["receipt" + str(number)][0] != {
            "schema": "sufficiency-smoke-receipt-fence-v1", "request_sha256": None,
            "blocked_request_sha256": original["request_sha256"], "attempt": number,
            "resolution_review_sha256": digest(resolution_review),
        }:
            raise ControlError("The late-receipt fences changed.")
    reserve = money(state["storage"]["reserve_usd"])
    credit = min(money(review["remaining_credit_usd"]), ledger.remaining_credit,
                 money(context[1]["approval"]["remaining_credit_usd"]))
    if (state["pending"] is not None or state["breached"] or state["epoch"] != resolved["resolution_epoch"]
            or digest(state.get("quarantine")) != snapshot["training_quarantine_sha256"]
            or state.get("inference_recovery") != snapshot["historical_recovery_sha256"]
            or money(state["total"]) + reserve != money(context[-1]["cumulative_reserved_usd"])
            or money(state["pilot_total"]) + reserve != money(context[-1]["pilot_reserved_including_storage_usd"])
            or money(state["total"]) + reserve + money(context[0]["credit_reserve_usd"]) > credit
            or ledger.artifact(original["run"], "smoke") is not None
            or ledger.artifact(original["run"], "seal") is not None
            or any(ledger.operation(original["run"], name) is not None for name in OPERATIONS)):
        raise ControlError("Authority or smoke progress changed; do not launch another prediction.")
    ledger.resolved_operation = expected_op
    return REQUEST_LIMIT


class SmokeBackend(SufficiencyBackend):
    def __init__(self, client, approval, config, examples, ledger, directory):
        self.approval, self.config, self.ledger, self.directory = approval, config, ledger, directory
        self.systems = {entry["system"]: (entry["project"], entry["variant"]) for entry in examples.values()}
        self.calls = 0

        def guard():
            self.phase = "guard"
            unexpired(ledger.continuation_review["expires_at"])
            ledger.guard_remote()

        def create(**kwargs):
            if self.calls >= 63 or ledger.active is None or ledger.active[1] not in OPERATIONS:
                raise ControlError("The reviewed prediction scope is exhausted.")
            self.phase = "sdk"
            self.calls += 1
            try:
                response = client.chat.completions.create(**kwargs)
            except Exception as error:
                status = getattr(error, "status_code", None)
                self.http_status = status if type(status) is int and 100 <= status <= 599 else None
                raise
            self.phase = "response_summary"
            summary = response_summary(response, config["model"])
            operation = ledger.operation(*ledger.active)
            self.phase = "diagnostic_write"
            exclusive_json(directory / "responses" / f"{ledger.active[1]}-{operation['attempts']}.json",
                           {"operation": ledger.active[1], "attempt": operation["attempts"],
                            "request_sha256": operation["request_sha256"], "summary": summary})
            self.phase = "scoring"
            return response

        self.guard = guard
        self.client = NS(chat=NS(completions=NS(create=create)))

    def predict(self, deployment, messages):
        self.phase, self.http_status = "input", None
        try:
            return super().predict(deployment, messages)
        except RetryableRejection:
            raise
        except Exception as error:
            reason = ("diagnostic_persistence_failed" if self.phase == "diagnostic_write" else
                      REASONS.get(str(error), "unclassified_error") if self.phase == "scoring"
                      else "unclassified_error")
            exclusive_json(self.directory / "failure-diagnostic.json", {
                "phase": self.phase, "reason": reason, "http_status": self.http_status,
                "model_requests": self.calls, "operation": self.ledger.active,
            })
            raise


def execute(root, review, directory):
    data = validate_review(root, review)
    config, authorization, binding, storage, examples = data[2][:5]
    tokenizer = Tokenizer(config["model"])
    records, rows = partition(root, cell_key(PILOT_PROJECT, PILOT_LEVEL, "text"), "validation")
    if len(records) < 20 or len(rows) < 20 or len({row["row_id"] for row in rows[:20]}) != 20:
        raise ControlError("The complete original 20-row smoke control is required.")
    (directory / "responses").mkdir()
    from azure.identity import AzureCliCredential
    from openai import OpenAI

    with ExitStack() as stack:
        store = InspectionStore(binding, SmokeBudget(REQUEST_LIMIT))
        stack.callback(store.close)
        store.authenticate()
        with AzureCliCredential(process_timeout=60) as credential:
            token = credential.get_token("https://cognitiveservices.azure.com/.default")
        if token.expires_on <= time.time() + 300:
            raise ControlError("Model token lifetime is too short; no lease or inference requested.")

        def cached_token():
            if token.expires_on <= time.time() + 120:
                raise ControlError("Model token expiring; no refresh under the lease.")
            return token.token

        store.verify_account()
        ledger = SmokeLedger(store, binding, storage["storage"],
                             remaining_credit=storage["remaining_credit_usd"],
                             access_expires=storage["expires_at"])
        ledger.bind(root, config)
        ledger.continuation_review, ledger.check_model_token = review, cached_token
        client = OpenAI(base_url=authorization["approval"]["endpoint"].rstrip("/") + "/openai/v1/",
                        api_key=cached_token, max_retries=0, timeout=60)
        stack.callback(client.close)
        backend = SmokeBackend(client, authorization["approval"], config, examples, ledger, directory)
        with ledger.session(requests=lambda: resolved_snapshot(ledger, data, review)):
            runner.smoke(root, config, ledger, backend, tokenizer)
            if any(ledger.operation(review["run"], name)["status"] != "succeeded" for name in OPERATIONS):
                raise ControlError("Smoke did not complete every remaining prediction.")
            if ledger.operation(review["run"], "smoke-0") != ledger.resolved_operation:
                raise ControlError("The accepted smoke-0 operation changed.")
            value = {"schema": "sufficiency-smoke-continuation-v1", "smoke_complete": True,
                     "resolved_sample_reused": True, "new_predictions": 21,
                     "model_requests": backend.calls, "review_sha256": digest(review),
                     "original_outcome": "UNKNOWN", "authorizes_validation": False}
    value["storage_requests_used"] = store.budget.used
    exclusive_json(directory / "continuation.json", value)
    return value


def main(argv=None):
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("template", "continue"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--resolution-review", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--review", type=Path)
    parser.add_argument("--execute-approved-continuation", action="store_true")
    args = parser.parse_args(argv)
    root = external_path(args.root)
    if args.stage == "template":
        if not args.resolution_review or not args.output or args.review or args.execute_approved_continuation:
            parser.error("Offline template requires --resolution-review and --output only.")
        output = external_path(args.output)
        if output == root or root in output.parents:
            parser.error("Keep the private template outside the preserved run.")
        exclusive_json(output, template(root, external_path(args.resolution_review)))
        print(json.dumps({"cloud_access": False, "checks_default_false": True}))
        return
    if not args.review or not args.execute_approved_continuation or args.resolution_review or args.output:
        parser.error("Continuation needs a separate --review and --execute-approved-continuation.")
    review = read_json(external_path(args.review))
    validate_review(root, review)
    directory = root / "jobs/continue-smoke"
    directory.mkdir(parents=True, exist_ok=True)
    exclusive_json(directory / "continuation.started", {"review_sha256": digest(review)})
    try:
        result = execute(root, review, directory)
    except Exception as error:
        exclusive_json(directory / "failure.json", {"error_type": type(error).__name__,
                                                   "cloud_access_may_have_occurred": True})
        raise
    print(json.dumps(result))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("SMOKE CONTINUATION STOPPED; preserve evidence and do not retry.", file=sys.stderr)
        raise SystemExit(1) from None
