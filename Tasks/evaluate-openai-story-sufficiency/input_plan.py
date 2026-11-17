"""Read-only input sizing and historical-rate estimates; never prepares a live run."""

from functools import lru_cache
import json
from pathlib import Path

from sufficiency import (
    EXAMPLE_POLICY, METHOD, Tokenizer, implementation_hash, measure_messages,
    source_evidence, source_payload, training_examples,
)
from protocol import CELLS, PILOT_LEVEL, PILOT_PROJECT, cell_key, digest, file_hash, read_json
from prepare_data import partition
from cost_control import estimate, money


class CountingTokenizer:
    """Retain only a few repeated encodings; do not cache the whole dataset."""

    def __init__(self, tokenizer):
        self.name, self.labels = tokenizer.name, tokenizer.labels
        self.encode = lru_cache(maxsize=16)(tokenizer.encode)
        self.decode = tokenizer.decode


def plan(source, tokenizer=None):
    evidence = source_evidence(source)
    source = Path(evidence["root"])
    config = read_json(source / "study.json")["config"]
    old = read_json(source / "prepared.json")
    tokenizer = CountingTokenizer(tokenizer or Tokenizer(config["model"]))
    if tokenizer.name != old["tokenizer"] or tokenizer.labels != old["label_tokens"]:
        raise ValueError("Tokenizer differs from the original experiment.")
    examples = training_examples(source, config, tokenizer)
    entries = {}
    maximum = 0
    inference_maximum = 0
    over = {split: 0 for split in ("train", "validation", "test")}
    matched = {}
    payload_bytes = 0
    for project, level, variant in CELLS:
        key = cell_key(project, level, variant)
        example_rows = {r["row_id"] for r in examples[key]["rows"]}
        parts = {}
        for split in ("train", "validation", "test"):
            records, rows = partition(source, key, split)
            identities = [r["row_id"] for r in rows]
            if (not rows or len(set(identities)) != len(identities)
                    or (split != "train" and example_rows.intersection(identities))):
                raise ValueError("Empty, duplicate, or training-overlapping source population.")
            counts, inputs = [], []
            for record, row in zip(records, rows):
                if type(row["label"]) is not int or row["label"] not in (0, 1):
                    raise ValueError("Source labels must be binary integers.")
                payload = source_payload(record, level, variant)
                pair, count = measure_messages(project, payload["original_text"],
                                               payload.get("train_fitted_structured_features"),
                                               tokenizer, examples[key]["examples"])
                counts.append(count)
                inputs.append({k: v for k, v in payload.items() if k != "unstable_word_threshold"})
                payload_bytes += len((json.dumps({"messages": pair}, ensure_ascii=False, allow_nan=False)
                                      + "\n").encode())
            match_key = (project, variant, split)
            comparison = (identities, digest(inputs))
            if match_key in matched and matched[match_key] != comparison:
                raise ValueError("Original target inputs differ across K.")
            matched[match_key] = comparison
            too_large = sum(n > config["max_input_tokens"] for n in counts)
            parts[split] = {"rows": len(rows), "tokens": sum(counts), "max_tokens": max(counts),
                            "over_current_limit": too_large}
            over[split] += too_large
            maximum = max(maximum, max(counts))
            if split != "train":
                inference_maximum = max(inference_maximum, max(counts))
        entries[key] = {
            "project": project, "level": level, "variant": variant, "partitions": parts,
            "system_tokens": len(tokenizer.encode(examples[key]["system"])),
            "demonstrations_sha256": digest(examples[key]),
            "truncated_examples": sum(r["truncated"] for r in examples[key]["rows"]),
        }
    smoke_counts = []
    pilot = examples[cell_key(PILOT_PROJECT, PILOT_LEVEL, "text")]["examples"]
    for text in ("Add a settings page.", "requirement " * config["text_tokens"]):
        text = tokenizer.decode(tokenizer.encode(text)[:config["text_tokens"]])
        _, count = measure_messages(PILOT_PROJECT, text, None, tokenizer, pilot)
        smoke_counts.append(count)
    maximum = max(maximum, *smoke_counts)
    # This worksheet value is not installed into any config or approval.
    candidate = max(config["max_input_tokens"], ((maximum + 1023) // 1024) * 1024)
    result = {
        "schema": "openai-sufficiency-input-plan-v1", "method": METHOD,
        "cloud_access": False, "authorizes_execution": False,
        "implementation_sha256": implementation_hash(),
        "source": {k: v for k, v in evidence.items() if k != "root"},
        "demonstration_policy": EXAMPLE_POLICY, "entries": entries,
        "current_input_limit": config["max_input_tokens"],
        "maximum_required_input_tokens": maximum,
        "maximum_validation_test_input_tokens": inference_maximum,
        "smoke_input_tokens": smoke_counts,
        "hypothetical_input_limit_for_costing": candidate,
        "over_current_limit": over, "prepared_payload_jsonl_bytes": payload_bytes,
        "historical_cost_estimate": {"available": False},
        "notes": [
            "No limits, study files, prepared payloads, selections, approvals, or reservations were changed.",
            "Sizing includes all ten examples, original target text/fields, and the conservative chat envelope.",
            "The maximum includes unused train-target payloads because preparation also writes that partition.",
            "JSONL byte count excludes sidecars, manifests, scores, filesystem overhead, and remote storage.",
            "The rounded hypothetical limit is not an approved configuration or a verified provider limit.",
            "Historical prices and storage reserve are illustrative, not current billing verification.",
            "Global remaining capacity, other reservations, current credit, and pricing still need review.",
            "Do not replace an existing partial run; any approved configuration change requires a new run ID.",
        ],
    }
    authorization = source / "authorization.json"
    if authorization.exists():
        approval = read_json(authorization)["approval"]
        if approval.get("study_sha256") != evidence["study_sha256"]:
            raise ValueError("Historical rate reference belongs to a different source study.")
        rates = approval["rates"]
        if (any(money(rates[k]) <= 0 for k in ("input_per_million", "output_per_million"))
                or money(approval["rate_safety_multiplier"]) < money("1.25")):
            raise ValueError("Historical rate reference is incomplete.")
        prepared = {"entries": entries}
        bounds = estimate(prepared, {**config, "max_input_tokens": candidate}, approval)
        result["historical_cost_estimate"] = {
            "available": True, "current_rates_verified": False,
            "source_authorization_sha256": file_hash(authorization),
            "source_approval_expires_at": approval["expires_at"],
            "rates": {k: rates[k] for k in ("input_per_million", "output_per_million")},
            "rate_safety_multiplier": approval["rate_safety_multiplier"],
            "max_attempts": config["request_attempts"],
            "storage_reserve_is_historical": True,
            "bounds": bounds,
        }
    return result


def summary(value):
    costs = value["historical_cost_estimate"]
    return {
        key: value[key] for key in (
            "cloud_access", "authorizes_execution", "current_input_limit",
            "maximum_required_input_tokens", "maximum_validation_test_input_tokens",
            "hypothetical_input_limit_for_costing", "over_current_limit",
        )
    } | {
        "historical_pilot_bound_usd": costs["bounds"]["pilot"] if costs["available"] else None,
        "historical_full_bound_usd": costs["bounds"]["full"] if costs["available"] else None,
        "current_rates_verified": False,
    }
