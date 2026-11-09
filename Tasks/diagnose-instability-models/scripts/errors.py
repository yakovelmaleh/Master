"""T3: exact matched-row ranking diagnostics, with fixed-threshold errors separate."""

from support import (
    FAMILIES, LEVELS, PROJECTS, calculate_metrics, digest, emit, file_hash, label_column,
    load_table, np, pd, probability_metrics, read_json, save_table,
)


def misranking(labels, scores):
    """Fraction of opposite-class rows outranking a row; ties count one half."""
    y, p = np.asarray(labels, int), np.asarray(scores, float)
    answer = np.full(len(y), np.nan)
    for label in (0, 1):
        other = np.sort(p[y != label])
        if len(other) == 0:
            continue
        values = p[y == label]
        left, right = np.searchsorted(other, values, "left"), np.searchsorted(other, values, "right")
        inversions = len(other) - right if label else left
        answer[y == label] = (inversions + .5 * (right - left)) / len(other)
    return answer


def support(frame, config):
    positives = int(frame.actual_label.sum())
    return {"rows": len(frame), "positives": positives, "negatives": len(frame) - positives,
            "adequate_support": bool(
                len(frame) >= config["minimum_slice_rows"]
                and positives >= config["minimum_slice_positives"]
                and len(frame) - positives >= config["minimum_slice_negatives"]
            )}


def paired_interval(frame, config):
    info = support(frame, config)
    if not info["adequate_support"]:
        return {"method": "paired moving time-block bootstrap", "interval_95": None,
                "valid_samples": 0, "reason": "insufficient support"}
    n = len(frame)
    block = min(config["time_block_rows"], n)
    rng = np.random.RandomState(config["seed"])
    values = []
    y = frame.actual_label.to_numpy()
    a, b = frame.classical_probability.to_numpy(), frame.model_probability.to_numpy()
    for _ in range(config["bootstrap_samples"]):
        starts = rng.randint(0, n - block + 1, int(np.ceil(n / block)))
        indices = np.concatenate([np.arange(s, s + block) for s in starts])[:n]
        if len(np.unique(y[indices])) != 2:
            continue
        values.append(probability_metrics(y[indices], b[indices])["auc_prc"]
                      - probability_metrics(y[indices], a[indices])["auc_prc"])
    return {"method": "paired non-circular moving time-block bootstrap within project/split/K",
            "time_block_rows": block, "requested_samples": config["bootstrap_samples"],
            "valid_samples": len(values),
            "interval_95": np.percentile(values, [2.5, 97.5]).tolist() if len(values) >= 100 else None,
            "limitations": "Exploratory unadjusted interval; block size fixed in config, not tuned. Does not pool K or projects; no significance claim."}


def paired(frame, config, uncertainty=False):
    info = support(frame, config)
    y = frame.actual_label.to_numpy()
    metrics = {}
    for name in ("classical", "model"):
        probability = frame[f"{name}_probability"].to_numpy()
        threshold = frame[f"{name}_threshold"].iloc[0]
        metrics[name] = calculate_metrics(y, probability, threshold)
    a, b = metrics["classical"]["auc_prc"], metrics["model"]["auc_prc"]
    info["metrics"] = metrics
    info["auc_prc_difference_model_minus_classical"] = b - a if a is not None and b is not None else None
    info["interpretation"] = "descriptive_exploratory" if info["adequate_support"] else "insufficient_support_do_not_interpret"
    ca = (frame.classical_probability >= frame.classical_threshold).to_numpy() == y
    cb = (frame.model_probability >= frame.model_threshold).to_numpy() == y
    info["fixed_threshold_outcomes"] = {
        "both_correct": int((ca & cb).sum()), "classical_only_correct": int((ca & ~cb).sum()),
        "model_only_correct": int((~ca & cb).sum()), "both_wrong": int((~ca & ~cb).sum()),
    }
    if "classical_misranking" in frame and "model_misranking" in frame:
        a, b = frame.classical_misranking, frame.model_misranking
        info["ranking_outcomes"] = {
            "classical_lower_inversion": int((a < b).sum()),
            "model_lower_inversion": int((b < a).sum()),
            "equal_inversion": int(a.eq(b).sum()),
            "shared_majority_inverted": int((a.ge(.5) & b.ge(.5)).sum()),
            "shared_minority_inverted": int((a.lt(.5) & b.lt(.5)).sum()),
            "undefined": int((a.isna() | b.isna()).sum()),
            "mean_by_label": {
                str(label): {
                    "rows": int(frame.actual_label.eq(label).sum()),
                    "classical": float(a[frame.actual_label.eq(label)].mean())
                    if a[frame.actual_label.eq(label)].notna().any() else None,
                    "model": float(b[frame.actual_label.eq(label)].mean())
                    if b[frame.actual_label.eq(label)].notna().any() else None,
                } for label in (0, 1)
            },
        }
    if uncertainty:
        info["uncertainty"] = paired_interval(frame, config)
    else:
        info["uncertainty"] = {"interval_95": None, "reason": "slice is descriptive; no slice-wise significance tests"}
    return info


