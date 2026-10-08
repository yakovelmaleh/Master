"""Pinned local inference with the publisher's native head, not a fresh classifier."""

import importlib
import importlib.util
import math
import os
from pathlib import Path
import sys


TASK = Path(__file__).resolve().parent
SHARED = TASK.parent / "train-hf-instability-within-project"
sys.path.insert(0, str(SHARED))
from common import LEVELS, digest, external_path, file_hash, read_json, write_json


MODEL = read_json(TASK / "model.json")
FILES = (
    "config.json", "head.safetensors", "model.safetensors", "open_jev_config.json",
    "added_tokens.json", "special_tokens_map.json", "tokenizer.json",
    "tokenizer_config.json", "spm.model", *(
        name for name in MODEL["reviewed_files"] if name.endswith(".py")
    ),
)
PROMPT = (
    "Predict whether, after sprint entry, the issue's summary, description or "
    "acceptance criteria will be edited and differ by at least {level} words "
    "from this original text. Use only the original issue text; predict a future "
    "change, not whether the issue describes a software change."
)


def questions(level):
    if level not in LEVELS:
        raise ValueError("Unsupported instability level.")
    return [{"type": "noul", "instructions": PROMPT.format(level=level)}]


def positive_probability(answers):
    if (not isinstance(answers, list) or len(answers) != 1
            or not isinstance(answers[0], dict) or set(answers[0]) != {"noul"}):
        raise ValueError("Expected exactly one native noul probability, not a confidence score.")
    value = answers[0]["noul"]
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError("Invalid positive-class probability.")
    return float(value)


def verify_reviewed_files(snapshot):
    for name, expected in MODEL["reviewed_files"].items():
        if file_hash(snapshot / name) != expected:
            raise ValueError(f"Reviewed upstream file changed: {name}")
    config = read_json(snapshot / "open_jev_config.json")
    if (config["pool"] != "span" or config["max_state_tokens"] != MODEL["max_state_tokens"]
            or config["max_len"] != MODEL["max_len"]):
        raise ValueError("Unexpected native model configuration.")


def prepare(cache):
    from huggingface_hub import snapshot_download

    cache = external_path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    snapshot = Path(snapshot_download(MODEL["id"], revision=MODEL["revision"],
                                      cache_dir=str(cache), allow_patterns=list(FILES)))
    if snapshot.name != MODEL["revision"]:
        raise ValueError("Runtime download resolved an unexpected revision.")
    for name in FILES:
        if not (snapshot / name).is_file():
            raise ValueError(f"Missing native model artifact: {name}")
    verify_reviewed_files(snapshot)
    write_json(cache / "ready/jev_deberta.json", {
        "model": MODEL, "snapshot": str(snapshot),
        "files": {name: file_hash(snapshot / name) for name in FILES},
    })
    print(f"READY jev_deberta: {MODEL['revision']}", flush=True)


def snapshot_for(cache):
    cache = external_path(cache)
    ready = read_json(cache / "ready/jev_deberta.json")
    if ready["model"] != MODEL or set(ready["files"]) != set(FILES):
        raise ValueError("Stale Jev readiness manifest.")
    snapshot = Path(ready["snapshot"]).resolve()
    if cache not in snapshot.parents or snapshot.name != MODEL["revision"]:
        raise ValueError("Unexpected Jev snapshot location.")
    for name, expected in ready["files"].items():
        path = snapshot / name
        if cache not in path.resolve().parents or file_hash(path) != expected:
            raise ValueError(f"Corrupt Jev snapshot file: {name}")
    verify_reviewed_files(snapshot)
    return snapshot, ready["files"]


def upstream_class(snapshot):
    package_name = "_master_reviewed_jev"
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        if package_name not in sys.modules:
            spec = importlib.util.spec_from_file_location(
                package_name, snapshot / "typed_decisions/__init__.py",
                submodule_search_locations=[str(snapshot / "typed_decisions")],
            )
            package = importlib.util.module_from_spec(spec)
            sys.modules[package_name] = package
            spec.loader.exec_module(package)
        return importlib.import_module(package_name + ".open_jev").OpenJev
    finally:
        sys.dont_write_bytecode = previous


class LocalJev:
    def __init__(self, cache):
        import torch

        # The reviewed loader is local-path based; prevent any Hub fallback.
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        if not torch.cuda.is_available():
            raise ValueError("An allocated CUDA GPU is required; no silent CPU fallback.")
        self.snapshot, self.files = snapshot_for(cache)
        self.native = upstream_class(self.snapshot).from_pretrained(str(self.snapshot), device="cuda")
        self.native.model.eval()

    def predict(self, texts, level):
        result = []
        for index, text in enumerate(texts):
            result.append(positive_probability(self.native.decide(str(text), questions(level))))
            if (index + 1) % 50 == 0:
                print(f"level={level} processed={index + 1}", flush=True)
        return result

    def coverage(self, texts):
        lengths = [len(self.native.tok(str(text), add_special_tokens=False)["input_ids"]) for text in texts]
        return {"rows": len(lengths), "state_token_limit": MODEL["max_state_tokens"],
                "truncated_rows": sum(value > MODEL["max_state_tokens"] for value in lengths),
                "policy": "native right truncation of concatenated historical text"}

    def close(self):
        import gc
        import torch

        del self.native
        gc.collect()
        torch.cuda.empty_cache()
