#!/usr/bin/env python3
"""Inventory every planned model/level, including missing or failed outputs."""

import csv
import json
import re
import sys
from pathlib import Path


def write_csv(path, rows, columns):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def summarize(bundle):
    bundle = Path(bundle).resolve()
    artifacts = bundle / "artifacts"
    coverage = []
    results = []
    accounted = set()
    metric_fields = ["auc_prc", "average_precision", "accuracy", "roc_auc",
                     "precision", "recall", "f1", "row_count", "positive_rate"]

    def collect(path, identity):
        test = json.loads(path.read_text())["test"]
        row = {**identity, **{k: test.get(k) for k in metric_fields},
               "metrics_path": str(path.relative_to(bundle))}
        results.append(row)
        accounted.add(path)

    for plan_path in sorted(artifacts.rglob("job_plan.json")):
        plan = json.loads(plan_path.read_text())
        root = plan_path.parent
        for job in plan["jobs"]:
            result_root = (root / job["results"]).resolve()
            if root.resolve() not in result_root.parents:
                raise ValueError(f"Job results escape run directory: {job['results']}")
            manifest_path = result_root / "verification_manifest.json"
            status = json.loads(manifest_path.read_text())["status"] if manifest_path.is_file() else "not_started"
            for model in job["models"]:
                for variant in job["variants"]:
                    directory = result_root / "model" / f"words_{job['level']}" / model / variant
                    metric_paths = list(directory.rglob("metrics.json"))
                    identity = {
                        "run": str(root.relative_to(artifacts)), "project": job["project"],
                        "level": job["level"], "model": model, "variant": variant,
                    }
                    missing = []
                    if len(metric_paths) == 1:
                        metric_path = metric_paths[0]
                        required = ["run_metadata.json", "test_predictions.csv", "validation_predictions.csv",
                                    "model.npz" if model == "Logistic" else "model.joblib"]
                        missing = [name for name in required if not (metric_path.parent / name).is_file()]
                        collect(metric_path, identity)
                    else:
                        missing = ["metrics.json" if not metric_paths else "ambiguous_metrics"]
                    coverage.append({
                        **identity, "job_status": status,
                        "coverage": "complete" if not missing and status == "succeeded" else "incomplete",
                        "missing_files": ";".join(missing),
                    })
    # Older runs have no job plan. Include every available level, but do not
    # infer completeness from whatever happens to be present.
    for path in sorted(artifacts.rglob("metrics.json")):
        if path in accounted:
            continue
        metadata = path.parent / "run_metadata.json"
        if not metadata.is_file():
            continue
        meta = json.loads(metadata.read_text())
        level = meta.get("level")
        if level is None:
            match = re.search(r"(?:num_words_|words_)(5|10|15|20)(?:$|/)", meta.get("label_column", "") + "/")
            level = int(match[1]) if match else "unknown"
        identity = {
            "run": str(path.parent.relative_to(artifacts)), "project": meta.get("project", "unknown"),
            "level": level, "model": meta.get("model", "unknown"), "variant": meta.get("variant", "legacy_unplanned"),
        }
        collect(path, identity)
        coverage.append({**identity, "job_status": "unplanned", "coverage": "unknown", "missing_files": ""})
    keys = ["run", "project", "level", "model", "variant"]
    write_csv(bundle / "LEVELS.csv", coverage, keys + ["job_status", "coverage", "missing_files"])
    write_csv(bundle / "RESULTS.csv", results, keys + metric_fields + ["metrics_path"])
    levels = sorted({str(row["level"]) for row in coverage},
                    key=lambda value: int(value) if value.isdigit() else 999)
    absent = sorted({"5", "10", "15", "20"} - set(levels), key=int)
    incomplete = sum(row["coverage"] != "complete" for row in coverage)
    text = (
        "\n## Unstable-level coverage\n\n"
        f"- Levels present/planned: {', '.join(levels) or 'none detected'}.\n"
        f"- Standard levels absent: {', '.join(absent) or 'none'}.\n"
        f"- Incomplete or unverified model/level entries: {incomplete} of {len(coverage)}.\n"
        "- Published historical reference CSVs are kept separately; they are not matched rerun scores.\n"
        "- AUC-PRC is trapezoidal PR area; average precision is a separate metric. Blank means not recorded.\n"
    )
    (bundle / "LEVEL_SUMMARY.md").write_text(text)
    print(text)


if __name__ == "__main__":
    summarize(sys.argv[1])
