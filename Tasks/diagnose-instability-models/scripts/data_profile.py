"""T2: descriptive profiles and reproducible, model-blind human review packets."""

import difflib
import json
import re

from support import (
    CHANGES, COUNT, LEVELS, TEXT_COLUMNS, digest, emit, file_hash, json_counts,
    label_column, load_table, np, pd, quantiles, read_json, save_table,
)
from unstable_model.data import CATEGORICAL_COLUMNS, NUMERIC_COLUMNS

RUBRIC = {
    "review_status": ["pending", "reviewed"],
    "edit_category": ["substantive_requirement", "clarification", "editorial_formatting",
                      "copied_logs_code", "mixed", "unclear", "no_observed_edit"],
    "evidence_quality": ["complete", "partial", "unavailable", "inconsistent"],
    "extraction_assessment": ["consistent", "suspected_error", "cannot_verify"],
    "instructions": [
        "Scores and model identities are hidden. Do not infer correctness from the stored label.",
        "Classify actual edits only when histories support the classification.",
        "An editorial edit can be a valid positive under the frozen changed-word rule.",
        "Missing histories or no recorded events are not evidence of stability.",
        "Record reviewer ID, rationale and cited event timestamps; do not modify labels.",
        "The independent reviewer works without seeing the first review; record disagreements separately.",
    ],
}


def characteristics(frame):
    output = frame[["row_id", "project", "split", "time_add_to_sprint", COUNT, CHANGES,
                    *[label_column(k) for k in LEVELS]]].copy()
    text = frame[TEXT_COLUMNS].fillna("").astype(str).agg(" ".join, axis=1)
    output["chars"] = text.str.len()
    output["words"] = text.str.findall(r"\b\w+\b").str.len()
    output["missing_fields"] = frame[TEXT_COLUMNS].apply(
        lambda s: s.fillna("").astype(str).str.strip().eq("")
    ).sum(axis=1)
    for column in TEXT_COLUMNS:
        output[f"chars_{column}"] = frame[column].fillna("").str.len()
        output[f"missing_{column}"] = frame[column].fillna("").str.strip().eq("")
    output["non_ascii"] = text.str.contains(r"[^\x00-\x7f]")
    output["template_marker"] = text.str.contains(
        r"\bas an?\b.{0,80}\bi want\b|\bacceptance criteria\b|\bTODO\b|\bTBD\b", case=False
    )
    output["code_or_log_marker"] = text.str.contains(
        r"```|\{code\}|Traceback|Exception:|</?[a-z][^>]*>|^\s*at \w+\.", case=False
    )
    normalized = text.str.casefold().str.replace(r"\s+", " ", regex=True).str.strip()
    output["text_sha256"] = normalized.map(lambda t: digest(t))
    output["duplicate_text"] = normalized.duplicated(keep=False) & normalized.ne("")
    split_count = output.groupby("text_sha256").split.transform("nunique")
    output["cross_split_duplicate"] = output.duplicate_text & split_count.gt(1)
    output["quarter"] = pd.to_datetime(output.time_add_to_sprint).dt.to_period("Q").astype(str)
    for column in NUMERIC_COLUMNS:
        if column in frame:
            output[f"missing_numeric_{column}"] = pd.to_numeric(frame[column], errors="coerce").isna()
    for column in CATEGORICAL_COLUMNS:
        if column in frame:
            output[f"unknown_category_{column}"] = frame[column].eq("unknown")
    # Bounded lexical screening, not an exhaustive near-duplicate search or semantic grouping.
    output["adjacent_near_duplicate"] = False
    ordered = normalized[normalized.str.len().between(40, 10000)].sort_values()
    previous = None
    for idx, value in ordered.items():
        if previous is not None:
            old_idx, old_value = previous
            if old_value != value and value[:30] == old_value[:30] and (
                min(len(value), len(old_value)) / max(len(value), len(old_value)) >= .95
            ):
                matcher = difflib.SequenceMatcher(None, old_value, value, autojunk=True)
                if matcher.quick_ratio() >= .95 and matcher.ratio() >= .95:
                    output.loc[[idx, old_idx], "adjacent_near_duplicate"] = True
        previous = (idx, value)
    return output


