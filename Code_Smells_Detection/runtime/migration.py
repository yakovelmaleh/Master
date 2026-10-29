"""Import supported, pinned preparation formats without changing their runs."""

import hashlib

import pandas as pd

from . import collection
from .common import (
    PARTITIONS, SCHEMA, atomic_bytes, digest, external, file_hash, identifier,
    immutable_json, read_json, relative as safe_relative, source_hash, stage_state, tree_manifest,
)
from .prepare import audit, source_candidates


PARENT_SOURCE_SHA256 = "67c6b55de71534f36736c3756b8ab895eb83638b7ed4a7baf6ad2adaec5f2e07"
FROZEN_PARENT_SOURCE_SHA256 = "c0005a0d6467c4e053ccceb7d8b27b910d2131eed863650d660a1fc6153c1fb7"
RECOVERY_PARENT_SOURCE_SHA256 = "a8776a676eea4425b8f8332e2cecca3def8bf38afd53b1fd0f0fa84e9594d335"


def inventory(parent):
    study = read_json(parent / "study.json")
    frozen_import = study["source_sha256"] in (FROZEN_PARENT_SOURCE_SHA256, RECOVERY_PARENT_SOURCE_SHA256)
    if study["schema"] != SCHEMA or study["source_sha256"] not in (
            PARENT_SOURCE_SHA256, FROZEN_PARENT_SOURCE_SHA256, RECOVERY_PARENT_SOURCE_SHA256):
        raise ValueError("Unsupported parent code/schema; migration requires the pinned preparation implementation.")
    if study.get("prior") or study.get("migration_sha256") and not frozen_import:
        raise ValueError("This migration supports original runs without prior imports only.")
    forbidden = ("detection", "labels", "models", "reports") + (() if frozen_import else ("evidence",))
    if any((parent / name).exists() for name in forbidden):
        raise ValueError("Only preparation-only runs can be migrated by this operation.")
    if set(study["inputs"]) != {"candidates.csv", "sources.csv"}:
        raise ValueError("Unsupported parent cohort inputs.")
    files = {}

    def add(relative, destination=None):
        path = parent / relative
        if any(part.is_symlink() for part in (path, *path.parents) if part != parent and parent in part.parents):
            raise ValueError(f"Symlink in parent artifacts: {relative}")
        if not path.is_file():
            raise ValueError(f"Missing parent artifact: {relative}")
        files[destination or relative] = {"path": relative, "sha256": file_hash(path)}

    add("study.json", "parent/study.json")
    if frozen_import and study.get("migration_sha256"):
        add("migration.json", "parent/migration.json")
        add("migration_complete.json", "parent/migration_complete.json")
        previous = read_json(parent / "migration.json")
        expected_schema = ("code-smell-frozen-import-v1" if study["source_sha256"] == RECOVERY_PARENT_SOURCE_SHA256
                           else "code-smell-preparation-import-v1")
        if (file_hash(parent / "migration.json") != study["migration_sha256"] or
                read_json(parent / "migration_complete.json") != {"migration_sha256": study["migration_sha256"]} or
                previous.get("schema") != expected_schema or
                previous.get("source_sha256") != study["source_sha256"] or
                previous.get("parent_study_sha256") != file_hash(parent / "parent/study.json")):
            raise ValueError("Parent migration is incomplete or its provenance changed.")
        for name, entry in previous["files"].items():
            path = parent / safe_relative(name)
            if path.is_symlink() or file_hash(path) != entry["sha256"]:
                raise ValueError(f"Parent imported artifact changed: {name}")
        for name in tree_manifest(parent / "parent"):
            add("parent/" + name, "parent/parent/" + name)
    if frozen_import and (parent / "evidence").exists():
        for name in tree_manifest(parent / "evidence"):
            if name.endswith(".json"):
                add("evidence/" + name, "parent/evidence/" + name)
            elif not name.endswith(".lock"):
                raise ValueError(f"Unexpected parent evidence artifact: {name}")
    for name, expected in study["inputs"].items():
        add("cohort/" + name)
        if files["cohort/" + name]["sha256"] != expected:
            raise ValueError(f"Parent input changed: {name}")
    for path in sorted((parent / "status").glob("*.json")):
        if read_json(path).get("status") == "running":
            raise ValueError("Parent has a running stage; stop/wait before migration.")
        add(path.relative_to(parent).as_posix(), "parent/status/" + path.name)
    candidates = pd.read_csv(parent / "cohort/candidates.csv", keep_default_na=False)
    if candidates.duplicated(["source", "issue_key"]).any():
        raise ValueError("Duplicate parent candidate IDs.")
    sources = {}
    for source in study["sources"]:
        identifier(source)
        keys = set(candidates.loc[candidates.source == source, "issue_key"])
        for key in keys:
            identifier(key)
        raw = parent / "raw" / source
        allowed = {key + ".json" for key in keys} | {"manifest.json", "field_map.json", "collection_errors.json",
                                                   ".collection.lock"}
        if frozen_import:
            allowed |= {"collection_diagnostics.json", "collection_exclusions.json", "missing_records.proposed.json"}
        if raw.exists() and any(path.name not in allowed or not path.is_file() for path in raw.iterdir()):
            raise ValueError(f"Unexpected parent raw artifacts: {source}")
        records = {}
        for key in sorted(keys):
            path = raw / f"{key}.json"
            if path.exists():
                relative = path.relative_to(parent).as_posix()
                add(relative)
                collection.valid_record(read_json(path), key)
                records[key] = files[relative]["sha256"]
        if (raw / "field_map.json").exists():
            add(f"raw/{source}/field_map.json")
            if not isinstance(read_json(raw / "field_map.json"), dict):
                raise ValueError("Invalid parent field map.")
        elif records:
            raise ValueError(f"Parent cached records have no field map: {source}")
        if (raw / "collection_errors.json").exists():
            add(f"raw/{source}/collection_errors.json", f"parent/errors/{source}.json")
        if frozen_import:
            for name in ("collection_diagnostics.json", "collection_exclusions.json", "missing_records.proposed.json"):
                if (raw / name).exists():
                    add(f"raw/{source}/{name}")
        complete = (raw / "manifest.json").exists()
        approved = {}
        if complete:
            add(f"raw/{source}/manifest.json")
            saved = read_json(raw / "manifest.json")
            if frozen_import:
                saved, approved = collection.load_manifest(parent, source, keys)
                consistent = saved["records"] == records
            else:
                consistent = saved == {"records": records, "field_map": file_hash(raw / "field_map.json")} and set(records) == keys
            if not consistent:
                raise ValueError(f"Parent raw manifest differs from cached bytes or cohort: {source}")
            if read_json(parent / "status" / f"enrich-{source}.json").get("status") != "succeeded":
                raise ValueError(f"Parent complete collection has no successful status: {source}")
        split_path = parent / "splits" / f"{source}.json"
        frozen = split_path.exists()
        if frozen_import and (not complete or not frozen):
            raise ValueError(f"Frozen-run migration requires every source to be finalized and frozen: {source}")
        if frozen:
            if not complete or read_json(parent / "status" / f"freeze-{source}.json").get("status") != "succeeded":
                raise ValueError(f"Parent frozen source has incomplete preparation: {source}")
            split = read_json(split_path)
            feature_path = parent / "features" / source / "features.csv"
            frame = pd.read_csv(feature_path, keep_default_na=False)
            if (split["feature_sha256"] != file_hash(feature_path) or
                    split["raw_manifest_sha256"] != file_hash(raw / "manifest.json") or
                    split["rows"] != frame.row_id.tolist() or frame.row_id.duplicated().any() or
                    set(split["assignment"]) != set(frame.row_id) or
                    not set(split["assignment"].values()) <= set(PARTITIONS) or
                    not set(frame.issue_key) <= keys or not (frame.source == source).all() or
                    frame.row_id.tolist() != (source + ":" + frame.issue_key).tolist()):
                raise ValueError(f"Parent frozen feature/split provenance differs: {source}")
            for relative in (f"features/{source}/features.csv", f"features/{source}/filter_decisions.json",
                             f"splits/{source}.json", *(f"splits/{source}/{name}_rows.csv" for name in PARTITIONS)):
                add(relative)
            decisions = read_json(parent / "features" / source / "filter_decisions.json")
            if (len(decisions) != len(keys) or
                    {item["row_id"] for item in decisions} != {f"{source}:{key}" for key in keys}):
                raise ValueError(f"Parent preprocessing decisions do not conserve candidate IDs: {source}")
            if frozen_import:
                unavailable = {item["row_id"]: item.get("collection_reason") for item in decisions
                               if item["reason"] == "jira_unavailable"}
                accepted = {item["row_id"] for item in decisions if item["reason"] == "accepted"}
                if (unavailable != {f"{source}:{key}": reason for key, reason in approved.items()} or
                        accepted != set(frame.row_id) or set(frame.issue_key) - set(records) or
                        approved and split.get("filter_decisions_sha256") !=
                        file_hash(parent / f"features/{source}/filter_decisions.json")):
                    raise ValueError(f"Parent frozen eligibility differs from reviewed collection: {source}")
            for name in PARTITIONS:
                saved_rows = pd.read_csv(parent / "splits" / source / f"{name}_rows.csv", keep_default_na=False)
                expected = frame.loc[frame.row_id.map(split["assignment"]) == name, ["row_id", "source", "issue_key"]]
                if (not saved_rows.reset_index(drop=True).equals(expected.reset_index(drop=True)) or
                        split["counts"][name] != len(expected)):
                    raise ValueError(f"Parent partition membership differs: {source}/{name}")
        elif (parent / "features" / source).exists() or (parent / "splits" / source).exists():
            raise ValueError(f"Partial frozen artifacts require investigation before migration: {source}")
        sources[source] = {"complete": complete, "frozen": frozen, "cached_records": len(records),
                           "candidate_count": len(keys),
                           "hash_origin": "parent_manifest" if complete else "migration_snapshot"}
        if frozen_import:
            sources[source]["approved_unavailable"] = len(approved)
    return study, files, sources


