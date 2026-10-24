"""Fail-closed, single-partition control plane. Importing this module is offline."""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import re
import threading
import time
import uuid

from cost_control import CONTROL, money
from protocol import TASK, digest, read_json

SCHEMA = "azure-table-control-v1"
ROOT = "root"
LEASE_SECONDS = 60
MAX_VALUE_BYTES = 60000


class ControlError(ValueError):
    """Safe-to-log control failure; never contains a provider response body."""


class Conflict(ControlError):
    pass


class RetryableRejection(ControlError):
    """The provider explicitly rejected an inference attempt (HTTP 429 only)."""

    def __init__(self, delay):
        super().__init__("Inference throttled; bounded retry requires a new durable attempt.")
        self.delay = delay


def encoded(value):
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if len(text.encode("utf-16-le")) > MAX_VALUE_BYTES:
        raise ControlError("Control record exceeds the reviewed entity size bound.")
    return text


def unexpired(value):
    expiry = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if expiry.tzinfo is None or expiry <= datetime.now(timezone.utc):
        raise ControlError("Storage access approval expired; renew it before cloud access.")


def binding_at():
    value = read_json(TASK / "control_store.json")
    if value.get("schema") != SCHEMA or value.get("experiment") != "master-openai-instability":
        raise ControlError("Unsupported cloud authority.")
    match = re.fullmatch(
        r"/subscriptions/[0-9a-fA-F-]{36}/resourceGroups/[A-Za-z0-9_.()-]+"
        r"/providers/Microsoft.Storage/storageAccounts/([a-z0-9]{3,24})",
        value.get("storage_resource_id", ""),
    )
    if not match or not re.fullmatch(r"[A-Za-z][A-Za-z0-9]{2,62}", value.get("table", "")):
        raise ControlError("Cloud control is unbound; separately approved storage setup is required.")
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{1,61}[a-z0-9])", value.get("container", "")):
        raise ControlError("Invalid private control container.")
    try:
        uuid.UUID(value["authority_id"])
    except (ValueError, KeyError) as error:
        raise ControlError("A fixed bootstrap UUID is required.") from error
    if not value.get("resource_id") or not value.get("endpoint"):
        raise ControlError("Cloud authority must pin the Azure OpenAI billing target.")
    return value


def storage_plan(value):
    """Conservative all-requests-at-highest-meter worksheet, including bootstrap."""
    for key in ("max_requests", "session_requests", "max_sessions", "session_seconds"):
        if type(value.get(key)) is not int or value[key] <= 0:
            raise ControlError("Storage request, session and runtime bounds must be positive integers.")
    if value["session_requests"] < 100 or value["session_seconds"] > 14400:
        raise ControlError("Storage sessions need at least 100 requests and at most four hours.")
    if value["max_requests"] < value["session_requests"] + 100:
        raise ControlError("Storage worksheet must cover a session and 100 bootstrap requests.")
    if money(value["request_usd"]) <= 0 or money(value["margin"]) < money("1.25"):
        raise ControlError("Verified storage request pricing and a 25% margin are required.")
    for key in ("bootstrap_usd", "capacity_usd", "transfer_usd", "reserve_usd"):
        if money(value[key]) <= 0:
            raise ControlError("Reserve capacity, transfers and storage explicitly; do not assume free tiers.")
    bound = money(value["margin"]) * (
        value["max_requests"] * money(value["request_usd"])
        + money(value["bootstrap_usd"]) + money(value["capacity_usd"]) + money(value["transfer_usd"])
    )
    if bound > money(value["reserve_usd"]) or money(value["reserve_usd"]) >= money("80"):
        raise ControlError("Storage reserve does not cover its worksheet within the experiment cap.")
    if not value.get("evidence") or not value.get("retention_until"):
        raise ControlError("Storage price/size/transfer evidence and retention deadline are required.")
    unexpired(value["retention_until"])
    return value


