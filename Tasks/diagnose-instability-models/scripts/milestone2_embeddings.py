"""Reuse input-addressed frozen caches only; never load encoders or infer vectors."""

import re
from pathlib import Path

from support import HF, REPO, digest, file_hash, np, pd, row_hash


def historical_source_fingerprint():
    # Exact original cache producer fingerprint, without importing its GPU runtime.
    roots = [HF, REPO / "Tasks/research-hf-instability-models",
             REPO / "Tasks/jira-url-to-instability-model/unstable_model"]
    return digest({str(p.relative_to(REPO)): file_hash(p)
                   for root in roots for p in root.rglob("*.py")
                   if "cluster_runs" not in p.parts and "__pycache__" not in p.parts})


def inspect_cache(path, expected_rows, config):
    before = file_hash(path)
    values = np.load(path, mmap_mode="r", allow_pickle=False)
    if (values.ndim != 2 or values.shape[0] != expected_rows
            or not 1 <= values.shape[1] <= config["maximum_embedding_dimensions"]
            or values.dtype.kind != "f"):
        raise ValueError("Cache dimensions or numeric dtype differ from the frozen contract.")
    norms = np.sqrt(np.einsum("ij,ij->i", values, values, dtype=np.float64))
    if not np.isfinite(values).all() or not np.isfinite(norms).all() or (norms == 0).any():
        raise ValueError("Cache contains nonfinite or zero-norm vectors.")
    shape = list(values.shape)
    if file_hash(path) != before:
        raise ValueError("Embedding cache changed during inspection.")
    return {"path": str(path), "sha256": before, "shape": shape, "dtype": str(values.dtype)}


def inventory(population, integrity, artifact_roots, config):
    records, selected = [], {}
    source_fingerprint = historical_source_fingerprint()
    for project, group in population.groupby("project", sort=True):
        study_values = {
            digest(cell["protocol"]["study"]): cell["protocol"]["study"]
            for cell in integrity["cells"] if cell["project"] == project
            and cell["family"] == "SLM1" and cell["status"] == "succeeded"
        }
        if len(study_values) != 1:
            records.append({"project": project, "status": "blocked",
                            "reason": "Need one verified SLM1 study for this project."})
            continue
        study = next(iter(study_values.values()))
        for encoder in config["embedding_preference"]:
            entry = study["models"].get(encoder)
            identity = {"project": project, "encoder": encoder, "study_sha256": digest(study)}
            if not entry:
                records.append({**identity, "status": "blocked", "reason": "Encoder absent from sealed study."})
                continue
            if (study["source_sha256"] != source_fingerprint
                    or not re.fullmatch(r"[a-f0-9]{40}", entry["revision"])
                    or entry["pooling"] not in ("mean", "last")):
                records.append({**identity, "status": "blocked",
                                "reason": "Cache-producing source/revision/pooling cannot be verified; no inference fallback.",
                                "expected_source_sha256": study["source_sha256"],
                                "available_source_sha256": source_fingerprint})
                continue
            representation = {**identity, "model": entry, "original_config": study["config"],
                              "producer_versions": study["versions"],
                              "producer_source_sha256": source_fingerprint,
                              "tokenization": "Original TextBackend.encode_batch: pinned-revision tokenizer defaults, padding=True, truncation=True, max_length from original config; no adapters.",
                              "input_fields": "Existing frozen model_text, exact ordered strings.",
                              "integrity_limit": "Original cache has no independent vector checksum or row-ID sidecar. Ordered text/model/config/version key, producer code and shape are verified; observed numerical bytes are hashed and frozen now, not claimed historically checksum-verified."}
            partitions = {}
            for split in ("train", "validation", "test"):
                current = group[group.split == split]
                key = digest({"model": entry, "texts": current.model_text.tolist(),
                              "config": study["config"], "versions": study["versions"]})
                paths = sorted({(Path(root) / "embeddings" / (key + ".npy")).resolve()
                                for root in artifact_roots})
                present = [path for path in paths if path.is_file()]
                record = {**identity, "split": split, "expected_key": key,
                          "rows": len(current), "row_ids_sha256": row_hash(current.row_id),
                          "source_texts_sha256": digest(current.model_text.tolist()),
                          "searched_paths": [str(p) for p in paths]}
                try:
                    if len(present) != 1:
                        raise ValueError(f"Need exactly one matching cache; found {len(present)}.")
                    value = inspect_cache(present[0], len(current), config)
                    record.update(status="available", **value)
                    partitions[split] = record
                except (OSError, ValueError, TypeError) as exc:
                    record.update(status="blocked", reason=str(exc))
                records.append(record)
            if "train" in partitions:
                dimensions = partitions["train"]["shape"][1]
                for split in list(partitions):
                    if partitions[split]["shape"][1] != dimensions:
                        partitions[split].update(status="blocked", reason="Dimension differs from training space.")
                        del partitions[split]
                # Selection is by predeclared encoder preference and training availability only.
                if project not in selected:
                    selected[project] = {**representation, "partitions": partitions}
    return {"candidates": records, "selected": selected,
            "selection": "Per-project first preferred frozen encoder with valid training cache; never selected on test coverage, labels or scores.",
            "resource_policy": "Existing .npy reads only; no model/adapter loading, tokenization, download, inference or GPU.",
            "missing_test_note": "Original frozen workflow caches train/validation embeddings, not test inference vectors. Missing test caches block embedding-dependent test analyses only."}


def load_partition(record):
    path = Path(record["path"])
    if file_hash(path) != record["sha256"]:
        raise ValueError("Embedding bytes changed after inventory.")
    values = np.array(np.load(path, mmap_mode="r", allow_pickle=False), dtype=np.float32)
    if list(values.shape) != record["shape"] or not np.isfinite(values).all():
        raise ValueError("Embedding shape/values changed after inventory.")
    norms = np.sqrt(np.einsum("ij,ij->i", values, values, dtype=np.float64))
    if not np.isfinite(norms).all() or (norms == 0).any():
        raise ValueError("Invalid embedding norms after conversion.")
    values /= norms[:, None]
    if file_hash(path) != record["sha256"]:
        raise ValueError("Embedding bytes changed during loading.")
    return values


def bank_indices(row_ids, maximum, seed, purpose):
    return np.array(sorted(range(len(row_ids)), key=lambda i: digest(
        [seed, purpose, str(row_ids[i])]
    ))[:maximum], dtype=int)


def affinities(vectors, centers):
    # Small centroid products avoid BLAS-dependent floating-point status warnings.
    scores = np.einsum("ij,kj->ik", vectors, centers, optimize=False)
    if not np.isfinite(scores).all():
        raise ValueError("Nonfinite centroid similarity.")
    return scores


def nearest(query, bank, query_ids, bank_ids, query_text_hash, bank_text_hash, config, exclude_duplicates):
    k = config["neighbors"]
    answer = np.full((len(query), k), -1, dtype=int)
    similarities = np.full((len(query), k), np.nan)
    for start in range(0, len(query), config["distance_batch_rows"]):
        end = min(start + config["distance_batch_rows"], len(query))
        scores = query[start:end] @ bank.T
        invalid = np.asarray(query_ids[start:end])[:, None] == np.asarray(bank_ids)[None, :]
        if exclude_duplicates:
            invalid |= np.asarray(query_text_hash[start:end])[:, None] == np.asarray(bank_text_hash)[None, :]
        scores[invalid] = -np.inf
        order = np.argsort(-scores, axis=1, kind="stable")[:, :min(k, len(bank))]
        top = np.take_along_axis(scores, order, axis=1)
        valid = np.isfinite(top)
        answer[start:end, :order.shape[1]] = np.where(valid, order, -1)
        similarities[start:end, :order.shape[1]] = np.where(valid, np.clip(top, -1, 1), np.nan)
    return answer, similarities


def cluster_fit(train, config, seed):
    unique_indices = np.sort(np.unique(train, axis=0, return_index=True)[1])
    k = min(config["clusters"], len(unique_indices))
    if k < 2:
        raise ValueError("Training representation has fewer than two distinct vectors.")
    rng = np.random.RandomState(seed)
    centers = train[rng.choice(unique_indices, k, replace=False)].copy()
    for iteration in range(config["cluster_iterations"]):
        scores = affinities(train, centers)
        labels = np.argmax(scores, axis=1)
        updated = centers.copy()
        farthest = np.argsort(scores.max(axis=1), kind="stable")
        empty = 0
        for i in range(k):
            members = train[labels == i]
            mean = members.mean(axis=0) if len(members) else np.zeros(train.shape[1])
            norm = np.linalg.norm(mean)
            if norm > 0:
                updated[i] = mean / norm
            else:
                updated[i] = train[farthest[empty]]
                empty += 1
        if np.allclose(updated, centers, atol=1e-6, rtol=0):
            centers = updated
            break
        centers = updated
    return centers, {"iterations": iteration + 1, "effective_clusters": k,
                     "requested_clusters": config["clusters"], "seed": seed,
                     "method": "Bounded spherical k-means on label-blind, hash-sampled training rows; unit-vector normalization only.",
                     "training_empty_clusters": int(sum(~np.isin(np.arange(k), np.argmax(affinities(train, centers), axis=1))))}


def adjusted_rand(a, b):
    _, a = np.unique(a, return_inverse=True)
    _, b = np.unique(b, return_inverse=True)
    table = np.zeros((a.max() + 1, b.max() + 1), dtype=np.int64)
    np.add.at(table, (a, b), 1)
    choose2 = lambda x: float(np.sum(x * (x - 1) / 2))
    total = len(a) * (len(a) - 1) / 2
    if total == 0:
        return 1.0
    row, col = choose2(table.sum(axis=1)), choose2(table.sum(axis=0))
    expected, maximum = row * col / total, (row + col) / 2
    return (choose2(table) - expected) / (maximum - expected) if maximum != expected else 1.0


