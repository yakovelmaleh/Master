import csv
import json
import re
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd

from unstable_model.config import load_config
from unstable_model.training import partition_summary, train_model
from unstable_model.data import chronological_split, label_column

from .client import JiraClient
from .preprocessing import add_previous_creator_counts, preprocess_record


def slug(value):
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")


def repository_name(jira_url):
    hostname = (urlparse(jira_url).hostname or "").casefold()
    parts = hostname.split(".")
    if len(parts) >= 3 and parts[-2:] == ["atlassian", "net"]:
        return slug(parts[0])
    if len(parts) >= 2 and parts[0] in {
        "jira",
        "issues",
        "bugs",
        "bugreports",
    }:
        return slug(parts[1])
    return slug(parts[0] if parts else "jira")


def default_run_name(jira_url, project):
    repository = repository_name(jira_url)
    return (
        f"{repository}-{slug(project)}"
        if project
        else repository
    )


def write_json(path, value):
    Path(path).write_text(
        json.dumps(value, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def selected_field_ids(field_map):
    standard = [
        "summary",
        "description",
        "issuetype",
        "project",
        "created",
        "updated",
        "resolutiondate",
        "priority",
        "creator",
        "reporter",
    ]
    custom = [
        field_map[name]
        for name in ("Sprint", "Acceptance Criteria", "Story Points")
        if name in field_map
    ]
    return standard + custom


def build_jql(
    project, custom_jql, terminal_only, require_pr_evidence,
    require_current_sprint=False, pr_evidence_jql=None, terminal_jql=None,
):
    clauses = []
    if project:
        clauses.append(f'project = "{project}"')
    clauses.append(custom_jql or "type != Bug")
    if require_current_sprint:
        clauses.append("Sprint is not EMPTY")
    if terminal_only:
        clauses.append(terminal_jql or "statusCategory = Done")
    if require_pr_evidence:
        clauses.append(pr_evidence_jql or 'comment ~ "https://github.com"')
    return " AND ".join(f"({clause})" for clause in clauses) + (
        " ORDER BY created ASC"
    )


def download_records(client, keys, field_ids, raw_path, error_path):
    records = []
    errors = []
    for index, key in enumerate(keys, start=1):
        try:
            record = {
                "issue": client.issue(key, field_ids),
                "comments": client.comments(key),
                "changelog": client.changelog(key),
            }
            records.append(record)
        except Exception as error:
            errors.append({"issue_key": key, "error": str(error)})
        if index % 25 == 0 or index == len(keys):
            print(
                f"Downloaded {index:,}/{len(keys):,} issues "
                f"({len(errors)} errors)",
                flush=True,
            )
    with raw_path.open("w", encoding="utf-8") as raw_file:
        for record in records:
            raw_file.write(json.dumps(record, default=str) + "\n")
    with error_path.open("w", newline="", encoding="utf-8") as error_file:
        writer = csv.DictWriter(
            error_file, fieldnames=["issue_key", "error"]
        )
        writer.writeheader()
        writer.writerows(errors)
    return records


def read_records(raw_path):
    records = []
    with raw_path.open(encoding="utf-8") as raw_file:
        for line in raw_file:
            if line.strip():
                records.append(json.loads(line))
    return records


def dataset_analysis(frame, config):
    analysis = {
        "rows": len(frame),
        "unique_issues": int(frame["issue_key"].nunique()) if len(frame) else 0,
        "levels": {},
        "warnings": [],
    }
    if len(frame) and frame["issue_key"].duplicated().any():
        raise ValueError("Duplicate issue keys in the processed dataset.")
    partitions = {}
    if len(frame) >= 30:
        train, validation, test = chronological_split(
            frame, config.train_fraction, config.validation_fraction
        )
        partitions = {"train": train, "validation": validation, "test": test}
    else:
        analysis["warnings"].append("Fewer than 30 rows; model training is not possible.")
    for level in (5, 10, 15, 20):
        target = label_column(level)
        positives = int(frame[target].sum()) if len(frame) else 0
        details = {
            "positive_count": positives,
            "negative_count": len(frame) - positives,
            "positive_rate": positives / len(frame) if len(frame) else None,
            "partitions": {},
        }
        for name, partition in partitions.items():
            summary = partition_summary(partition, target)
            details["partitions"][name] = summary
            if summary["positive_count"] in (0, summary["row_count"]):
                analysis["warnings"].append(
                    f"Level {level}: {name} has only one class; "
                    "PR/ROC discrimination cannot be evaluated."
                )
        analysis["levels"][str(level)] = details
    return analysis


def run_pipeline(args):
    run_name = args.run_name or default_run_name(
        args.jira_url, args.project
    )
    run_dir = args.output_root / run_name
    raw_dir = run_dir / "raw"
    processed_dir = run_dir / "processed"
    model_dir = run_dir / "model"
    raw_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)
    model_dir.mkdir(parents=True, exist_ok=True)

    client = JiraClient(args.jira_url)
    field_map = client.fields()
    write_json(raw_dir / "field_map.json", field_map)
    if "Sprint" not in field_map:
        raise RuntimeError(
            "This Jira repository does not expose a field named 'Sprint'. "
            "Use --jql only if an equivalent sprint field is configured."
        )
    jql = build_jql(
        args.project,
        args.jql,
        args.terminal_only,
        args.require_pr_evidence,
        getattr(args, "require_current_sprint", False),
        getattr(args, "pr_evidence_jql", None),
        getattr(args, "terminal_jql", None),
    )
    metadata = {
        "jira_url": args.jira_url,
        "project": args.project,
        "jql": jql,
        "max_issues": args.max_issues,
        "terminal_only": args.terminal_only,
        "require_pr_evidence": args.require_pr_evidence,
        "require_current_sprint": getattr(args, "require_current_sprint", False),
        "label_threshold": args.label_threshold,
        "api_version": client.api_version,
    }
    raw_path = raw_dir / "issues.jsonl"
    error_path = raw_dir / "download_errors.csv"
    config_path = run_dir / "run_config.json"
    if raw_path.exists() and not args.refresh:
        if not config_path.exists():
            raise ValueError("Cached issues have no run configuration. Use --refresh.")
        previous = json.loads(config_path.read_text(encoding="utf-8"))
        if previous.get("download_complete") is False:
            raise ValueError("The cached download is incomplete. Use --refresh.")
        selection_keys = ("jira_url", "project", "jql", "max_issues")
        if any(previous.get(key) != metadata[key] for key in selection_keys):
            raise ValueError(
                "Cached issues were collected with different selection settings. "
                "Use --refresh or a new --run-name."
            )
        records = read_records(raw_path)
        keys = json.loads((raw_dir / "issue_keys.json").read_text(encoding="utf-8"))
    else:
        keys = client.search_issue_keys(jql, args.max_issues)
        if len(keys) != len(set(keys)):
            raise ValueError("Jira search returned duplicate issue keys.")
        metadata["download_complete"] = False
        write_json(config_path, metadata)
        write_json(raw_dir / "issue_keys.json", keys)
        records = download_records(
            client,
            keys,
            selected_field_ids(field_map),
            raw_path,
            error_path,
        )
    if len(keys) != len(set(keys)):
        raise ValueError("Jira search returned duplicate issue keys.")
    metadata["download_complete"] = len(records) == len(keys)
    write_json(config_path, metadata)

    rows = []
    decisions = []
    reasons = Counter()
    for record in records:
        row, reason = preprocess_record(record, field_map)
        reasons[reason] += 1
        decisions.append({"issue_key": record["issue"]["key"], "reason": reason})
        if row:
            rows.append(row)
    frame = add_previous_creator_counts(pd.DataFrame(rows)) if rows else pd.DataFrame()
    source_name = default_run_name(args.jira_url, args.project)
    source_dir = processed_dir / source_name
    source_dir.mkdir(parents=True, exist_ok=True)
    dataset_path = source_dir / "features_labels_table_os.csv"
    if rows:
        frame.to_csv(dataset_path, index=False)
    with (processed_dir / "filter_decisions.csv").open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=["issue_key", "reason"])
        writer.writeheader()
        writer.writerows(decisions)
    write_json(
        processed_dir / "filter_summary.json",
        {
            "selected_keys": len(keys),
            "downloaded_records": len(records),
            "download_failed_records": len(keys) - len(records),
            "download_limited": args.max_issues is not None,
            "effective_jql": jql,
            "accepted_records": len(frame),
            "rejected_records": len(records) - len(frame),
            "reasons": dict(reasons),
        },
    )

    config = load_config(Path(__file__).resolve().parents[1] / "model_config.json")
    analysis = dataset_analysis(frame, config)
    write_json(processed_dir / "dataset_analysis.json", analysis)
    for warning in analysis["warnings"]:
        print(f"WARNING: {warning}", flush=True)
    if len(records) != len(keys):
        raise RuntimeError(
            f"{len(keys) - len(records)} issues failed to download. "
            "See raw/download_errors.csv; use --refresh to retry."
        )
    if not rows:
        raise RuntimeError(
            f"No valid model rows remained after preprocessing: {reasons}"
        )
    trained_dir, metrics = train_model(
        data_root=processed_dir,
        output_root=model_dir,
        project=source_name,
        threshold=args.label_threshold,
        config=config,
    )
    return {
        "run_directory": str(run_dir.resolve()),
        "dataset": str(dataset_path.resolve()),
        "model_directory": str(trained_dir.resolve()),
        "accepted_rows": len(frame),
        "test_metrics": metrics["test"],
    }
