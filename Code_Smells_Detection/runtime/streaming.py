"""Checkpointed story labels with one temporary source revision at a time."""

from collections import Counter, defaultdict
import os
from pathlib import Path
import platform
import tempfile

import pandas as pd

from . import detectors, evidence
from .common import (
    SCHEMA, atomic_bytes, digest, external, file_hash, identifier, immutable_json,
    lock, read_json, require_stage, tree_manifest, verify_original_files,
    verify_study, verify_tree, write_csv, write_json,
)
from .prepare import frozen_frame


PROTOCOL = "sequential-story-smells-v1"
BENIGN = {"pr_not_merged", "commit_not_on_default_history", "no_supported_post_change_files"}


def revision_identity(repository, revision, profile):
    return {"protocol": PROTOCOL, "repository": repository, "revision": revision,
            "profile_sha256": digest(profile)}


def revision_directory(root, repository, revision, profile):
    return root / "streaming/revisions" / digest(revision_identity(repository, revision, profile))


def remember(checked, key, value):
    checked[key] = value
    if len(checked) > 2:
        del checked[next(iter(checked))]
    return value


def report_files(output, profile):
    paths = set()
    for spec in [*profile["coverage"], *profile["reports"].values()]:
        paths.update(output.glob(spec["file"]))
    return sorted(paths)


def save_revision(root, repository, revision, profile, source, snapshot_path, output, outcome):
    identity = revision_identity(repository, revision, profile)
    directory = revision_directory(root, repository, revision, profile)
    snapshot = read_json(snapshot_path)
    if (snapshot.get("repository"), snapshot.get("revision")) != (repository, revision):
        raise ValueError("Snapshot identity differs from requested revision.")
    verify_original_files(source, snapshot["files"])
    index = {}
    if outcome["status"] == "analyzed" or outcome.get("reasons") == ["report_attribution"]:
        index = {name: sorted(paths) for name, paths in detectors.source_index(source, profile["language"]).items()}
    artifacts = {
        "snapshot.json": snapshot_path.read_bytes(),
        "index.json": None,
    }
    for path in report_files(output, profile):
        artifacts["reports/" + path.relative_to(output).as_posix()] = path.read_bytes()
    for suffix in ("out", "err"):
        artifacts["native." + suffix] = (output.parent / (output.name + "." + suffix)).read_bytes()
    for name, content in artifacts.items():
        target = directory / "audit" / name
        if content is None:
            write_json(target, index)
        else:
            atomic_bytes(target, content)
    value = {"identity": identity, "source_root": source.as_posix(), **outcome,
             "snapshot_manifest_sha256": file_hash(snapshot_path),
             "artifacts": tree_manifest(directory / "audit")}
    # Validate portable attribution and logs before publishing the commit marker.
    validate_revision(directory, profile, value)
    immutable_json(directory / "result.json", value)
    return value


def validate_revision(directory, profile, value):
    audit = directory / "audit"
    verify_tree(audit, value["artifacts"])
    identity = value["identity"]
    if (identity["protocol"] != PROTOCOL or identity["profile_sha256"] != digest(profile) or
            directory.name != digest(identity)):
        raise ValueError("Portable result identity changed.")
    snapshot = read_json(audit / "snapshot.json")
    if (file_hash(audit / "snapshot.json") != value["snapshot_manifest_sha256"] or
            (snapshot["repository"], snapshot["revision"]) != (identity["repository"], identity["revision"])):
        raise ValueError("Portable snapshot provenance changed.")
    index = read_json(audit / "index.json")
    snapshot_files = set(snapshot["files"])
    for names in index.values():
        if not isinstance(names, list) or not names or not set(names) <= snapshot_files:
            raise ValueError("Attribution index names files outside the source manifest.")
    messages = "\n".join((audit / ("native." + suffix)).read_text(errors="replace") for suffix in ("out", "err"))
    try:
        detectors.check_native_messages(messages, profile, best_effort=True)
    except detectors.NativeAnalysisIncomplete as error:
        if (value["status"] == "incomplete" and value.get("reasons") == error.reasons and
                not value.get("coverage") and not value.get("findings")):
            return value
        raise ValueError("Portable native failure differs from preserved logs.")
    try:
        parsed = detectors.parse_indexed_reports(
            audit / "reports", Path(value["source_root"]), profile,
            {name: set(paths) for name, paths in index.items()})
    except detectors.ReportAttributionIncomplete:
        if (value["status"] == "incomplete" and value.get("reasons") == ["report_attribution"] and
                not value.get("coverage") and not value.get("findings")):
            return value
        raise ValueError("Portable attribution failure differs from preserved reports.")
    if (value["status"] != "analyzed" or value.get("reasons") or
            parsed["coverage"] != value.get("coverage") or
            sorted(parsed["findings"], key=digest) != sorted(value.get("findings", []), key=digest) or
            parsed.get("ambiguous_entities") != value.get("ambiguous_entities")):
        raise ValueError("Portable findings differ from preserved reports.")
    return value


def load_revision(root, repository, revision, profile):
    directory = revision_directory(root, repository, revision, profile)
    value = read_json(directory / "result.json")
    if value["identity"] != revision_identity(repository, revision, profile):
        raise ValueError("Portable result belongs to another revision/profile.")
    return validate_revision(directory, profile, value)


def import_legacy(root, item, profile, legacy):
    directory = revision_directory(root, item["repository"], item["revision"], profile)
    if (directory / "result.json").exists():
        return load_revision(root, item["repository"], item["revision"], profile)
    cache = Path(item["snapshot"])
    if file_hash(cache / "manifest.json") != item["snapshot_manifest_sha256"]:
        raise ValueError("Legacy snapshot manifest changed.")
    verify_tree(cache / "source", read_json(cache / "manifest.json")["files"])
    if (legacy / "failure.json").exists():
        value = detectors.load_failure(legacy, detectors.detection_key(item, profile), profile)
        output = legacy / value["attempt"] / "output"
        outcome = {"status": "incomplete", "reasons": value["reasons"], "coverage": [], "findings": []}
    else:
        value = detectors.load_result(legacy, detectors.detection_key(item, profile), profile)
        attempts = [p for p in (legacy / "attempts").glob("*/output")
                    if tree_manifest(p) == value["reports"] and
                    p.with_suffix(".out").is_file() and p.with_suffix(".err").is_file()]
        if not attempts:
            raise ValueError("Portable import requires matching native logs.")
        output = attempts[0]
        outcome = {"status": "analyzed", "coverage": value["coverage"], "findings": value["findings"]}
        if value.get("ambiguous_entities"):
            outcome["ambiguous_entities"] = value["ambiguous_entities"]
    return save_revision(root, item["repository"], item["revision"], profile,
                         cache / "source", cache / "manifest.json", output, outcome)


def initialize(root, parent):
    from .migration import migrate
    with lock(root / "streaming/process.lock"):
        if (root / "streaming/mode.json").exists():
            check_mode(root)
            if read_json(root / "migration.json")["parent"] != str(external(parent)):
                raise ValueError("Sequential study belongs to a different parent.")
            return
        migrate(root, parent, reuse_verified=True, portable=True)
        immutable_json(root / "streaming/mode.json",
                       {"protocol": PROTOCOL, "study_sha256": file_hash(root / "study.json")})


def check_mode(root):
    study = verify_study(root)
    if read_json(root / "streaming/mode.json") != {
            "protocol": PROTOCOL, "study_sha256": file_hash(root / "study.json")}:
        raise ValueError("Sequential study binding changed.")
    return study


def registered_profiles(root):
    return {p.stem: detectors.load_profile(p) for p in sorted((root / "detection/profiles").glob("*.json"))}


def catalog_for(profiles):
    catalog = {"any_supported_smell": {"language": None, "category": "any", "smell": "any"}}
    for language, profile in sorted(profiles.items()):
        for category, names in sorted(profile["catalog"].items()):
            for smell in names:
                catalog[language + "." + category + "." + digest(smell)[:16]] = {
                    "language": language, "category": category, "smell": smell}
    return catalog


