"""Separately versioned, explicitly approved recovery of sealed prompt inference."""

from datetime import datetime
from pathlib import Path
import re
import sys
import time

TASK = Path(__file__).resolve().parent
FROZEN = TASK.parent / "train-openai-instability-within-project"
sys.path.insert(0, str(FROZEN))

from azure_backend import AzureBackend, ProviderError
from cloud_control import ControlError, Ledger, QUARANTINE_SCHEMA, ROOT
from cloud_control import SCHEMA, unexpired
from cost_control import check_approval, money
from failure_evidence import error_details
from protocol import BASE_SCHEMA, CELLS, cell_key, digest, file_hash, read_json, study_id

RECOVERY_SCHEMA = "azure-table-control-inference-recovery-v1"
REVIEW_SCHEMA = "sealed-inference-recovery-review-v1"
REPORT_SCHEMA = "openai-instability-prompt-recovery-report-v1"
CHECKS = (
    "old_workers_stopped", "private_failure_evidence_reviewed",
    "unknown_attempts_and_reservations_retained", "possible_duplicate_charge_accepted",
    "bounded_http500_retries_approved", "execution_policy_amendment_approved",
    "offline_sdk_tests_passed",
)


def implementation_hash():
    return digest({p.name: file_hash(p) for p in sorted(TASK.glob("*.py"))})


def timestamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class UncertainHTTP500(ProviderError):
    status_code = 500

    def __init__(self, details):
        super().__init__("HTTP 500; original outcome remains UNKNOWN.")
        self.details = details


class RecoveryBackend(AzureBackend):
    def predict(self, deployment, messages):
        from openai import APIStatusError

        try:
            return super().predict(deployment, messages)
        except ProviderError as error:
            # `raise ... from None` suppresses display, not the original context.
            cause = error.__context__
            if isinstance(cause, APIStatusError) and cause.status_code == 500:
                raise UncertainHTTP500(error_details(cause)) from None
            raise


