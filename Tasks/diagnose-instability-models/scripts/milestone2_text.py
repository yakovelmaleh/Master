"""Training-defined T5 characteristics and support-aware paired diagnostics."""

import re

from support import (
    FAMILIES, LEVELS, TEXT_COLUMNS, align_predictions, digest, label_column,
    np, pd, quantiles,
)
from errors import paired, support

FLAGS = ("empty_description", "summary_equals_description", "reference_only_description",
         "seen_in_train", "duplicate_within_split", "first_text_occurrence")
REFERENCE = r"https?://\S+|\b[A-Z][A-Z0-9]+-\d+\b"
REFERENCE_WORDS = {"see", "also", "refer", "to", "reference", "references",
                   "issue", "ticket", "link", "url", "please", "and"}


def normalize(text):
    return re.sub(r"\s+", " ", str(text)).strip().casefold()


def reference_only(text):
    if not re.search(REFERENCE, text):
        return False
    residue = re.sub(REFERENCE, " ", text)
    return set(re.findall(r"\b\w+\b", residue.casefold())).issubset(REFERENCE_WORDS)


def text_features(population):
    fields = population[TEXT_COLUMNS].fillna("").astype(str)
    text = fields.agg(" ".join, axis=1)
    result = population[["row_id", "project", "split", "time_add_to_sprint"]].copy()
    result["words"] = text.str.findall(r"\b\w+\b").str.len()
    result["chars"] = text.str.len()
    result["text_sha256"] = text.map(normalize).map(digest)
    result["text_nonempty"] = text.str.strip().ne("")
    summary = fields.original_summary_sprint.map(normalize)
    description = fields.original_description_sprint.map(normalize)
    result["empty_description"] = description.eq("")
    result["summary_equals_description"] = description.ne("") & summary.eq(description)
    result["reference_only_description"] = fields.original_description_sprint.map(reference_only)
    keys = ["project", "split", "text_sha256"]
    result["duplicate_within_split"] = result.duplicated(keys, keep=False) & result.text_nonempty
    ordered = result.sort_values(["project", "split", "time_add_to_sprint", "row_id"], kind="stable")
    result["first_text_occurrence"] = ~ordered.duplicated(keys).reindex(result.index)
    result["seen_in_train"] = False
    for project, group in result.groupby("project", sort=True):
        train_counts = group[group.split.eq("train") & group.text_nonempty].text_sha256.value_counts()
        counts = group.text_sha256.map(train_counts).fillna(0)
        result.loc[group.index, "seen_in_train"] = counts.gt(group.split.eq("train").astype(int))
    for k in LEVELS:
        result[label_column(k)] = population[label_column(k)]
    return result


def fit_lengths(features, config):
    definitions = {}
    for project, group in features.groupby("project", sort=True):
        train = group[group.split.eq("train")]
        if train.empty:
            raise ValueError(f"No training rows for length bins: {project}")
        cutpoints = sorted(set(float(train.words.quantile(q)) for q in config["length_quantiles"]))
        definitions[project] = {
            "training_rows": len(train), "cutpoints": cutpoints,
            "requested_quantiles": config["length_quantiles"],
            "effective_bins": len(cutpoints) + 1,
            "training_row_ids_sha256": digest(train.row_id.tolist()),
            "interval_convention": "(-inf,c1], (c1,c2], ..., (clast,+inf); repeated cutpoints collapsed",
        }
    return definitions


def assign_lengths(features, definitions):
    result = features.copy()
    result["length_bin"] = -1
    for project, group in result.groupby("project"):
        result.loc[group.index, "length_bin"] = np.searchsorted(
            definitions[project]["cutpoints"], group.words.to_numpy(), side="left"
        )
    return result