def migrate(root, parent):
    root, parent = external(root), external(parent)
    if root == parent or root in parent.parents or parent in root.parents:
        raise ValueError("Migration must use distinct, non-nested run directories.")
    if root.exists() and any(path.name not in ("status", "migration.json", "migration_complete.json", "study.json",
                                              "cohort", "raw", "features", "splits", "parent")
                             for path in root.iterdir()):
        raise ValueError("Migration destination is not a preparation-only run.")
    old, files, sources = inventory(parent)
    frozen_import = old["source_sha256"] in (FROZEN_PARENT_SOURCE_SHA256, RECOVERY_PARENT_SOURCE_SHA256)
    migration = {"schema": "code-smell-frozen-import-v1" if frozen_import else "code-smell-preparation-import-v1",
                 "parent": str(parent),
                 "parent_study_sha256": file_hash(parent / "study.json"),
                 "source_sha256": source_hash(), "files": files, "sources": sources}
    if (root / "study.json").exists() and not (root / "migration.json").exists():
        raise ValueError("Do not migrate into an existing independent study.")
    immutable_json(root / "migration.json", migration)
    audit(root, parent / "cohort/candidates.csv", parent / "cohort/sources.csv",
          migration_sha256=file_hash(root / "migration.json"))
    new = read_json(root / "study.json")
    if any(new[name] != old[name] for name in ("inputs", "sources", "min_rows", "prior")):
        raise ValueError("Parent cohort configuration differs from the audited study.")
    for destination, entry in files.items():
        content = (parent / entry["path"]).read_bytes()
        if hashlib.sha256(content).hexdigest() != entry["sha256"]:
            raise ValueError("Parent changed during migration.")
        path = root / destination
        if path.is_symlink() or any(part.is_symlink() for part in path.parents if root in part.parents):
            raise ValueError(f"Symlink in migration destination: {destination}")
        if path.exists():
            if file_hash(path) != entry["sha256"]:
                raise ValueError(f"Migration destination changed: {destination}")
        else:
            atomic_bytes(path, content)
        if file_hash(path) != entry["sha256"]:
            raise ValueError(f"Migration copy verification failed: {destination}")
    _, after, after_sources = inventory(parent)
    if after != files or after_sources != sources:
        raise ValueError("Parent inventory changed during migration.")
    immutable_json(root / "migration_complete.json", {"migration_sha256": file_hash(root / "migration.json")})
    for source, state in sources.items():
        if state["complete"]:
            with stage_state(root, "enrich", source, digest({"migration": migration["parent_study_sha256"], "source": source})):
                collection.load_manifest(root, source, set(source_candidates(root, source).issue_key))
    if frozen_import:
        print("Imported frozen preparation and original collection approvals byte-for-byte. "
              "Run freeze to revalidate every source before fetch-code. Parent evidence is archived only; "
              "re-resolve links under the new code, reusing verified shared snapshots.", flush=True)
    else:
        print("Imported verified preparation caches. Run freeze to revalidate imported feature/split parity; "
              "diagnose incomplete sources before approving exclusions.", flush=True)