def summarize(frame, k):
    counts = pd.to_numeric(frame[COUNT], errors="coerce")
    changes = pd.to_numeric(frame[CHANGES], errors="coerce")
    return {
        "rows": len(frame), "positives": int(frame[label_column(k)].sum()),
        "prevalence": float(frame[label_column(k)].mean()),
        "missing_fields": json_counts(frame.missing_fields),
        "missing_by_field": {c: int(frame[f"missing_{c}"].sum()) for c in TEXT_COLUMNS},
        "missing_numeric": {c: int(frame[f"missing_numeric_{c}"].sum())
                            for c in NUMERIC_COLUMNS if f"missing_numeric_{c}" in frame},
        "unknown_category_sentinel": {c: int(frame[f"unknown_category_{c}"].sum())
                                     for c in CATEGORICAL_COLUMNS if f"unknown_category_{c}" in frame},
        "field_chars": {c: quantiles(frame[f"chars_{c}"]) for c in TEXT_COLUMNS},
        "chars": quantiles(frame.chars), "words": quantiles(frame.words),
        "duplicate_rows": int(frame.duplicate_text.sum()),
        "cross_split_duplicate_rows": int(frame.cross_split_duplicate.sum()),
        "adjacent_near_duplicate_rows": int(frame.adjacent_near_duplicate.sum()),
        "non_ascii_rows": int(frame.non_ascii.sum()),
        "template_marker_rows": int(frame.template_marker.sum()),
        "code_or_log_marker_rows": int(frame.code_or_log_marker.sum()),
        "changed_words": quantiles(counts),
        "unknown_changed_word_count": int(counts.isna().sum()),
        "unknown_change_count": int(changes.isna().sum()),
        "word_count_at_boundary": {str(n): int(counts.eq(n).sum()) for n in range(k - 2, k + 3)},
        "changes_below_k": int(((counts < k) & (changes > 0)).sum()),
    }


def sample_plan(frame, config):
    memberships, inclusion = [], {}
    for project, split in frame[["project", "split"]].drop_duplicates().itertuples(index=False, name=None):
        population = frame[(frame.project == project) & (frame.split == split)]
        counts = pd.to_numeric(population[COUNT], errors="coerce")
        for k in LEVELS:
            boundary = (counts - k).abs().le(config["boundary_radius"])
            for label in (0, 1):
                for is_boundary in (False, True):
                    eligible = population[(population[label_column(k)] == label) & boundary.eq(is_boundary)]
                    ids = sorted(eligible.row_id)
                    n = min(config["review_per_stratum"], len(ids))
                    stratum = f"{project}/{split}/{k}/{label}/{int(is_boundary)}"
                    # Independent seeded draws per overlapping K stratum; union stories afterward.
                    seed = int(digest([config["seed"], stratum])[:8], 16)
                    selected = set(np.random.RandomState(seed).choice(ids, n, replace=False)) if n else set()
                    probability = n / len(ids) if ids else 0
                    for row_id in ids:
                        inclusion[row_id] = inclusion.get(row_id, 1.0) * (1 - probability)
                    memberships.append({
                        "stratum": stratum, "project": project, "split": split, "level": k,
                        "label": label, "boundary": is_boundary, "population": len(ids),
                        "sampled": n, "stratum_probability": probability, "selected_row_ids": sorted(selected),
                    })
    selected_ids = set(r for s in memberships for r in s["selected_row_ids"])
    sample = frame[frame.row_id.isin(selected_ids)].copy().sort_values(["project", "split", "row_id"])
    sample["inclusion_probability"] = sample.row_id.map(lambda r: 1 - inclusion[r])
    sample["independent_review_required"] = sample.row_id.map(
        lambda r: int(digest([config["seed"], "independent", r])[:8], 16) / 2**32
        < config["independent_review_fraction"]
    )
    sample["sample_id"] = sample.row_id.map(lambda r: digest([config["seed"], r])[:16])
    return sample, memberships


