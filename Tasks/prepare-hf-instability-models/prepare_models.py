#!/usr/bin/env python3
"""Download immutable model snapshots only when this runtime command is invoked."""

import argparse
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "train-hf-instability-within-project"))
from common import external_path, file_hash, model_registry, read_json, write_json


ALLOW = ["*.json", "*.safetensors", "tokenizer.model", "spiece.model", "*.txt", "*.jinja"]


def prepare(cache, names, offline=False):
    from huggingface_hub import HfApi, snapshot_download

    cache = external_path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    registry = model_registry()
    for name in names:
        model = registry[name]
        if not offline:
            info = HfApi().model_info(model["id"], revision=model["revision"], files_metadata=True)
            size = sum(f.size or 0 for f in info.siblings if "/" not in f.rfilename)
            if shutil.disk_usage(cache).free < size:
                raise ValueError(f"Insufficient disk space for {name}: require {size} free bytes.")
        snapshot = Path(snapshot_download(
            repo_id=model["id"], revision=model["revision"], cache_dir=str(cache),
            allow_patterns=ALLOW, ignore_patterns=["onnx/*", "openvino/*", "*.bin", "*.py"],
            local_files_only=offline,
        ))
        if snapshot.name != model["revision"]:
            raise ValueError(f"Unexpected resolved revision for {name}.")
        files = {str(path.relative_to(snapshot)): file_hash(path)
                 for path in snapshot.rglob("*") if path.is_file()}
        if "config.json" not in files or not any(k.endswith(".safetensors") for k in files):
            raise ValueError(f"Incomplete snapshot: {name}")
        index = snapshot / "model.safetensors.index.json"
        if index.exists() and not set(read_json(index)["weight_map"].values()).issubset(files):
            raise ValueError(f"Missing weight shards for {name}.")
        write_json(cache / "ready" / f"{name}.json",
                   {"model": model, "snapshot": str(snapshot), "files": files})
        print(f"READY {name}: {model['revision']}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", required=True)
    parser.add_argument("--models", nargs="+", choices=sorted(model_registry()), required=True)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    prepare(args.cache, args.models, args.offline)


if __name__ == "__main__":
    main()