def label_values(record, catalog):
    if record["status"] != "complete":
        return {key: None for key in catalog}
    found = {tuple(item) for item in record["smells"]}
    return {key: (int(bool(found)) if item["language"] is None else
                  None if item["language"] not in record["languages"] else
                  int((item["language"], item["category"], item["smell"]) in found))
            for key, item in catalog.items()}


def export_progress(root, source, rows, catalog):
    output = [{**{key: row[key] for key in ("row_id", "source", "partition", "status")},
               "reason": "; ".join(row["reasons"]), **label_values(row, catalog)} for row in rows.values()]
    columns = ["row_id", "source", "partition", "status", "reason", *catalog]
    write_csv(root / "streaming" / (source + ".csv"), pd.DataFrame(output, columns=columns))
    write_json(root / "streaming/catalog.json", catalog)
    shared = defaultdict(set)
    for row in rows.values():
        for repository, revision in row["revisions"]:
            shared[repository, revision].add(row["partition"])
    write_json(root / "streaming" / (source + "-progress.json"),
               {"processed": len(output), "counts": dict(Counter(row["status"] for row in output)),
                "cross_partition_revisions": [
                    {"repository": repository, "revision": revision, "partitions": sorted(partitions)}
                    for (repository, revision), partitions in sorted(shared.items()) if len(partitions) > 1],
                "interpretation": "Retrospective linked-code labels; label availability may postdate story splits."})


def load_story(root, source, row_id, split, raw_hash, profiles, checked):
    name = identifier(row_id.split(":", 1)[1]) + ".json"
    if file_hash(root / "raw" / source / name) != raw_hash:
        raise ValueError("Frozen Jira record changed.")
    path = root / "streaming/stories" / source / name
    if not path.exists():
        return None
    envelope = read_json(path)
    value = envelope["value"]
    if (digest(value) != envelope["sha256"] or value["row_id"] != row_id or value["source"] != source or
            value["partition"] != split["assignment"][row_id] or value["raw_sha256"] != raw_hash or
            value["split_sha256"] != file_hash(root / "splits" / (source + ".json")) or
            value["status"] not in ("complete", "excluded", "pending")):
        raise ValueError("Story checkpoint identity/integrity changed.")
    for key, expected in value["metadata"].items():
        if file_hash(root / "evidence/resolved" / (key + ".json")) != expected:
            raise ValueError("Checkpoint link evidence changed.")
    if value.get("prior_evidence"):
        _, binding = prior_evidence(root, source, row_id, split)
        if binding != value["prior_evidence"]:
            raise ValueError("Checkpoint inherited evidence changed.")
    for key, expected in value["analyses"].items():
        directory = root / "streaming/revisions" / identifier(key)
        if file_hash(directory / "result.json") != expected:
            raise ValueError("Checkpoint analysis changed.")
        if key not in checked:
            result = read_json(directory / "result.json")
            profile = next((p for p in profiles.values() if digest(p) == result["identity"]["profile_sha256"]), None)
            if profile is None:
                raise ValueError("Checkpoint profile is unavailable.")
            remember(checked, key, validate_revision(directory, profile, result))
    return value


def resolve(root, url, github):
    path = root / "evidence/resolved" / (digest(url) + ".json")
    if not path.exists():
        try:
            item = {"status": "resolved", "value": github.resolve(url)}
        except evidence.EvidenceExcluded as error:
            item = {"status": "excluded", "url": url, "reason": str(error)}
        immutable_json(path, item)
    item = read_json(path)
    if ((item.get("status") == "resolved" and item["value"]["url"] != url) or
            (item.get("status") == "excluded" and item["url"] != url) or
            item.get("status") not in ("resolved", "excluded")):
        raise ValueError("Link cache identity changed.")
    return item, file_hash(path)


