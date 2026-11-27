"""Lease-safe execution of one separately reviewed sufficiency evaluation stage."""

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
SUFFICIENCY = TASK.parent / "evaluate-openai-story-sufficiency"
sys.path.insert(0, str(SUFFICIENCY))
from sufficiency import check_approval, demonstrations, frozen_study
from backend import SufficiencyBackend
from cloud_control import ControlError, RequestBudget, RetryableRejection, access_at, binding_at, unexpired
from cost_control import control_requests, estimate, money
from ledger import SufficiencyLedger
from protocol import CELLS, PILOT, cell_key, digest, external_path, file_hash, read_json, slug, study_id
from renew_storage import validate as validate_storage

sys.path.insert(0, str(TASK.parent / "recover-openai-sufficiency-smoke"))
from diagnostics import REASONS, response_summary
from inspection_auth import InspectionStore
from one_shot import exclusive_json, implementation_hash as diagnostic_implementation_hash

spec = importlib.util.spec_from_file_location("lease_safe_sufficiency_core", SUFFICIENCY / "run_experiment.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)

STAGES = ("preflight", "validate", "seal", "test", "report")
SCHEMA = "sufficiency-evaluation-review-v1"
CHECKS = (
    "old_workers_stopped_and_prior_job_outcome_reviewed",
    "exact_stage_scope_and_request_limits_approved",
    "pilot_review_and_allocation_change_reviewed_if_preflight",
    "frozen_data_and_selection_gates_preserved",
    "verified_429_only_three_attempt_policy",
    "unknown_and_all_reservations_retained",
    "current_credit_and_storage_reviewed",
    "one_job_only_no_stage_chaining",
)


def implementation_hash():
    return digest({path.name: file_hash(path) for path in sorted(TASK.glob("*.py"))})


def inputs(root, stage, approval_path=None):
    if stage not in STAGES or (stage == "preflight") != (approval_path is not None):
        raise ControlError("Only preflight takes a separate model approval.")
    config = frozen_study(root)
    path = external_path(approval_path) if approval_path is not None else root / "authorization.json"
    value = read_json(path)
    approval = value if stage == "preflight" else value["approval"]
    check_approval(approval, digest(read_json(root / "study.json")), config)
    binding = binding_at()
    storage = access_at(binding)
    validate_storage(storage, binding, root)
    if (approval["authority_sha256"] != digest(binding)
            or money(approval["storage_reserve_usd"]) != money(storage["storage"]["reserve_usd"])
            or config["request_attempts"] != 3):
        raise ControlError("Model, authority, Storage or retry policy changed.")
    if stage in ("seal", "test") and approval["scope"] != "full":
        raise ControlError("Sealing and final test require full-scope model approval.")
    prepared = read_json(root / "prepared.json")
    if stage != "preflight" and value["prepared_sha256"] != file_hash(root / "prepared.json"):
        raise ControlError("Preparation differs from model authorization.")
    return config, approval, binding, storage, prepared, path


def template(root, stage, label, approval_path=None):
    config, approval, binding, storage, prepared, path = inputs(root, stage, approval_path)
    maximum_rows = config["batch_rows"] if stage in ("validate", "test") else 0
    allocation = estimate(prepared, config, approval)[approval["scope"]] if stage == "preflight" else None
    return {
        "schema": SCHEMA, "stage": stage, "job_label": slug(label), "run": study_id(root),
        "study_sha256": digest(read_json(root / "study.json")),
        "prepared_sha256": file_hash(root / "prepared.json"), "model_review_path": str(path),
        "model_review_sha256": file_hash(path), "scope": approval["scope"],
        "authority_sha256": digest(binding), "storage_approval_sha256": digest(storage),
        "implementation_sha256": implementation_hash(),
        "diagnostic_helpers_sha256": diagnostic_implementation_hash(),
        "authentication_helper_sha256": file_hash(TASK.parent / "recover-openai-sufficiency-smoke/inspection_auth.py"),
        "max_predictions": maximum_rows, "max_model_requests": maximum_rows * config["request_attempts"],
        "retry_http_statuses": [429], "next_authoritative_batch_only": True,
        "preflight_scope_bound_including_storage_usd": allocation,
        "storage_request_limit": control_requests(stage, prepared, config, approval["scope"]),
        "storage_sessions": 1, "token_acquisitions": 3 if stage in ("preflight", "validate", "test") else 2,
        "remaining_credit_usd": "0", "expires_at": "", "execution_approved": False,
        "checks": {key: False for key in CHECKS},
    }


def validate_review(root, review):
    path = external_path(review["model_review_path"]) if review["stage"] == "preflight" else None
    expected = template(root, review["stage"], review["job_label"], path)
    editable = {"remaining_credit_usd", "expires_at", "execution_approved", "checks"}
    if (set(review) != set(expected)
            or any(review[key] != value for key, value in expected.items() if key not in editable)
            or review["execution_approved"] is not True or set(review["checks"]) != set(CHECKS)
            or any(review["checks"][key] is not True for key in CHECKS)):
        raise ControlError("A separate exact evaluation-job review is required.")
    unexpired(review["expires_at"])
    data = inputs(root, review["stage"], path)
    expiry = datetime.fromisoformat(review["expires_at"].replace("Z", "+00:00"))
    if any(expiry > datetime.fromisoformat(value.replace("Z", "+00:00")) for value in (
        data[1]["expires_at"], data[3]["expires_at"], data[3]["storage"]["retention_until"],
    )):
        raise ControlError("Evaluation approval cannot outlive existing approvals.")
    if money(review["remaining_credit_usd"]) <= money(data[0]["credit_reserve_usd"]):
        raise ControlError("Current reviewed credit is required.")
    return data


def queued_review(root, path, stage, label):
    review = read_json(path)
    validate_review(root, review)
    if review["stage"] != stage or review["job_label"] != label:
        raise ControlError("Queued stage/label differs from the private review.")
    return {"review_path": str(path), "review_sha256": file_hash(path),
            "implementation_sha256": implementation_hash()}


class EvaluationLedger(SufficiencyLedger):
    def authorize(self, run, approval, estimate_value, config, evidence=None):
        unexpired(self.review["expires_at"])
        if self.review["stage"] != "preflight" or approval != self.approval:
            raise ControlError("Only separately reviewed preflight may change model allocation.")
        return super().authorize(run, approval, estimate_value, config, evidence)

    def begin(self, run, name, amount, kind, request, recovery=False):
        split = {"validate": "validation", "test": "test"}.get(self.review["stage"])
        if split is None or recovery or kind != "inference":
            raise ControlError("Only this reviewed evaluation split may predict.")
        identity = None
        for key in self.cells:
            prefix = f"{split}-{key}-"
            index = name[len(prefix):] if name.startswith(prefix) else ""
            if index.isdigit() and 0 <= int(index) < self.prepared["entries"][key]["partitions"][split]["rows"]:
                identity = (key, int(index) // self.config["batch_rows"])
                break
        if identity is None or (self.batch is not None and identity != self.batch):
            raise ControlError("Prediction is outside the approved single-cell batch.")
        self.batch = identity
        self.seen.add(name)
        if len(self.seen) > self.review["max_predictions"]:
            raise ControlError("Reviewed prediction count exhausted.")
        return super().begin(run, name, amount, kind, request, recovery)

    def dispatch(self, run, name, attempts):
        if name not in self.seen or attempts != 3:
            raise ControlError("Dispatch lacks a reviewed bounded evaluation operation.")
        unexpired(self.review["expires_at"])
        self.check_model_token()
        return super().dispatch(run, name, attempts)

    def record(self, run, name, value):
        unexpired(self.review["expires_at"])
        stage = self.review["stage"]
        allowed = stage == "seal" and name == "seal"
        split = {"validate": "validation", "test": "test"}.get(stage)
        if split:
            allowed = any(
                name == f"{split}-{key}" or (
                    name.startswith(f"batch-{split}-{key}-")
                    and name[len(f"batch-{split}-{key}-"):].isdigit()
                ) for key in self.cells
            )
        if not allowed:
            raise ControlError("This job cannot write another stage's scientific artifact.")
        return super().record(run, name, value)


def claim_job(ledger, review):
    unexpired(review["expires_at"])
    state, etag = ledger._root()
    credit = min(money(review["remaining_credit_usd"]), ledger.remaining_credit,
                 money(ledger.approval["remaining_credit_usd"]))
    if (state["pending"] is not None or state["breached"]
            or money(state["total"]) + money(state["storage"]["reserve_usd"])
            + money(ledger.config["credit_reserve_usd"]) > credit):
        raise ControlError("Pending outcome, breach or current credit blocks evaluation.")
    key = ledger._key(ledger.run, review["stage"] + ":" + review["job_label"], "sufficiency-evaluation-job")
    if ledger.store.get(key)[0] is not None:
        raise ControlError("This evaluation label was already consumed; never replay it.")
    ledger._write(state, etag, [(key, {"review": review, "epoch": ledger.owner}, None)])
    return key


class EvaluationBackend(SufficiencyBackend):
    def __init__(self, client, http, credential, approval, config, examples, ledger, directory):
        self.approval, self.config, self.http, self.credential = approval, config, http, credential
        self.ledger, self.directory = ledger, directory
        self.systems = {entry["system"]: (entry["project"], entry["variant"]) for entry in examples.values()}
        self.calls = 0

        def guard():
            self.phase = "guard"
            unexpired(ledger.review["expires_at"])
            ledger.guard_remote()

        def create(**kwargs):
            if (self.calls >= ledger.review["max_model_requests"] or ledger.active is None
                    or ledger.active[1] not in ledger.seen):
                raise ControlError("Evaluation request scope exhausted.")
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
        self.client = NS(chat=NS(completions=NS(create=create)), models=client.models)

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
    config, approval, binding, storage, prepared, _ = validate_review(root, review)
    stage, network_backend = review["stage"], review["token_acquisitions"] == 3
    examples = demonstrations(root) if network_backend else None
    (directory / "responses").mkdir()
    with ExitStack() as stack:
        store = InspectionStore(binding, RequestBudget(review["storage_request_limit"]))
        stack.callback(store.close)
        store.authenticate()
        backend, token = None, None
        if network_backend:
            from azure.identity import AzureCliCredential
            from openai import OpenAI
            import httpx

            with AzureCliCredential(process_timeout=60) as credential:
                token = credential.get_token("https://cognitiveservices.azure.com/.default")
            if token.expires_on <= time.time() + 300:
                raise ControlError("Model token lifetime too short; no lease or inference requested.")

        def cached_token():
            if token is None or token.expires_on <= time.time() + 120:
                raise ControlError("Model token unavailable or expiring; no refresh under the lease.")
            return token.token

        store.verify_account()
        ledger = EvaluationLedger(store, binding, storage["storage"],
                                  remaining_credit=min(money(storage["remaining_credit_usd"]),
                                                       money(review["remaining_credit_usd"])),
                                  access_expires=storage["expires_at"])
        ledger.bind(root, config)
        ledger.review, ledger.approval, ledger.prepared = review, approval, prepared
        ledger.cells = {cell_key(*cell) for cell in (PILOT if approval["scope"] == "pilot" else CELLS)}
        ledger.batch, ledger.seen, ledger.check_model_token = None, set(), cached_token
        if network_backend:
            client = OpenAI(base_url=approval["endpoint"].rstrip("/") + "/openai/v1/",
                            api_key=cached_token, max_retries=0, timeout=60)
            stack.callback(client.close)
            http = httpx.Client(timeout=60, follow_redirects=False)
            stack.callback(http.close)
            backend = EvaluationBackend(client, http, store.credential, approval, config, examples, ledger, directory)
        with ledger.session(requests=lambda: review["storage_request_limit"]):
            key = claim_job(ledger, review)
            if stage == "preflight":
                runner.core.preflight(root, config, approval, ledger, backend)
                result = {"authorized_scope": approval["scope"]}
            else:
                authorization = runner.core.authorized(root, config, ledger)
                if authorization["approval"] != approval:
                    raise ControlError("Cloud model approval differs from this job's review.")
                if stage == "seal":
                    runner.core.seal(root, ledger)
                    result = {"sealed": True}
                elif stage == "report":
                    result = runner.report(root, ledger)
                else:
                    result = runner.evaluate(root, config, ledger, backend,
                                             "validation" if stage == "validate" else "test")
            value = {"schema": "sufficiency-evaluation-job-result-v1", "stage": stage,
                     "job_label": review["job_label"], "scope": approval["scope"],
                     "review_sha256": digest(review), "result": result,
                     "model_requests": backend.calls if backend else 0,
                     "authorizes_next_job": False}
            ledger.renew()
            state, etag = ledger._root()
            grant, grant_etag = store.get(key)
            if grant != {"review": review, "epoch": ledger.owner}:
                raise ControlError("Evaluation ownership or job grant changed.")
            ledger._write(state, etag, [(key, {**grant, "result": value}, grant_etag)])
    value["storage_requests_used"] = store.budget.used
    exclusive_json(directory / "result.json", value)
    return value


def main(argv=None):
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("template", "execute"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--stage", choices=STAGES)
    parser.add_argument("--job-label")
    parser.add_argument("--approval", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--review", type=Path)
    parser.add_argument("--execute-approved-evaluation", action="store_true")
    args = parser.parse_args(argv)
    root = external_path(args.root)
    if args.command == "template":
        if not args.stage or not args.job_label or not args.output or args.review or args.execute_approved_evaluation:
            parser.error("Offline template requires --stage, --job-label and --output.")
        output = external_path(args.output)
        if output == root or root in output.parents:
            parser.error("Keep the private review outside the preserved run.")
        exclusive_json(output, template(root, args.stage, args.job_label, args.approval))
        print(json.dumps({"cloud_access": False, "checks_default_false": True}))
        return
    if not args.review or not args.execute_approved_evaluation or any((
        args.stage, args.job_label, args.approval, args.output,
    )):
        parser.error("Execution requires a private --review and --execute-approved-evaluation only.")
    review = read_json(external_path(args.review))
    validate_review(root, review)
    directory = root / "jobs" / f"eval-{review['stage']}-{review['job_label']}"
    directory.mkdir(parents=True, exist_ok=True)
    exclusive_json(directory / "evaluation.started", {"review_sha256": digest(review)})
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
        print("EVALUATION STOPPED; preserve evidence and do not resubmit automatically.", file=sys.stderr)
        raise SystemExit(1) from None
