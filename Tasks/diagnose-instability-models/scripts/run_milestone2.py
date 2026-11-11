#!/usr/bin/env python3
"""New-run T5-first/T4 diagnostics from successful M1 evidence, never inference."""

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import sys

from support import (
    HF, LEVELS, REPO, TASK, digest, emit, external_path, file_hash, label_column,
    np, pd, read_json, save_table, slug, source_hash, write_json,
)
from diagnostic_config import validate_milestone2
from evidence import verify_population
from prepare_review import load_inputs
from errors import support
from milestone2_text import (
    FLAGS, assign_lengths, definitions_note, exact_duplicate_disagreement,
    fit_lengths, metric_slices, prevalence, profiles_and_shift, text_features,
)
from milestone2_embeddings import inventory, fit_project, assign_project


def verify_inputs(source, batch_id, config):
    inputs = load_inputs(source)
    original_config = inputs["run"]["configuration"]
    for key in ("minimum_slice_rows", "minimum_slice_positives", "minimum_slice_negatives", "metric_tolerance"):
        if config[key] != original_config[key]:
            raise ValueError(f"Milestone two must preserve M1's {key}.")
    reference = read_json(HF / "reference_contract.json")
    if file_hash(HF / "reference_contract.json") != inputs["run"]["reference_sha256"]:
        raise ValueError("Frozen population contract differs from M1.")
    if set(inputs["population"].project) != set(reference["projects"]):
        raise ValueError("Milestone-one population is incomplete.")
    for project, group in inputs["population"].groupby("project"):
        if len(group) > config["maximum_project_rows"]:
            raise ValueError("Project population exceeds the frozen CPU resource bound.")
        verify_population(group, [group[group.split.eq(s)] for s in ("train", "validation", "test")],
                          reference["projects"][project])
    prefix = f"error-analysis/{slug(batch_id)}/"
    status_path = source / prefix / "status.json"
    status = read_json(status_path)
    if status["status"] != "succeeded" or status["run_id"] != inputs["run"]["run_id"]:
        raise ValueError("Successful CI reconciliation supplement is required.")
    for name, expected in status["input_sha256"].items():
        if file_hash(source / name) != expected:
            raise ValueError("M1 evidence differs from the reconciled snapshot.")
    ci_path = source / prefix / "ci_reconciliation.json"
    if file_hash(ci_path) != status["outputs_sha256"]["ci_reconciliation.json"]:
        raise ValueError("Reconciliation JSON hash differs from its status manifest.")
    ci = read_json(ci_path)
    if (ci["run_id"] != inputs["run"]["run_id"]
            or {(c["project"], c["level"]) for c in ci["cells"]} != {("MariaDB", 15), ("IntelDAOS", 5)}
            or any(c["status"] != "succeeded" for c in ci["cells"])):
        raise ValueError("Both original CI targets must have successful exact-input replays.")
    for cell in ci["cells"]:
        if cell["configurations"]["diagnostic"] != original_config:
            raise ValueError("Reconciled diagnostic configuration differs from M1.")
    inputs["input_sha256"].update({
        prefix + "status.json": file_hash(status_path),
        prefix + "ci_reconciliation.json": file_hash(ci_path),
    })
    inputs["reconciliation"] = ci
    return inputs


def embedding_summaries(assignments, features, diagnostics, config, fits):
    profiles, shifts = [], []
    keyed = features.set_index("row_id")
    for (project, split, policy), rows in assignments.groupby(["project", "split", "duplicate_policy"]):
        joined = rows.merge(features, on=["row_id", "project", "split"], validate="one_to_one")
        for k in LEVELS:
            valid = joined.neighbors.eq(config["neighbors"])
            y = joined.loc[valid, label_column(k)]
            bank_labels = keyed.loc[fits[project]["bank_ids"], label_column(k)]
            profiles.append({
                "project": project, "split": split, "level": k, "duplicate_policy": policy,
                "analysis": "training_neighbor_label_disagreement", "query_rows": len(joined),
                "rows_without_k_neighbors": int((~valid).sum()),
                "training_bank_rows": len(bank_labels),
                "training_bank_positives": int(bank_labels.sum()),
                "training_bank_prevalence": float(bank_labels.mean()),
                **support(pd.DataFrame({"actual_label": y}), config),
                "mean_disagreement": float(joined.loc[valid, f"label_disagreement_{k}"].mean()) if valid.any() else None,
                "by_recorded_label": {
                    str(label): {
                        "rows": int((valid & joined[label_column(k)].eq(label)).sum()),
                        "adequate_class_support": int((valid & joined[label_column(k)].eq(label)).sum())
                        >= config["minimum_slice_positives" if label else "minimum_slice_negatives"],
                        "mean_disagreement": float(joined.loc[
                            valid & joined[label_column(k)].eq(label), f"label_disagreement_{k}"
                        ].mean()) if (valid & joined[label_column(k)].eq(label)).any() else None,
                    } for label in (0, 1)
                },
                "interpretation": "Representation-dependent descriptive disagreement, not label error, Bayes error, predictability limit or a classifier evaluation.",
            })
        if policy != "include_duplicates":
            continue
        training = assignments[(assignments.project == project) & assignments.split.eq("train")
                               & assignments.duplicate_policy.eq(policy)]
        clusters = sorted(set(training.cluster) | set(rows.cluster))
        a = training.cluster.value_counts(normalize=True).reindex(clusters, fill_value=0)
        b = rows.cluster.value_counts(normalize=True).reindex(clusters, fill_value=0)
        clustered = bool(rows.cluster.ne("").any())
        shifts.append({
            "project": project, "split": split, "rows": len(rows),
            "cluster_status": "available" if clustered else "blocked",
            "cluster_total_variation_from_training": float(np.abs(a - b).sum() / 2) if clustered else None,
            "outlier_rows": int(rows.cluster_outlier.sum()) if clustered else None,
            "outlier_rate": float(rows.cluster_outlier.mean()) if clustered else None,
            "mean_centroid_cosine_similarity": float(rows.centroid_cosine_similarity.mean())
            if rows.centroid_cosine_similarity.notna().any() else None,
        })
        for cluster, members in joined[joined.cluster.ne("")].groupby("cluster"):
            members = members.sort_values("time_add_to_sprint", kind="stable")
            token_rows = diagnostics[(diagnostics.project == project) & (diagnostics.split == split)
                                     & diagnostics.row_id.isin(members.row_id)]
            token_coverage = []
            if "tokens" in token_rows and "truncated" in token_rows:
                for (family, k), token_group in token_rows.groupby(["family", "level"]):
                    available = pd.to_numeric(token_group.tokens, errors="coerce").notna()
                    token_coverage.append({
                        "family": family, "level": int(k), "available_rows": int(available.sum()),
                        "truncated_rows": int(token_group.loc[available, "truncated"].astype(str).str.lower().eq("true").sum()),
                        "scope": "Selected prediction model tokenizer, not necessarily this embedding encoder.",
                    })
            profiles.append({
                "analysis": "cluster_profile", "project": project, "split": split,
                "cluster": cluster, "rows": len(members), "word_length_median": float(members.words.median()),
                "characteristics": {flag: {"rows": int(members[flag].sum()),
                                         "rate": float(members[flag].mean())} for flag in FLAGS},
                "labels": {str(k): prevalence(members, k, config) for k in LEVELS},
                "classifier_token_coverage": token_coverage,
                "interpretation": "Unreviewed numeric cluster, not a named semantic story category.",
            })
    return profiles, shifts