def histories_at(path, population):
    if path is None:
        return {}, {"status": "unavailable", "rows": 0}
    known = population.set_index("row_id")
    histories = {}
    for line in path.read_text().splitlines():
        record = json.loads(line)
        row_id = record["row_id"]
        if row_id in histories or row_id not in known.index:
            raise ValueError("Duplicate or unknown normalized history row identity.")
        if record["project"] != known.loc[row_id, "project"]:
            raise ValueError("History project does not match frozen row identity.")
        entry = pd.Timestamp(known.loc[row_id, "time_add_to_sprint"])
        start, end = pd.Timestamp(record["observation_start"]), pd.Timestamp(record["observation_end"])
        if any(pd.isna(t) for t in (entry, start, end)) or start > entry or end < entry:
            raise ValueError("History coverage does not contain sprint entry.")
        if type(record["history_complete"]) is not bool:
            raise ValueError("History completeness must be explicit, not inferred.")
        events = []
        for event in record["events"]:
            at = pd.Timestamp(event["at"])
            if event["field"] not in ("summary", "description", "acceptance_criteria"):
                raise ValueError("Unexpected history field.")
            if pd.isna(at) or at < start or at > end:
                raise ValueError("History event outside declared observation coverage.")
            if not all(isinstance(event[c], str) for c in ("before", "after")):
                raise ValueError("Missing before/after text is not an empty edit.")
            delta = list(difflib.ndiff(event["before"].split(), event["after"].split()))
            events.append({**event, "post_entry": bool(at > entry),
                           "adjacent_edit_removed_words": sum(t.startswith("- ") for t in delta),
                           "adjacent_edit_added_words": sum(t.startswith("+ ") for t in delta),
                           "unified_diff": "\n".join(difflib.unified_diff(
                               event["before"].splitlines(), event["after"].splitlines(),
                               fromfile="before", tofile="after", lineterm=""
                           ))})
        fields = {}
        for field in ("summary", "description", "acceptance_criteria"):
            observed = sorted(
                [e for e in events if e["field"] == field and e["post_entry"]],
                key=lambda e: pd.Timestamp(e["at"])
            )
            fields[field] = {
                "observed_post_entry_events": len(observed),
                "original_matches_first_observed_before": (
                    known.loc[row_id, f"original_{field}_sprint"] == observed[0]["before"]
                    if observed else None
                ),
                "adjacent_history_chain_gaps": sum(
                    a["after"] != b["before"] for a, b in zip(observed, observed[1:])
                ),
                "interpretation": "Mismatch/gaps require extractor context; not automatic label errors. Earliest observed event may differ from the historical >1-hour eligibility filter.",
            }
        histories[row_id] = {**record, "events": sorted(events, key=lambda e: pd.Timestamp(e["at"])),
                             "field_evidence": fields,
                             "observation_days_after_entry": (end - entry).total_seconds() / 86400,
                             "label_reconstruction": "unverified; normalized edits alone do not reproduce the historical tokenizer/counter"}
    return histories, {
        "status": "available_not_human_reviewed", "rows": len(histories),
        "sha256": file_hash(path),
        "complete_rows": sum(r["history_complete"] for r in histories.values()),
        "observation_days_after_entry": quantiles([r["observation_days_after_entry"] for r in histories.values()]),
    }


