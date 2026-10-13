"""Persistent credit reservations; not a replacement for Azure spending limits."""

from datetime import datetime, timezone
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re
import sqlite3
from urllib.parse import urlparse

from protocol import CELLS, PILOT, cell_key, digest

CONTROL = Path.home() / ".local/state/master-openai"
CHECKS = (
    "credit_offer_covers_all_meters", "spending_limit_enabled", "no_out_of_pocket",
    "data_export_approved", "sft_model_region_quota_verified",
    "developer_deployment_verified", "logprobs_supported", "rates_verified",
    "cluster_egress_verified",
    "shared_control_storage_verified",
)


def money(value):
    try:
        result = Decimal(str(value))
    except InvalidOperation as error:
        raise ValueError("Invalid monetary value.") from error
    if not result.is_finite() or result < 0:
        raise ValueError("Money must be finite and nonnegative.")
    return result


def check_approval(value, study_hash, config):
    if value["study_sha256"] != study_hash:
        raise ValueError("Approval must name the current study hash.")
    if value["scope"] not in ("pilot", "full"):
        raise ValueError("Approval scope must be pilot or full.")
    if any(value["checks"].get(name) is not True for name in CHECKS):
        raise ValueError("Azure eligibility and no-overage evidence is incomplete.")
    expiry = datetime.fromisoformat(value["expires_at"].replace("Z", "+00:00"))
    if expiry.tzinfo is None or expiry <= datetime.now(timezone.utc):
        raise ValueError("Credit/spending approval expired.")
    if not value.get("evidence") or not value.get("credit_offer"):
        raise ValueError("Record the reviewed offer and evidence reference.")
    url = urlparse(value["endpoint"])
    if (url.scheme != "https" or not url.hostname or url.username or url.password or
            url.port or url.path not in ("", "/") or url.query or url.fragment or
            not url.hostname.endswith((".openai.azure.com", ".cognitiveservices.azure.com"))):
        raise ValueError("Endpoint must be an explicit Azure OpenAI resource.")
    if not re.fullmatch(
        r"/subscriptions/[0-9a-fA-F-]{36}/resourceGroups/[A-Za-z0-9_.()-]+"
        r"/providers/Microsoft\.CognitiveServices/accounts/[A-Za-z0-9_.-]+", value["resource_id"]
    ):
        raise ValueError("Use the exact approved Azure resource ID.")
    if value["model"] != config["model"] or value["deployment_sku"] != config["deployment_sku"]:
        raise ValueError("Approval model/deployment differs from experiment.")
    for name in ("training_per_million", "input_per_million", "output_per_million"):
        if money(value["rates"][name]) <= 0:
            raise ValueError("Verified positive token rates are required.")
    if money(value["rate_safety_multiplier"]) < Decimal("1.25"):
        raise ValueError("A minimum 25% token/rate accounting margin is required.")
    money(value["other_cost_reserve_usd"])
    if money(value["remaining_credit_usd"]) <= money(config["credit_reserve_usd"]):
        raise ValueError("Insufficient credit after the protected reserve.")


def token_cost(tokens, rate, approval):
    return money(tokens) * money(rate) * money(approval["rate_safety_multiplier"]) / Decimal(1000000)


def inference_bound(tokens, config, approval):
    rates = approval["rates"]
    return config["request_attempts"] * (
        token_cost(tokens, rates["input_per_million"], approval)
        + token_cost(1, rates["output_per_million"], approval)
    )


def estimate(prepared, config, approval):
    costs = {}
    for cell in CELLS:
        key = cell_key(*cell)
        parts = prepared["entries"][key]["partitions"]
        train = token_cost(parts["train"]["tokens"] * config["epochs"],
                           approval["rates"]["training_per_million"], approval)
        values = {"train": str(train)}
        for split in ("validation", "test"):
            part = parts[split]
            values[split] = str(config["request_attempts"] * (
                token_cost(part["tokens"], approval["rates"]["input_per_million"], approval)
                + token_cost(part["rows"], approval["rates"]["output_per_million"], approval)))
        costs[key] = values
    # Two maximum-sized synthetic capability requests, before fine-tuning.
    smoke = 2 * inference_bound(config["max_input_tokens"], config, approval)
    control_part = prepared["entries"][cell_key("Jira", 10, "text")]["partitions"]["validation"]
    control = min(20, control_part["rows"]) * inference_bound(control_part["max_tokens"], config, approval)
    pilot = sum(money(costs[cell_key(*cell)][stage]) for cell in PILOT for stage in ("train", "validation"))
    full = sum(money(amount) for item in costs.values() for amount in item.values())
    extra = money(approval["other_cost_reserve_usd"]) + smoke + control
    return {"entries": costs, "smoke": str(smoke), "base_control": str(control),
            "pilot": str(pilot + extra), "full": str(full + extra)}


