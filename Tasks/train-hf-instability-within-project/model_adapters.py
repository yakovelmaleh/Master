"""Local-only Hugging Face representations and reloadable classification heads."""

import gc
import importlib.metadata
from pathlib import Path
import random

import numpy as np

from common import digest, external_path, file_hash, model_registry, read_json, write_json


def seed_everything(seed):
    import torch

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def versions():
    return {name: importlib.metadata.version(name) for name in
            ("torch", "transformers", "peft", "accelerate", "huggingface-hub",
             "safetensors", "numpy", "pandas", "scikit-learn")}


def pool(hidden, mask, strategy):
    import torch

    if hidden.ndim != 3 or hidden.shape[:2] != mask.shape or not mask.any(dim=1).all():
        raise ValueError("Invalid text hidden states or empty attention mask.")
    if strategy == "mean":
        value = (hidden.float() * mask.unsqueeze(-1)).sum(dim=1) / mask.sum(dim=1, keepdim=True)
    elif strategy == "last":
        positions = torch.arange(mask.shape[1], device=mask.device).expand_as(mask)
        last = positions.masked_fill(~mask.bool(), -1).max(dim=1).values
        value = hidden[torch.arange(len(hidden), device=hidden.device), last].float()
    else:
        raise ValueError(f"Unknown pooling strategy: {strategy}")
    return torch.nn.functional.normalize(value, dim=-1)


def snapshot_for(cache, name):
    cache = external_path(cache)
    ready = read_json(cache / "ready" / f"{name}.json")
    if ready["model"] != model_registry()[name]:
        raise ValueError(f"Stale cache manifest for {name}; rerun runtime preparation.")
    snapshot = Path(ready["snapshot"]).resolve()
    if cache not in snapshot.parents:
        raise ValueError("Snapshot escapes configured cache.")
    for relative, expected in ready["files"].items():
        path = snapshot / relative
        if cache not in path.resolve().parents or file_hash(path) != expected:
            raise ValueError(f"Corrupt cached snapshot file: {relative}")
    return snapshot


class TextBackend:
    def __init__(self, name, cache, config, training=False, adapter=None):
        import torch
        from transformers import AutoModel, AutoTokenizer, BitsAndBytesConfig

        self.name = name
        self.config = config
        self.entry = model_registry()[name]
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        dtype = getattr(torch, config["dtype"])
        if config["dtype"] == "bfloat16" and (
            self.device.type != "cuda" or not torch.cuda.is_bf16_supported()
        ):
            raise ValueError("Configured BF16 is unsupported on this device.")
        if self.device.type == "cpu" and dtype != torch.float32:
            raise ValueError("CPU smoke checks require float32.")
        snapshot = snapshot_for(cache, name)
        self.tokenizer = AutoTokenizer.from_pretrained(snapshot, local_files_only=True, trust_remote_code=False)
        if self.tokenizer.pad_token_id is None:
            if self.tokenizer.eos_token_id is None:
                raise ValueError("Tokenizer has neither a pad nor EOS token.")
            self.tokenizer.pad_token = self.tokenizer.eos_token
        options = {"local_files_only": True, "trust_remote_code": False,
                   "attn_implementation": "eager", "dtype": dtype}
        quantized = self.entry["quantize"]
        if quantized:
            if self.device.type != "cuda":
                raise ValueError(f"{name} requires a CUDA quantization profile; no CPU fallback.")
            options["quantization_config"] = BitsAndBytesConfig(
                load_in_4bit=True, bnb_4bit_quant_type="nf4",
                bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=dtype,
            )
            options["device_map"] = {"": torch.cuda.current_device()}
        self.model = AutoModel.from_pretrained(snapshot, **options)
        if not quantized:
            self.model.to(self.device)
        if hasattr(self.model.config, "use_cache"):
            self.model.config.use_cache = False
        if hasattr(self.model.config, "reference_compile"):
            self.model.config.reference_compile = False
        text_config = getattr(self.model.config, "text_config", self.model.config)
        self.hidden_size = text_config.hidden_size
        if adapter is not None:
            from peft import PeftModel

            self.model = PeftModel.from_pretrained(self.model, adapter, is_trainable=False)
        elif training:
            from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training

            if quantized:
                self.model = prepare_model_for_kbit_training(self.model, use_gradient_checkpointing=True)
            targets = [
                path for path, _ in self.model.named_modules()
                if path.split(".")[-1] in self.entry["lora_targets"]
                and not any(word in path.lower() for word in ("vision", "visual", "audio"))
            ]
            if not targets:
                raise ValueError(f"No language-only LoRA targets found for {name}.")
            self.model = get_peft_model(self.model, LoraConfig(
                r=config["lora_rank"], lora_alpha=2 * config["lora_rank"],
                lora_dropout=0.0, target_modules=targets, bias="none",
            ))
        if not training:
            self.model.requires_grad_(False)
        self.model.eval()

    def encode_batch(self, texts):
        tokens = self.tokenizer(
            list(texts), padding=True, truncation=True,
            max_length=self.config["max_length"], return_tensors="pt",
        ).to(self.device)
        output = self.model(**tokens)
        hidden = getattr(output, "last_hidden_state", None)
        if hidden is None:
            raise ValueError(f"{self.name} does not expose text last_hidden_state; profile failed.")
        return pool(hidden, tokens["attention_mask"], self.entry["pooling"])

    def length_report(self, texts):
        lengths = [len(self.tokenizer(text, truncation=False)["input_ids"]) for text in texts]
        limit = self.config["max_length"]
        return {
            "rows": len(lengths), "max_length": limit,
            "token_length_percentiles": np.percentile(lengths, [50, 90, 95, 99, 100]).tolist(),
            "truncated_rows": sum(length > limit for length in lengths),
            "retained_token_fraction": sum(min(length, limit) for length in lengths) / sum(lengths),
            "policy": "concatenate original summary, description, acceptance criteria; right truncate",
        }

    def embeddings(self, texts, storage):
        import torch

        texts = list(texts)
        key = digest({"model": self.entry, "texts": texts, "config": self.config,
                      "versions": versions()})
        destination = external_path(storage) / "embeddings" / f"{key}.npy"
        from common import exclusive_lock

        with exclusive_lock(destination.with_suffix(".lock")):
            if destination.exists():
                values = np.load(destination, allow_pickle=False)
            else:
                batches = []
                self.model.eval()
                with torch.no_grad():
                    for start in range(0, len(texts), self.config["batch_size"]):
                        batches.append(self.encode_batch(
                            texts[start:start + self.config["batch_size"]]
                        ).cpu().numpy())
                values = np.concatenate(batches)
                destination.parent.mkdir(parents=True, exist_ok=True)
                with destination.with_suffix(".writing").open("wb") as stream:
                    np.save(stream, values, allow_pickle=False)
                destination.with_suffix(".writing").replace(destination)
        if values.shape != (len(texts), self.hidden_size) or not np.isfinite(values).all():
            raise ValueError("Invalid cached embeddings.")
        return values

    def close(self):
        import torch

        del self.model
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


