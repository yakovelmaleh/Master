"""Offline-only probes of the unchanged sufficiency backend; never a recovery grant."""

import argparse
import json
import math
import os
from pathlib import Path
import sys
from types import SimpleNamespace as NS

TASK = Path(__file__).resolve().parent
sys.path.insert(0, str(TASK.parent / "evaluate-openai-story-sufficiency"))

from sufficiency import QUESTION, demonstrations, frozen_study, system_message
from backend import SufficiencyBackend
from protocol import (
    BASE_METHOD, PILOT_LEVEL, PILOT_PROJECT, cell_key, digest, external_path,
    file_hash, read_json, study_id,
)

REASONS = {
    "Expected one classification choice.": "choice_count",
    "Classification was refused or filtered.": "refused_or_filtered",
    "Expected an exact binary token and its log probabilities.": "binary_output_or_logprobs",
    "Classification must contain exactly one scored token.": "scored_token_count",
    "Output and scored token disagree.": "token_mismatch",
    "Invalid class log probability.": "invalid_logprob",
    "Conflicting class log probabilities.": "conflicting_logprobs",
    "Both class log probabilities are required; no probability fallback.": "missing_class_logprobs",
    "Provider did not return token usage.": "missing_usage",
    "Unexpected provider token accounting.": "invalid_usage",
    "Inference returned a different model snapshot; retain the dispatch.": "model_mismatch",
}


class OfflineBoundary(Exception):
    pass


class DiagnosticWriteError(RuntimeError):
    pass


def object_tree(value):
    if isinstance(value, dict):
        return NS(**{key: object_tree(item) for key, item in value.items()})
    if isinstance(value, list):
        return [object_tree(item) for item in value]
    return value


def response_summary(response, expected_model):
    choices = getattr(response, "choices", None)
    choice = choices[0] if isinstance(choices, list) and len(choices) == 1 else None
    message = getattr(choice, "message", None)
    finish = getattr(choice, "finish_reason", None)
    content = getattr(getattr(choice, "logprobs", None), "content", None)
    token = content[0] if isinstance(content, list) and len(content) == 1 else None
    top = getattr(token, "top_logprobs", None)
    values = {}
    invalid, conflicting = False, False
    for item in ([token] + top if token is not None and isinstance(top, list) else []):
        label, probability = getattr(item, "token", None), getattr(item, "logprob", None)
        if label not in ("0", "1"):
            continue
        if type(probability) not in (int, float) or not math.isfinite(probability) or probability > 0:
            invalid = True
            continue
        conflicting |= label in values and values[label] != probability
        values[label] = probability
    usage = getattr(response, "usage", None)
    return {
        "choice_count": len(choices) if isinstance(choices, list) else None,
        "finish_reason": finish if finish in ("stop", "length", "content_filter", "tool_calls") else "other",
        "refused": bool(getattr(message, "refusal", None)),
        "binary_output": getattr(message, "content", None) in ("0", "1"),
        "scored_token_count": len(content) if isinstance(content, list) else None,
        "both_class_logprobs": set(values) == {"0", "1"},
        "invalid_class_logprobs": invalid, "conflicting_class_logprobs": conflicting,
        "usage": {
            key: value if type(value) is int and value >= 0 else None
            for key, value in (
                ("input_tokens", getattr(usage, "prompt_tokens", None)),
                ("output_tokens", getattr(usage, "completion_tokens", None)),
            )
        },
        "expected_model_match": getattr(response, "model", None) == expected_model,
    }


def probe(config, approval, examples, pair, record, response=None, guard_error=None, sdk_error=None):
    """Exercise real validation/scoring with a fake client and no-op cloud guard."""
    phase = "input"

    def save(name, value):
        try:
            record(name, value)
        except Exception:
            raise DiagnosticWriteError("Diagnostic persistence failed; keep partial evidence.") from None

    def guard():
        nonlocal phase
        phase = "guard"
        if guard_error is not None:
            raise guard_error

    def transport(**kwargs):
        nonlocal phase
        phase = "sdk"
        save("request", {"arguments_sha256": digest(kwargs)})
        if sdk_error is not None:
            raise sdk_error
        if response is None:
            raise OfflineBoundary()
        phase = "response_summary"
        save("response", response_summary(response, config["model"]))
        phase = "scoring"
        return response

    backend = SufficiencyBackend.__new__(SufficiencyBackend)
    backend.config, backend.approval = config, approval
    backend.systems = {entry["system"]: (entry["project"], entry["variant"]) for entry in examples.values()}
    backend.guard = guard
    backend.client = NS(chat=NS(completions=NS(create=transport)))
    try:
        backend.predict(approval["base_deployment"], pair)
    except OfflineBoundary:
        result = {"phase": "sdk", "reason": "fake_transport_reached", "fixture_score_valid": None}
    except DiagnosticWriteError:
        raise
    except Exception as error:
        reason = REASONS.get(str(error), "unclassified_error") if phase == "scoring" else "unclassified_error"
        result = {
            "phase": "model_check" if reason == "model_mismatch" else phase,
            "reason": reason, "fixture_score_valid": False,
        }
    else:
        result = {"phase": "complete", "reason": "valid_fixture", "fixture_score_valid": True}
    save("result", result)
    return result