class Ledger:
    def __init__(self, directory=CONTROL):
        self.directory = Path(directory)
        self.path = self.directory / "ledger.sqlite3"

    @contextmanager
    def connection(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        database = sqlite3.connect(self.path, timeout=60)
        try:
            database.execute("PRAGMA synchronous=FULL")
            database.execute("CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, value TEXT NOT NULL)")
            database.execute("CREATE TABLE IF NOT EXISTS operations (run TEXT, name TEXT, kind TEXT, status TEXT, value TEXT NOT NULL, PRIMARY KEY(run,name))")
            database.execute("CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY, breached INTEGER NOT NULL)")
            database.execute("INSERT OR IGNORE INTO state VALUES (1,0)")
            database.commit()
            database.execute("BEGIN IMMEDIATE")
            with database:
                yield database
        finally:
            database.close()

    def read(self):
        with self.connection() as database:
            return self._state(database)

    @staticmethod
    def _state(database):
        return {"runs": {key: json.loads(value) for key, value in database.execute("SELECT id,value FROM runs")},
                "breached": bool(database.execute("SELECT breached FROM state WHERE id=1").fetchone()[0])}

    def operation(self, run, name):
        with self.connection() as database:
            row = database.execute("SELECT value FROM operations WHERE run=? AND name=?", (run, name)).fetchone()
            return json.loads(row[0]) if row else None

    def authorize(self, run, approval, estimate_value, config):
        amount = money(estimate_value[approval["scope"]])
        limit = money(config["pilot_limit_usd"] if approval["scope"] == "pilot" else config["total_limit_usd"])
        if amount > limit:
            raise ValueError("Complete approved scope exceeds its cost limit; do not reduce data silently.")
        with self.connection() as database:
            state = self._state(database)
            if state["breached"]:
                raise ValueError("Cost bound was breached; reconcile billing before any further use.")
            previous = state["runs"].get(run)
            if previous:
                for key in ("resource_id", "endpoint", "rates", "rate_safety_multiplier", "model"):
                    if previous["approval"][key] != approval[key]:
                        raise ValueError("Billing target or rates changed; review existing reservations.")
                if previous["scope"] == "full" and approval["scope"] != "full":
                    raise ValueError("Cannot shrink an active full-study reservation.")
                amount = max(amount, money(previous["reserved"]))
            total = sum(money(item["reserved"]) for key, item in state["runs"].items() if key != run) + amount
            if total > money(config["total_limit_usd"]):
                raise ValueError("Global experiment reservations exceed $80.")
            if total + money(config["credit_reserve_usd"]) > money(approval["remaining_credit_usd"]):
                raise ValueError("Credit cannot cover reservations plus protected reserve.")
            value = {"reserved": str(amount), "used": previous["used"] if previous else "0",
                     "scope": approval["scope"], "approval": approval, "estimate": estimate_value}
            database.execute("INSERT OR REPLACE INTO runs VALUES (?,?)", (run, json.dumps(value)))

    def begin(self, run, operation, amount, kind, request):
        with self.connection() as database:
            state = self._state(database)
            if state["breached"] or run not in state["runs"]:
                raise ValueError("No valid cost allocation.")
            existing = database.execute("SELECT value FROM operations WHERE run=? AND name=?", (run, operation)).fetchone()
            if existing:
                prior = json.loads(existing[0])
                if prior["request_sha256"] != digest(request):
                    raise ValueError("Operation provenance changed.")
                if prior["status"] in ("succeeded", "terminal"):
                    return prior["result"]
                raise ValueError("Unconfirmed operation; reconcile remote state before retrying.")
            used = money(state["runs"][run]["used"])
            if used + money(amount) > money(state["runs"][run]["reserved"]):
                raise ValueError("Operation would exceed the reserved complete-study budget.")
            if kind == "training" and database.execute(
                "SELECT 1 FROM operations WHERE kind='training' AND status!='terminal' LIMIT 1"
            ).fetchone():
                raise ValueError("A cloud training job is still active or unconfirmed.")
            value = {
                "run": run, "reserved": str(amount), "kind": kind, "status": "started",
                "request_sha256": digest(request),
            }
            database.execute("INSERT INTO operations VALUES (?,?,?,?,?)",
                             (run, operation, kind, "started", json.dumps(value)))
            state["runs"][run]["used"] = str(used + money(amount))
            database.execute("UPDATE runs SET value=? WHERE id=?", (json.dumps(state["runs"][run]), run))
            return None

    def finish(self, run, operation, result, actual=None, terminal=False):
        breached = False
        with self.connection() as database:
            state = self._state(database)
            item = json.loads(database.execute(
                "SELECT value FROM operations WHERE run=? AND name=?", (run, operation)).fetchone()[0])
            item["result"] = result
            item["status"] = "terminal" if terminal else "succeeded"
            if actual is not None:
                item["actual_usd"] = str(money(actual))
                if money(actual) > money(item["reserved"]):
                    breached = True
                    allocation = state["runs"][run]
                    allocation["used"] = str(money(allocation["used"]) + money(actual) - money(item["reserved"]))
                    database.execute("UPDATE runs SET value=? WHERE id=?", (json.dumps(allocation), run))
                    item["reserved"] = str(money(actual))
                    state["breached"] = True
            database.execute("UPDATE operations SET status=?,value=? WHERE run=? AND name=?",
                             (item["status"], json.dumps(item), run, operation))
            database.execute("UPDATE state SET breached=? WHERE id=1", (int(state["breached"]),))
        if breached:
            raise ValueError("Provider usage exceeded the conservative reservation; stop and review.")

    def training_terminal(self, run, operation, result):
        self.finish(run, operation, result, terminal=True)

    def snapshot(self, run):
        with self.connection() as database:
            state = self._state(database)
            operations = [json.loads(row[0]) for row in database.execute(
                "SELECT value FROM operations WHERE run=?", (run,))]
        return {
            "reserved_usd": state["runs"][run]["reserved"],
            "operation_bounds_usd": str(sum(money(item["reserved"]) for item in operations)),
            "reported_actual_usd": str(sum(money(item.get("actual_usd", 0)) for item in operations)),
            "actual_complete": all("actual_usd" in item for item in operations),
            "breached": state["breached"],
        }
