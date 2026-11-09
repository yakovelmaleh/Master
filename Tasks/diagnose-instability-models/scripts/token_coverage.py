"""Optional offline tokenizer-only coverage; no weights, remote code or inference."""

import os
from pathlib import Path

from support import emit, external_path, file_hash, pd, read_json, save_table


def token_coverage(root, population, cache):
    rows, checks = [], []
    cells = read_json(root / "manifest/integrity_checks.json")["cells"]
    for cell in cells:
        if cell["status"] != "succeeded" or cell["family"] == "classical":
            continue
        family, project, k = cell["family"], cell["project"], cell["level"]
        identity = {"family": family, "project": project, "level": k}
        if cache is None:
            checks.append({**identity, "status": "unavailable", "reason": "No offline tokenizer cache supplied."})
            continue
        try:
            os.environ["HF_HUB_OFFLINE"] = "1"
            os.environ["TRANSFORMERS_OFFLINE"] = "1"
            from transformers import AutoTokenizer

            protocol = cell["protocol"]
            if family == "Jev":
                model = protocol["study"]["model"]
                name = "jev_deberta"
                limit = model["max_state_tokens"]
            else:
                inference = protocol["inference"]
                model = inference["model"]
                name = inference["model_key"]
                limit = inference["config"]["max_length"]
            cache = external_path(cache)
            ready = read_json(cache / "ready" / f"{name}.json")
            if ready["model"] != model:
                raise ValueError("Offline tokenizer manifest model/revision differs from selected model.")
            snapshot = Path(ready["snapshot"]).resolve()
            if cache not in snapshot.parents or snapshot.name != model["revision"]:
                raise ValueError("Offline snapshot escapes cache or has wrong revision.")
            checked = {}
            for relative, expected in ready["files"].items():
                if any(part in relative for part in (
                    "tokenizer", "special_tokens", "added_tokens", "vocab", "merges",
                    "spm.model", "sentencepiece", "config.json",
                )) and not relative.endswith(".py"):
                    if Path(relative).is_absolute() or ".." in Path(relative).parts:
                        raise ValueError("Invalid relative tokenizer artifact path.")
                    path = (snapshot / relative).resolve()
                    # HF cache symlinks to its blob directory are legitimate, but not outside cache.
                    if cache not in path.parents or file_hash(path) != expected:
                        raise ValueError(f"Offline tokenizer bytes changed: {relative}")
                    checked[relative] = expected
            if not any("tokenizer" in name for name in checked):
                raise ValueError("No hashed tokenizer artifacts found.")
            tokenizer = AutoTokenizer.from_pretrained(
                snapshot, local_files_only=True, trust_remote_code=False
            )
            if tokenizer.truncation_side != "right":
                raise ValueError("Tokenizer truncation side differs from audited right-truncation policy.")
            selected = population[population.project == project]
            for row in selected.itertuples():
                options = {"add_special_tokens": False} if family == "Jev" else {}
                length = len(tokenizer(row.model_text, truncation=False, **options)["input_ids"])
                rows.append({**identity, "row_id": row.row_id, "split": row.split,
                             "tokens": length, "limit": limit, "truncated": length > limit})
            checks.append({**identity, "status": "succeeded", "revision": model["revision"],
                           "tokenizer_hashes": checked, "limit": limit,
                           "policy": "native state tokens without special tokens" if family == "Jev"
                           else "AutoTokenizer default special tokens; concatenated original fields"})
        except (OSError, ValueError, KeyError, ImportError) as exc:
            # A failed cell must not leave partial coverage rows eligible for analysis.
            rows = [r for r in rows if not all(r[key] == value for key, value in identity.items())]
            checks.append({**identity, "status": "blocked", "reason": str(exc)})
    frame = pd.DataFrame(rows, columns=[
        "family", "project", "level", "row_id", "split", "tokens", "limit", "truncated"
    ])
    save_table(root, "data-characterization/token_coverage.csv", frame, "T2")
    emit(root, "data-characterization/token_coverage.json", "T2",
         "succeeded" if checks and all(c["status"] == "succeeded" for c in checks) else "blocked",
         cells=checks, note="Missing tokenizer evidence is not approximated by words or characters.")
    return frame