def access_at(binding):
    value = read_json(CONTROL / "cloud-approval.json")
    if value.get("authority_sha256") != digest(binding):
        raise ControlError("Private storage approval differs from the fixed authority.")
    unexpired(value["expires_at"])
    if value.get("scope") not in ("pilot", "full"):
        raise ControlError("Storage approval must explicitly name pilot or full scope.")
    if any(value.get("checks", {}).get(key) is not True for key in (
        "zero_use_migration_verified", "old_workers_stopped", "storage_rates_verified",
        "credit_covers_storage", "private_storage_verified", "spending_limit_enabled",
    )):
        raise ControlError("Storage setup, migration and cost approval is incomplete.")
    storage_plan(value["storage"])
    if value["scope"] == "pilot" and money(value["storage"]["reserve_usd"]) >= money("7"):
        raise ControlError("Pilot storage reserve must leave room under $7 for model work.")
    if money(value["remaining_credit_usd"]) < money(value["storage"]["reserve_usd"]) + money("20"):
        raise ControlError("Storage approval cannot cover its reserve plus the protected $20.")
    return value


class RequestBudget:
    def __init__(self, limit):
        self.limit, self.used = limit, 0
        self.lock = threading.Lock()

    def charge(self, count=1):
        with self.lock:
            if self.used + count > self.limit:
                raise ControlError("Storage session request allowance exhausted; no automatic extension.")
            self.used += count

    def require_tail(self, minimum=30):
        with self.lock:
            if self.limit - self.used < minimum:
                raise ControlError("Storage allowance reserved for completion; stop before another dispatch.")


class AzureStore:
    """Small transport surface, also implemented by the offline fault-injection store."""

    def __init__(self, binding, budget):
        from azure.data.tables import TableClient
        from azure.identity import DefaultAzureCredential
        from azure.storage.blob import BlobClient

        self.binding, self.budget = binding, budget
        self.partition = binding["experiment"]
        account = binding["storage_resource_id"].rsplit("/", 1)[1]
        self.credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)
        options = {"retry_total": 0, "connection_timeout": 5, "read_timeout": 10}
        self.table = TableClient(
            f"https://{account}.table.core.windows.net", binding["table"],
            credential=self.credential, **options,
        )
        self.blob = BlobClient(
            f"https://{account}.blob.core.windows.net", binding["container"], "coordinator",
            credential=self.credential, **options,
        )

    def entity(self, key, value):
        return {"PartitionKey": self.partition, "RowKey": key, "value": encoded(value)}

    def verify_account(self):
        import httpx

        token = self.credential.get_token("https://management.azure.com/.default").token
        with httpx.Client(timeout=20, follow_redirects=False) as client:
            response = client.get(
                "https://management.azure.com" + self.binding["storage_resource_id"],
                params={"api-version": "2023-05-01"},
                headers={"Authorization": "Bearer " + token},
            )
        if response.status_code != 200:
            raise ControlError("Cannot verify the approved storage account using scoped management access.")
        account = response.json()
        properties = account["properties"]
        name = self.binding["storage_resource_id"].rsplit("/", 1)[1]
        endpoints = properties["primaryEndpoints"]
        services = properties["encryption"]["services"]
        if not isinstance(services, dict):
            raise ControlError("Storage encryption service metadata is malformed.")
        table = services.get("table")
        # ARM omits Table settings for the default Microsoft-managed service key.
        service_key = "table" not in services or (
            isinstance(table, dict) and table.get("keyType") == "Service"
            and ("enabled" not in table or table["enabled"] is True)
        )
        if (account["id"].casefold() != self.binding["storage_resource_id"].casefold()
                or account["kind"] != "StorageV2" or account["sku"]["name"] != "Standard_ZRS"
                or properties.get("accessTier") != "Hot"
                or properties.get("allowBlobPublicAccess") is not False
                or properties.get("allowSharedKeyAccess") is not False
                or properties.get("supportsHttpsTrafficOnly") is not True
                or properties.get("isHnsEnabled", False)
                or properties["encryption"]["keySource"] != "Microsoft.Storage"
                or not service_key
                or endpoints["table"].rstrip("/") != f"https://{name}.table.core.windows.net"
                or endpoints["blob"].rstrip("/") != f"https://{name}.blob.core.windows.net"):
            raise ControlError("Storage account identity, SKU, encryption, or access policy differs from the reviewed design.")
        return {"storage_account_verified": True, "storage_location": account["location"]}

    def get(self, key):
        from azure.core.exceptions import ResourceNotFoundError

        self.budget.charge()
        try:
            entity = self.table.get_entity(self.partition, key)
        except ResourceNotFoundError as error:
            if getattr(error, "error_code", None) == "TableNotFound":
                raise ControlError("Control table is missing; never create a replacement implicitly.") from None
            return None, None
        return json.loads(entity["value"]), entity.metadata["etag"]

    def transaction(self, changes):
        from azure.core import MatchConditions
        from azure.core.exceptions import HttpResponseError

        if not changes or len(changes) > 100 or len({key for key, _, _ in changes}) != len(changes):
            raise ControlError("Invalid bounded control transaction.")
        operations = []
        payload_bytes = 0
        for key, value, etag in changes:
            entity = self.entity(key, value)
            payload_bytes += len(json.dumps(entity).encode()) + 4096
            operations.append(("create", entity) if etag is None else (
                "update", entity, {"mode": "replace", "etag": etag,
                                   "match_condition": MatchConditions.IfNotModified}))
        if payload_bytes > 4 * 1024 * 1024:
            raise ControlError("Control transaction exceeds its payload bound.")
        self.budget.charge(len(changes))
        try:
            self.table.submit_transaction(operations)
        except HttpResponseError as error:
            if error.status_code in (409, 412):
                raise Conflict("Conditional control transaction conflicted; no call was dispatched.") from None
            raise ControlError("Control transaction failed or its response is unknown; reconcile before proceeding.") from None

    def query(self, prefix):
        pages = self.table.query_entities(
            "PartitionKey eq @p and RowKey ge @lo and RowKey lt @hi",
            parameters={"p": self.partition, "lo": prefix, "hi": prefix + "~"},
            results_per_page=100,
        ).by_page()
        result = {}
        while True:
            self.budget.charge()
            try:
                page = next(pages)
            except StopIteration:
                return result
            for entity in page:
                result[entity["RowKey"]] = json.loads(entity["value"])

    def acquire(self):
        self.budget.charge()
        return self.blob.acquire_lease(lease_duration=LEASE_SECONDS)

    def renew(self, lease):
        self.budget.charge()
        lease.renew()

    def release(self, lease):
        self.budget.charge()
        lease.release()

    def close(self):
        self.table.close()
        self.blob.close()
        self.credential.close()


