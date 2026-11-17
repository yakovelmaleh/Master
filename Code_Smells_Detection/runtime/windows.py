"""Checksummed C# work exchange with a user-owned isolated Windows worker."""

import argparse
from pathlib import Path
import shutil
import tempfile
import uuid

from .common import (
    digest, file_hash, immutable_json, lock, read_json, relative, source_relative,
    tree_manifest, verify_original_files, verify_tree,
    write_json,
)
from .detectors import (
    detection_key, evidence_records, execute, install_profile, load_profile,
    qualified, qualify, register_profile,
    exclusion_policy, bounded_exclusions, load_result,
    ReportAttributionIncomplete,
)


def export_work(root, source, profile_path, destination, exclude_incomplete=False):
    profile = load_profile(profile_path)
    if profile["language"] != "csharp" or profile["platform"] != "Windows":
        raise ValueError("Windows exchange requires the C# Windows profile.")
    if exclude_incomplete:
        policy = exclusion_policy(root, source, -1)
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=False)
    jobs = {}
    for record in evidence_records(root, source):
        if record["status"] != "complete":
            continue
        for evidence in record["evidence"]:
            required = sorted(item["path"] for item in evidence["files"] if item["language"] == "csharp")
            if not required:
                continue
            key = detection_key(evidence, profile)
            if key in jobs:
                jobs[key]["required"] = sorted(set(jobs[key]["required"]) | set(required))
                continue
            cache = Path(evidence["snapshot"])
            if file_hash(cache / "manifest.json") != evidence["snapshot_manifest_sha256"]:
                raise ValueError("Snapshot manifest changed.")
            files = read_json(cache / "manifest.json")["files"]
            for name in files:
                source_relative(name, windows=True)
            verify_tree(cache / "source", files)
            shutil.copytree(cache / "source", destination / "snapshots" / key)
            jobs[key] = {"required": required, "files": files}
    if not jobs:
        raise ValueError("No complete C# evidence for this source.")
    work = {"schema": "code-smell-windows-work-v1", "profile": profile, "jobs": jobs}
    if exclude_incomplete:
        work.update(exclude_incomplete=True, source=source, policy_sha256=digest(policy))
    immutable_json(destination / "work.json", work)
    register_profile(root, profile)
    immutable_json(root / "detection/windows" / (digest(work) + ".json"), work)


def run_work(bundle, storage):
    bundle = Path(bundle).resolve()
    with lock(bundle / "worker.lock"):
        return run_locked_work(bundle, storage)


def run_locked_work(bundle, storage):
    work = read_json(bundle / "work.json")
    profile = work["profile"]
    tool = qualified(storage, profile)
    results = {}
    for key, job in work["jobs"].items():
        for name in job["files"]:
            source_relative(name, windows=True)
        source = bundle / "snapshots" / key
        verify_tree(source, job["files"])
        destination = bundle / "results" / key
        if (destination / "result.json").exists():
            existing = read_json(destination / "result.json")
            verify_tree(destination / "reports", existing["reports"])
            results[key] = file_hash(destination / "result.json")
            continue
        destination.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="worker-", dir=destination) as scratch:
            copied = Path(scratch) / "source"
            shutil.copytree(source, copied)
            output = destination / "attempts" / uuid.uuid4().hex / "output"
            try:
                result = execute(tool, profile, copied, output)
            except ReportAttributionIncomplete:
                if not work.get("exclude_incomplete"):
                    raise
                result = {"coverage": [], "findings": [], "incomplete_reason": "report_attribution"}
            verify_original_files(copied, job["files"])
            if not work.get("exclude_incomplete") and not set(job["required"]) <= set(result["coverage"]):
                raise ValueError("C# changed-file coverage is incomplete.")
            if (destination / "reports").exists():
                verify_tree(destination / "reports", tree_manifest(output))
            else:
                shutil.copytree(output, destination / "reports")
        immutable_json(destination / "result.json", {
            "key": key, "status": "analyzed" if work.get("exclude_incomplete") else "succeeded",
            "profile_sha256": digest(profile), **result,
            "reports": tree_manifest(destination / "reports"),
        })
        results[key] = file_hash(destination / "result.json")
    immutable_json(bundle / "completed.json", {"work_sha256": digest(work), "results": results,
                                              "qualification": read_json(tool / "qualified.json")})


def import_work(root, bundle):
    bundle = Path(bundle).resolve()
    work, completed = read_json(bundle / "work.json"), read_json(bundle / "completed.json")
    expected = read_json(root / "detection/windows" / (digest(work) + ".json"))
    if work != expected or completed["work_sha256"] != digest(work):
        raise ValueError("Returned Windows work does not match the exported study.")
    if set(completed["results"]) != set(work["jobs"]):
        raise ValueError("Windows work is incomplete.")
    profile = work["profile"]
    if work.get("exclude_incomplete"):
        policy = exclusion_policy(root, work["source"], -1)
        if digest(policy) != work["policy_sha256"]:
            raise ValueError("Windows exclusion policy changed.")
    qualification = completed["qualification"]
    if qualification["status"] != "succeeded" or qualification["profile_sha256"] != digest(profile):
        raise ValueError("C# tool was not qualified for this profile.")
    for key, job in work["jobs"].items():
        path = bundle / "results" / key
        if file_hash(path / "result.json") != completed["results"][key]:
            raise ValueError("Returned result checksum differs.")
        value = read_json(path / "result.json")
        verify_tree(path / "reports", value["reports"])
        if (value["status"] != ("analyzed" if work.get("exclude_incomplete") else "succeeded") or value["key"] != key or
                value["profile_sha256"] != digest(profile) or
                not work.get("exclude_incomplete") and not set(job["required"]) <= set(value["coverage"]) or
                not set(value["coverage"]) <= set(job["files"])):
            raise ValueError("Windows result has inconsistent provenance/coverage.")
        for finding in value["findings"]:
            relative(finding["path"])
            if (finding["language"] != "csharp" or finding["path"] not in value["coverage"] or
                    finding["smell"] not in profile["catalog"].get(finding["category"], [])):
                raise ValueError("Invalid normalized Windows finding.")
        destination = root / "detection/results" / key
        if destination.exists():
            if read_json(destination / "result.json") != value:
                raise ValueError("Existing C# result differs.")
        else:
            shutil.copytree(path, destination)
    register_profile(root, profile)
    if work.get("exclude_incomplete"):
        source = work["source"]
        records = list(evidence_records(root, source))
        items = []
        for record in records:
            if record["status"] != "complete":
                continue
            for evidence in record["evidence"]:
                required = {f["path"] for f in evidence["files"] if f["language"] == "csharp"}
                if not required:
                    continue
                key = detection_key(evidence, profile)
                result = load_result(root / "detection/results" / key, key, profile)
                missing = sorted(required - set(result["coverage"]))
                items.append({"row_id": record["row_id"], "key": key, "required_files": sorted(required),
                              "missing_files": missing, "status": "incomplete" if missing else "complete"})
        write_json(root / "detection/coverage" / f"{source}-csharp.json", {
            "source": source, "language": "csharp", "study_sha256": policy["study_sha256"],
            "split_sha256": policy["split_sha256"], "profile_sha256": digest(profile), "scan_complete": True,
            "items": items, "incomplete_stories": sorted({x["row_id"] for x in items if x["missing_files"]}),
        })
        profiles = {p.stem: read_json(p) for p in (root / "detection/profiles").glob("*.json")}
        bounded_exclusions(root, source, records, profiles, policy)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--storage", type=Path, required=True)
    args = parser.parse_args()
    run_work(args.bundle, args.storage)


if __name__ == "__main__":
    main()
