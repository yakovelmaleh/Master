#!/usr/bin/env python3
"""Reject HF model/runtime artifacts in the staged changes, independent of ignores."""

from pathlib import Path
import subprocess

from common import REPO


def forbidden(path):
    value = Path(path)
    return (
        value.suffix.lower() in {".safetensors", ".bin", ".pt", ".pth", ".onnx", ".gguf"}
        or any(part in {"checkpoint", "checkpoints", "snapshots", "blobs", "embeddings"}
               for part in value.parts)
        or "hf-instability" in str(value) and "cluster_runs" in value.parts
    )


if __name__ == "__main__":
    paths = subprocess.check_output(
        ["git", "-C", str(REPO), "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"]
    ).decode().split("\0")
    blocked = [path for path in paths if path and forbidden(path)]
    if blocked:
        raise SystemExit("Refusing model/runtime files in Git changes:\n" + "\n".join(blocked))
    print("Staged changes contain no HF weight/runtime artifacts.")
