"""Shared runtime contracts; importing this module never downloads a model."""

import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from contextlib import contextmanager


TASK = Path(__file__).resolve().parent
REPO = TASK.parents[1]
LEVELS = (5, 10, 15, 20)
PROJECTS = ("Apache", "Hyperledger", "IntelDAOS", "Jira", "MariaDB", "Qt")
for directory in ("jira-url-to-instability-model", "verify-refactored-instability-model"):
    sys.path.insert(0, str(REPO / "Tasks" / directory))


def read_json(path):
    return json.loads(Path(path).read_text())


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    descriptor, temporary = tempfile.mkstemp(prefix=".writing-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as stream:
            stream.write(text)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def file_hash(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def external_path(path):
    resolved = Path(path).expanduser().resolve()
    if resolved == REPO or REPO in resolved.parents:
        raise ValueError("HF cache/checkpoint storage must be outside the Git checkout.")
    return resolved


def slug(value):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", value):
        raise ValueError(f"Invalid identifier: {value!r}")
    return value


def model_registry():
    registry = read_json(REPO / "Tasks/research-hf-instability-models/models.json")
    for item in registry.values():
        if not re.fullmatch(r"[0-9a-f]{40}", item["revision"]):
            raise ValueError("Every model requires an immutable full revision.")
    return registry


def artifact_hashes(directory):
    directory = Path(directory)
    values = {}
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Checkpoint symlink is forbidden: {path}")
        if path.is_file():
            values[str(path.relative_to(directory))] = file_hash(path)
    if not values:
        raise ValueError(f"Empty checkpoint: {directory}")
    return values


def check_artifact(directory, expected):
    if artifact_hashes(directory) != expected:
        raise ValueError("Checkpoint files changed after selection.")


@contextmanager
def exclusive_lock(path):
    import fcntl

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield
