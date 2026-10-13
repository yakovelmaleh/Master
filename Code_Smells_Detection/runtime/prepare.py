"""Enrich fixed Jira IDs and freeze split membership before code exclusions."""

from collections import Counter
import csv
import json
from pathlib import Path
import re

import pandas as pd

from .common import (
    CANDIDATE_HASH, PARTITIONS, SCHEMA, SOURCES, atomic_bytes, digest, file_hash,
    identifier, immutable_json, now, read_json, require_stage, source_hash,
    verify_study, write_csv, write_json,
)
from jira_pipeline.client import JiraClient
from jira_pipeline.orchestrator import selected_field_ids
from jira_pipeline.preprocessing import (
    add_previous_creator_counts, display_value, field_changes, flattened_changes,
    preprocess_record, timestamp,
)
from unstable_model.data import (
    CATEGORICAL_COLUMNS, IDENTIFIER_COLUMNS, NUMERIC_COLUMNS, TEXT_COLUMNS,
    prepare_feature_frame,
)


FEATURE_COLUMNS = IDENTIFIER_COLUMNS + TEXT_COLUMNS + CATEGORICAL_COLUMNS + NUMERIC_COLUMNS


class CompleteJiraClient(JiraClient):
    """The legacy expanded-changelog fallback must not silently truncate history."""

    def pages(self, key, endpoint, fields, fallback=False):
        rows, start, total = [], 0, None
        while True:
            response = self.request(
                "GET", f"/rest/api/{self.api_version}/issue/{key}/{endpoint}",
                params={"startAt": start, "maxResults": 100},
            )
            if fallback and response.status_code in (404, 405):
                issue = self.json_request("GET", f"/rest/api/{self.api_version}/issue/{key}",
                                          params={"expand": "changelog", "fields": "key"})
                payload = issue.get("changelog") or {}
                history = payload.get("histories", [])
                if payload.get("total") != len(history) or payload.get("startAt", 0) != 0:
                    raise ValueError(f"Incomplete expanded changelog for {key}")
                return history
            response.raise_for_status()
            payload = response.json()
            page = next((payload[name] for name in fields if name in payload), None)
            if not isinstance(page, list) or payload.get("startAt", start) != start:
                raise ValueError(f"Invalid {endpoint} page for {key}")
            current_total = payload.get("total")
            if total is not None and current_total != total:
                raise ValueError(f"{endpoint} changed during collection for {key}; retry")
            total = current_total
            rows.extend(page)
            start += len(page)
            if total is not None and start == total:
                break
            if payload.get("isLast") is True:
                if total is not None and start != total:
                    raise ValueError(f"Truncated {endpoint} for {key}")
                break
            if not page or total is not None and start > total:
                raise ValueError(f"Incomplete {endpoint} for {key}")
        ids = [item["id"] for item in rows]
        if len(set(ids)) != len(ids):
            raise ValueError(f"Duplicated {endpoint} pages for {key}")
        return rows

    def comments(self, key):
        return self.pages(key, "comment", ("comments",))

    def changelog(self, key):
        return self.pages(key, "changelog", ("values", "histories"), fallback=True)


def audit(root, candidates, sources, prior_manifest=None):
    candidates, sources = Path(candidates), Path(sources)
    if file_hash(candidates) != CANDIDATE_HASH:
        raise ValueError("Expected the frozen September 10 candidate CSV, not a refreshed cohort.")
    with candidates.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    if (Counter(row["source"] for row in rows) != SOURCES or
            len({(row["source"], row["issue_key"]) for row in rows}) != sum(SOURCES.values())):
        raise ValueError("Candidate counts or unique source/issue IDs differ.")
    for row in rows:
        identifier(row["issue_key"])
    with sources.open(newline="") as stream:
        source_rows = list(csv.DictReader(stream))
    selected = sorted(name for name, count in SOURCES.items() if count >= 100)
    configuration = {}
    for name in selected:
        matches = [row for row in source_rows if row["source"] == name]
        if len(matches) != 1 or int(matches[0]["candidate_count"]) != SOURCES[name]:
            raise ValueError(f"Missing or inconsistent source provenance: {name}")
        row = matches[0]
        if not row["base_url"].startswith("https://") or not row["jql"]:
            raise ValueError(f"Invalid Jira source configuration: {name}")
        configuration[name] = {"url": row["base_url"], "jql": row["jql"]}
    inputs = {"candidates.csv": file_hash(candidates), "sources.csv": file_hash(sources)}
    prior = read_json(prior_manifest) if prior_manifest else {}
    if set(prior) - set(selected):
        raise ValueError("Prior manifest contains sources outside the selected cohort.")
    for source, entry in prior.items():
        if set(entry) - {"raw_jsonl", "field_map", "features", "split"}:
            raise ValueError(f"Unknown prior artifact type: {source}")
        if ("raw_jsonl" in entry) != ("field_map" in entry):
            raise ValueError("Cached raw JSONL requires its matching field map.")
        if ("split" in entry) != ("features" in entry):
            raise ValueError("Importing split membership requires matching feature bytes.")
        for kind, value in entry.items():
            path = Path(value).expanduser().resolve()
            entry[kind] = {"path": str(path), "sha256": file_hash(path)}
    manifest = {"schema": SCHEMA, "source_sha256": source_hash(), "inputs": inputs,
                "sources": configuration, "min_rows": 100, "prior": prior}
    root.mkdir(parents=True, exist_ok=True)
    if (root / "study.json").exists() and read_json(root / "study.json") != manifest:
        raise ValueError("Study exists with different inputs/configuration.")
    for source, name in ((candidates, "candidates.csv"), (sources, "sources.csv")):
        destination = root / "cohort" / name
        if destination.exists() and file_hash(destination) != inputs[name]:
            raise ValueError(f"Existing cohort file differs: {destination}")
        atomic_bytes(destination, source.read_bytes())
    immutable_json(root / "study.json", manifest)
    write_json(root / "cohort/retention.json", {
        "candidates": SOURCES, "selected_sources": selected,
        "selected_candidates": sum(SOURCES[name] for name in selected),
        "excluded": {name: "fewer_than_100_candidates" for name in SOURCES if name not in selected},
        "model_ready": False,
    })


def prior_file(manifest, source, name):
    value = manifest["prior"].get(source, {}).get(name)
    if value is None:
        return None
    path = Path(value["path"])
    if file_hash(path) != value["sha256"]:
        raise ValueError(f"Prior artifact changed: {source}/{name}")
    return path


def source_candidates(root, source):
    manifest = verify_study(root)
    if source not in manifest["sources"]:
        raise ValueError(f"Source is not selected: {source}")
    frame = pd.read_csv(root / "cohort/candidates.csv", keep_default_na=False)
    return frame[frame.source == source]


def enrich(root, source, client_factory=CompleteJiraClient):
    manifest = verify_study(root)
    candidates = source_candidates(root, source)
    raw = root / "raw" / source
    raw.mkdir(parents=True, exist_ok=True)
    keys = set(candidates.issue_key)
    previous = prior_file(manifest, source, "raw_jsonl")
    if previous:
        field_map = json.loads(prior_file(manifest, source, "field_map").read_text())
        immutable_json(raw / "field_map.json", field_map)
        seen = set()
        with previous.open() as stream:
            for line in stream:
                record = json.loads(line)
                key = record["issue"]["key"]
                if key not in keys:
                    continue
                if key in seen:
                    raise ValueError(f"Duplicate cached issue: {source}/{key}")
                seen.add(key)
                # Existing caches are provenance inputs, not proof that pagination completed.
                if not record.get("collection_complete"):
                    print(f"Re-fetching unverified cached history: {source}/{key}", flush=True)
                    continue
                immutable_json(raw / f"{identifier(key)}.json", record)
    missing = [key for key in candidates.issue_key if not (raw / f"{key}.json").exists()]
    client = client_factory(manifest["sources"][source]["url"]) if missing else None
    if client:
        immutable_json(raw / "field_map.json", client.fields())
    if not (raw / "field_map.json").exists():
        raise ValueError("Missing field map for cached Jira records.")
    field_map = read_json(raw / "field_map.json")
    errors = []
    for index, key in enumerate(missing):
        try:
            record = {"issue": client.issue(key, selected_field_ids(field_map)),
                      "comments": client.comments(key), "changelog": client.changelog(key),
                      "collection_complete": True, "collected_at": now()}
            if record["issue"]["key"] != key:
                raise ValueError(f"Jira returned a different key for {key}")
            immutable_json(raw / f"{key}.json", record)
        except (ValueError, RuntimeError, OSError) as error:
            errors.append({"issue_key": key, "error_type": type(error).__name__})
            print(f"Failed Jira collection {source}/{key}: {type(error).__name__}", flush=True)
        except Exception:
            # HTTP failures are not swallowed; a failed stage can reuse completed records.
            write_json(raw / "collection_errors.json", errors + [{"issue_key": key, "error_type": "request_failed"}])
            raise
        if (index + 1) % 25 == 0:
            print(f"{source}: {index + 1}/{len(missing)} downloaded; {len(errors)} failed", flush=True)
    write_json(raw / "collection_errors.json", errors)
    if errors:
        raise ValueError(f"{source}: {len(errors)} incomplete records; resolve/retry before freezing.")
    hashes = {key: file_hash(raw / f"{key}.json") for key in sorted(keys)}
    immutable_json(raw / "manifest.json", {"records": hashes, "field_map": file_hash(raw / "field_map.json")})


