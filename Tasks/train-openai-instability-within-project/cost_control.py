"""Persistent credit reservations; not a replacement for Azure spending limits."""

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re
from urllib.parse import urlparse

from protocol import CELLS, PILOT, PILOT_LEVEL, PILOT_PROJECT, cell_key

CONTROL = Path.home() / ".local/state/master-openai"
CHECKS = (
    "credit_offer_covers_all_meters", "spending_limit_enabled", "no_out_of_pocket",
    "data_export_approved", "sft_model_region_quota_verified",
    "developer_deployment_verified", "logprobs_supported", "rates_verified",
    "cluster_egress_verified",
    "cloud_control_verified", "storage_costs_verified",
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
    if value.get("control_schema") != "azure-table-control-v1":
        raise ValueError("Cloud control approval is required; use a new run and approval.")
    if not value.get("authority_sha256"):
        raise ValueError("Approval must bind the fixed cloud authority.")
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
    if money(value["storage_reserve_usd"]) <= 0:
        raise ValueError("A verified positive storage reserve is required.")
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
    control_part = prepared["entries"][cell_key(PILOT_PROJECT, PILOT_LEVEL, "text")]["partitions"]["validation"]
    control = min(20, control_part["rows"]) * inference_bound(control_part["max_tokens"], config, approval)
    pilot = sum(money(costs[cell_key(*cell)][stage]) for cell in PILOT for stage in ("train", "validation"))
    full = sum(money(amount) for item in costs.values() for amount in item.values())
    storage = money(approval["storage_reserve_usd"])
    extra = money(approval["other_cost_reserve_usd"]) + smoke + control + storage
    return {"entries": costs, "smoke": str(smoke), "base_control": str(control),
            "pilot": str(pilot + extra), "full": str(full + extra), "storage": str(storage),
            "control_requests": {scope: control_envelope(prepared, config, scope) for scope in ("pilot", "full")}}


def control_requests(stage, prepared, config, scope="full"):
    """Upper envelope for table entity operations, lease calls and bounded polling."""
    rows = 0
    if stage == "smoke":
        rows = 22
    elif stage in ("validate", "test"):
        cells = PILOT if scope == "pilot" and stage == "validate" else CELLS
        split = "validation" if stage == "validate" else "test"
        rows = sum(prepared["entries"][cell_key(*cell)]["partitions"][split]["rows"] for cell in cells)
    elif stage == "report":
        rows = sum(part["rows"] for entry in prepared["entries"].values()
                   for split, part in entry["partitions"].items() if split != "train") // 100
    return 1000 + rows * config["request_attempts"] * 40


def control_envelope(prepared, config, scope):
    stages = ["smoke", "validate", "report", "cleanup"]
    stages += ["train-submit", "train-status"] * len(PILOT if scope == "pilot" else CELLS)
    if scope == "full":
        stages += ["seal", "test"]
    counts = [control_requests(stage, prepared, config, scope) for stage in stages]
    return {"requests": sum(counts), "sessions": len(counts), "max_session_requests": max(counts)}