def embedding_masks(assignments, config):
    indexed = {(p, s, d): g.set_index("row_id") for (p, s, d), g in assignments.groupby(
        ["project", "split", "duplicate_policy"]
    )}

    def masks(project, split, k, traits):
        for mode in ("include_duplicates", "exclude_duplicates"):
            group = indexed.get((project, split, mode))
            if group is None:
                continue
            if set(group.index) != set(traits.row_id):
                raise ValueError("Embedding assignment population differs from the matched partition.")
            group = group.loc[traits.row_id]
            complete = group.neighbors.eq(config["neighbors"])
            yield f"neighbors:{mode}:high_similarity", complete & group.high_training_similarity
            yield f"neighbors:{mode}:other_similarity", complete & ~group.high_training_similarity
            yield f"neighbors:{mode}:outcome_defined_majority_disagreement", complete & group[f"label_disagreement_{k}"].ge(.5)
            if mode == "include_duplicates":
                for cluster in sorted(group.cluster.unique()):
                    if cluster:
                        yield f"cluster:{cluster}", group.cluster.eq(cluster)
                if group.cluster.ne("").any():
                    yield "cluster_outlier:true", group.cluster_outlier
                    yield "cluster_outlier:false", ~group.cluster_outlier
    return masks


def concise_evidence(profiles, metrics):
    result = []
    for profile in profiles:
        if profile["split"] != "test" or not profile["slice"].startswith("length_bin:"):
            continue
        key = tuple(profile[name] for name in ("project", "level", "split", "slice"))
        matched = [m for m in metrics if tuple(m[name] for name in ("project", "level", "split", "slice")) == key]
        result.append({
            "project": key[0], "level": key[1], "slice": key[3], "rows": profile["rows"],
            "positives": profile["positives"], "adequate_support": profile["adequate_support"],
            "prevalence": profile["recorded_label_prevalence"],
            "prevalence_interval_95": profile["prevalence_interval_95"],
            "comparisons": [{
                "family": m["family"], "adequate_support": m["adequate_support"],
                "auc_prc": {name: m["metrics"][name]["auc_prc"] for name in ("classical", "model")}
                if m.get("metrics") else None,
                "delta_auc_prc": m.get("auc_prc_difference_model_minus_classical"),
                "delta_interval_95": m["uncertainty"]["interval_95"],
            } for m in matched],
        })
    return result