def initial_state(binding, plan):
    storage_plan(plan)
    if money(plan["reserve_usd"]) >= money("7"):
        raise ControlError("Initial storage reserve exceeds the pilot cap.")
    return {"schema": SCHEMA, "authority": digest(binding), "storage": plan,
            "total": "0", "pilot_total": "0", "breached": False, "epoch": None, "pending": None,
            "training": None, "deployment": None, "deployment_sequence": 0,
            "sessions": 0, "io_reserved": 100, "probe_atomic": False, "probe_verified": False,
            "storage_scope": "pilot"}


class Ledger:
    def __init__(self, store, binding, plan, remaining_credit, clock=time.monotonic, access_expires=None):
        self.store, self.binding, self.plan, self.clock = store, binding, plan, clock
        self.owner, self.lease, self.lost = None, None, False
        self.deadline, self.session_deadline = 0, 0
        self.stop = threading.Event()
        self.renew_lock = threading.Lock()
        self.active = None
        self.access_expires = access_expires or plan["retention_until"]
        self.remaining_credit = money(remaining_credit)

    @classmethod
    def configured(cls):
        binding = binding_at()
        approval = access_at(binding)
        plan = approval["storage"]
        return cls(AzureStore(binding, RequestBudget(plan["session_requests"])), binding, plan,
                   access_expires=approval["expires_at"], remaining_credit=approval["remaining_credit_usd"])

    def _root(self):
        value, etag = self.store.get(ROOT)
        if value is None or value.get("schema") != SCHEMA or value.get("authority") != digest(self.binding):
            raise ControlError("Missing or mismatched cloud authority; explicit bootstrap is required.")
        if value["storage"] != self.plan:
            raise ControlError("Storage allowance differs from the bootstrapped authority.")
        return value, etag

    def check(self):
        unexpired(self.access_expires)
        if (self.owner is None or self.lost or self.clock() >= self.deadline
                or self.clock() >= self.session_deadline):
            self.lost = True
            raise ControlError("Coordinator lease lost/expired; this process cannot resume paid work.")

    def renew(self):
        with self.renew_lock:
            self.check()
            unexpired(self.plan["retention_until"])
            start = self.clock()
            try:
                self.store.renew(self.lease)
            except Exception as error:
                self.lost = True
                raise ControlError("Coordinator renewal unconfirmed; stop and reconcile.") from error
            self.check()
            self.deadline = start + LEASE_SECONDS - 10

    def _heartbeat(self):
        while not self.stop.wait(20):
            try:
                self.renew()
            except ControlError:
                # The sticky lost flag is checked by every transition and dispatch.
                self.lost = True
                self.stop.set()

    @contextmanager
    def session(self, requests=None):
        if self.owner is not None or self.lost or self.stop.is_set():
            raise ControlError("Use a fresh coordinator process for each session.")
        start = self.clock()
        self.lease = self.store.acquire()
        self.owner = uuid.uuid4().hex
        self.deadline = start + LEASE_SECONDS - 10
        self.session_deadline = start + self.plan["session_seconds"]
        thread = None
        try:
            state, etag = self._root()
            if money(state["total"]) + money(self.plan["reserve_usd"]) + money("20") > self.remaining_credit:
                raise ControlError("Current storage approval cannot cover global reservations plus protected credit.")
            allowance = requests() if requests is not None else self.plan["session_requests"]
            if type(allowance) is not int or not 100 <= allowance <= self.plan["session_requests"]:
                raise ControlError("Command I/O envelope exceeds the reviewed per-session allowance.")
            self.store.budget.limit = allowance
            if state["sessions"] >= self.plan["max_sessions"]:
                raise ControlError("Approved storage session count exhausted.")
            reserved = state["io_reserved"] + allowance
            if reserved > self.plan["max_requests"]:
                raise ControlError("Approved cumulative storage request allowance exhausted.")
            state.update(epoch=self.owner, sessions=state["sessions"] + 1, io_reserved=reserved)
            self.check()
            self.store.transaction([(ROOT, state, etag)])
            # Acquisition and startup I/O can consume most of the initial lease.
            self.renew()
            thread = threading.Thread(target=self._heartbeat, name="control-lease")
            thread.start()
            yield self
        finally:
            self.stop.set()
            if thread is not None:
                thread.join()
            self.owner = None
            self.store.release(self.lease)

    def close(self):
        self.store.close()

    def _write(self, state, etag, changes=()):
        self.check()
        if state["epoch"] != self.owner:
            self.lost = True
            raise ControlError("Stale coordinator epoch; authoritative state is fenced.")
        self.store.transaction([(ROOT, state, etag), *changes])

    def guard_remote(self):
        self.store.budget.require_tail()
        self.renew()
        state, _ = self._root()
        self.check()
        if state["epoch"] != self.owner or self.active is None or state["pending"] != list(self.active):
            raise ControlError("External mutation lacks a current durable dispatch intent.")
        operation = self.operation(*self.active)
        if operation["kind"] not in ("cancel", "delete"):
            if state["breached"]:
                raise ControlError("Global cost bound breached; paid work is stopped.")
            unexpired(self.allocation(self.active[0])["approval"]["expires_at"])
        unexpired(self.plan["retention_until"])

    @staticmethod
    def _key(run, name, kind="op"):
        return f"{kind}:{run}:{digest(name)}"

    def allocation(self, run):
        return self.store.get("run:" + run)[0]

    def operation(self, run, name):
        return self.store.get(self._key(run, name))[0]

    def operations(self, run):
        return list(self.store.query(f"op:{run}:").values())

    def read(self):
        state, _ = self._root()
        return {"runs": {key[4:]: value for key, value in self.store.query("run:").items()},
                "breached": state["breached"]}

    def artifact(self, run, name):
        value, _ = self.store.get(self._key(run, name, "artifact"))
        return value["value"] if value is not None else None

    def record(self, run, name, value):
        state, etag = self._root()
        key = self._key(run, name, "artifact")
        previous, _ = self.store.get(key)
        if previous is not None:
            if previous["value"] != value:
                raise ControlError("Cloud artifact differs; provenance cannot be overwritten.")
            return
        self._write(state, etag, [(key, {"value": value}, None)])

    def require_capacity(self, envelope):
        state, _ = self._root()
        if (state["io_reserved"] + envelope["requests"] > self.plan["max_requests"]
                or state["sessions"] + envelope["sessions"] > self.plan["max_sessions"]
                or envelope["max_session_requests"] > self.plan["session_requests"]):
            raise ControlError("Storage allowance cannot cover the complete scope's command envelopes.")

    def authorize(self, run, approval, estimate_value, config, evidence=None):
        state, etag = self._root()
        if not state["probe_verified"]:
            raise ControlError("The separately approved two-node Storage probe has not completed.")
        storage = money(state["storage"]["reserve_usd"])
        if (approval["authority_sha256"] != state["authority"]
                or money(approval["storage_reserve_usd"]) != storage
                or approval["resource_id"] != self.binding["resource_id"]
                or approval["endpoint"] != self.binding["endpoint"]):
            raise ControlError("Approval billing target/storage reserve differs from the fixed authority.")
        amount = money(estimate_value[approval["scope"]])
        limit = money(config["pilot_limit_usd"] if approval["scope"] == "pilot" else config["total_limit_usd"])
        if amount > limit or amount < storage:
            raise ControlError("Complete approved scope exceeds its cost limit.")
        amount -= storage
        if state["breached"] or state["pending"]:
            raise ControlError("Cost breach or Unconfirmed operation; reconcile before authorization.")
        key = "run:" + run
        previous, previous_etag = self.store.get(key)
        if previous:
            for field in ("study_sha256", "resource_id", "endpoint", "rates", "rate_safety_multiplier", "model"):
                if previous["approval"][field] != approval[field]:
                    raise ControlError("Billing target or rates changed; review existing reservations.")
            if previous["authorization"] is not None and (
                evidence is None or previous["authorization"]["prepared_sha256"] != evidence["prepared_sha256"]
            ):
                raise ControlError("Prepared manifest cannot change when extending an authorized study.")
            if previous["scope"] == "full" and approval["scope"] != "full":
                raise ControlError("Cannot shrink an active full-study reservation.")
            amount = max(amount, money(previous["reserved"]))
        total = money(state["total"]) - money(previous["reserved"] if previous else 0) + amount
        pilot_amount = money(previous.get("pilot_reserved", 0) if previous else 0)
        if approval["scope"] == "pilot":
            pilot_total = money(state["pilot_total"]) - pilot_amount + amount
            if pilot_total + storage > money(config["pilot_limit_usd"]):
                raise ControlError("Global pilot reservations exceed the $7 cost limit including storage.")
            state["pilot_total"], pilot_amount = str(pilot_total), amount
        if total + storage > money(config["total_limit_usd"]):
            raise ControlError("Global experiment reservations exceed $80 including storage.")
        credit = min(self.remaining_credit, money(approval["remaining_credit_usd"]))
        if total + storage + money(config["credit_reserve_usd"]) > credit:
            raise ControlError("Credit cannot cover reservations plus protected reserve.")
        state["total"] = str(total)
        value = {"reserved": str(amount), "used": previous["used"] if previous else "0",
                 "scope": approval["scope"], "approval": approval, "estimate": estimate_value,
                 "authorization": evidence, "pilot_reserved": str(pilot_amount)}
        self._write(state, etag, [(key, value, previous_etag)])

    def begin(self, run, name, amount, kind, request, recovery=False):
        state, etag = self._root()
        key = self._key(run, name)
        previous, _ = self.store.get(key)
        if previous:
            if previous["request_sha256"] != digest(request) or previous["kind"] != kind:
                raise ControlError("Operation provenance changed.")
            if previous["status"] in ("succeeded", "terminal"):
                return previous["result"]
            if previous["status"] == "prepared":
                return None
            raise ControlError("Unconfirmed operation; reconcile remote state before retrying.")
        allocation, allocation_etag = self.store.get("run:" + run)
        if allocation is None or (state["breached"] and not recovery):
            raise ControlError("No valid cost allocation.")
        if state["pending"]:
            raise ControlError("Unconfirmed global dispatch; reconcile before another external mutation.")
        if not recovery:
            unexpired(allocation["approval"]["expires_at"])
        if recovery and money(amount) != 0:
            raise ControlError("Recovery cannot allocate paid calls.")
        used = money(allocation["used"]) + money(amount)
        if used > money(allocation["reserved"]) and not recovery:
            raise ControlError("Operation would exceed the reserved complete-study budget.")
        if kind == "training":
            if state["training"]:
                raise ControlError("A cloud training job is still active or unconfirmed.")
            state["training"] = [run, name]
        value = {"run": run, "name": name, "reserved": str(money(amount)), "kind": kind,
                 "status": "prepared", "attempts": 0, "request": request,
                 "request_sha256": digest(request)}
        allocation["used"] = str(used)
        self._write(state, etag, [(key, value, None), ("run:" + run, allocation, allocation_etag)])
        return None

    def dispatch(self, run, name, attempts):
        state, etag = self._root()
        key = self._key(run, name)
        operation, op_etag = self.store.get(key)
        if state["pending"] or operation["status"] != "prepared":
            raise ControlError("Unconfirmed dispatch; do not repeat the request.")
        if operation["attempts"] >= attempts:
            raise ControlError("Inference retry allowance exhausted; reservation retained.")
        operation.update(status="dispatched", attempts=operation["attempts"] + 1, epoch=self.owner)
        state["pending"] = [run, name]
        attempt_key = self._key(run, f"{name}:{operation['attempts']}", "attempt")
        attempt = {"status": "dispatched", "epoch": self.owner,
                   "request_sha256": operation["request_sha256"]}
        self._write(state, etag, [(key, operation, op_etag), (attempt_key, attempt, None)])
        self.active = (run, name)
        return operation["attempts"]

    def reject(self, run, name):
        state, etag = self._root()
        key = self._key(run, name)
        operation, op_etag = self.store.get(key)
        if state["pending"] != [run, name] or operation["status"] != "dispatched":
            raise ControlError("Cannot reject an operation without its pending dispatch.")
        attempt_key = self._key(run, f"{name}:{operation['attempts']}", "attempt")
        attempt, attempt_etag = self.store.get(attempt_key)
        attempt["status"] = "rejected-429"
        operation["status"] = "prepared"
        state["pending"] = None
        self._write(state, etag, [(key, operation, op_etag), (attempt_key, attempt, attempt_etag)])

    def receipt(self, run, name, result, actual=None):
        operation = self.operation(run, name)
        key = self._key(run, f"{name}:{operation['attempts']}", "receipt")
        value = {"request_sha256": operation["request_sha256"], "result": result,
                 "actual": str(money(actual)) if actual is not None else None}
        old, _ = self.store.get(key)
        if old is not None:
            if old != value:
                raise ControlError("Conflicting completion receipt; reconcile manually.")
            return
        self.store.transaction([(key, value, None)])

    def recover_receipt(self, run, name):
        operation = self.operation(run, name)
        value, _ = self.store.get(self._key(run, f"{name}:{operation['attempts']}", "receipt"))
        if value is None or value["request_sha256"] != operation["request_sha256"]:
            raise ControlError("Unconfirmed operation has no matching receipt; never replay it.")
        self.finish(run, name, value["result"], value["actual"])
        return value["result"]

    def perform(self, run, name, amount, kind, request, call, actual=None,
                attempts=1, recovery=False):
        self.store.budget.require_tail(60)
        previous = self.begin(run, name, amount, kind, request, recovery)
        if previous is not None:
            return previous
        while True:
            tail_seconds = 900 if kind == "delete" else 120
            if self.clock() + tail_seconds >= self.session_deadline:
                raise ControlError("Command runtime reserved for completion; resume in a new approved session.")
            self.store.budget.require_tail(60)
            number = self.dispatch(run, name, attempts)
            try:
                self.guard_remote()
                result = call()
            except RetryableRejection as error:
                self.reject(run, name)
                if number >= attempts:
                    raise ControlError("Inference retry allowance exhausted; reservation retained.") from None
                time.sleep(error.delay)
                continue
            finally:
                self.active = None
            if kind == "inference":
                result = {**result, "attempts": number}
            usage = actual(result) if actual is not None else None
            self.receipt(run, name, result, usage)
            self.finish(run, name, result, usage)
            return result

    def finish(self, run, name, result, actual=None, terminal=False):
        state, etag = self._root()
        key = self._key(run, name)
        operation, op_etag = self.store.get(key)
        if operation is None or operation["status"] not in ("dispatched", "succeeded", "terminal"):
            raise ControlError("Cannot finish an operation without dispatch evidence.")
        was_dispatched = operation["status"] == "dispatched"
        operation.update(result=result, status="terminal" if terminal else "succeeded")
        changes = []
        if was_dispatched:
            attempt_key = self._key(run, f"{name}:{operation['attempts']}", "attempt")
            attempt, attempt_etag = self.store.get(attempt_key)
            attempt.update(status="succeeded", result_sha256=digest(result))
            changes.append((attempt_key, attempt, attempt_etag))
        breached = False
        if actual is not None:
            actual = money(actual)
            operation["actual_usd"] = str(actual)
            if actual > money(operation["reserved"]):
                breached = True
                allocation, allocation_etag = self.store.get("run:" + run)
                allocation["used"] = str(money(allocation["used"]) + actual - money(operation["reserved"]))
                operation["reserved"] = str(actual)
                changes.append(("run:" + run, allocation, allocation_etag))
                state["breached"] = True
        if state["pending"] == [run, name]:
            state["pending"] = None
        if terminal and state["training"] == [run, name]:
            state["training"] = None
        changes.append((key, operation, op_etag))
        self._write(state, etag, changes)
        if breached:
            raise ControlError("Provider usage exceeded its bound; global spending is stopped.")

    def training_terminal(self, run, name, result):
        self.finish(run, name, result, terminal=True)

    def cancel_prepared_training(self, run, name, result):
        state, etag = self._root()
        key = self._key(run, name)
        operation, op_etag = self.store.get(key)
        if (operation["kind"] != "training" or operation["status"] != "prepared"
                or operation["attempts"] != 0 or state["training"] != [run, name]):
            raise ControlError("Only a provably undispatched training intent may be cancelled locally.")
        operation.update(status="terminal", result=result, actual_usd="0")
        state["training"] = None
        self._write(state, etag, [(key, operation, op_etag)])

    def deployment(self):
        return self._root()[0]["deployment"]

    def claim_deployment(self, run, key, model, sku):
        state, etag = self._root()
        old = state["deployment"]
        if old:
            if (old["run"], old["key"], old["model"], old["sku"]) != (run, key, model, sku):
                raise ControlError("Another deployment is active/unconfirmed; clean up its owning study.")
            return old
        if state["pending"]:
            raise ControlError("Unconfirmed operation blocks a new deployment.")
        state["deployment_sequence"] += 1
        record = {"run": run, "key": key, "model": model, "sku": sku,
                  "generation": state["deployment_sequence"]}
        record["name"] = "master-" + digest(record)[:24]
        state["deployment"] = record
        self._write(state, etag)
        return record

    def clear_deployment(self, record):
        state, etag = self._root()
        if state["deployment"] != record:
            raise ControlError("Deployment ownership changed.")
        state["deployment"] = None
        self._write(state, etag)

    def snapshot(self, run):
        state, etag = self._root()
        allocation = self.allocation(run)
        operations = self.operations(run)
        if self._root()[1] != etag:
            raise ControlError("Ledger changed while reading report; repeat the snapshot.")
        return {
            "reserved_usd": str(money(allocation["reserved"]) + money(state["storage"]["reserve_usd"])),
            "storage_reserved_usd": state["storage"]["reserve_usd"],
            "storage_reserve_scope": "experiment-global; not additive across run reports",
            "operation_bounds_usd": str(sum(money(item["reserved"]) for item in operations)),
            "reported_actual_usd": str(sum(money(item.get("actual_usd", 0)) for item in operations)),
            "actual_complete": False,
            "storage_actual_reconciled": False,
            "breached": state["breached"],
        }