def save_head(path, weight, bias):
    from safetensors.numpy import save_file

    save_file({"weight": np.ascontiguousarray(weight, dtype=np.float32),
               "bias": np.ascontiguousarray(bias, dtype=np.float32)}, str(path))


def load_head(path):
    from safetensors.numpy import load_file

    return load_file(str(path))


def sigmoid_head(features, head):
    from scipy.special import expit

    return expit((features @ head["weight"].T + head["bias"]).reshape(-1))


def train_adapter(backend, texts, structured, labels, config, output, learning_rate, balanced):
    import torch
    from sklearn.utils.class_weight import compute_sample_weight

    texts = list(texts)
    weights = compute_sample_weight("balanced", labels) if balanced else np.ones(len(labels))
    head = torch.nn.Linear(backend.hidden_size + structured.shape[1], 1).to(backend.device)
    optimizer = torch.optim.AdamW(
        [p for p in backend.model.parameters() if p.requires_grad] + list(head.parameters()),
        lr=learning_rate,
    )
    rng = np.random.RandomState(config["seed"])
    for _ in range(config["epochs"]):
        backend.model.train()
        for start in range(0, len(labels), config["batch_size"]):
            # The permutation is fixed per epoch, not independently resampled per batch.
            if start == 0:
                indices = rng.permutation(len(labels))
            batch = indices[start:start + config["batch_size"]]
            features = backend.encode_batch([texts[i] for i in batch])
            extra = torch.as_tensor(structured[batch], dtype=torch.float32, device=backend.device)
            logits = head(torch.cat([features, extra], dim=1)).reshape(-1)
            target = torch.as_tensor(labels[batch], dtype=torch.float32, device=backend.device)
            loss = torch.nn.functional.binary_cross_entropy_with_logits(
                logits, target, reduction="none"
            )
            loss = (loss * torch.as_tensor(weights[batch], device=backend.device)).mean()
            if not torch.isfinite(loss):
                raise ValueError("Nonfinite training loss; change configuration explicitly and reprofile.")
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(
                [p for group in optimizer.param_groups for p in group["params"]], 1.0
            )
            optimizer.step()
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    backend.model.save_pretrained(output / "adapter", safe_serialization=True)
    adapter_config = read_json(output / "adapter/adapter_config.json")
    adapter_config["base_model_name_or_path"] = backend.entry["id"]
    adapter_config["revision"] = backend.entry["revision"]
    write_json(output / "adapter/adapter_config.json", adapter_config)
    save_head(output / "head.safetensors", head.weight.detach().cpu().numpy(), head.bias.detach().cpu().numpy())
    backend.model.eval()
    return head


def predict(backend, texts, structured, head):
    import torch

    values = []
    texts = list(texts)
    backend.model.eval()
    with torch.no_grad():
        for start in range(0, len(texts), backend.config["batch_size"]):
            features = backend.encode_batch(texts[start:start + backend.config["batch_size"]]).cpu().numpy()
            values.extend(sigmoid_head(
                np.concatenate([features, structured[start:start + len(features)]], axis=1), head
            ))
    return np.asarray(values)
