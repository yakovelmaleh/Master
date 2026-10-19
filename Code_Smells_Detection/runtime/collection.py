"""Reviewed Jira unavailability, separate from preprocessing and detector exclusions."""

from collections import Counter
from datetime import datetime
import json

from .common import digest, file_hash, now, read_json


POLICY = "reviewed-jira-unavailability-v1"
REASONS = {401: "authentication_or_permission_denied",
           403: "authentication_or_permission_denied",
           404: "not_found_or_not_visible"}


class CollectionError(RuntimeError):
    def __init__(self, reason, http_status=None):
        self.reason = reason
        self.http_status = http_status
        super().__init__(f"{reason}" + (f" (HTTP {http_status})" if http_status else ""))


def failure(error, operation):
    # Do not persist exception text: legacy HTTP errors can contain response bodies.
    return {"operation": operation, "error_type": type(error).__name__,
            "reason": error.reason if isinstance(error, CollectionError) else "unclassified_collection_failure",
            "http_status": error.http_status if isinstance(error, CollectionError) else None,
            "observed_at": now()}


def project(key):
    return key.rsplit("-", 1)[0]


def valid_record(record, key):
    if (not isinstance(record, dict) or record.get("collection_complete") is not True or
            not isinstance(record.get("issue"), dict) or record["issue"].get("key") != key or
            not isinstance(record["issue"].get("fields"), dict) or
            not isinstance(record.get("comments"), list) or
            not isinstance(record.get("changelog"), list)):
        raise ValueError(f"Invalid or incomplete cached Jira record: {key}")


def read_review(path):
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate collection review key: {key}")
            result[key] = value
        return result
    with open(path, encoding="utf-8") as stream:
        return json.load(stream, object_pairs_hook=unique_pairs)


def controls(client, fields, missing, available):
    result = {"projects": {}}
    groups = [(None, sorted(available))]
    groups += [(name, sorted(key for key in available if project(key) == name))
               for name in sorted({project(key) for key in missing})]
    observed = {}
    for name, keys in groups:
        if not keys:
            value = {"status": "no_cached_control"}
        else:
            key = keys[0]
            if key not in observed:
                try:
                    issue = client.issue(key, fields)
                    if not isinstance(issue, dict) or issue.get("key") != key:
                        raise ValueError("Control issue key differs.")
                    observed[key] = {"status": "accessible", "issue_key": key, "observed_at": now()}
                except (ValueError, RuntimeError, OSError) as error:
                    observed[key] = {"status": "failed", "issue_key": key, **failure(error, "issue")}
            value = observed[key]
        if name is None:
            result["source"] = value
        else:
            result["projects"][name] = value
    return result


def diagnostic(root, source, keys, records, missing, control_results):
    return {"schema": POLICY, "study_sha256": file_hash(root / "study.json"),
            "source": source, "candidate_ids_sha256": digest(sorted(keys)),
            "field_map_sha256": file_hash(root / "raw" / source / "field_map.json"),
            "complete_records_sha256": digest(records), "observed_at": now(),
            "missing": missing, "controls": control_results}


def proposal(diagnostics, diagnostic_hash):
    return {"schema": POLICY, "study_sha256": diagnostics["study_sha256"],
            "source": diagnostics["source"],
            "candidate_ids_sha256": diagnostics["candidate_ids_sha256"],
            "diagnostics_sha256": diagnostic_hash,
            "approved": False, "reviewed_at": "", "review_note": "",
            "reviewed_uncontrolled_projects": [],
            "records": {key: item["reason"] for key, item in diagnostics["missing"].items()
                        if eligible(item)}}


def eligible(item):
    return (item["operation"] == "issue" and item["http_status"] in REASONS and
            item["reason"] == REASONS[item["http_status"]])