def fit_project(train, features, representation, config):
    values = load_partition(representation["partitions"]["train"])
    ids = train.row_id.to_numpy()
    hashes = features.set_index("row_id").loc[ids].text_sha256.to_numpy()
    bank = bank_indices(ids, config["neighbor_bank_rows"], config["seed"], "neighbors")
    fit = bank_indices(ids, config["cluster_fit_rows"], config["seed"], "clusters")
    thresholds = {}
    for duplicate_policy in ("include_duplicates", "exclude_duplicates"):
        _, scores = nearest(values, values[bank], ids, ids[bank], hashes, hashes[bank],
                            config, duplicate_policy == "exclude_duplicates")
        finite = scores[:, 0][np.isfinite(scores[:, 0])]
        thresholds[duplicate_policy] = float(np.quantile(finite, config["similarity_quantile"])) if len(finite) else None
    try:
        centers, cluster_info = cluster_fit(values[fit], config, config["seed"])
        other, _ = cluster_fit(values[fit], config, config["seed"] + config["stability_seed_offset"])
        primary_scores = affinities(values, centers)
        primary_labels = np.argmax(primary_scores, axis=1)
        affinity_cutoff = float(np.quantile(primary_scores.max(axis=1), config["outlier_quantile"]))
        stability = adjusted_rand(primary_labels, np.argmax(affinities(values, other), axis=1))
        representatives = []
        for i in range(len(centers)):
            eligible = np.flatnonzero(primary_labels == i)
            best = eligible[np.argmax(primary_scores[eligible, i])] if len(eligible) else None
            representatives.append({"cluster": f"C{i:02d}", "training_rows": len(eligible),
                                    "representative_row_id": str(ids[best]) if best is not None else None})
        cluster_info.update(status="succeeded", training_stability_adjusted_rand=stability,
                            outlier_training_quantile=config["outlier_quantile"],
                            outlier_similarity_cutoff=affinity_cutoff,
                            outlier_policy="Retain nearest-cluster assignment; separately flag affinity below the training cutoff.",
                            stability_seed=config["seed"] + config["stability_seed_offset"],
                            representatives=representatives,
                            stability_policy="One declared alternate seed; primary seed retained regardless of stability or labels.")
    except ValueError as exc:
        centers, cluster_info = None, {"status": "blocked", "reason": str(exc)}
    contract = {
        "neighbor_bank_rows": len(bank), "neighbor_bank_row_ids_sha256": row_hash(ids[bank]),
        "cluster_fit_rows": len(fit), "cluster_fit_row_ids_sha256": row_hash(ids[fit]),
        "training_similarity_quantile": config["similarity_quantile"],
        "training_similarity_thresholds": thresholds, "cluster": cluster_info,
        "distance": "cosine on unit-normalized vectors; ties broken by label-independent bank hash order",
        "bank_scope": "Same project training rows only; bounded deterministic sample, not the full nearest-neighbor population.",
    }
    return {"values": values, "bank_indices": bank, "centers": centers,
            "contract": contract, "bank_ids": ids[bank], "bank_text_hashes": hashes[bank]}


def assign_project(group, features, representation, fit, config):
    from support import LEVELS, label_column
    output = []
    train = group[group.split.eq("train")]
    bank = fit["bank_indices"]
    for split, record in representation["partitions"].items():
        current = group[group.split == split]
        vectors = fit["values"] if split == "train" else load_partition(record)
        ids = current.row_id.to_numpy()
        hashes = features.set_index("row_id").loc[ids].text_sha256.to_numpy()
        scores = affinities(vectors, fit["centers"]) if fit["centers"] is not None else None
        clusters = (np.argmax(scores, axis=1)
                    if fit["centers"] is not None else np.full(len(current), -1))
        affinity = (scores.max(axis=1) if fit["centers"] is not None
                    else np.full(len(current), np.nan))
        for mode in ("include_duplicates", "exclude_duplicates"):
            indices, similarities = nearest(vectors, fit["values"][bank], ids, fit["bank_ids"],
                                            hashes, fit["bank_text_hashes"], config,
                                            mode == "exclude_duplicates")
            valid = indices >= 0
            count = valid.sum(axis=1)
            threshold = fit["contract"]["training_similarity_thresholds"][mode]
            rows = pd.DataFrame({
                "row_id": ids, "project": current.project.to_numpy(), "split": split,
                "encoder": representation["encoder"], "duplicate_policy": mode,
                "neighbors": count, "nearest_cosine_similarity": similarities[:, 0],
                "high_training_similarity": similarities[:, 0] >= threshold if threshold is not None else False,
                "cluster": [f"C{i:02d}" if i >= 0 else "" for i in clusters],
                "centroid_cosine_similarity": affinity,
                "cluster_outlier": affinity < fit["contract"]["cluster"].get("outlier_similarity_cutoff", -np.inf),
            })
            for k in LEVELS:
                bank_labels = train[label_column(k)].to_numpy()[bank]
                neighbor_labels = bank_labels[np.maximum(indices, 0)]
                positives = (neighbor_labels * valid).sum(axis=1)
                y = current[label_column(k)].to_numpy()
                disagreement = np.where(y == 1, count - positives, positives)
                rows[f"label_disagreement_{k}"] = np.divide(
                    disagreement, count, out=np.full(len(count), np.nan), where=count > 0)
            output.append(rows)
    return pd.concat(output, ignore_index=True)