def prior_evidence(root, source, row_id, split):
    directory = root / "evidence" / source
    manifest_path = directory / "manifest.json"
    if not manifest_path.exists():
        return None, None
    require_stage(root, "fetch-code", source)
    manifest = read_json(manifest_path)
    if (manifest["split_sha256"] != file_hash(root / "splits" / (source + ".json")) or
            set(manifest["records"]) != set(split["assignment"])):
        raise ValueError("Inherited evidence belongs to another frozen cohort.")
    path = directory / (identifier(row_id.split(":", 1)[1]) + ".json")
    if file_hash(path) != manifest["records"][row_id]:
        raise ValueError("Inherited evidence record changed.")
    value = read_json(path)
    if (value["row_id"] != row_id or value["source"] != source or
            value["partition"] != split["assignment"][row_id] or value["status"] not in ("complete", "excluded")):
        raise ValueError("Inherited evidence identity changed.")
    return value, {"manifest_sha256": file_hash(manifest_path), "record_sha256": file_hash(path)}


def analyze(root, scratch, info, profiles, tools, checked, snapshot_loader):
    repository, revision = info["repository"], info["revision"]
    required_languages = {f["language"] for f in info["files"]}
    missing, results = [], {}
    for language in sorted(required_languages & profiles.keys()):
        profile = profiles[language]
        key = digest(revision_identity(repository, revision, profile))
        directory = revision_directory(root, repository, revision, profile)
        if (directory / "result.json").exists():
            if key not in checked:
                remember(checked, key, load_revision(root, repository, revision, profile))
            results[language] = checked[key]
        elif language in tools:
            missing.append(language)
    if not missing:
        return results
    # This directory is created by this invocation and contains just one revision.
    # Never clean up caller-owned caches, scratch roots or previous run directories.
    with tempfile.TemporaryDirectory(prefix="story-revision-", dir=scratch) as temporary:
        temporary = Path(temporary)
        print(f"Fetching {repository}@{revision} into worker scratch", flush=True)
        cache, snapshot = snapshot_loader(temporary, repository, revision)
        source = cache / "source"
        if not source.resolve().is_relative_to(temporary.resolve()):
            raise ValueError("Sequential snapshot loader escaped its temporary workspace.")
        verify_tree(source, snapshot["files"])
        for language in missing:
            profile = profiles[language]
            key = digest(revision_identity(repository, revision, profile))
            output = temporary / language / "output"
            output.parent.mkdir(parents=True)
            try:
                outcome = {"status": "analyzed", **detectors.execute(tools[language], profile, source, output,
                                                                  best_effort=True)}
            except (detectors.NativeAnalysisIncomplete, detectors.ReportAttributionIncomplete) as error:
                outcome = {"status": "incomplete", "coverage": [], "findings": [],
                           "reasons": (error.reasons if isinstance(error, detectors.NativeAnalysisIncomplete)
                                       else ["report_attribution"])}
            except Exception:
                for suffix in ("out", "err"):
                    log = output.parent / ("output." + suffix)
                    if log.exists():
                        atomic_bytes(root / "streaming/errors" / (key + "." + suffix), log.read_bytes())
                raise
            results[language] = remember(checked, key, save_revision(
                root, repository, revision, profile, source, cache / "manifest.json", output, outcome))
    return results