def prevalence(frame, k, config):
    y = frame[label_column(k)].to_numpy(int)
    info = support(pd.DataFrame({"actual_label": y}), config)
    info["recorded_label_prevalence"] = float(y.mean()) if len(y) else None
    info["prevalence_interval_95"] = None
    info["uncertainty_method"] = "non-circular chronological row moving blocks; descriptive, not a population survey"
    info["uncertainty_block_rows"] = min(config["time_block_rows"], len(y))
    info["uncertainty_samples"] = config["bootstrap_samples"] if info["adequate_support"] else 0
    if info["adequate_support"]:
        rng = np.random.RandomState(config["seed"])
        block = min(config["time_block_rows"], len(y))
        means = []
        for _ in range(config["bootstrap_samples"]):
            starts = rng.randint(0, len(y) - block + 1, int(np.ceil(len(y) / block)))
            indices = np.concatenate([np.arange(s, s + block) for s in starts])[:len(y)]
            means.append(float(y[indices].mean()))
        info["prevalence_interval_95"] = np.percentile(means, [2.5, 97.5]).tolist()
    info["uncertainty_note"] = (
        "Chronological row blocks within this slice, not fixed calendar windows; gaps may be compressed. "
        "Preserves local dependence only. Exploratory, unadjusted; no inference for unsupported slices."
    )
    return info


def definitions_note():
    return {
        "word_length": r"Count Unicode \b\w+\b tokens in original summary + description + acceptance criteria, separated by spaces.",
        "normalization": "Unicode casefold and whitespace collapse, punctuation retained.",
        "summary_equals_description": "Nonempty description exactly equals normalized summary.",
        "reference_only_description": {
            "reference_regex": REFERENCE, "allowed_residual_words": sorted(REFERENCE_WORDS),
            "meaning": "Literal reference-only indicator, not a semantic completeness judgment.",
        },
        "seen_in_train": "Same project, nonempty normalized full text in training; exclude self for train.",
        "first_text_occurrence": "Keep first chronological row per project/split/normalized text; label-blind duplicate sensitivity.",
        "disclaimer": "Measurable proxies only; not automatic clarity scores, edit types or verified labels.",
    }


def masks_for(group, definitions):
    yield "all", np.ones(len(group), dtype=bool)
    for index in range(definitions[group.project.iloc[0]]["effective_bins"]):
        yield f"length_bin:{index}", group.length_bin.eq(index).to_numpy()
    for flag in FLAGS:
        for value in (True, False):
            yield f"{flag}:{str(value).lower()}", group[flag].eq(value).to_numpy()


def profiles_and_shift(features, definitions, config):
    profiles, shifts = [], []
    for (project, split), group in features.groupby(["project", "split"], sort=True):
        group = group.sort_values("time_add_to_sprint", kind="stable")
        for name, mask in masks_for(group, definitions):
            current = group[mask]
            for k in LEVELS:
                profiles.append({
                    "project": project, "split": split, "level": k, "slice": name,
                    **prevalence(current, k, config),
                })
        train = features[(features.project == project) & features.split.eq("train")]
        bins = range(definitions[project]["effective_bins"])
        a = train.length_bin.value_counts(normalize=True).reindex(bins, fill_value=0)
        b = group.length_bin.value_counts(normalize=True).reindex(bins, fill_value=0)
        shifts.append({
            "project": project, "split": split, "rows": len(group), "training_rows": len(train),
            "length_bin_counts": {str(i): int(group.length_bin.eq(i).sum()) for i in bins},
            "length_bin_total_variation_from_train": float(np.abs(a - b).sum() / 2),
            "word_length_quantiles": quantiles(group.words),
            "character_length_quantiles": quantiles(group.chars),
            "characteristics": {
                flag: {"rows": int(group[flag].sum()), "rate": float(group[flag].mean()),
                       "train_rate": float(train[flag].mean()),
                       "rate_difference_from_train": float(group[flag].mean() - train[flag].mean())}
                for flag in FLAGS
            },
            "labels": {
                str(k): {"positives": int(group[label_column(k)].sum()),
                         "prevalence": float(group[label_column(k)].mean()),
                         "training_positives": int(train[label_column(k)].sum()),
                         "training_prevalence": float(train[label_column(k)].mean()),
                         "prevalence_difference_from_train": float(
                             group[label_column(k)].mean() - train[label_column(k)].mean())}
                for k in LEVELS
            },
            "interpretation": "Descriptive chronological split difference, not a causal or significance test.",
        })
    return profiles, shifts


