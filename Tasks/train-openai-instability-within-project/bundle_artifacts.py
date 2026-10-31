#!/usr/bin/env python3
"""Only code and final summaries may leave the hosted experiment's storage."""

import argparse
import json
import os
from pathlib import Path

BLOCKED = {"data", "prepared", "remote", "validation", "final", "batches", "logs", "status", "failures",
           ".git", "__pycache__", "cache", ".cache"}
MAX_BYTES = 10 * 1024 * 1024


def copy_tree(source, destination, definition=False):
    source, destination = Path(source), Path(destination)
    if source.is_symlink():
        raise ValueError("Bundle source cannot be a symlink.")
    omitted = []
    for directory, dirs, files in os.walk(source, followlinks=False):
        for name in list(dirs):
            path = Path(directory) / name
            if name in BLOCKED or path.is_symlink() or (definition and name in ("cluster_runs", "results", "runs")):
                dirs.remove(name)
                omitted.append(str(path.relative_to(source)))
        for name in files:
            path = Path(directory) / name
            if definition:
                allowed = path.suffix in (".py", ".sh") or name in (
                    "README.md", "requirements.txt", "experiment.json", "prompt_only.json",
                    "reference_contract.json", "model_config.json")
            else:
                allowed = name == "llm_report.json"
            if path.is_symlink() or not allowed or path.stat().st_size > MAX_BYTES:
                omitted.append(str(path.relative_to(source)))
                continue
            if not definition:
                value = json.loads(path.read_text())
                if value.get("schema") not in ("openai-instability-report-v1", "openai-instability-report-v2",
                                              "openai-instability-prompt-report-v1"):
                    raise ValueError("Only the explicit LLM report schema may be bundled.")
            with path.open("rb") as stream:
                content = stream.read(MAX_BYTES + 1)
            if len(content) > MAX_BYTES:
                raise ValueError("Bundle artifact exceeded the size limit while reading.")
            output = destination / path.relative_to(source)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(content)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "LLM_OMITTED_FILES.json").write_text(json.dumps(omitted, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--definition", action="store_true")
    args = parser.parse_args()
    copy_tree(args.source, args.destination, args.definition)