def process_story(root, source, row, split, raw_hash, profiles, tools, scratch, github, checked,
                  snapshot_loader):
    raw_path = root / "raw" / source / (row.issue_key + ".json")
    if file_hash(raw_path) != raw_hash:
        raise ValueError("Frozen Jira record changed.")
    value = {"row_id": row.row_id, "source": source, "partition": split["assignment"][row.row_id],
             "raw_sha256": raw_hash, "split_sha256": file_hash(root / "splits" / (source + ".json")),
             "metadata": {}, "analyses": {}, "languages": [], "smells": [], "reasons": [], "revisions": []}
    revisions, exclusions = {}, []
    prior, binding = prior_evidence(root, source, row.row_id, split)
    if prior is not None:
        value["prior_evidence"] = binding
        if prior["status"] == "excluded":
            return {**value, "status": "excluded", "reasons": [prior["reason"]],
                    "revisions": [list(identity) for identity in sorted(
                        {(item["repository"], item["revision"]) for item in prior["evidence"]})]}
        resolved = prior["evidence"]
        exclusions = [item["reason"] for item in prior["exclusions"]]
    else:
        resolved = []
        for url in evidence.links(read_json(raw_path)):
            item, checksum = resolve(root, url, github)
            value["metadata"][digest(url)] = checksum
            if item["status"] == "excluded":
                exclusions.append(item["reason"])
            else:
                resolved.append(item["value"])
    for info in resolved:
        files = [f for f in info["files"] if f["language"] and f["status"] != "removed"]
        if not files:
            exclusions.append("no_supported_post_change_files")
            continue
        identity = (info["repository"], info["revision"])
        revisions.setdefault(identity, {**info, "files": []})["files"].extend(files)
    value["revisions"] = [list(identity) for identity in sorted(revisions)]
    if not revisions or any(reason not in BENIGN for reason in exclusions):
        return {**value, "status": "excluded", "reasons": sorted(set(exclusions or ["no_supported_code_evidence"]))}
    languages = {f["language"] for info in revisions.values() for f in info["files"]}
    value["languages"] = sorted(languages)
    pending = set()
    smells, failures = set(), []
    for info in revisions.values():
        try:
            results = analyze(root, scratch, info, profiles, tools, checked, snapshot_loader)
        except evidence.EvidenceExcluded as error:
            failures.append(str(error))
            continue
        pending.update({f["language"] for f in info["files"]} - results.keys())
        for language, result in results.items():
            key = digest(result["identity"])
            directory = root / "streaming/revisions" / key
            value["analyses"][key] = file_hash(directory / "result.json")
            required = {f["path"] for f in info["files"] if f["language"] == language}
            snapshot = read_json(directory / "audit/snapshot.json")
            if not required <= set(snapshot["files"]):
                failures.append(language + ":changed_file_missing_from_snapshot")
            elif result["status"] == "incomplete":
                failures.extend(language + ":" + reason for reason in result["reasons"])
            elif not required <= set(result["coverage"]):
                failures.append(language + ":uncovered_changed_files")
            else:
                smells.update((language, f["category"], f["smell"]) for f in result["findings"] if f["path"] in required)
    value.update(status="excluded" if failures else "pending" if pending else "complete",
                 reasons=sorted(set(failures or ["unconfigured_language:" + name for name in pending])),
                 smells=[list(item) for item in sorted(smells)] if not failures and not pending else [])
    return value


