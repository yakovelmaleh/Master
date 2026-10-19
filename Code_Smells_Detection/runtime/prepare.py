"""Enrich fixed Jira IDs and freeze split membership before code exclusions."""

from collections import Counter
from contextlib import ExitStack
import csv
import json
from pathlib import Path
import re

import pandas as pd

from . import collection
from .common import (
    CANDIDATE_HASH, PARTITIONS, SCHEMA, SOURCES, atomic_bytes, digest, file_hash,
    identifier, immutable_json, lock, now, read_json, require_stage, source_hash,
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

    def request(self, method, path, **kwargs):
        try:
            return super().request(method, path, **kwargs)
        except RuntimeError as error:
            raise collection.CollectionError("request_retries_exhausted") from error

    @staticmethod
    def response_json(response):
        if response.status_code >= 400:
            raise collection.CollectionError(
                collection.REASONS.get(response.status_code, "http_failure"), response.status_code)
        try:
            return response.json()
        except ValueError as error:
            raise collection.CollectionError("invalid_json") from error

    def json_request(self, method, path, **kwargs):
        return self.response_json(self.request(method, path, **kwargs))

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
            payload = self.response_json(response)
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


def audit(root, candidates, sources, prior_manifest=None, migration_sha256=None):
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
    if migration_sha256:
        manifest["migration_sha256"] = migration_sha256
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


def enrich(root, source, client_factory=CompleteJiraClient, missing_records=None, diagnose=False):
    identifier(source)
    if source not in verify_study(root)["sources"]:
        raise ValueError(f"Source is not selected: {source}")
    if diagnose and missing_records:
        raise ValueError("Diagnosis cannot approve collection exclusions.")
    with lock(root / "raw" / source / ".collection.lock"), ExitStack() as resources:
        def managed_client(url):
            client = client_factory(url)
            if getattr(client, "session", None) is not None:
                resources.callback(client.session.close)
            return client
        return collect(root, source, managed_client, missing_records, diagnose)


def collect(root, source, client_factory, missing_records, diagnose):
    manifest = verify_study(root)
    candidates = source_candidates(root, source)
    raw = root / "raw" / source
    raw.mkdir(parents=True, exist_ok=True)
    keys = set(candidates.issue_key)
    if (raw / "manifest.json").exists():
        saved, approved = collection.load_manifest(root, source, keys)
        if missing_records and (not approved or
                                collection.read_review(missing_records) != collection.read_review(raw / "collection_exclusions.json")):
            raise ValueError("Collection is already finalized with a different approval.")
        for key, expected in saved["records"].items():
            if file_hash(raw / f"{key}.json") != expected:
                raise ValueError(f"Finalized Jira record changed: {key}")
        print(f"{source}: finalized; {len(saved['records'])} collected, {len(approved)} approved unavailable.", flush=True)
        return
    if (raw / "collection_exclusions.json").exists() and not missing_records:
        raise ValueError("Approval finalization was interrupted; resume with the same --missing-records ledger.")
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
    if missing_records:
        hashes = {key: file_hash(raw / f"{key}.json") for key in sorted(keys - set(missing))}
        ledger = collection.read_review(missing_records)
        collection.validate_review(root, source, keys, hashes, ledger,
                                   read_json(raw / "collection_diagnostics.json"))
        immutable_json(raw / "collection_exclusions.json", ledger)
        immutable_json(raw / "manifest.json", {
            "records": hashes, "field_map": file_hash(raw / "field_map.json"),
            "collection": {name: file_hash(raw / name) for name in
                           ("collection_diagnostics.json", "collection_exclusions.json")}})
        print(f"{source}: finalized with {len(missing)} explicitly approved unavailable records.", flush=True)
        return
    client = client_factory(manifest["sources"][source]["url"]) if missing else None
    if client:
        current_fields = client.fields()
        if (raw / "field_map.json").exists():
            cached_fields = read_json(raw / "field_map.json")
            if any(cached_fields.get(name) != current_fields.get(name)
                   for name in ("Sprint", "Acceptance Criteria", "Story Points")):
                raise ValueError("Required Jira field mappings changed; do not mix cached and current records.")
        else:
            immutable_json(raw / "field_map.json", current_fields)
    if not (raw / "field_map.json").exists():
        raise ValueError("Missing field map for cached Jira records.")
    field_map = read_json(raw / "field_map.json")
    errors, observations = [], {}
    for index, key in enumerate(missing):
        operation = "issue"
        try:
            issue = client.issue(key, selected_field_ids(field_map))
            if not isinstance(issue, dict) or issue.get("key") != key:
                raise ValueError(f"Jira returned a different key for {key}")
            operation = "comments"
            comments = client.comments(key)
            operation = "changelog"
            record = {"issue": issue, "comments": comments, "changelog": client.changelog(key),
                      "collection_complete": True, "collected_at": now()}
            collection.valid_record(record, key)
            immutable_json(raw / f"{key}.json", record)
        except (ValueError, RuntimeError, OSError) as error:
            errors.append({"issue_key": key, "error_type": type(error).__name__})
            observations[key] = collection.failure(error, operation)
            print(f"Failed Jira collection {source}/{key}: {observations[key]['reason']} "
                  f"(HTTP {observations[key]['http_status']}, {operation})", flush=True)
        except Exception:
            # HTTP failures are not swallowed; a failed stage can reuse completed records.
            write_json(raw / "collection_errors.json", errors + [{"issue_key": key, "error_type": "request_failed"}])
            raise
        if (index + 1) % 25 == 0:
            print(f"{source}: {index + 1}/{len(missing)} attempted; {len(errors)} failed", flush=True)
    write_json(raw / "collection_errors.json", errors)
    hashes = {}
    for key in sorted(keys - set(observations)):
        path = raw / f"{key}.json"
        collection.valid_record(read_json(path), key)
        hashes[key] = file_hash(path)
    checked = collection.controls(client, selected_field_ids(field_map), observations, hashes) if observations else {}
    diagnostics = collection.diagnostic(root, source, keys, hashes, observations, checked)
    write_json(raw / "collection_diagnostics.json", diagnostics)
    write_json(raw / "missing_records.proposed.json",
               collection.proposal(diagnostics, file_hash(raw / "collection_diagnostics.json")))
    if diagnose:
        print(f"{source}: diagnostic complete; {len(hashes)} collected, {len(observations)} unresolved. "
              "Review collection_diagnostics.json; enrichment is not finalized.", flush=True)
        return
    if errors:
        raise ValueError(f"{source}: {len(errors)} incomplete records; resolve/retry before freezing.")
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
    candidates = source_candidates(root, source)
    raw_manifest, unavailable = collection.load_manifest(root, source, set(candidates.issue_key))
    field_map = read_json(raw / "field_map.json")
    rows, decisions = [], []
    for key in candidates.issue_key:
        if key in unavailable:
            decisions.append({"row_id": f"{source}:{key}", "reason": "jira_unavailable",
                              "collection_reason": unavailable[key]})
            continue
        path = raw / f"{key}.json"
        if file_hash(path) != raw_manifest["records"][key]:
            raise ValueError(f"Raw record changed: {key}")
        record = read_json(path)
        collection.valid_record(record, key)
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
    immutable_json(destination / "filter_decisions.json", decisions)
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
    if unavailable:
        split["filter_decisions_sha256"] = file_hash(destination / "filter_decisions.json")
    immutable_json(root / "splits" / f"{source}.json", split)
    for partition in PARTITIONS:
        write_csv(root / "splits" / source / f"{partition}_rows.csv",
                  frame[frame.row_id.map(assignment) == partition][["row_id", "source", "issue_key"]])


def frozen_frame(root, source):
    require_stage(root, "freeze", source)
    split = read_json(root / "splits" / f"{source}.json")
    if "raw_manifest_sha256" in split:
        if file_hash(root / "raw" / source / "manifest.json") != split["raw_manifest_sha256"]:
            raise ValueError("Frozen Jira manifest changed.")
        collection.load_manifest(root, source, set(source_candidates(root, source).issue_key))
    if ("filter_decisions_sha256" in split and
            file_hash(root / "features" / source / "filter_decisions.json") != split["filter_decisions_sha256"]):
        raise ValueError("Frozen preprocessing or collection decisions changed.")
    path = root / "features" / source / "features.csv"
    if file_hash(path) != split["feature_sha256"]:
        raise ValueError(f"Frozen features changed: {source}")
    frame = pd.read_csv(path, keep_default_na=False)
    if frame.row_id.tolist() != split["rows"] or set(frame.row_id) != set(split["assignment"]):
        raise ValueError("Frozen split row membership differs.")
    return frame, split
