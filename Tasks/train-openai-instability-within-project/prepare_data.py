"""Export exact historical partitions without uploading any data."""

import json
from pathlib import Path

from protocol import (
    CELLS, PROJECTS, PROMPT, cell_key, file_hash, read_json,
    prompt_only, require_unsealed, write_json,
)


class Tokenizer:
    def __init__(self, model):
        import tiktoken

        self.encoding = tiktoken.encoding_for_model(model)
        self.name = self.encoding.name
        self.labels = {s: self.encoding.encode(s, disallowed_special=()) for s in ("0", "1")}
        if any(len(tokens) != 1 for tokens in self.labels.values()):
            raise ValueError("Classification requires single-token class labels.")

    def encode(self, text):
        return self.encoding.encode(text, disallowed_special=())

    def decode(self, tokens):
        return self.encoding.decode(tokens)


def messages(text, level, features, tokenizer, config):
    original = tokenizer.encode(str(text))
    selected = original[:config["text_tokens"]]
    payload = {"unstable_word_threshold": level, "original_text": tokenizer.decode(selected)}
    if features is not None:
        payload["train_fitted_structured_features"] = features
    value = [{"role": "system", "content": PROMPT},
             {"role": "user", "content": json.dumps(payload, ensure_ascii=False, allow_nan=False)}]
    # Conservative chat-envelope allowance; actual billed usage is also checked.
    tokens = 32 + sum(16 + len(tokenizer.encode(item["content"])) for item in value)
    if tokens > config["max_input_tokens"]:
        raise ValueError("Structured prompt exceeds frozen input limit; no rows may be dropped.")
    return value, tokens, len(original) > len(selected)


def write_jsonl(path, rows):
    temporary = path.with_suffix(".writing")
    with temporary.open("w") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
    temporary.replace(path)


def read_records(path):
    with Path(path).open() as stream:
        return [json.loads(line) for line in stream]


def prepare(root, config, tokenizer=None, loader=None):
    from data_contract import load_project
    from unstable_model.data import label_column
    from unstable_model.features import FeatureTransformer

    require_unsealed(root)
    loader = loader or load_project
    tokenizer = tokenizer or Tokenizer(config["model"])
    frames = {}
    transforms = {}
    for project in PROJECTS:
        frames[project] = loader(project, root)
        train = frames[project][0]
        transform = FeatureTransformer().fit(train)
        transforms[project] = transform
        write_json(root / "prepared" / project / "transformer.json", transform.to_dict())
    entries = {}
    for project, level, variant in CELLS:
        key = cell_key(project, level, variant)
        target = root / "prepared" / key
        target.mkdir(parents=True, exist_ok=True)
        parts = {}
        for split, frame in zip(("train", "validation", "test"), frames[project]):
            feature_rows = [None] * len(frame)
            if variant == "structured":
                transform = transforms[project]
                matrix = transform.transform(frame)
                feature_rows = [
                    {name: float(format(value, ".8g"))
                     for name, value in zip(transform.feature_names, row)}
                    for row in matrix
                ]
            rows, sidecar, counts = [], [], []
            truncated = 0
            for item, features in zip(frame.to_dict("records"), feature_rows):
                prompt, tokens, cut = messages(item["model_text"], level, features, tokenizer, config)
                label = int(item[label_column(level)])
                if split == "train" and not prompt_only(config):
                    prompt = prompt + [{"role": "assistant", "content": str(label)}]
                    tokens += 17
                rows.append({"messages": prompt})
                sidecar.append({"row_id": item["row_id"], "label": label, "input_tokens": tokens})
                counts.append(tokens)
                truncated += int(cut)
            data_path, sidecar_path = target / f"{split}.jsonl", target / f"{split}_rows.json"
            write_jsonl(data_path, rows)
            write_json(sidecar_path, sidecar)
            parts[split] = {
                "rows": len(rows), "tokens": sum(counts), "max_tokens": max(counts),
                "truncated_rows": truncated, "payload_sha256": file_hash(data_path),
                "sidecar_sha256": file_hash(sidecar_path),
            }
        entries[key] = {"project": project, "level": level, "variant": variant, "partitions": parts,
                        "transformer_sha256": file_hash(root / "prepared" / project / "transformer.json")}
    manifest = {"schema": "openai-prepared-v1", "tokenizer": tokenizer.name,
                "label_tokens": tokenizer.labels, "entries": entries}
    path = root / "prepared.json"
    if path.exists() and read_json(path) != manifest:
        raise ValueError("Prepared data changed; use a new run ID.")
    write_json(path, manifest)
    return manifest


def partition(root, key, split):
    manifest = read_json(root / "prepared.json")
    entry = manifest["entries"][key]
    part = entry["partitions"][split]
    directory = root / "prepared" / key
    data_path, rows_path = directory / f"{split}.jsonl", directory / f"{split}_rows.json"
    if (file_hash(data_path) != part["payload_sha256"] or
            file_hash(rows_path) != part["sidecar_sha256"] or
            file_hash(root / "prepared" / entry["project"] / "transformer.json") != entry["transformer_sha256"]):
        raise ValueError("Prepared data or transformer changed.")
    records, rows = read_records(data_path), read_json(rows_path)
    if len(records) != len(rows) or len(rows) != part["rows"]:
        raise ValueError("Prepared row count changed.")
    return records, rows
