#!/usr/bin/env python3
"""Explicit private checkpoint publication; never invoked implicitly by training."""

import argparse
from pathlib import Path
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "train-hf-instability-within-project"))
from common import artifact_hashes, check_artifact, external_path, read_json, write_json


ALLOWED = {"head.safetensors", "inference.json", "README.md",
           "adapter/adapter_model.safetensors", "adapter/adapter_config.json", "adapter/README.md"}


def export_files(checkpoint):
    hashes = artifact_hashes(checkpoint)
    forbidden = set(hashes) - ALLOWED
    if forbidden:
        raise ValueError(f"Files not approved for private publication: {sorted(forbidden)}")
    if not {"head.safetensors", "inference.json"}.issubset(hashes):
        raise ValueError("Missing inference configuration/head.")
    return hashes


def ensure_private(api, repo_id):
    api.create_repo(repo_id=repo_id, private=True, exist_ok=True, repo_type="model")
    info = api.repo_info(repo_id=repo_id, repo_type="model")
    if info.private is not True:
        raise ValueError("Destination is public. Refusing to upload any file.")
    return info.sha


def publish(checkpoint, repo_id, storage, cache):
    import numpy as np
    from huggingface_hub import HfApi, snapshot_download
    from data_contract import load_project
    from run_experiment import predict_checkpoint

    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*", repo_id):
        raise ValueError("Explicit namespace/model-name is required.")
    checkpoint = external_path(checkpoint)
    hashes = export_files(checkpoint)
    spec = read_json(checkpoint / "inference.json")
    # Publication is permitted only for a selected checkpoint from a sealed study.
    studies = [parent for parent in checkpoint.parents if (parent / "sealed.json").is_file()]
    if len(studies) != 1:
        raise ValueError("Checkpoint must belong to one sealed study.")
    root = studies[0]
    matches = [item for item in read_json(root / "sealed.json")["selections"]
               if (root / item["directory"] / "checkpoint").resolve() == checkpoint]
    if len(matches) != 1:
        raise ValueError("Checkpoint was not selected for final evaluation.")
    check_artifact(checkpoint, matches[0]["checkpoint_files"])
    _, validation, _ = load_project(spec["project"], root)
    sample = validation.iloc[:8]
    expected = predict_checkpoint(checkpoint, cache, sample)
    api = HfApi()
    parent_commit = ensure_private(api, repo_id)
    commit = api.upload_folder(
        repo_id=repo_id, repo_type="model", folder_path=str(checkpoint),
        allow_patterns=sorted(hashes), parent_commit=parent_commit,
        commit_message="Publish selected within-project instability classifier",
    )
    if api.repo_info(repo_id=repo_id, repo_type="model").private is not True:
        raise ValueError("Destination privacy changed during upload; review repository access immediately.")
    with tempfile.TemporaryDirectory(prefix="hf-reload-", dir=external_path(storage)) as temporary:
        downloaded = Path(snapshot_download(repo_id=repo_id, revision=commit.oid, local_dir=temporary,
                                            allow_patterns=sorted(hashes)))
        for relative, value in hashes.items():
            from common import file_hash

            if file_hash(downloaded / relative) != value:
                raise ValueError("Uploaded artifact hash mismatch.")
        import pandas as pd
        import os
        from common import TASK

        input_file = Path(temporary) / "reload_input.csv"
        output_file = Path(temporary) / "reload_predictions.csv"
        sample.to_csv(input_file, index=False)
        subprocess.run([
            sys.executable, str(TASK / "predict.py"), "--checkpoint", str(downloaded),
            "--cache", str(cache), "--input-csv", str(input_file), "--output", str(output_file),
        ], check=True, env={**os.environ, "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"})
        actual = pd.read_csv(output_file).instability_probability.to_numpy()
        np.testing.assert_allclose(expected, actual, atol=1e-5, rtol=1e-4)
    write_json(root / "publications" / f"{spec['project']}-{spec['level']}.json",
               {"repo_id": repo_id, "revision": commit.oid, "private": True, "files": hashes})
    print(f"Published private model {repo_id} at immutable revision {commit.oid}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--repo-id", required=True)
    parser.add_argument("--storage", required=True)
    parser.add_argument("--cache", required=True)
    parser.add_argument("--approve-export", action="store_true")
    args = parser.parse_args()
    if not args.approve_export:
        raise ValueError("Review data-export and license permission, then explicitly supply --approve-export.")
    publish(args.checkpoint, args.repo_id, args.storage, args.cache)