def reviewed_annotations(root, path):
    if path is None:
        return None
    annotations = pd.read_csv(path, keep_default_na=False, dtype={"row_id": str, "sample_id": str})
    required = {"row_id", "sample_id", "review_status", "reviewer_id", "edit_category",
                "evidence_quality", "extraction_assessment", "rationale"}
    if not required.issubset(annotations):
        raise ValueError("Review annotations lack required rubric fields.")
    if annotations.row_id.duplicated().any():
        raise ValueError("Review annotations duplicate a story across K.")
    audit = load_table(root, "data-characterization/label_audit.csv").set_index("row_id")
    if not set(annotations.row_id).issubset(audit.index):
        raise ValueError("Review annotations contain stories outside the frozen sampling plan.")
    for row in annotations.itertuples():
        if row.sample_id != audit.loc[row.row_id, "sample_id"]:
            raise ValueError("Review sample identity changed.")
    reviewed = annotations[annotations.review_status == "reviewed"].copy()
    from data_profile import RUBRIC
    for column in ("edit_category", "evidence_quality", "extraction_assessment"):
        if not reviewed[column].isin(RUBRIC[column]).all():
            raise ValueError(f"Unknown review rubric category: {column}")
    if reviewed.reviewer_id.str.strip().eq("").any() or reviewed.rationale.str.strip().eq("").any():
        raise ValueError("Reviewed examples require a reviewer and rationale.")
    return reviewed[["row_id", "edit_category", "evidence_quality", "extraction_assessment"]]


