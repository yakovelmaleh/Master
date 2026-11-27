"""Bounded numeric response capture and synthetic-only offline scorer diagnostics."""

import argparse
import json
import math
import os
from pathlib import Path
import sys
from types import SimpleNamespace as NS

TASK = Path(__file__).resolve().parent
sys.path.insert(0, str(TASK.parent / "recover-openai-sufficiency-smoke"))
from diagnostics import REASONS
from azure_backend import positive_score
import azure_backend
from protocol import external_path, file_hash

MAX_TOP_LOGPROBS = 20
MAX_INTEGER_BITS = 1024
CASES = ("valid", "tiny-positive", "nan", "positive-infinity", "negative-infinity",
         "conflicting", "missing-class", "non-numeric")


class CaptureError(RuntimeError):
    pass


def numeric_value(value):
    if type(value) is float:
        if math.isnan(value):
            category = "nan"
        elif math.isinf(value):
            category = "positive_infinity" if value > 0 else "negative_infinity"
        else:
            category = "positive" if value > 0 else "negative" if value < 0 else "zero"
        # Strings preserve nonfinite values in strict JSON; hex preserves finite float bits.
        return {"type": "float", "category": category, "value": repr(value), "hex": value.hex()}
    if type(value) is int:
        if value.bit_length() > MAX_INTEGER_BITS:
            return {"type": "int", "category": "oversized", "bits": value.bit_length()}
        return {"type": "int", "category": "positive" if value > 0 else "negative" if value < 0 else "zero",
                "value": str(value)}
    kind = "null" if value is None else "bool" if type(value) is bool else "str" if type(value) is str else "other"
    return {"type": kind, "category": "non_numeric"}


def response_evidence(response, expected_model):
    choices = getattr(response, "choices", None)
    choice = choices[0] if type(choices) is list and len(choices) == 1 else None
    content = getattr(getattr(choice, "logprobs", None), "content", None)
    token = content[0] if type(content) is list and len(content) == 1 else None
    top = getattr(token, "top_logprobs", None)
    message = getattr(choice, "message", None)
    label = getattr(message, "content", None)
    finish = getattr(choice, "finish_reason", None)
    entries = []
    truncated = type(top) is list and len(top) > MAX_TOP_LOGPROBS
    items = [("generated", None, token)]
    if type(top) is list:
        items.extend(("top_logprobs", index, item) for index, item in enumerate(top[:MAX_TOP_LOGPROBS]))
    for source, index, item in items:
        item_label = getattr(item, "token", None)
        if type(item_label) is str and item_label in ("0", "1"):
            entries.append({"source": source, "index": index, "label": item_label,
                            "logprob": numeric_value(getattr(item, "logprob", None))})
    usage = getattr(response, "usage", None)
    counts = {}
    for key, attribute in (("input_tokens", "prompt_tokens"), ("output_tokens", "completion_tokens")):
        value = getattr(usage, attribute, None)
        counts[key] = value if type(value) is int and 0 <= value < 2**63 else None
    return {
        "schema": "sufficiency-numeric-logprob-response-v1",
        "choice_count": len(choices) if type(choices) is list else None,
        "scored_token_count": len(content) if type(content) is list else None,
        "top_logprobs_count": len(top) if type(top) is list else None,
        "output_label": label if type(label) is str and label in ("0", "1") else None,
        "finish_reason": finish if finish in ("stop", "length", "content_filter", "tool_calls") else "other",
        "refused": bool(getattr(message, "refusal", None)),
        "expected_model_match": getattr(response, "model", None) == expected_model,
        "usage": counts,
        "class_logprobs": entries,
        "capture_complete": not truncated and not any(
            entry["logprob"]["category"] == "oversized" for entry in entries
        ),
    }


def capture_response(response, expected_model, record):
    """Persist numeric evidence before returning the identical response for frozen scoring."""
    evidence = response_evidence(response, expected_model)
    try:
        record(evidence)
    except Exception:
        raise CaptureError("Numeric diagnostic persistence failed; stop before scoring.") from None
    if not evidence["capture_complete"]:
        raise CaptureError("Numeric diagnostic limit exceeded; stop before scoring.")
    return response


def exclusive_json(path, value):
    data = json.dumps(value, indent=2, allow_nan=False).encode("utf-8")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def synthetic_response(case):
    zero = {"tiny-positive": 1e-12, "nan": float("nan"),
            "positive-infinity": float("inf"), "negative-infinity": float("-inf"),
            "non-numeric": "synthetic nonnumeric value"}.get(case, -1.7)
    top = [NS(token="0", logprob=zero), NS(token="1", logprob=-.2)]
    if case == "conflicting":
        top.append(NS(token="0", logprob=-2.0))
    elif case == "missing-class":
        top = top[1:]
    return NS(
        choices=[NS(message=NS(content="1", refusal=None), finish_reason="length",
                    logprobs=NS(content=[NS(token="1", logprob=-.2, top_logprobs=top)]))],
        usage=NS(prompt_tokens=30, completion_tokens=1), model="synthetic-model", id="synthetic-id",
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=CASES, required=True, help="Built-in synthetic response only.")
    parser.add_argument("--output", type=Path, required=True, help="New private diagnostic directory.")
    args = parser.parse_args(argv)
    output = external_path(args.output)
    output.mkdir(mode=0o700)
    envelope = {
        "schema": "sufficiency-numeric-logprob-simulation-v1",
        "simulation": True, "cloud_access": False, "authorizes_execution": False,
        "historical_response_recovered": False, "case": args.case,
        "implementation_sha256": file_hash(Path(__file__)),
        "scorer_sha256": file_hash(Path(azure_backend.__file__)),
    }
    response = capture_response(
        synthetic_response(args.case), "synthetic-model",
        lambda value: exclusive_json(output / "response.json", {**envelope, "response": value}),
    )
    try:
        positive_score(response)
    except Exception as error:
        outcome = {"scorer_accepted": False, "reason": REASONS.get(str(error), "unclassified_error")}
    else:
        outcome = {"scorer_accepted": True, "reason": "unchanged_scorer_accepted"}
    exclusive_json(output / "result.json", {**envelope, **outcome})
    print(json.dumps({"cloud_access": False, "simulation": True,
                      "historical_response_recovered": False, **outcome}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("OFFLINE DIAGNOSTIC FAILED; preserve output and do not overwrite it.", file=sys.stderr)
        raise SystemExit(1) from None
