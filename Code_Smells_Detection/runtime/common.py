"""Shared immutable manifests, paths and stage states."""

import contextlib
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import sys
import tempfile
from datetime import datetime, timezone


REPO = Path(__file__).resolve().parents[2]
JIRA = REPO / "Tasks/jira-url-to-instability-model"
COMPARISON = REPO / "Tasks/verify-refactored-instability-model"
for directory in (JIRA, COMPARISON):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

SCHEMA = "story-code-smells-v1"
LANGUAGES = {".java": "java", ".py": "python", ".cs": "csharp"}
PARTITIONS = ("train", "validation", "test")
SOURCES = {"Apache": 3289, "IntelDAOS": 866, "Jira": 3, "JiraEcosystem": 23,
           "MongoDB": 39169, "Qt": 86, "RedHat": 24920, "Sakai": 2}
CANDIDATE_HASH = "a96d260478dfe2c6eb78ce8c47bac74707039c05853e90e0c8e2775d103d0aab"
TASKS = {"prepare": "prepare-code-smell-dataset", "detect": "detect-code-smells",
         "train": "train-code-smell-models"}


def now():
    return datetime.now(timezone.utc).isoformat()


def identifier(value):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", value) or value in (".", ".."):
        raise ValueError(f"Unsafe identifier: {value!r}")
    return value


def relative(value):
    path = source_relative(value)
    if ":" in value:
        raise ValueError(f"Unsafe relative path: {value!r}")
    return path


def source_relative(value, *, windows=False):
    path = PurePosixPath(value)
    if (not value or "\\" in value or path.is_absolute() or PureWindowsPath(value).drive or
            any(part in ("", ".", "..") for part in value.split("/")) or
            any(ord(char) < 32 for char in value)):
        raise ValueError(f"Unsafe relative path: {value!r}")
    # Source names are literal POSIX names, not URLs or portable artifact identifiers.
    if windows or os.name == "nt":
        if any(re.search(r'[<>:"|?*]', part) or part.endswith((".", " ")) or
               PureWindowsPath(part).is_reserved() for part in path.parts):
            raise ValueError(f"Source path is not representable on Windows: {value!r}")
    return path


def read_json(path):
    with Path(path).open(encoding="utf-8") as stream:
        return json.load(stream)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False,
                                     separators=(",", ":")).encode()).hexdigest()


def file_hash(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def atomic_bytes(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix="." + path.name, dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def write_json(path, value):
    atomic_bytes(path, (json.dumps(value, indent=2, sort_keys=True,
                                  allow_nan=False) + "\n").encode())


def immutable_json(path, value):
    path = Path(path)
    if path.exists():
        if read_json(path) != value:
            raise ValueError(f"Immutable manifest differs: {path}")
    else:
        write_json(path, value)


def write_csv(path, frame):
    atomic_bytes(path, frame.to_csv(index=False).encode())


def external(path):
    path = Path(path).expanduser().resolve()
    if path == REPO or REPO in path.parents:
        raise ValueError("Runtime storage must be outside the Git repository.")
    return path


def study(storage, run_id):
    return external(storage) / "runs" / identifier(run_id)


def source_hash():
    paths = list((REPO / "Code_Smells_Detection/runtime").glob("*.py"))
    paths += list((JIRA / "jira_pipeline").glob("*.py"))
    paths += list((JIRA / "unstable_model").glob("*.py"))
    paths += [COMPARISON / "model_comparison.py"]
    return digest({str(p.relative_to(REPO)): file_hash(p) for p in sorted(paths)})


@contextlib.contextmanager
def lock(path, wait=False):
    """OS-backed lock, released even if a worker is killed (POSIX and Windows)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        if os.name == "nt":
            import msvcrt
            stream.seek(0)
            stream.write(b"0")
            stream.flush()
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK if wait else msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream, fcntl.LOCK_EX | (0 if wait else fcntl.LOCK_NB))
        try:
            yield
        finally:
            if os.name == "nt":
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


@contextlib.contextmanager
def stage_state(root, stage, unit, fingerprint):
    path = root / "status" / f"{identifier(stage)}-{identifier(unit)}.json"
    with lock(path.with_suffix(".lock")):
        write_json(path, {"status": "running", "fingerprint": fingerprint, "started": now()})
        try:
            yield
        except Exception as error:
            write_json(path, {"status": "failed", "fingerprint": fingerprint,
                              "error_type": type(error).__name__, "finished": now()})
            raise
        write_json(path, {"status": "succeeded", "fingerprint": fingerprint, "finished": now()})


def require_stage(root, stage, unit):
    path = root / "status" / f"{stage}-{unit}.json"
    if not path.exists() or read_json(path)["status"] != "succeeded":
        raise ValueError(f"Required stage is not successful: {stage}/{unit}")


def tree_manifest(root):
    root = Path(root)
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Symlink forbidden in artifact tree: {path}")
        if path.is_file():
            result[path.relative_to(root).as_posix()] = file_hash(path)
    return result


def verify_tree(root, manifest):
    if tree_manifest(root) != manifest:
        raise ValueError(f"Artifact tree changed or is incomplete: {root}")


def verify_original_files(root, manifest):
    for name, expected in manifest.items():
        path = Path(root) / source_relative(name)
        if path.is_symlink() or not path.is_file() or file_hash(path) != expected:
            raise ValueError(f"Analyzer modified original source: {name}")


def verify_study(root):
    manifest = read_json(root / "study.json")
    if manifest["schema"] != SCHEMA or manifest["source_sha256"] != source_hash():
        raise ValueError("Study code/schema changed; use the original checkout or a new run ID.")
    for name, expected in manifest["inputs"].items():
        if file_hash(root / "cohort" / name) != expected:
            raise ValueError(f"Study input changed: {name}")
    if "migration_sha256" in manifest:
        expected = manifest["migration_sha256"]
        if (not (root / "migration.json").is_file() or not (root / "migration_complete.json").is_file() or
                file_hash(root / "migration.json") != expected or
                read_json(root / "migration_complete.json") != {"migration_sha256": expected}):
            raise ValueError("Run migration is incomplete or its provenance changed.")
    return manifest