def errors(root, config, review_path=None):
    predictions = load_table(root, "manifest/predictions.csv")
    population = load_table(root, "manifest/population.csv")
    traits_path = root / "data-characterization/characteristics.csv"
    traits = load_table(root, "data-characterization/characteristics.csv") if traits_path.exists() else None
    tokens_path = root / "data-characterization/token_coverage.csv"
    tokens = load_table(root, "data-characterization/token_coverage.csv") if tokens_path.exists() else None
    reviews = reviewed_annotations(root, review_path)
    rows, comparisons, missing, examples, four_way = [], [], [], [], []
    for project in PROJECTS:
        for split in ("validation", "test"):
            canonical = population[(population.project == project) & (population.split == split)]
            for k in LEVELS:
                cell = predictions[(predictions.project == project) & (predictions.level == k)
                                   & (predictions.split == split)]
                available = set(cell.family)
                absent = set(FAMILIES) - available
                if absent:
                    missing.append({"project": project, "split": split, "level": k,
                                    "missing_families": sorted(absent)})
                prepared = {}
                for family in FAMILIES:
                    if family not in available:
                        continue
                    current = cell[cell.family == family].copy().set_index("row_id")
                    if set(current.index) != set(canonical.row_id):
                        raise ValueError("T3 refuses partial matched populations.")
                    current = current.loc[canonical.row_id].reset_index()
                    current["opposite_class_misranking_fraction"] = misranking(
                        current.actual_label, current.instability_probability
                    )
                    current["predicted_label"] = (current.instability_probability >= current.threshold).astype(int)
                    current["fixed_threshold_error"] = np.select(
                        [(current.actual_label == 0) & (current.predicted_label == 1),
                         (current.actual_label == 1) & (current.predicted_label == 0)],
                        ["false_positive", "false_negative"], default="correct"
                    )
                    # Tie-aware rank ranges, never an arbitrary rank within equal scores.
                    current["rank_best"] = current.instability_probability.rank(ascending=False, method="min")
                    current["rank_worst"] = current.instability_probability.rank(ascending=False, method="max")
                    current["constant_score_auc_prc"] = (1 + current.actual_label.mean()) / 2
                    current["constant_score_ap"] = current.actual_label.mean()
                    if traits is not None:
                        current = current.merge(
                            traits.drop(columns=["project", "split"]), on="row_id",
                            validate="one_to_one"
                        )
                    if tokens is not None:
                        current = current.merge(
                            tokens[(tokens.family == family) & (tokens.level == k)][
                                ["row_id", "tokens", "limit", "truncated"]
                            ], on="row_id", how="left", validate="one_to_one"
                        )
                    if reviews is not None:
                        current = current.merge(reviews, on="row_id", how="left", validate="one_to_one")
                    rows.append(current)
                    prepared[family] = current
                if not absent:
                    correct = np.column_stack([
                        prepared[f].predicted_label.to_numpy() == prepared[f].actual_label.to_numpy()
                        for f in FAMILIES
                    ])
                    four_way.append({"project": project, "split": split, "level": k,
                                     "rows": len(canonical), "positives": int(canonical[label_column(k)].sum()),
                                     "all_correct": int(correct.all(axis=1).sum()),
                                     "all_wrong": int((~correct).all(axis=1).sum()),
                                     "fixed_threshold_patterns": pd.Series([
                                         "".join("1" if v else "0" for v in row) for row in correct
                                     ]).value_counts().to_dict(), "pattern_order": list(FAMILIES)})
                if "classical" not in prepared:
                    continue
                for family in ("SLM1", "SLM2", "Jev"):
                    if family not in prepared:
                        continue
                    classical = prepared["classical"].set_index("row_id")
                    model = prepared[family].set_index("row_id").loc[classical.index]
                    frame = canonical.set_index("row_id").loc[classical.index, ["time_add_to_sprint"]].copy()
                    frame["actual_label"] = classical.actual_label
                    for name, source in (("classical", classical), ("model", model)):
                        frame[f"{name}_probability"] = source.instability_probability
                        frame[f"{name}_threshold"] = source.threshold
                        frame[f"{name}_misranking"] = source.opposite_class_misranking_fraction
                    if traits is not None:
                        frame = frame.join(traits.set_index("row_id")[
                            ["chars", "missing_fields", "duplicate_text", "code_or_log_marker", "quarter"]
                        ])
                    if "truncated" in model:
                        frame["model_truncated"] = model.truncated
                    if "edit_category" in model:
                        frame["audited_edit_category"] = model.edit_category
                    frame = frame.sort_values(["time_add_to_sprint"], kind="stable").reset_index()
                    identity = {"project": project, "split": split, "level": k, "family": family}
                    comparisons.append({**identity, "slice": "all", **paired(frame, config, uncertainty=True)})
                    if traits is not None:
                        masks = {
                            "missing_text_field": frame.missing_fields.gt(0),
                            "all_text_fields_present": frame.missing_fields.eq(0),
                            "long_4000_chars": frame.chars.ge(4000),
                            "shorter_4000_chars": frame.chars.lt(4000),
                            "duplicate_text": frame.duplicate_text.eq(True),
                            "code_or_log_marker": frame.code_or_log_marker.eq(True),
                        }
                        masks.update({f"quarter:{q}": frame.quarter.eq(q) for q in sorted(frame.quarter.unique())})
                        if "model_truncated" in frame and frame.model_truncated.notna().any():
                            masks["model_truncated"] = frame.model_truncated.eq(True)
                            masks["model_not_truncated"] = frame.model_truncated.eq(False)
                        if "audited_edit_category" in frame:
                            masks.update({
                                f"reviewed_sample_edit:{category}": frame.audited_edit_category.eq(category)
                                for category in sorted(frame.audited_edit_category.dropna().unique())
                            })
                        for name, mask in masks.items():
                            if mask.any():
                                comparisons.append({**identity, "slice": name, **paired(frame[mask], config)})
                    # Ranking disagreements and shared successes/errors use continuous pairwise error,
                    # not a newly selected classification threshold. At most two examples per category/class.
                    a, b = frame.classical_misranking, frame.model_misranking
                    groups = {
                        "classical_better_ranking": b > a, "model_better_ranking": a > b,
                        "shared_bad_ranking": a.ge(.5) & b.ge(.5),
                        "matched_good_ranking": a.lt(.5) & b.lt(.5),
                    }
                    for category, mask in groups.items():
                        for label in (0, 1):
                            eligible = frame[mask & frame.actual_label.eq(label)].copy()
                            eligible["example_order"] = eligible.row_id.map(
                                lambda r: digest([config["seed"], category, r])
                            )
                            for _, row in eligible.sort_values("example_order").head(2).iterrows():
                                examples.append({**identity, "category": category, "row_id": row.row_id,
                                                 "label": label, "category_support": len(eligible),
                                                 "review_status": "pending",
                                                 "classical_misranking": row.classical_misranking,
                                                 "model_misranking": row.model_misranking})
    diagnostics = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(
        columns=["row_id", "project", "split", "level", "family"])
    save_table(root, "error-analysis/row_diagnostics.csv", diagnostics, "T3")
    save_table(root, "error-analysis/review_candidates.csv", pd.DataFrame(
        examples, columns=["project", "split", "level", "family", "category", "row_id", "label",
                           "category_support", "review_status", "classical_misranking", "model_misranking"]
    ), "T3")
    status = "succeeded" if not missing else "blocked"
    emit(root, "error-analysis/error_slices.json", "T3", status, comparisons=comparisons,
         missing_comparisons=missing, four_family_fixed_threshold=four_way,
         ranking_definition="Opposite-class score inversion fraction; ties count 1/2. rank_best/worst are tied rank bounds. Larger misranking is worse.",
         fixed_thresholds="Original archived validation-selected thresholds, not the HF report classical 0.5 control.",
         review_status="pending; candidates are not a reviewed example set",
         reviewed_annotations=(
             {"path": str(review_path), "sha256": file_hash(review_path),
              "unique_reviewed_stories": len(reviews),
              "interpretation": "reviewed sampled stories only; not population error rates; independent disagreements remain in annotation file"}
             if review_path else {"status": "unavailable", "human_reviews_ingested": 0}
         ),
         unavailable_relations=["per-row tokenizer truncation absent unless separately extracted",
                                "audited edit type unavailable unless validated human annotations are supplied"],
         support_rule={key: config[key] for key in (
             "minimum_slice_rows", "minimum_slice_positives", "minimum_slice_negatives")},
         limitations="No pooling across nested K; no causal claims; slices exploratory and unadjusted; one-class AUC-PRC/AP/ROC are null.")
    return status
