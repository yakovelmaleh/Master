#!/usr/bin/env python3
"""Run only milestone 1; all data-bearing outputs must remain outside Git."""

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import sys

from support import (
    HF, REPO, TASK, digest, emit, exclusive_lock, external_path, file_hash,
    read_json, slug, source_hash, write_json,
)
from diagnostic_config import validate_config


def initialize(args):
    config = read_json(args.config)
    validate_config(config)
    root = external_path(args.output_root) / slug(args.run_id)
    roots = sorted({external_path(p) for p in (args.artifact_root or [Path.home() / "master-hf"])})
    histories = external_path(args.histories) if args.histories else None
    tokenizer_cache = external_path(args.tokenizer_cache) if args.tokenizer_cache else None
    signature = {
        "run_id": args.run_id, "configuration": config,
        "configuration_sha256": digest(config), "source_sha256": source_hash(),
        "reference_sha256": file_hash(HF / "reference_contract.json"),
        "artifact_roots": [str(p) for p in roots],
        "histories": str(histories) if histories else None,
        "histories_sha256": file_hash(histories) if histories else None,
        "tokenizer_cache": str(tokenizer_cache) if tokenizer_cache else None,
    }
    root.mkdir(parents=True, exist_ok=True)
    with exclusive_lock(root / ".initialize.lock"):
        path = root / "run.json"
        if path.exists():
            saved = read_json(path)
            if any(saved.get(key) != value for key, value in signature.items()):
                raise ValueError("Run provenance changed; use a new diagnostic run ID.")
        else:
            write_json(path, {**signature, "created_utc": datetime.now(timezone.utc).isoformat(),
                              "python": sys.version, "repo": str(REPO),
                              "human_review_completed": False})
    return root, config, roots, histories, tokenizer_cache


def execute(args):
    from evidence import inventory
    from errors import errors
    from data_profile import profile

    root, config, roots, histories, cache = initialize(args)
    stages = ("inventory", "profile", "errors") if args.stage == "milestone1" else (args.stage,)
    statuses = {}
    with exclusive_lock(root / ".analysis.lock"):
        for stage in stages:
            status_path = root / "manifest" / f"{stage}_status.json"
            # Do not silently overwrite diagnostics or a user's review work.
            if status_path.exists():
                raise ValueError(f"{stage} already attempted; use a new run ID rather than overwrite artifacts.")
            if stage != "inventory" and not (root / "manifest/integrity_checks.json").is_file():
                raise ValueError("Run inventory first; aggregate reports alone are not T1 evidence.")
            emit(root, f"manifest/{stage}_status.json", stage, "deferred", reason="execution started")
            try:
                if stage == "inventory":
                    status = inventory(root, roots, config, histories)
                elif stage == "profile":
                    status = profile(root, config, histories, cache)
                else:
                    status = errors(root, config, external_path(args.reviews) if args.reviews else None)
                emit(root, f"manifest/{stage}_status.json", stage, status)
                statuses[stage] = status
            except Exception as exc:
                emit(root, f"manifest/{stage}_status.json", stage, "failed",
                     error_type=type(exc).__name__, reason=str(exc))
                raise
    print(f"Diagnostic artifacts: {root}")
    for stage, status in statuses.items():
        print(f"{stage}: {status}")
    return 2 if "blocked" in statuses.values() else 0


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", required=True, choices=("inventory", "profile", "errors", "milestone1"))
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output-root", type=Path, default=Path.home() / "master-hf/diagnostics")
    parser.add_argument("--artifact-root", type=Path, action="append",
                        help="External storage containing runs/ or jev-runs/, or a direct study directory; repeatable.")
    parser.add_argument("--histories", type=Path, help="Explicit normalized history JSONL; never infer empty history.")
    parser.add_argument("--tokenizer-cache", type=Path, help="Optional existing offline ready/ tokenizer cache.")
    parser.add_argument("--reviews", type=Path, help="Optional human-annotated copy of label_audit.csv, used only by T3.")
    parser.add_argument("--config", type=Path, default=TASK / "configuration/milestone1.json")
    args = parser.parse_args()
    try:
        return execute(args)
    except (OSError, ValueError, KeyError) as exc:
        print(f"Blocked/failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