def profile(root, config, history_path=None, tokenizer_cache=None):
    population = load_table(root, "manifest/population.csv")
    if population.empty:
        emit(root, "data-characterization/data_profile.json", "T2", "blocked",
             reason="No verified frozen dataset.")
        return "blocked"
    traits = characteristics(population)
    save_table(root, "data-characterization/characteristics.csv", traits, "T2")
    from token_coverage import token_coverage
    tokens = token_coverage(root, population, tokenizer_cache)
    profiles = []
    for (project, split), frame in traits.groupby(["project", "split"], sort=True):
        for k in LEVELS:
            profiles.append({"project": project, "split": split, "level": k, **summarize(frame, k)})
            for quarter, period in frame.groupby("quarter"):
                profiles.append({"project": project, "split": split, "level": k,
                                 "quarter": quarter, **summarize(period, k)})
    history_error = None
    try:
        histories, coverage = histories_at(history_path, population)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        histories, coverage = {}, {"status": "blocked", "reason": str(exc)}
        history_error = str(exc)
    sample, strata = sample_plan(traits, config)
    audit_columns = ["sample_id", "row_id", "project", "split", COUNT, CHANGES,
                     *[label_column(k) for k in LEVELS], "inclusion_probability", "independent_review_required"]
    audit = sample[audit_columns].copy()
    audit["history_status"] = audit.row_id.map(lambda r: "available" if r in histories else "unavailable")
    for column in ("reviewer_id", "edit_category", "evidence_quality", "extraction_assessment",
                   "rationale", "event_references", "second_reviewer_id", "second_edit_category",
                   "disagreement_resolution"):
        audit[column] = ""
    audit["review_status"] = "pending"
    save_table(root, "data-characterization/label_audit.csv", audit, "T2")
    packets = []
    indexed = population.set_index("row_id")
    for row in sample.itertuples():
        story = indexed.loc[row.row_id]
        packets.append({
            "sample_id": row.sample_id, "row_id": row.row_id, "project": row.project,
            "split": row.split, "time_add_to_sprint": story.time_add_to_sprint,
            "original_text": {c: story[c] for c in TEXT_COLUMNS},
            "history": histories.get(row.row_id, {"status": "unavailable"}),
            "review_status": "pending", "model_scores_hidden": True,
            "independent_review_required": row.independent_review_required,
        })
    packet_path = root / "data-characterization/review_examples.jsonl"
    packet_path.write_text("".join(json.dumps(p, ensure_ascii=True) + "\n" for p in packets))
    emit(root, "data-characterization/review_examples.metadata.json", "T2", "succeeded",
         sha256=file_hash(packet_path), rows=len(packets), model_scores_hidden=True)
    emit(root, "data-characterization/sampling_plan.json", "T2", "succeeded",
         rubric=RUBRIC, strata=strata, unique_stories=len(sample),
         independent_review_stories=int(sample.independent_review_required.sum()),
         method="independent simple random sample per project/split/K/class/boundary; deduplicated union; inclusion probability=1-product(1-n/N)",
         review_completed=0, sample_size_fixed_before_review=True,
         rule="No score-based selection. Human annotations go in a separate copy; reruns never ingest annotations implicitly.")
    integrity = read_json(root / "manifest/integrity_checks.json")
    verified_projects = {p["project"] for p in integrity["populations"] if p["status"] == "succeeded"}
    status = "succeeded" if len(verified_projects) == 6 and history_error is None else "blocked"
    emit(root, "data-characterization/data_profile.json", "T2", status, profiles=profiles,
         coverage=coverage, unique_stories=len(population), profiles_executed=True,
         human_review_status="pending", label_validity="unverified_without_source_history_and_human_review",
         tokenizer_coverage_rows=len(tokens),
         language="unavailable; non-ASCII is a script/character flag, not a language classifier",
         near_duplicates="bounded exploratory lexical screening: adjacent normalized texts, same first 30 chars, 40-10000 chars, SequenceMatcher>=.95; not exhaustive",
         truncation="Only original saved model-specific token reports are evidence; character/word lengths are not token lengths. See T1 cell protocols. Per-row coverage may be unavailable.",
         snapshot_construction={
             "source": "Using_CSV_files/CalculateData/prepare_data_sql.py:getChangesWithWords",
             "observed_code": "filters changes strictly after first sprint entry and different_time_from_creat>1; takes earliest eligible from_string per field and its *_minus_last/*_plus_last counters; no sprint-end bound in this function; fallback to current default when first from_string is null",
             "entry_time_source": "calculate_time_add_sprint.py prefers first available sprint start_date, then earliest sprint-change.created, then issue.created; actual per-row fallback provenance is absent from exported feature table",
             "word_counter_source": "SetUpData.py:get_different_between_string uses whitespace split and difflib.ndiff; *_last counters must be checked against raw extractor tables before reconstructing labels",
             "last_counter_meaning": "SetUpData.py compares each change.from_string to the exported current summary/description/acceptance field, not just to that event.to_string; reverted/intermediate edits need not yield positive final changed-word counts",
             "limitation": "Code tracing is not proof of exported history completeness, counter correctness or a sprint-end observation window."
         })
    (root / "data-characterization/summary.txt").write_text(
        f"Verified population: {len(population)} unique project/story rows across {len(verified_projects)} projects.\n"
        f"Prepared {len(sample)} deduplicated review stories; 0 human reviews performed.\n"
        f"History evidence: {coverage['status']}. Label meaning/validity remains pending review.\n"
        "See data_profile.json for project/split/K/time support. No causal conclusions or relabeling.\n"
    )
    return status
