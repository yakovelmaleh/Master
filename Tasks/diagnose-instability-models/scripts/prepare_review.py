#!/usr/bin/env python3
"""Read a frozen T2/T3 run; write a separate pending human-review supplement."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import html
import json
import os
from pathlib import Path
import subprocess
import sys

from support import (
    CHANGES, COUNT, HF, REPO, TASK, TEXT_COLUMNS, align_predictions, digest,
    external_path, file_hash, label_column, load_table, np, pd,
    read_json, slug, write_json,
)
from diagnostic_config import REVIEW_POLICY
from errors import misranking
from data_profile import histories_at
from reconcile_intervals import reconcile_cell, reconciliation_markdown


def load_inputs(root):
    run = read_json(root / "run.json")
    if run["run_id"] != root.name or digest(run["configuration"]) != run["configuration_sha256"]:
        raise ValueError("Source run identity or configuration digest differs.")
    paths = ["run.json", "manifest/integrity_checks.json", "manifest/artifact_manifest.json",
             "error-analysis/error_slices.json"]
    for stage in ("inventory", "profile", "errors"):
        relative = f"manifest/{stage}_status.json"
        paths.append(relative)
        status = read_json(root / relative)
        if status["status"] != "succeeded" or status["run_id"] != run["run_id"]:
            raise ValueError(f"Source stage is not successfully completed: {stage}")
        if (status["source_sha256"] != run["source_sha256"]
                or status["configuration_sha256"] != run["configuration_sha256"]):
            raise ValueError("Source stage provenance differs.")
    tables = {}
    for name in ("manifest/population.csv", "manifest/predictions.csv", "error-analysis/row_diagnostics.csv"):
        paths.extend([name, name + ".metadata.json"])
        sidecar = read_json(root / (name + ".metadata.json"))
        if (sidecar["run_id"] != run["run_id"] or sidecar["source_sha256"] != run["source_sha256"]
                or sidecar["configuration_sha256"] != run["configuration_sha256"]):
            raise ValueError(f"Source table provenance differs: {name}")
        tables[name] = load_table(root, name)
        if len(tables[name]) != sidecar["rows"]:
            raise ValueError(f"Source table row count differs: {name}")
    integrity = read_json(root / paths[1])
    slices = read_json(root / "error-analysis/error_slices.json")
    for document in (integrity, slices):
        if (document["run_id"] != run["run_id"] or document["source_sha256"] != run["source_sha256"]
                or document["configuration_sha256"] != run["configuration_sha256"]):
            raise ValueError("Source evidence provenance differs.")
    population = tables["manifest/population.csv"]
    if population.row_id.isna().any() or population.row_id.duplicated().any():
        raise ValueError("Population must have unique nonnull story identities.")
    return {
        "run": run, "population": population,
        "predictions": tables["manifest/predictions.csv"],
        "diagnostics": tables["error-analysis/row_diagnostics.csv"],
        "integrity": integrity, "slices": slices,
        "input_sha256": {name: file_hash(root / name) for name in paths},
    }


def candidate_pairs(population, predictions, diagnostics, integrity, policy=REVIEW_POLICY):
    canonical = population[population.split == policy["split"]]
    verified = {(c["family"], c["project"], c["level"])
                for c in integrity["cells"] if c["status"] == "succeeded"}
    candidates = []
    selected_predictions = predictions[
        (predictions.split == policy["split"]) & predictions.family.isin(policy["families"])
    ]
    expected_cells = {(project, level, family) for family, project, level in verified
                      if family in policy["families"]}
    if set(selected_predictions.groupby(["project", "level", "family"]).groups) != expected_cells:
        raise ValueError("Review predictions omit verified model cells.")
    for (project, level, family), group in selected_predictions.groupby(["project", "level", "family"], sort=True):
        if (family, project, level) not in verified or ("classical", project, level) not in verified:
            raise ValueError("Unverified model pair in review population.")
        expected = canonical[canonical.project == project]
        classical = predictions[(predictions.family == "classical") & (predictions.project == project)
                                & (predictions.level == level) & (predictions.split == policy["split"])]
        left, right = [align_predictions(g, expected, level) for g in (classical, group)]
        y = expected[label_column(level)].to_numpy()
        a = misranking(y, left.instability_probability)
        b = misranking(y, right.instability_probability)
        details = []
        for name, scored, inversion in (("classical", left, a), (family, right, b)):
            diagnostic = diagnostics[
                (diagnostics.family == name) & (diagnostics.project == project)
                & (diagnostics.level == level) & (diagnostics.split == policy["split"])
            ]
            diagnostic = align_predictions(diagnostic, expected, level)
            if not np.allclose(scored.instability_probability, diagnostic.instability_probability,
                               atol=1e-14, rtol=0):
                raise ValueError("Saved diagnostics differ from verified prediction scores.")
            if not np.allclose(inversion, pd.to_numeric(
                diagnostic.opposite_class_misranking_fraction, errors="coerce"
            ), atol=1e-12, rtol=0, equal_nan=True):
                raise ValueError("Saved per-row ranking errors do not reproduce.")
            if scored.model.nunique() != 1 or scored.threshold.nunique() != 1:
                raise ValueError("A cell contains mixed selected models or thresholds.")
            rank_best = scored.instability_probability.rank(ascending=False, method="min")
            rank_worst = scored.instability_probability.rank(ascending=False, method="max")
            details.append([
                {"model": str(scored.model.iloc[i]), "score": float(scored.instability_probability.iloc[i]),
                 "inversion_fraction": float(inversion[i]),
                 "fixed_threshold": float(scored.threshold.iloc[i]),
                 "fixed_prediction": int(scored.instability_probability.iloc[i] >= scored.threshold.iloc[i]),
                 "descending_rank_best": int(rank_best.iloc[i]),
                 "descending_rank_worst": int(rank_worst.iloc[i]),
                 "truncation": (
                     {"tokens": int(float(diagnostic.tokens.iloc[i])), "limit": int(float(diagnostic.limit.iloc[i])),
                      "truncated": str(diagnostic.truncated.iloc[i]).lower() == "true"}
                     if "tokens" in diagnostic and str(diagnostic.tokens.iloc[i]) not in ("", "nan") else None
                 )}
                for i in range(len(expected))
            ])
        good, poor = policy["good_max_inversion"], policy["poor_min_inversion"]
        masks = ((a <= good) & (b >= poor), (b <= good) & (a >= poor),
                 (a >= poor) & (b >= poor), (a <= good) & (b <= good))
        for category, mask in zip(policy["categories"], masks):
            for i in np.flatnonzero(mask):
                candidates.append({
                    "row_id": str(expected.row_id.iloc[i]), "project": str(project),
                    "level": int(level), "family": str(family), "split": policy["split"],
                    "label": int(y[i]), "category": category,
                    "partition_rows": len(expected), "partition_positives": int(y.sum()),
                    "opposite_class_rows": int((y != y[i]).sum()),
                    "classical": details[0][i], "slm": details[1][i],
                })
    return candidates


def select_batch(candidates, policy=REVIEW_POLICY):
    selected, used = [], set()
    counts = {key: Counter() for key in ("project", "level", "family", "label")}
    category_projects = Counter()
    pools = {category: [r for r in candidates if r["category"] == category]
             for category in policy["categories"]}
    shortages = []
    for _ in range(policy["per_category"]):
        for category in policy["categories"]:
            available = [r for r in pools[category] if r["row_id"] not in used]
            if not available:
                continue
            def priority(row):
                return (
                    counts["project"][row["project"]],
                    counts["level"][row["level"]],
                    counts["family"][row["family"]],
                    counts["label"][row["label"]],
                    category_projects[(category, row["project"])],
                    digest([policy["seed"], row["row_id"], row["level"], row["family"], category]),
                )
            chosen = min(available, key=priority)
            selected.append({**chosen, "review_id": f"R{len(selected) + 1:02d}", "review_status": "pending"})
            used.add(chosen["row_id"])
            for key, values in counts.items():
                values[chosen[key]] += 1
            category_projects[(category, chosen["project"])] += 1
    for category in policy["categories"]:
        actual = sum(r["category"] == category for r in selected)
        if actual < policy["per_category"]:
            shortages.append({"category": category, "requested": policy["per_category"], "selected": actual})
    if len(counts["project"]) < 2 or len(counts["level"]) < 2:
        shortages.append({"reason": "Multiple projects and K values could not be covered."})
    return selected, {
        "policy": policy, "requested_stories": len(policy["categories"]) * policy["per_category"],
        "selected_stories": len(selected), "shortages": shortages,
        "candidate_support": {
            category: {"pair_rows": len(pool), "unique_stories": len({r["row_id"] for r in pool})}
            for category, pool in pools.items()
        },
        "selected_by_project": dict(counts["project"]),
        "selected_by_K": {str(k): v for k, v in counts["level"].items()},
        "selected_by_family": dict(counts["family"]),
        "selected_by_label": {str(k): v for k, v in counts["label"].items()},
        "method": "Round-robin category quotas. Prefer least represented project, K, SLM family, label, then category/project; break ties by fixed seed+identity hash. Deduplicate project/story globally across K and SLMs. No fallback or threshold relaxation.",
        "interpretation": "Purposive diagnostic sample of the full verified test population, separate from the 522-story label-audit sample. Not a probability sample and not an estimate of population error rates.",
        "ranking_definition": "Good: <=25% opposite-class inversion; poor: >=50%; ties count half. These are review categories, not a deployment threshold or proof of correctness.",
        "bias_warning": "Scores/labels are disclosed as requested; this is not blinded review. HTML hides scores initially to allow text-first inspection. No human review has been completed.",
    }


def enrich(selected, population, history, coverage):
    indexed = population.set_index("row_id")
    for item in selected:
        story = indexed.loc[item["row_id"]]
        item["sprint_entry"] = str(story.time_add_to_sprint)
        item["original_text"] = {name: str(story[name]) for name in TEXT_COLUMNS}
        item["recorded_counts"] = {name: float(story[name]) if str(story[name]) != "" else None
                                   for name in (COUNT, CHANGES)}
        actual_history = history.get(item["row_id"])
        item["history"] = actual_history or {
            "status": "unavailable", "reason": coverage.get("reason", "No history supplied for this story.")
        }
        item["label_verification"] = "pending_human_review" if actual_history else "unavailable"
        item["questions"] = [
            "Is the recorded label supported by the available history? Cite evidence, or answer unavailable.",
            "What actually changed, and when? Separate requirement changes, editorial edits and uncertain extraction.",
            "Was there a plausible clue in the original sprint-entry text? Quote it and note alternative explanations.",
        ]
    return selected


def render_html(batch, selection):
    escape = lambda value: html.escape(str(value), quote=True)
    lines = [
        '<!doctype html><html lang="en"><meta charset="utf-8"><title>Pending diagnostic review</title>',
        "<style>body{max-width:1000px;margin:2em auto;font:16px sans-serif;line-height:1.5}"
        "pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f4f4;padding:1em}"
        "article{border-top:2px solid #888;margin-top:3em}table{border-collapse:collapse}"
        "td,th{padding:.5em;border:1px solid #aaa}</style>",
        "<h1>First human-review batch: all answers pending</h1>",
        "<p>" + escape(selection["interpretation"]) + "</p>",
        "<p>" + escape(selection["ranking_definition"]) + "</p>",
        "<p>Read text first, then expand scores. Probabilities are P(recorded unstable=1); "
        "cross-model magnitudes are not a calibration comparison. Rank 1 means highest score. "
        "Ranking is relative to the full project/test/K population, not this review batch.</p>",
        "<p>Enter answers in review_sheet.csv. No scripts, remote assets, links or external requests "
        "are embedded in this page. Story content is displayed as escaped text.</p>",
    ]
    for item in batch:
        lines += [
            "<article>",
            f"<h2>{escape(item['review_id'])}: {escape(item['row_id'])}</h2>",
            f"<p>K={item['level']}; recorded label={item['label']}; "
            f"sprint entry: {escape(item['sprint_entry'])}; split: {escape(item['split'])}.</p>",
        ]
        for field, text in item["original_text"].items():
            lines += [f"<h3>{escape(field)}</h3>", "<pre>" + escape(text or "[empty field]") + "</pre>"]
        lines += ["<details><summary>Classical/SLM scores and ranking explanation</summary>",
                  f"<p>Category: {escape(item['category'])}; SLM family: {escape(item['family'])}.</p>",
                  f"<p>Full cell: {item['partition_rows']} stories, {item['partition_positives']} positives; "
                  f"{item['opposite_class_rows']} opposite-class stories for this example.</p>",
                  "<table><tr><th>Model</th><th>P(unstable)</th><th>Inverted opposite-class fraction</th>"
                  "<th>Descending rank range</th><th>Fixed threshold / prediction</th></tr>"]
        for name in ("classical", "slm"):
            m = item[name]
            lines.append(
                f"<tr><td>{escape(name + ': ' + m['model'])}</td><td>{m['score']:.12g}</td>"
                f"<td>{m['inversion_fraction']:.3%}</td>"
                f"<td>{m['descending_rank_best']}-{m['descending_rank_worst']}</td>"
                f"<td>{m['fixed_threshold']:.12g} / {m['fixed_prediction']}</td></tr>"
            )
        direction = ("negative stories scoring above this positive" if item["label"] else
                     "positive stories scoring below this negative")
        lines += ["</table>", f"<p>Inversion measures {direction}, with ties counting half. "
                  "Lower is better. Fixed-threshold errors are separate from ranking categories.</p>"]
        if item["slm"]["truncation"]:
            lines.append("<p>Selected-model tokenizer coverage: " + escape(
                json.dumps(item["slm"]["truncation"])) + "</p>")
        lines += ["</details>", "<h3>Later changes and label evidence</h3>",
                  "<p>Label verification: <b>" + escape(item["label_verification"]) + "</b>.</p>"]
        if "events" not in item["history"]:
            lines.append("<p>History unavailable. Do not infer the label is supported or that no change occurred.</p>")
        else:
            history = item["history"]
            lines += [f"<p>Declared coverage: {escape(history['observation_start'])} to "
                      f"{escape(history['observation_end'])}; complete={escape(history['history_complete'])}. "
                      "This declaration alone does not establish label validity.</p>"]
            later = [e for e in history["events"] if e["post_entry"]]
            if not later:
                lines.append("<p>No post-entry event in the supplied evidence; this is not proof of stability.</p>")
            for event in later:
                lines += [
                    f"<h4>{escape(event['at'])}: {escape(event['field'])}</h4>",
                    "<p>Before</p><pre>" + escape(event["before"]) + "</pre>",
                    "<p>After</p><pre>" + escape(event["after"]) + "</pre>",
                ]
        lines += ["<ol>"] + ["<li>" + escape(q) + "</li>" for q in item["questions"]]
        lines += ["</ol><p>Reviewer: ______; answers: ______; status: pending.</p></article>"]
    lines.append("</html>")
    return "\n".join(lines)


def write_batch(output, batch, selection):
    write_json(output / "selection_manifest.json", selection)
    write_json(output / "review_batch.json", {"review_status": "pending", "stories": batch})
    (output / "review_batch.html").write_text(render_html(batch, selection))
    sheet = []
    for item in batch:
        row = {key: item[key] for key in (
            "review_id", "row_id", "project", "split", "level", "label", "family", "category",
            "label_verification", "review_status",
        )}
        row.update({name: "" for name in (
            "reviewer_id", "label_supported_yes_no_uncertain_unavailable", "what_changed",
            "edit_category", "evidence_timestamps", "plausible_entry_clue", "clue_quote",
            "alternative_explanation", "extraction_concern", "second_reviewer_id",
            "second_label_assessment", "disagreement_notes",
        )})
        # Prevent source-controlled identifiers from becoming spreadsheet formulas.
        sheet.append({k: "'" + v if isinstance(v, str) and v.startswith(("=", "+", "-", "@", "\t", "\r"))
                      else v for k, v in row.items()})
    pd.DataFrame(sheet, columns=list(sheet[0]) if sheet else [
        "review_id", "row_id", "review_status", "reviewer_id"
    ]).to_csv(output / "review_sheet.csv", index=False)


def execute(root, batch_id):
    root = external_path(root)
    inputs = load_inputs(root)
    output = root / "error-analysis" / slug(batch_id)
    if output.resolve().parent != (root / "error-analysis").resolve():
        raise ValueError("Review output escaped the source run.")
    output.mkdir(exist_ok=False)
    status_path = output / "status.json"
    producer_files = [Path(__file__), TASK / "scripts/reconcile_intervals.py",
                      TASK / "scripts/diagnostic_config.py", TASK / "scripts/errors.py",
                      TASK / "scripts/data_profile.py", TASK / "scripts/support.py",
                      TASK / "scripts/evidence.py", TASK / "cluster/submit_jobs.py",
                      HF / "evaluate.py", HF / "common.py", HF / "reference_contract.json",
                      REPO / "Tasks/jira-url-to-instability-model/unstable_model/evaluation.py"]
    metadata = {
        "run_id": inputs["run"]["run_id"], "source_run": str(root), "batch_id": batch_id,
        "stage": "T2-T3-human-review-and-interval-reconciliation",
        "source_run_sha256": inputs["run"]["source_sha256"],
        "input_sha256": inputs["input_sha256"],
        "producer_sha256": {str(p.relative_to(REPO)): file_hash(p) for p in producer_files},
        "policy_sha256": digest(REVIEW_POLICY),
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "human_reviews_completed": 0,
    }
    write_json(status_path, {**metadata, "status": "deferred", "reason": "export started"})
    try:
        candidates = candidate_pairs(inputs["population"], inputs["predictions"],
                                     inputs["diagnostics"], inputs["integrity"])
        selected, selection = select_batch(candidates)
        history, coverage = {}, {"status": "unavailable", "reason": "No history supplied in the source run."}
        if inputs["run"].get("histories"):
            path = Path(inputs["run"]["histories"])
            try:
                if file_hash(path) != inputs["run"]["histories_sha256"]:
                    raise ValueError("History bytes differ from source run.")
                history, coverage = histories_at(path, inputs["population"])
            except (OSError, ValueError, TypeError, KeyError) as exc:
                coverage = {"status": "unavailable", "reason": str(exc)}
        batch = enrich(selected, inputs["population"], history, coverage)
        write_batch(output, batch, {**metadata, **selection, "history_coverage": coverage})
        intervals = []
        for project, level in REVIEW_POLICY["ci_targets"]:
            try:
                intervals.append(reconcile_cell(
                    root, inputs["population"], inputs["predictions"], inputs["integrity"],
                    inputs["slices"], project, level,
                ))
            except (OSError, ValueError, KeyError, StopIteration, subprocess.CalledProcessError) as exc:
                intervals.append({"project": project, "level": level, "status": "blocked",
                                  "reason": str(exc) or "Required target evidence is missing."})
        write_json(output / "ci_reconciliation.json", {**metadata, "cells": intervals})
        (output / "ci_reconciliation.md").write_text(reconciliation_markdown(intervals))
        # A concurrent source edit invalidates this supplement rather than silently mixing runs.
        for name, expected in inputs["input_sha256"].items():
            if file_hash(root / name) != expected:
                raise ValueError(f"Frozen input changed during review export: {name}")
        blocked = bool(selection["shortages"]) or any(c["status"] != "succeeded" for c in intervals)
        state = "blocked" if blocked else "succeeded"
        (output / "coordination_handoff.md").write_text(
            "# MAster SLM: T2/T3 review supplement\n\n"
            f"Source run: `{root}`.\n\n"
            f"Export status: {state}; prepared {len(batch)} unique stories; human reviews completed: 0.\n\n"
            "Review `review_batch.html` locally and answer in `review_sheet.csv`. "
            "Full source text and scores are in `review_batch.json`; all are outside Git. "
            "This is a purposive score-disclosed diagnostic sample, not a population error-rate estimate.\n\n"
            f"History evidence: {coverage['status']}. Missing histories mean label verification unavailable.\n\n"
            "Read `ci_reconciliation.md` and `.json` for exact-input replay of BOTH uncertainty methods. "
            "A blocked replay is not a reconciliation; do not choose a favorable interval.\n\n"
            "No new predictions, training, label changes or T4-T7 work. "
            "Do not upload story text externally. Keep all review answers pending until supplied by a human.\n"
        )
        outputs = {p.name: file_hash(p) for p in output.iterdir() if p.is_file() and p != status_path}
        write_json(status_path, {**metadata, "status": state, "prepared_stories": len(batch),
                                 "history_status": coverage["status"], "outputs_sha256": outputs,
                                 "reconciliation_status": [{"project": c["project"], "level": c["level"],
                                                            "status": c["status"]} for c in intervals]})
        print(f"Review supplement: {output}")
        print(f"Prepared stories: {len(batch)}; human reviews completed: 0; status: {state}")
        return 2 if blocked else 0
    except Exception as exc:
        write_json(status_path, {**metadata, "status": "failed", "error_type": type(exc).__name__,
                                 "reason": str(exc)})
        raise


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-run", type=Path, required=True)
    parser.add_argument("--batch-id", default="human-review-01")
    parser.add_argument("--policy-sha256", default=digest(REVIEW_POLICY))
    args = parser.parse_args()
    try:
        if args.policy_sha256 != digest(REVIEW_POLICY):
            raise ValueError("Review policy changed after submission; submit again with a new batch ID.")
        return execute(args.source_run, args.batch_id)
    except (OSError, ValueError, KeyError) as exc:
        print(f"Review export blocked/failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