def metric_slices(population, predictions, features, definitions, config, extra=None):
    results = []
    for (project, split), population_group in population[
        population.split.isin(["validation", "test"])
    ].groupby(["project", "split"], sort=True):
        canonical = population_group.sort_values("time_add_to_sprint", kind="stable")
        traits = features.set_index("row_id").loc[canonical.row_id].reset_index()
        for k in LEVELS:
            cell = predictions[(predictions.project == project) & (predictions.split == split)
                               & (predictions.level == k)]
            for family in FAMILIES[1:]:
                sources = [align_predictions(cell[cell.family == f], canonical, k)
                           for f in ("classical", family)]
                frame = pd.DataFrame({"actual_label": canonical[label_column(k)].to_numpy()})
                for name, source in zip(("classical", "model"), sources):
                    if source.model.nunique() != 1 or source.threshold.nunique() != 1:
                        raise ValueError("Mixed model identity or threshold in matched cell.")
                    frame[name + "_probability"] = source.instability_probability.to_numpy()
                    frame[name + "_threshold"] = source.threshold.to_numpy()
                masks = list(masks_for(traits, definitions)) if extra is None else list(
                    extra(project, split, k, traits)
                )
                for name, mask in masks:
                    if name == "all":
                        continue  # M1 already computed full-cell comparisons and intervals.
                    mask = np.asarray(mask, dtype=bool)
                    if len(mask) != len(frame):
                        raise ValueError("Slice membership alignment differs.")
                    current = frame[mask]
                    identity = {"project": project, "split": split, "level": k, "family": family,
                                "slice": name, "model": str(sources[1].model.iloc[0]),
                                "classical_model": str(sources[0].model.iloc[0])}
                    if current.empty:
                        results.append({**identity, **support(current, config), "metrics": None,
                                        "interpretation": "empty_slice", "uncertainty": {"interval_95": None}})
                    else:
                        results.append({**identity, **paired(current, config, uncertainty=True),
                                        "uncertainty_scope": "Chronological row blocks within the slice; not fixed-duration blocks."})
    return results


def exact_duplicate_disagreement(features, config):
    output = []
    for project, group in features.groupby("project"):
        train = group[group.split.eq("train") & group.text_nonempty]
        for k in LEVELS:
            label = label_column(k)
            bank = train.groupby("text_sha256")[label].agg(["count", "sum"])
            for split, current in group.groupby("split"):
                counts = current.text_sha256.map(bank["count"]).fillna(0).to_numpy(float)
                positives = current.text_sha256.map(bank["sum"]).fillna(0).to_numpy(float)
                y = current[label].to_numpy(int)
                if split == "train":
                    counts -= current.text_nonempty.to_numpy(int)
                    positives -= y * current.text_nonempty.to_numpy(int)
                valid = (counts > 0) & current.text_nonempty.to_numpy()
                disagreements = np.where(y[valid] == 1, counts[valid] - positives[valid], positives[valid])
                output.append({
                    "project": project, "split": split, "level": k,
                    **support(pd.DataFrame({"actual_label": y[valid]}), config),
                    "fraction_with_any_opposite_label_training_duplicate": float(
                        (disagreements > 0).mean()) if valid.any() else None,
                    "mean_training_duplicate_label_disagreement": float(
                        (disagreements / counts[valid]).mean()) if valid.any() else None,
                    "training_only_bank": True, "self_excluded": True,
                    "interpretation": "Descriptive recorded-label conflict among exact normalized-text matches; structured inputs may differ; no label-error or causality inference.",
                })
    return output