def reconstruct_metadata(row, record):
    """Categorical feature names are retained, but current values cannot leak backwards."""
    fields = record["issue"]["fields"]
    changes = flattened_changes(record["changelog"])
    sprint = timestamp(row["time_add_to_sprint"])
    for column, names, field in (
        ("priority", {"priority"}, "priority"),
        ("issue_type", {"issuetype", "issue type"}, "issuetype"),
        ("project_key", {"project"}, "project"),
    ):
        after = sorted((change for change in field_changes(changes, names)
                        if change["created"] > sprint), key=lambda change: change["created"])
        if after:
            if after[0]["from_string"] is None:
                raise ValueError(f"Unreconstructable {column}")
            row[column] = after[0]["from_string"]
        else:
            row[column] = display_value(fields.get(field))
    for column, names in (
        ("original_summary_sprint", {"summary"}),
        ("original_description_sprint", {"description"}),
        ("original_acceptance_criteria_sprint", {"Acceptance Criteria"}),
        ("original_story_points_sprint", {"Story Points"}),
    ):
        after = sorted((change for change in field_changes(changes, names)
                        if change["created"] > sprint), key=lambda change: change["created"])
        if after:
            value = after[0]["from_string"]
            if column == "original_story_points_sprint":
                row[column] = pd.to_numeric(value, errors="coerce")
            else:
                row[column] = value or ""
    return row


def freeze(root, source):
    manifest = verify_study(root)
    require_stage(root, "enrich", source)
    raw = root / "raw" / source
    raw_manifest = read_json(raw / "manifest.json")
    if file_hash(raw / "field_map.json") != raw_manifest["field_map"]:
        raise ValueError("Jira field map changed.")
    field_map = read_json(raw / "field_map.json")
    rows, decisions = [], []
    for key in source_candidates(root, source).issue_key:
        path = raw / f"{key}.json"
        if file_hash(path) != raw_manifest["records"][key]:
            raise ValueError(f"Raw record changed: {key}")
        record = read_json(path)
        row, reason = preprocess_record(record, field_map)
        if row is not None:
            try:
                row = reconstruct_metadata(row, record)
            except ValueError:
                row, reason = None, "unreconstructable_pre_sprint_metadata"
        decisions.append({"row_id": f"{source}:{key}", "reason": reason})
        if row is not None:
            rows.append(row)
    destination = root / "features" / source
    write_json(destination / "filter_decisions.json", decisions)
    if rows:
        frame = add_previous_creator_counts(pd.DataFrame(rows))
        frame = prepare_feature_frame(frame)
    else:
        frame = pd.DataFrame(columns=FEATURE_COLUMNS)
        print(f"{source}: no valid story rows; this source will be reported as insufficient data.", flush=True)
    frame["row_id"] = source + ":" + frame.issue_key.astype(str)
    frame["source"] = source
    frame = frame.sort_values(["time_add_to_sprint", "row_id"], kind="stable").reset_index(drop=True)
    content = frame[["row_id", "source"] + FEATURE_COLUMNS].to_csv(index=False).encode()
    path = destination / "features.csv"
    if path.exists() and path.read_bytes() != content:
        raise ValueError("Frozen feature rows changed.")
    atomic_bytes(path, content)
    count = len(frame)
    train_end, validation_end = int(count * .6), int(count * .6) + int(count * .2)
    assignment = {row: partition for partition, values in (
        ("train", frame.row_id.iloc[:train_end]),
        ("validation", frame.row_id.iloc[train_end:validation_end]),
        ("test", frame.row_id.iloc[validation_end:]),
    ) for row in values}
    imported = prior_file(manifest, source, "split")
    if imported:
        if file_hash(prior_file(manifest, source, "features")) != file_hash(path):
            raise ValueError("Prior features do not match the frozen feature bytes.")
        saved = read_json(imported)
        prior_assignment = saved.get("assignment", {})
        if set(prior_assignment) != set(assignment) or set(prior_assignment.values()) != set(PARTITIONS):
            raise ValueError("Prior split membership is incomplete or incompatible.")
        positions = [PARTITIONS.index(prior_assignment[row]) for row in frame.row_id]
        if positions != sorted(positions):
            raise ValueError("Prior split is not chronological in the frozen row order.")
        assignment = prior_assignment
    split = {"feature_sha256": file_hash(path), "assignment": assignment,
             "protocol": "within_jira_source_chronological_60_20_20",
             "inherited": bool(imported), "tie_policy": "sprint_entry_then_source_issue_id",
             "counts": {name: list(assignment.values()).count(name) for name in PARTITIONS},
             "rows": frame.row_id.tolist(),
             "raw_manifest_sha256": file_hash(raw / "manifest.json")}
    immutable_json(root / "splits" / f"{source}.json", split)
    for partition in PARTITIONS:
        write_csv(root / "splits" / source / f"{partition}_rows.csv",
                  frame[frame.row_id.map(assignment) == partition][["row_id", "source", "issue_key"]])


def frozen_frame(root, source):
    require_stage(root, "freeze", source)
    split = read_json(root / "splits" / f"{source}.json")
    path = root / "features" / source / "features.csv"
    if file_hash(path) != split["feature_sha256"]:
        raise ValueError(f"Frozen features changed: {source}")
    frame = pd.read_csv(path, keep_default_na=False)
    if frame.row_id.tolist() != split["rows"] or set(frame.row_id) != set(split["assignment"]):
        raise ValueError("Frozen split row membership differs.")
    return frame, split