def process(root, storage, source, profile_paths, scratch=None, github=None, snapshot_loader=evidence.snapshot):
    with lock(root / "streaming/process.lock", wait=True):
        check_mode(root)
        if (root / "labels/manifest.json").exists():
            raise ValueError("Final labels already sealed; use a new study for further processing.")
        selected, tools = {}, {}
        for path in profile_paths:
            profile = detectors.load_profile(path)
            language = profile["language"]
            if language in selected or profile["platform"] != platform.system():
                raise ValueError("Select one compatible worker profile per language.")
            tools[language] = detectors.qualified(storage, profile)
            selected[language] = profile
            detectors.register_profile(root, profile)
        location = scratch or os.environ.get("SLURM_SCRATCH_DIR")
        if not location:
            raise ValueError("Worker scratch is required; use --scratch or SLURM_SCRATCH_DIR.")
        scratch = external(location)
        if (not scratch.is_dir() or scratch == Path.home() or Path.home() in scratch.parents or
                scratch == external(storage) or external(storage) in scratch.parents or scratch in external(storage).parents):
            raise ValueError("Scratch must be outside home, repository and persistent study storage.")
        frame, split = frozen_frame(root, source)
        raw = read_json(root / "raw" / source / "manifest.json")["records"]
        profiles, checked, rows = registered_profiles(root), {}, {}
        catalog = catalog_for(profiles)
        for row in frame.itertuples():
            previous = load_story(root, source, row.row_id, split, raw[row.issue_key], profiles, checked)
            if previous:
                rows[row.row_id] = previous
        export_progress(root, source, rows, catalog)
        github = github or evidence.GitHub()
        for position, row in enumerate(frame.itertuples(), 1):
            previous = rows.get(row.row_id)
            if previous and previous["status"] != "pending":
                continue
            print(f"[{source} {position}/{len(frame)}] {row.issue_key}: processing", flush=True)
            value = process_story(root, source, row, split, raw[row.issue_key], profiles, tools,
                                  scratch, github, checked, snapshot_loader)
            path = root / "streaming/stories" / source / (identifier(row.issue_key) + ".json")
            write_json(path, {"sha256": digest(value), "value": value})
            rows[row.row_id] = value
            export_progress(root, source, rows, catalog)
            print(f"[{source} {position}/{len(frame)}] {row.issue_key}: {value['status']}; "
                  f"checkpoint and CSV saved; temporary source removed", flush=True)
        write_json(root / "streaming" / (source + "-scan.json"),
                   {"scan_complete": True, "split_sha256": file_hash(root / "splits" / (source + ".json")),
                    "counts": dict(Counter(row["status"] for row in rows.values())),
                    "rows": {row: digest(value) for row, value in rows.items()}})


def finalize(root):
    with lock(root / "streaming/process.lock", wait=True):
        study = check_mode(root)
        profiles = registered_profiles(root)
        catalog = catalog_for(profiles)
        labels, statuses, exclusions, checked = [], [], {}, {}
        for source in study["sources"]:
            frame, split = frozen_frame(root, source)
            raw = read_json(root / "raw" / source / "manifest.json")["records"]
            for row in frame.itertuples():
                value = load_story(root, source, row.row_id, split, raw[row.issue_key], profiles, checked)
                if value is None or value["status"] == "pending":
                    raise ValueError(f"Unfinished story or detector prerequisites: {row.row_id}")
                if value["status"] == "complete":
                    labels.append({"row_id": row.row_id, "source": source, "partition": value["partition"],
                                   **label_values(value, catalog)})
                    statuses.append({"row_id": row.row_id, "status": "complete", "languages": value["languages"]})
                else:
                    exclusions[row.row_id] = "; ".join(value["reasons"])
                    statuses.append({"row_id": row.row_id, "status": "excluded", "reason": exclusions[row.row_id]})
        coverage = {"rows": statuses, "status_counts": dict(Counter(row["status"] for row in statuses)),
                    "source_labeled_counts": dict(Counter(row["source"] for row in labels))}
        write_json(root / "streaming/final-coverage.json", coverage)
        if not labels:
            raise ValueError("No completely labeled stories; coverage is recorded without fabricated negatives.")
        frame = pd.DataFrame(labels)
        destination = root / "labels/story_labels.csv"
        content = frame.to_csv(index=False).encode()
        if destination.exists() and destination.read_bytes() != content:
            raise ValueError("Final labels are immutable.")
        atomic_bytes(destination, content)
        immutable_json(root / "labels/catalog.json", catalog)
        immutable_json(root / "labels/coverage.json", coverage)
        immutable_json(root / "labels/exclusions.json", exclusions)
        immutable_json(root / "labels/manifest.json", {
            "schema": SCHEMA, "protocol": PROTOCOL, "labels_sha256": file_hash(destination),
            "catalog_sha256": digest(catalog), "coverage_sha256": digest(coverage),
            "exclusions_sha256": digest(exclusions),
            "profiles": {name: digest(value) for name, value in profiles.items()}, "exclusion_policies": {},
            "source_counts": coverage["source_labeled_counts"], "min_source_rows": study["min_rows"],
            "splits": {name: file_hash(root / "splits" / (name + ".json")) for name in study["sources"]},
        })