def execute(args):
    config = read_json(args.config)
    validate_milestone2(config)
    source = external_path(args.source_run)
    root = external_path(args.output_root) / slug(args.run_id)
    if source == root or source in root.parents or root in source.parents:
        raise ValueError("M2 must be a separate run, not inside or above its M1 source.")
    if root.exists():
        raise ValueError("Milestone-two output already exists; choose a new run ID, never overwrite.")
    inputs = verify_inputs(source, args.batch_id, config)
    root.mkdir(parents=True, exist_ok=False)
    run = {
        "schema": config["schema"], "run_id": args.run_id, "configuration": config, "configuration_sha256": digest(config),
        "source_sha256": source_hash(), "created_utc": datetime.now(timezone.utc).isoformat(),
        "source_run": str(source), "source_run_sha256": inputs["run"]["source_sha256"],
        "input_sha256": inputs["input_sha256"], "reference_sha256": inputs["run"]["reference_sha256"],
        "numpy_version": np.__version__, "pandas_version": pd.__version__, "python": sys.version,
        "execution_environment": {key: os.environ.get(key) for key in (
            "SLURM_JOB_ID", "SLURM_CPUS_PER_TASK", "SLURM_MEM_PER_NODE",
            "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"
        )},
        "review_use": "Hypothesis generation only; no review rows or answers enter feature fitting, clustering or bank selection.",
        "scope": "T5 prioritized, automated T4; no predictive training, inference, downloads, relabeling, T6/T7.",
    }
    write_json(root / "run.json", run)
    emit(root, "manifest/status.json", "T4-T5", "deferred", reason="execution started")
    try:
        population, predictions = inputs["population"], inputs["predictions"]
        emit(root, "manifest/prior_ci_reconciliation.json", "T4-T5", "succeeded",
             source_path=str(source / "error-analysis" / args.batch_id / "ci_reconciliation.json"),
             cells=inputs["reconciliation"]["cells"],
             interpretation="Both previous methods/configurations retained; no rerun or selection by interval sign.")
        features = text_features(population)
        lengths = fit_lengths(features, config)
        features = assign_lengths(features, lengths)
        caches = inventory(population, inputs["integrity"], inputs["run"]["artifact_roots"], config)
        emit(root, "manifest/embedding_inventory.json", "T4-T5", "succeeded", **caches)
        fits, embedding_blocks = {}, []
        for project in sorted(population.project.unique()):
            representation = caches["selected"].get(project)
            if representation is None:
                embedding_blocks.append({"project": project, "reason": "No verified frozen training embedding cache."})
                continue
            train = population[(population.project == project) & population.split.eq("train")]
            try:
                fits[project] = fit_project(train, features, representation, config)
            except (ValueError, OSError) as exc:
                embedding_blocks.append({"project": project, "reason": str(exc)})
                continue
            for split in ("train", "validation", "test"):
                if split not in representation["partitions"]:
                    embedding_blocks.append({"project": project, "split": split, "reason": "Matching cache unavailable."})
            if fits[project]["centers"] is not None:
                path = root / "semantic-groups" / f"{project}-centroids.npy"
                path.parent.mkdir(parents=True, exist_ok=True)
                np.save(path, fits[project]["centers"], allow_pickle=False)
                fits[project]["contract"]["centroids_sha256"] = file_hash(path)
            else:
                embedding_blocks.append({"project": project, "analysis": "clustering",
                                         "reason": fits[project]["contract"]["cluster"]["reason"]})
        # Persist train-only definitions before any validation/test slice evaluation.
        emit(root, "manifest/analysis_contract.json", "T4-T5", "succeeded",
             feature_definitions=definitions_note(), length_bins=lengths,
             embedding_training_contracts={p: fit["contract"] for p, fit in fits.items()},
             grouping_scope="Separate projects; one frozen encoder per project across all K.",
             fit_scope="Training text/vectors only, no labels in bin/cluster/bank/threshold fitting.",
             uncertainty="Existing support gates; 500 non-circular chronological row-block resamples, 20 rows per block. Slice intervals exploratory/unadjusted and compress gaps; no significance claims.",
             semantic_names="Unavailable: numeric cluster IDs are not manually reviewed categories.",
             outcome_defined_slices="Neighbor-disagreement slices explicitly condition on recorded query labels; diagnostic, never prospective targeting rules.")
        save_table(root, "complexity/text_characteristics.csv", features, "T5")
        profiles, shifts = profiles_and_shift(features, lengths, config)
        metrics = metric_slices(population, predictions, features, lengths, config)
        emit(root, "complexity/characteristic_profiles.json", "T5", "succeeded", profiles=profiles)
        emit(root, "complexity/matched_characteristic_metrics.json", "T5", "succeeded", comparisons=metrics,
             original_full_cell_comparisons=[
                 c for c in inputs["slices"]["comparisons"] if c["slice"] == "all"
             ], full_cell_note="Copied from verified M1 evidence; not recomputed or reselected.")
        emit(root, "complexity/exact_duplicate_disagreement.json", "T5", "succeeded",
             comparisons=exact_duplicate_disagreement(features, config))
        emit(root, "shift/temporal_shift.json", "T5", "succeeded", comparisons=shifts)
        emit(root, "complexity/length_evidence.json", "T5", "succeeded",
             results=concise_evidence(profiles, metrics),
             interpretation="All predeclared test length bins, not a selection of winning slices; unsupported cells flagged.")
        emit(root, "manifest/t5_text_status.json", "T5", "succeeded")
        assignments = []
        for project, fit in fits.items():
            assignments.append(assign_project(
                population[population.project == project], features, caches["selected"][project], fit, config
            ))
        embedding_metrics = []
        if assignments:
            assignments = pd.concat(assignments, ignore_index=True)
            save_table(root, "semantic-groups/assignments_and_neighbors.csv", assignments, "T4-T5")
            ep, es = embedding_summaries(assignments, features, inputs["diagnostics"], config, fits)
            embedding_metrics = metric_slices(population, predictions, features, lengths, config,
                                             extra=embedding_masks(assignments, config))
            emit(root, "semantic-groups/profiles.json", "T4-T5", "succeeded", profiles=ep)
            emit(root, "shift/representation_shift.json", "T5", "succeeded", comparisons=es)
            emit(root, "semantic-groups/matched_metrics.json", "T4-T5", "succeeded",
                 comparisons=embedding_metrics)
        for name, expected in inputs["input_sha256"].items():
            if file_hash(source / name) != expected:
                raise ValueError(f"M1 input changed during M2 execution: {name}")
        if source_hash() != run["source_sha256"]:
            raise ValueError("Producer code changed during milestone-two execution.")
        for representation in caches["selected"].values():
            for record in representation["partitions"].values():
                if file_hash(Path(record["path"])) != record["sha256"]:
                    raise ValueError("Embedding cache changed during analysis.")
        state = "blocked" if embedding_blocks else "succeeded"
        emit(root, "manifest/embedding_status.json", "T4-T5", state, blocked=embedding_blocks)
        emit(root, "summary.json", "T4-T5", state,
             t5_text_status="succeeded", embedding_blocks=embedding_blocks,
             input_rows=len(population), characteristic_comparisons=len(metrics),
             supported_characteristic_comparisons=sum(c["adequate_support"] for c in metrics),
             embedding_comparisons=len(embedding_metrics),
             history_based_label_verification="unavailable",
             training_model_performance="Unavailable in M1 saved prediction partitions; no training predictions regenerated.",
             review_independence="20 diagnostic text reviews are hypothesis-generating, not new labels.",
             prior_ci_artifact=str(source / "error-analysis" / args.batch_id / "ci_reconciliation.json"),
             other_work="Existing validation ablation comparisons and feature-refit experiments are not implemented in this focused pass; no substitute model fits.",
             findings_status="Read per-project/K counts and supported comparisons before drawing conclusions; automated completion is not causal interpretation.")
        (root / "coordination_handoff.md").write_text(
            "# MAster SLM: T5-first / automated T4\n\n"
            f"Source: `{source}`. New output: `{root}`.\n\n"
            f"T5 text/length/duplicate/temporal diagnostics: succeeded. Embedding coverage: {state}.\n"
            f"Embedding blocks: {len(embedding_blocks)}; inspect `manifest/embedding_status.json`.\n\n"
            "Read `complexity/length_evidence.json` for counts, recorded-label prevalence and paired "
            "AUC-PRC intervals for every predeclared length bin. Other supported flags are in "
            "`complexity/matched_characteristic_metrics.json`; temporal differences in "
            "`shift/temporal_shift.json`. AP stays in detailed metrics JSON.\n\n"
            "Embedding-dependent results exist only for verified available partitions. "
            "Numeric clusters are unreviewed; neighbor disagreement is not a label-error estimate. "
            "No new encoder inference or model training occurred. Cache bytes have a new observed "
            "checksum, not a historical numeric checksum.\n\n"
            "Return 3-5 supported findings, or inconclusive evidence, with project/K, rows/positives, "
            "metrics, intervals and limitations. Histories remain unavailable and labels unverified. "
            "Review-inspired tests remain exploratory. No T6/T7 or improvement experiments.\n"
        )
        artifacts = {str(p.relative_to(root)): file_hash(p) for p in root.rglob("*")
                     if p.is_file() and p != root / "manifest/status.json"}
        emit(root, "manifest/status.json", "T4-T5", state, outputs_sha256=artifacts,
             t5_text_status="succeeded", embedding_blocks=embedding_blocks)
        print(f"Milestone-two artifacts: {root}")
        print(f"T5 text diagnostics: succeeded; embedding coverage: {state}; blocked items: {len(embedding_blocks)}")
        return 2 if embedding_blocks else 0
    except Exception as exc:
        emit(root, "manifest/status.json", "T4-T5", "failed",
             error_type=type(exc).__name__, reason=str(exc))
        raise


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-run", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--batch-id", default="human-review-01")
    parser.add_argument("--output-root", type=Path, default=Path.home() / "master-hf/diagnostics")
    parser.add_argument("--config", type=Path, default=TASK / "configuration/milestone2.json")
    args = parser.parse_args()
    try:
        return execute(args)
    except (OSError, ValueError, KeyError) as exc:
        print(f"Milestone two blocked/failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
