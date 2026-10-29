"""Private failure diagnostics, never authority to replay or release a reservation."""

from collections.abc import Mapping
from datetime import datetime, timezone
import hashlib
import re
import uuid

from protocol import digest, file_hash, read_json, study_id, write_json


ERROR_CODES = {
    value.casefold() for value in (
        "BadRequest", "InvalidArgument", "InvalidModel", "InvalidParameter",
        "InvalidPayload", "InvalidRequest", "InvalidRequestContent", "InvalidValue",
        "DeploymentNotFound", "OperationNotSupported", "QuotaExceeded",
        "RateLimitExceeded", "ResourceNotFound", "Unauthorized", "Forbidden",
        "ResponsibleAIPolicyViolation", "content_filter", "invalid_request_error",
        "invalid_api_key", "insufficient_quota", "model_not_found",
        "file_not_found", "invalid_training_file", "rate_limit_exceeded",
        "context_length_exceeded", "server_error",
    )
}
ERROR_TYPES = {
    "invalid_request_error", "authentication_error", "permission_error",
    "rate_limit_error", "server_error", "api_error",
}
PARAMETERS = {
    "model", "training_file", "validation_file", "seed", "suffix", "trainingType",
    "method", "method.type", "method.supervised", "hyperparameters",
    "method.supervised.hyperparameters",
    *(prefix + name for prefix in ("hyperparameters.", "method.supervised.hyperparameters.")
      for name in ("batch_size", "learning_rate_multiplier", "n_epochs")),
}
REQUEST_ID = re.compile(
    r"(?:[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}|req_[0-9a-fA-F]{16,64})"
)


def error_details(error):
    status = getattr(error, "status_code", None)
    value = {
        "error_type": type(error).__name__,
        "http_status": status if type(status) is int and 100 <= status <= 599 else None,
    }
    body = getattr(error, "body", None)
    if not isinstance(body, Mapping):
        body = {}
    if isinstance(body.get("error"), Mapping):
        body = body["error"]
    provider = {}
    for key, allowed in (("code", ERROR_CODES), ("type", ERROR_TYPES), ("param", PARAMETERS)):
        field = getattr(error, key, None)
        if field is None:
            field = body.get(key)
        if not isinstance(field, str):
            continue
        candidate = field.casefold() if key == "code" else field
        if candidate in allowed:
            provider[key] = field
        else:
            # Unknown fields can echo input. Retain a fingerprint, not their text.
            provider[key + "_sha256"] = hashlib.sha256(
                field.encode("utf-8", errors="backslashreplace")
            ).hexdigest()
    headers = getattr(getattr(error, "response", None), "headers", {})
    if not isinstance(headers, Mapping):
        headers = {}
    headers = {key.lower(): field for key, field in headers.items() if isinstance(key, str)}
    for key, field in (
        ("request_id", getattr(error, "request_id", None)),
        ("x_request_id", headers.get("x-request-id")),
        ("apim_request_id", headers.get("apim-request-id")),
        ("x_ms_request_id", headers.get("x-ms-request-id")),
    ):
        if isinstance(field, str) and REQUEST_ID.fullmatch(field):
            provider[key] = field
    if provider:
        value["provider"] = provider
    return value


def record_failure(root, stage, error, failed_dispatch=None):
    evidence = {
        "schema": "openai-failure-evidence-v1",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "stage": stage,
        "run": study_id(root),
        "study_sha256": digest(read_json(root / "study.json")),
        "error": error_details(error),
    }
    if failed_dispatch is not None:
        dispatch_error, context = failed_dispatch
        evidence["dispatch"] = {**context, "error": error_details(dispatch_error)}
    path = root / "failures" / f"{stage}-{uuid.uuid4().hex}.json"
    write_json(path, evidence)
    return {"path": str(path.relative_to(root)), "sha256": file_hash(path)}