def validate_review(root, source, keys, records, ledger, diagnostics):
    expected = {"schema": POLICY, "study_sha256": file_hash(root / "study.json"),
                "source": source, "candidate_ids_sha256": digest(sorted(keys))}
    if any(ledger.get(name) != value or diagnostics.get(name) != value for name, value in expected.items()):
        raise ValueError("Collection review belongs to another study, source, policy or cohort.")
    raw = root / "raw" / source
    if (ledger.get("diagnostics_sha256") != file_hash(raw / "collection_diagnostics.json") or
            diagnostics.get("field_map_sha256") != file_hash(raw / "field_map.json") or
            diagnostics.get("complete_records_sha256") != digest(records)):
        raise ValueError("Collection review evidence or cached inventory changed; diagnose and review again.")
    if ledger.get("approved") is not True or not isinstance(ledger.get("review_note"), str) or not ledger["review_note"].strip():
        raise ValueError("Missing explicit collection approval and review note.")
    try:
        reviewed = datetime.fromisoformat(ledger["reviewed_at"])
        observed = datetime.fromisoformat(diagnostics["observed_at"])
        if reviewed.utcoffset() is None or reviewed < observed:
            raise ValueError("Review must follow the diagnostic observation.")
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("A timezone-aware review timestamp after diagnosis is required.") from error
    approved, missing = ledger.get("records", {}), diagnostics.get("missing", {})
    if not isinstance(approved, dict) or set(approved) != set(keys) - set(records) or set(approved) != set(missing):
        raise ValueError("Approval must cover exactly the missing candidates, without overlaps or foreign IDs.")
    if not approved or any(not eligible(item) or approved[key] != item["reason"] for key, item in missing.items()):
        raise ValueError("Unclassified, transient or incomplete-history failures cannot be approved.")
    checked = diagnostics.get("controls", {})
    source_control = checked.get("source", {})
    if source_control.get("status") != "accessible" or source_control.get("issue_key") not in records:
        raise ValueError("Source access control failed or is missing; investigate before exclusions.")
    uncontrolled = set()
    for name in {project(key) for key in approved}:
        control = checked.get("projects", {}).get(name, {})
        status = control.get("status")
        if status == "no_cached_control":
            if any(project(key) == name for key in records):
                raise ValueError(f"Project control evidence contradicts the cached inventory: {name}")
            uncontrolled.add(name)
        elif (status != "accessible" or control.get("issue_key") not in records or
              project(control["issue_key"]) != name):
            raise ValueError(f"Project access control failed or is missing: {name}")
    reviewed_projects = ledger.get("reviewed_uncontrolled_projects")
    if (not isinstance(reviewed_projects, list) or len(set(reviewed_projects)) != len(reviewed_projects) or
            set(reviewed_projects) != uncontrolled):
        raise ValueError("Explicitly review exactly the projects with no cached control.")
    return approved


def load_manifest(root, source, keys):
    raw = root / "raw" / source
    saved = read_json(raw / "manifest.json")
    records = saved["records"]
    if not set(records) <= set(keys) or saved["field_map"] != file_hash(raw / "field_map.json"):
        raise ValueError("Jira manifest contains foreign IDs or a changed field map.")
    approved = {}
    if "collection" in saved:
        for name, expected in saved["collection"].items():
            if name not in ("collection_diagnostics.json", "collection_exclusions.json"):
                raise ValueError("Unknown collection provenance artifact.")
            if file_hash(raw / name) != expected:
                raise ValueError(f"Frozen collection provenance changed: {name}")
        if set(saved["collection"]) != {"collection_diagnostics.json", "collection_exclusions.json"}:
            raise ValueError("Incomplete collection provenance.")
        approved = validate_review(root, source, keys, records,
                                   read_review(raw / "collection_exclusions.json"),
                                   read_json(raw / "collection_diagnostics.json"))
        if any((raw / f"{key}.json").exists() for key in approved):
            raise ValueError("An approved unavailable record appeared after finalization; use a new run.")
    if set(records) | set(approved) != set(keys) or set(records) & set(approved):
        raise ValueError("Jira candidate accounting is incomplete or overlapping.")
    return saved, approved


def summary(candidates, records, approved):
    states = {key: "collected_complete" for key in records}
    states.update({key: "approved_unavailable" for key in approved})
    if set(states) != set(candidates.issue_key) or set(records) & set(approved):
        raise ValueError("Collection summary does not conserve candidate membership.")
    by_project, by_year = {}, {}
    for row in candidates.itertuples():
        name = project(row.issue_key)
        year = str(row.created)[:4]
        year = year if len(year) == 4 and year.isdigit() else "unknown"
        by_project.setdefault(name, Counter())[states[row.issue_key]] += 1
        by_year.setdefault(year, Counter())[states[row.issue_key]] += 1
    return {"state": "complete_with_approved_missing" if approved else "complete",
            "candidates": len(candidates), "collected_complete": len(records),
            "approved_unavailable": len(approved), "unresolved": 0,
            "by_reason": dict(Counter(approved.values())),
            "by_project": {key: dict(value) for key, value in sorted(by_project.items())},
            "by_candidate_creation_year": {key: dict(value) for key, value in sorted(by_year.items())}}
