"""Revalidate compatible pinned work during an explicit 009/010 migration."""

from collections import Counter, defaultdict
from pathlib import Path

from .common import (
    atomic_bytes, digest, file_hash, immutable_json, read_json, relative, stage_state,
    tree_manifest, verify_tree,
)
from .detectors import (
    NativeAnalysisIncomplete, check_native_messages, detection_key, load_failure,
    load_profile, load_result, parse_reports, register_profile,
)
from .evidence import links
from .prepare import freeze


def copy_verified(source, destination):
    for name, expected in tree_manifest(source).items():
        target = destination / relative(name)
        content = (source / name).read_bytes()
        if target.exists():
            if file_hash(target) != expected:
                raise ValueError(f"Reused artifact changed: {target}")
        else:
            atomic_bytes(target, content)
        if file_hash(target) != expected:
            raise ValueError(f"Reused copy differs: {target}")


def reuse_verified_work(root, sources, portable=False):
    from .migration import (
        BEST_EFFORT_PARENT_SOURCE_SHA256, BOUNDED_EXCLUSIONS_PARENT_SOURCE_SHA256,
        INHERITANCE_PARENT_SOURCE_SHA256,
        MISSING_COMMIT_PARENT_SOURCE_SHA256,
    )

    parent = root / "parent"
    summary = {"migration_sha256": file_hash(root / "migration.json"),
               "frozen_sources": [], "evidence_sources": [], "missing_evidence_sources": [],
               "results": {}, "skipped_results": {}, "resolved_links": 0}
    snapshots, urls = {}, set()
    for source in sources:
        with stage_state(root, "freeze", source, digest({"reuse": file_hash(root / "migration.json"), "source": source})):
            freeze(root, source)
        summary["frozen_sources"].append(source)
        split_path = root / "splits" / f"{source}.json"
        split = read_json(split_path)
        for row in split["rows"]:
            urls.update(links(read_json(root / "raw" / source / (row.split(":", 1)[1] + ".json"))))
        status = parent / "status" / f"fetch-code-{source}.json"
        if not status.exists() or read_json(status)["status"] != "succeeded":
            summary["missing_evidence_sources"].append(source)
            continue
        directory = parent / "evidence" / source
        manifest = read_json(directory / "manifest.json")
        if manifest["split_sha256"] != file_hash(split_path) or set(manifest["records"]) != set(split["assignment"]):
            raise ValueError("Reused evidence does not match frozen membership.")
        counts, shared = Counter(), defaultdict(set)
        for row, expected in manifest["records"].items():
            path = directory / (row.split(":", 1)[1] + ".json")
            if file_hash(path) != expected:
                raise ValueError("Reused evidence hash changed.")
            record = read_json(path)
            if (record["row_id"] != row or record["source"] != source or
                    record["partition"] != split["assignment"][row] or record["status"] not in ("complete", "excluded")):
                raise ValueError("Reused evidence membership changed.")
            counts[record["status"]] += 1
            for item in record["evidence"]:
                identity = (item["repository"], item["revision"], item["snapshot_manifest_sha256"])
                shared[identity[:2]].add(record["partition"])
                if identity not in snapshots:
                    cache = Path(item["snapshot"])
                    if file_hash(cache / "manifest.json") != item["snapshot_manifest_sha256"]:
                        raise ValueError("Reused snapshot manifest changed.")
                    saved = read_json(cache / "manifest.json")
                    if (saved["repository"], saved["revision"]) != identity[:2]:
                        raise ValueError("Reused snapshot identity changed.")
                    verify_tree(cache / "source", saved["files"])
                    snapshots[identity] = item
        audit = read_json(directory / "audit.json")
        overlaps = [{"repository": k[0], "revision": k[1], "partitions": sorted(v)}
                    for k, v in shared.items() if len(v) > 1]
        if audit["counts"] != dict(counts) or sorted(audit["cross_partition_revisions"], key=digest) != sorted(
                overlaps, key=digest):
            raise ValueError("Reused evidence audit differs.")
        with stage_state(root, "fetch-code", source, digest({"reused_manifest": file_hash(directory / "manifest.json")})):
            copy_verified(directory, root / "evidence" / source)
        summary["evidence_sources"].append(source)

    # Unfinished fetches have no final story manifest. Reuse only their atomic
    # link decisions, anchored by the migration inventory, not partial stories.
    resolved = parent / "evidence/resolved"
    for name in tree_manifest(resolved):
        item = read_json(resolved / name)
        if item.get("status") == "resolved":
            url = item["value"]["url"]
        elif item.get("status") == "excluded" and isinstance(item.get("reason"), str) and item["reason"]:
            url = item["url"]
        else:
            raise ValueError("Invalid cached link decision.")
        if url not in urls or name != digest(url) + ".json":
            raise ValueError("Cached link decision does not match frozen story links.")
        summary["resolved_links"] += 1
    copy_verified(resolved, root / "evidence/resolved")

    # Only these predecessor formats share the source attribution and evidence semantics.
    while (parent / "study.json").exists() and read_json(parent / "study.json")["source_sha256"] in (
            BEST_EFFORT_PARENT_SOURCE_SHA256, INHERITANCE_PARENT_SOURCE_SHA256,
            BOUNDED_EXCLUSIONS_PARENT_SOURCE_SHA256, MISSING_COMMIT_PARENT_SOURCE_SHA256):
        for path in sorted((parent / "detection/profiles").glob("*.json")):
            profile = load_profile(path)
            if profile["language"] != "java":
                continue
            for item in snapshots.values():
                key = detection_key(item, profile)
                if key in summary["results"]:
                    continue
                directory = parent / "detection/results" / key
                if not (directory / "result.json").exists() and not (directory / "failure.json").exists():
                    continue
                if (directory / "failure.json").exists():
                    if (directory / "result.json").exists():
                        raise ValueError("Conflicting reusable result and failure.")
                    load_failure(directory, key, profile)
                    copy_verified(directory, root / "detection/results" / key)
                else:
                    value = load_result(directory, key, profile)
                    attempts = [p for p in (directory / "attempts").glob("*/output")
                                if tree_manifest(p) == value["reports"] and
                                (p.parent / "output.out").is_file() and (p.parent / "output.err").is_file()]
                    if not attempts:
                        summary["skipped_results"][key] = "No matching native logs; rerun required."
                        continue
                    try:
                        messages = "\n".join((attempts[0].parent / name).read_text(errors="replace")
                                             for name in ("output.out", "output.err"))
                        check_native_messages(messages, profile, best_effort=True)
                    except NativeAnalysisIncomplete:
                        summary["skipped_results"][key] = "Native logs reveal incomplete analysis; rerun required."
                        continue
                    parsed = parse_reports(directory / "reports", Path(item["snapshot"]) / "source", profile)
                    if (any(parsed.get(name) != value.get(name) for name in ("coverage", "ambiguous_entities")) or
                            sorted(parsed["findings"], key=digest) != sorted(value["findings"], key=digest)):
                        raise ValueError("Reused native reports differ under current attribution.")
                    copy_verified(directory, root / "detection/results" / key)
                register_profile(root, profile)
                if portable:
                    from .streaming import import_legacy
                    import_legacy(root, item, profile, root / "detection/results" / key)
                summary["results"][key] = directory.relative_to(root).as_posix()
                summary["skipped_results"].pop(key, None)
        parent = parent / "parent"
    immutable_json(root / "reuse.json", summary)