class RecoveryLedger(Ledger):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.review = None
        self.allow_legacy = False
        self.captured = None

    def _root(self):
        state, etag = self.store.get(ROOT)
        if self.allow_legacy and state and state.get("schema") in (SCHEMA, QUARANTINE_SCHEMA):
            return super()._root()
        if (state is None or state.get("schema") != RECOVERY_SCHEMA
                or state.get("authority") != digest(self.binding)
                or state.get("storage") != self.plan or self.review is None
                or state.get("inference_recovery") != digest(self.review)):
            raise ControlError("Recovery authority, storage, or private review mismatch.")
        if state.get("quarantine") and state["training"] != state["quarantine"]["operation"]:
            raise ControlError("Original training quarantine changed.")
        if digest(state.get("quarantine")) != self.review["training_quarantine_sha256"]:
            raise ControlError("Original training quarantine evidence changed.")
        manifest, _ = self.store.get("inference-recovery:" + digest(self.review))
        if manifest != self.review:
            raise ControlError("Missing or altered immutable recovery manifest.")
        return state, etag

    @staticmethod
    def review_state(state):
        return Ledger.quarantine_state(state)

    def plan_review(self, root):
        state, _ = self._root()
        run = study_id(root)
        if state.get("inference_recovery") or state["pending"] is None or state["pending"][0] != run:
            raise ControlError("Expected this study's original unresolved inference.")
        name = state["pending"][1]
        op = self.operation(run, name)
        allocation = self.allocation(run)
        seal = self.artifact(run, "seal")
        if (not op or op["kind"] != "inference" or op["status"] != "dispatched"
                or not name.startswith("test-") or allocation["scope"] != "full"
                or not seal or set(seal["cells"]) != {cell_key(*cell) for cell in CELLS}):
            raise ControlError("Recovery requires a fully sealed prompt-only test study.")
        self._allow_operation(state, run, "inference", op["request"])
        config = read_json(root / "study.json")["config"]
        if config["schema"] != BASE_SCHEMA or config["request_attempts"] != 3:
            raise ControlError("Only the existing three-attempt prompt protocol is supported.")
        if (seal["study_sha256"] != digest(read_json(root / "study.json"))
                or seal["prepared_sha256"] != file_hash(root / "prepared.json")):
            raise ControlError("The original seal does not match the frozen study.")
        attempt, _ = self.store.get(self._key(run, f"{name}:{op['attempts']}", "attempt"))
        receipt, _ = self.store.get(self._key(run, f"{name}:{op['attempts']}", "receipt"))
        if receipt is not None:
            raise ControlError("A receipt exists; use exact receipt recovery instead.")
        if (not attempt or attempt["status"] != "dispatched" or op["attempts"] >= 3
                or attempt["request_sha256"] != op["request_sha256"]):
            raise ControlError("No unused attempt allowance for this dispatch.")
        return {
            "schema": REVIEW_SCHEMA, "authority_sha256": digest(self.binding),
            "run": run, "operation": name, "attempt": op["attempts"],
            "request_sha256": op["request_sha256"], "operation_sha256": digest(op),
            "attempt_sha256": digest(attempt), "allocation_sha256": digest(allocation),
            "state_sha256": digest(self.review_state(state)),
            "training_quarantine_sha256": digest(state.get("quarantine")),
            "study_sha256": digest(read_json(root / "study.json")),
            "prepared_sha256": file_hash(root / "prepared.json"),
            "seal_sha256": digest(seal), "implementation_sha256": implementation_hash(),
            "max_attempts": 3, "retry_http_statuses": [500], "expires_at": "",
            "http_status": None, "evidence_sha256": "",
            "checks": {key: False for key in CHECKS},
        }

    def validate_review(self, root, review):
        if (review.get("schema") != REVIEW_SCHEMA
                or review.get("authority_sha256") != digest(self.binding)
                or review.get("implementation_sha256") != implementation_hash()
                or review.get("run") != study_id(root)
                or review.get("study_sha256") != digest(read_json(root / "study.json"))
                or review.get("prepared_sha256") != file_hash(root / "prepared.json")
                or review.get("seal_sha256") != digest(self.artifact(review["run"], "seal"))
                or review.get("max_attempts") != 3 or review.get("retry_http_statuses") != [500]
                or review.get("http_status") != 500
                or not re.fullmatch(r"[a-f0-9]{64}", review.get("evidence_sha256", ""))
                or any(review.get("checks", {}).get(key) is not True for key in CHECKS)):
            raise ControlError("Exact, separately approved recovery evidence is required.")
        unexpired(review["expires_at"])
        allocation = self.allocation(review["run"])
        config = read_json(root / "study.json")["config"]
        check_approval(allocation["approval"], review["study_sha256"], config)
        if allocation["scope"] != "full" or config["request_attempts"] != 3:
            raise ControlError("Recovery requires the unchanged full allocation.")
        if any(timestamp(review["expires_at"]) > timestamp(expiry) for expiry in (
            self.access_expires, allocation["approval"]["expires_at"], self.plan["retention_until"]
        )):
            raise ControlError("Recovery expiry exceeds an existing approval.")

    def activate(self, root, review):
        self.review = review
        self.validate_review(root, review)
        state, etag = self._root()
        if state.get("inference_recovery"):
            return {"activated": True, "review_sha256": digest(review)}
        expected = self.plan_review(root)
        for key in (
            "run", "operation", "attempt", "request_sha256", "operation_sha256",
            "attempt_sha256", "allocation_sha256", "state_sha256", "seal_sha256",
            "training_quarantine_sha256",
        ):
            if review[key] != expected[key]:
                raise ControlError("Recovery review is stale; no dispatch was changed.")
        if state["breached"]:
            raise ControlError("A breach blocks recovery activation.")
        note = self.unknown_note(review["run"], review["operation"], review["attempt"],
                                 review["request_sha256"], {"http_status": 500},
                                 evidence=review["evidence_sha256"])
        state.update(schema=RECOVERY_SCHEMA, inference_recovery=digest(review))
        self._write(state, etag, [
            ("inference-recovery:" + digest(review), review, None),
            (self.unknown_key(review["run"], review["operation"], review["attempt"]), note, None),
        ])
        self.allow_legacy = False
        return {"activated": True, "review_sha256": digest(review)}

    def _allow_operation(self, state, run, kind, request=None):
        super()._allow_operation(state, run, kind, request)
        if state.get("schema") == RECOVERY_SCHEMA:
            if (self.review is None or run != self.review["run"] or kind != "inference"
                    or implementation_hash() != self.review["implementation_sha256"]):
                raise ControlError("Only the reviewed recovery implementation and study may dispatch.")
            unexpired(self.review["expires_at"])

    def dispatch(self, run, name, attempts):
        if not name.startswith("test-") or attempts != 3:
            raise ControlError("Recovery permits sealed tests with at most three total attempts.")
        number = super().dispatch(run, name, attempts)
        op = self.operation(run, name)
        self.captured = (run, name, number, op["request_sha256"], self.owner)
        return number

    def receipt(self, run, name, result, actual=None):
        if self.captured is None or self.captured[:2] != (run, name):
            raise ControlError("Receipt requires an exact captured dispatch.")
        _, _, number, request_hash, epoch = self.captured
        attempt, _ = self.store.get(self._key(run, f"{name}:{number}", "attempt"))
        if not attempt or attempt["request_sha256"] != request_hash or attempt["epoch"] != epoch:
            raise ControlError("Receipt dispatch identity changed.")
        key = self._key(run, f"{name}:{number}", "receipt")
        value = {"request_sha256": request_hash, "result": result,
                 "actual": str(money(actual)) if actual is not None else None}
        old, _ = self.store.get(key)
        if old is not None:
            if old != value:
                raise ControlError("Conflicting completion receipt.")
            return
        self.store.transaction([(key, value, None)])

    def finish(self, run, name, result, actual=None, terminal=False):
        state, etag = self._root()
        key = self._key(run, name)
        op, op_etag = self.store.get(key)
        if (terminal or self.captured is None or self.captured[:2] != (run, name)
                or op["attempts"] != self.captured[2]
                or op["request_sha256"] != self.captured[3]):
            raise ControlError("A stale attempt cannot finish a newer dispatch.")
        if op["status"] == "succeeded":
            if op["result"] != result:
                raise ControlError("Completion cannot replace a recorded result.")
            return
        if op["status"] != "dispatched" or state["pending"] != [run, name] or actual is None:
            raise ControlError("Completion requires the current dispatch and real token usage.")
        known, uncertain = money(actual), money("0")
        for number in range(1, op["attempts"]):
            old_attempt, _ = self.store.get(self._key(run, f"{name}:{number}", "attempt"))
            receipt, _ = self.store.get(self._key(run, f"{name}:{number}", "receipt"))
            if receipt is not None:
                if receipt["request_sha256"] != op["request_sha256"] or receipt["actual"] is None:
                    raise ControlError("Earlier receipt has inconsistent accounting.")
                known += money(receipt["actual"])
            elif old_attempt["status"] != "rejected-429":
                uncertain += money(op["reserved"]) / 3
        accounted = known + uncertain
        op.update(status="succeeded", result=result, actual_usd=str(known),
                  unknown_attempt_bound_usd=str(uncertain), accounted_bound_usd=str(accounted))
        attempt_key = self._key(run, f"{name}:{op['attempts']}", "attempt")
        attempt, attempt_etag = self.store.get(attempt_key)
        attempt.update(status="succeeded", result_sha256=digest(result))
        changes = [(attempt_key, attempt, attempt_etag)]
        breached = accounted > money(op["reserved"])
        if breached:
            allocation_key = "run:" + run
            allocation, allocation_etag = self.store.get(allocation_key)
            allocation["used"] = str(money(allocation["used"]) + accounted - money(op["reserved"]))
            op["reserved"] = str(accounted)
            state["breached"] = True
            changes.append((allocation_key, allocation, allocation_etag))
        state["pending"] = None
        self._write(state, etag, [*changes, (key, op, op_etag)])
        if breached:
            raise ControlError("Known usage plus unknown-attempt bounds exceeded the reservation; spending stopped.")

    def recover_receipt(self, run, name):
        op = self.operation(run, name)
        number = op["attempts"]
        attempt, _ = self.store.get(self._key(run, f"{name}:{number}", "attempt"))
        value, _ = self.store.get(self._key(run, f"{name}:{number}", "receipt"))
        if not value or value["request_sha256"] != op["request_sha256"]:
            raise ControlError("No exact receipt; do not fabricate completion.")
        self.captured = (run, name, number, op["request_sha256"], attempt["epoch"])
        self.finish(run, name, value["result"], value["actual"])
        return value["result"]

    def unknown_key(self, run, name, number):
        return self._key(run, f"{name}:{number}", "unknown")

    def unknown_note(self, run, name, number, request_hash, details, evidence=None):
        return {"run": run, "operation": name, "attempt": number,
                "request_sha256": request_hash, "outcome": "UNKNOWN",
                "review_sha256": digest(self.review), "error": details,
                "evidence_sha256": evidence}

    def mark_unknown(self, run, name, details):
        state, etag = self._root()
        op = self.operation(run, name)
        if (self.captured is None or self.captured[:4] != (
            run, name, op["attempts"], op["request_sha256"]
        ) or state["pending"] != [run, name]):
            raise ControlError("Unknown outcome belongs to a different attempt.")
        key = self.unknown_key(run, name, op["attempts"])
        note = self.unknown_note(run, name, op["attempts"], op["request_sha256"], details)
        old, _ = self.store.get(key)
        if old is not None:
            if old != note:
                raise ControlError("Unknown outcome evidence changed.")
            return
        self._write(state, etag, [(key, note, None)])

    def retry_unknown(self, run, name):
        state, etag = self._root()
        self._allow_operation(state, run, "inference")
        op, op_etag = self.store.get(self._key(run, name))
        receipt, _ = self.store.get(self._key(run, f"{name}:{op['attempts']}", "receipt"))
        if receipt is not None:
            return self.recover_receipt(run, name)
        note, _ = self.store.get(self.unknown_key(run, name, op["attempts"]))
        if (state["breached"] or state["pending"] != [run, name]
                or op["status"] != "dispatched" or op["attempts"] >= 3
                or not note or note["request_sha256"] != op["request_sha256"]
                or note["review_sha256"] != digest(self.review)
                or note["error"].get("http_status") != 500):
            raise ControlError("No approved unused HTTP-500 retry; pending outcome retained.")
        grant = {
            "run": run, "operation": name, "unknown_attempt": op["attempts"],
            "next_attempt": op["attempts"] + 1, "request_sha256": op["request_sha256"],
            "review_sha256": digest(self.review), "unknown_note_sha256": digest(note),
            "operation_before_sha256": digest(op), "reserved_usd_retained": op["reserved"],
        }
        op["status"] = "prepared"
        state["pending"] = None
        self._write(state, etag, [
            (self._key(run, name), op, op_etag),
            (self._key(run, f"{name}:{op['attempts']}", "retry-grant"), grant, None),
        ])
        return None

    def perform(self, run, name, amount, kind, request, call, actual=None,
                attempts=1, recovery=False):
        if kind != "inference" or recovery or attempts != 3:
            raise ControlError("Recovery runner only executes bounded test inference.")
        while True:
            op = self.operation(run, name)
            if op and op["status"] == "dispatched":
                saved = self.retry_unknown(run, name)
                if saved is not None:
                    return saved
                time.sleep(min(2 ** op["attempts"], 8))
            try:
                return super().perform(run, name, amount, kind, request, call, actual, attempts)
            except UncertainHTTP500 as error:
                self.mark_unknown(run, name, error.details)
                # The next iteration consumes a durable retry grant, never resetting money.

    def audit(self, root):
        state, etag = self._root()
        run = study_id(root)
        notes = self.store.query(f"unknown:{run}:")
        grants = self.store.query(f"retry-grant:{run}:")
        for note in notes.values():
            op = self.operation(run, note["operation"])
            if (note["review_sha256"] != digest(self.review)
                    or op is None or note["request_sha256"] != op["request_sha256"]
                    or note["attempt"] > op["attempts"]):
                raise ControlError("Recovery audit differs from the original attempt evidence.")
        for grant in grants.values():
            note = notes.get(self.unknown_key(run, grant["operation"], grant["unknown_attempt"]))
            if (note is None or grant["unknown_note_sha256"] != digest(note)
                    or grant["review_sha256"] != digest(self.review)):
                raise ControlError("Retry grant has no matching unknown-attempt evidence.")
        if self._root()[1] != etag:
            raise ControlError("Recovery audit changed during export.")
        return {
            "review": self.review, "review_sha256": digest(self.review),
            "unknown_attempts": list(notes.values()),
            "retry_grants": list(grants.values()),
            "original_study_sha256": digest(read_json(root / "study.json")),
            "seal_sha256": digest(self.artifact(run, "seal")),
            "scientific_protocol_unchanged": True, "execution_policy_amended": True,
            "possible_duplicate_charges": True, "actual_cost_complete": False,
            "pending": state["pending"],
        }