def audit(root, failure_path):
    config = frozen_study(root)
    study = read_json(root / "study.json")
    failure = read_json(failure_path)
    dispatch = failure.get("dispatch", {})
    if (failure.get("schema") != "openai-failure-evidence-v1"
            or failure.get("study_sha256") != digest(study)
            or failure.get("run") != study_id(root) or failure.get("stage") != "smoke"
            or dispatch.get("run") != study_id(root) or dispatch.get("operation") != "smoke-0"
            or dispatch.get("kind") != "inference" or dispatch.get("attempt") != 1):
        raise ValueError("Failure identity does not match smoke-0 attempt 1.")
    status = read_json(root / "status/smoke.json")
    reference = status["failure_evidence"]
    if (status.get("status") != "failed" or reference["path"] != str(failure_path.relative_to(root))
            or reference["sha256"] != file_hash(failure_path)):
        raise ValueError("Failure evidence does not match the saved status.")
    authorization = read_json(root / "authorization.json")
    approval = authorization["approval"]
    if (approval["study_sha256"] != digest(study)
            or authorization["prepared_sha256"] != file_hash(root / "prepared.json")):
        raise ValueError("Authorization provenance changed.")
    examples = demonstrations(root)
    # Hash equality below proves exact reconstruction without a tokenizer/cache download.
    pair = [
        {"role": "system", "content": system_message(
            PILOT_PROJECT, examples[cell_key(PILOT_PROJECT, PILOT_LEVEL, "text")]["examples"],
        )},
        {"role": "user", "content": json.dumps({
            "project": PILOT_PROJECT, "question": QUESTION, "original_text": "Add a settings page.",
        }, ensure_ascii=False, allow_nan=False)},
    ]
    request = {
        "resource_id": approval["resource_id"], "model": config["model"],
        "messages_sha256": digest(pair), "config_sha256": digest(config),
        "deployment": approval["base_deployment"], "method": BASE_METHOD,
    }
    if digest(request) != dispatch.get("request_sha256"):
        raise ValueError("Reconstructed request differs from the failed dispatch.")
    context = {
        "study_sha256": digest(study), "run": study_id(root), "operation": "smoke-0", "attempt": 1,
        "request_sha256": digest(request), "failure_sha256": file_hash(failure_path),
        "implementation_sha256": file_hash(Path(__file__)),
    }
    return config, approval, examples, pair, context


def main(argv=None):
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--failure", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path, help="New private output directory.")
    parser.add_argument("--response-fixture", type=Path, help="Optional synthetic JSON response; never historical evidence.")
    args = parser.parse_args(argv)
    root = external_path(args.root)
    failure = external_path(args.failure)
    output = external_path(args.output)
    if output == root or root in output.parents:
        parser.error("Keep diagnostics outside the preserved run.")
    # Validate all inputs before creating any output; never overwrite existing evidence.
    config, approval, examples, pair, context = audit(root, failure)
    fixture = read_json(external_path(args.response_fixture)) if args.response_fixture else None
    response = object_tree(fixture) if fixture is not None else None
    output.mkdir(mode=0o700)

    def record(name, value):
        envelope = {
            "schema": "sufficiency-offline-diagnostic-v1", **context,
            "cloud_access": False, "authorizes_execution": False, "simulation": True,
            "historical_outcome": "UNKNOWN",
            "fixture_sha256": digest(fixture) if fixture is not None else None,
            "diagnostic": value,
        }
        with (output / (name + ".json")).open("x") as stream:
            json.dump(envelope, stream, indent=2, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())

    result = probe(config, approval, examples, pair, record, response)
    print(json.dumps({"cloud_access": False, "historical_outcome": "UNKNOWN", **result}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("OFFLINE DIAGNOSTIC STOPPED; preserve existing evidence.", file=sys.stderr)
        raise SystemExit(1) from None
