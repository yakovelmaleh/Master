"""Qualified native report adapters, snapshot analysis and complete story labels."""

from collections import Counter, defaultdict
import csv
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import tempfile
import uuid
import zipfile

import pandas as pd
import requests

from .common import (
    LANGUAGES, SCHEMA, digest, external, file_hash, identifier, immutable_json,
    lock, now, read_json, relative, require_stage, source_relative, tree_manifest, verify_study,
    verify_original_files, verify_tree, write_csv, write_json,
)
from .prepare import frozen_frame


def load_profile(path):
    profile = read_json(path)
    required = {"language", "edition", "version", "origin", "platform", "artifacts",
                "command", "catalog", "reports", "coverage", "license"}
    if required - set(profile):
        raise ValueError(f"Tool profile lacks: {sorted(required - set(profile))}")
    if profile["language"] not in LANGUAGES.values():
        raise ValueError("Unknown detector language.")
    if profile["license"] not in ("community", "academic", "professional", "enterprise"):
        raise ValueError("Full export-capable lawful license required; trials are not qualified.")
    if set(profile["catalog"]) != {"implementation", "design"} or any(
            not names or len(names) != len(set(names)) for names in profile["catalog"].values()):
        raise ValueError("Both design and implementation catalogs must be explicit and unique.")
    if set(profile["reports"]) != set(profile["catalog"]) or not profile["coverage"]:
        raise ValueError("Both smell reports and a file-coverage report are required.")
    if not profile["command"] or not all(isinstance(arg, str) for arg in profile["command"]):
        raise ValueError("Detector command must be an argument list, not shell text.")
    if not all("{" + name + "}" in " ".join(profile["command"]) for name in ("input", "output")):
        raise ValueError("Command requires {input} and {output} placeholders.")
    for entry in profile["artifacts"]:
        relative(entry["name"])
        if not re.fullmatch("[0-9a-f]{64}", entry["sha256"]):
            raise ValueError("Every detector artifact requires a verified SHA256.")
    if not profile["artifacts"]:
        raise ValueError("Detector binary/dependency inventory is required.")
    return profile


def install_profile(storage, path):
    profile = load_profile(path)
    root = external(storage) / "tools" / profile["language"] / digest(profile)
    with lock(root.with_suffix(".lock")):
        root.mkdir(parents=True, exist_ok=True)
        for entry in profile["artifacts"]:
            destination = root / relative(entry["name"])
            if destination.exists():
                if file_hash(destination) != entry["sha256"]:
                    raise ValueError(f"Detector artifact changed: {destination}")
                continue
            if "local_path" in entry:
                source = Path(entry["local_path"]).expanduser()
                if file_hash(source) != entry["sha256"]:
                    raise ValueError("Local detector checksum differs.")
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)
            elif "url" in entry:
                url = entry["url"]
                if not url.startswith("https://www.designite-tools.com/"):
                    raise ValueError("Automatic tool downloads require the official publisher HTTPS host.")
                with requests.get(url, timeout=120, stream=True, allow_redirects=False) as response:
                    response.raise_for_status()
                    if response.status_code != 200:
                        raise ValueError("Tool download redirected; review the new publisher URL.")
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    temporary = destination.with_suffix(".download")
                    try:
                        with temporary.open("wb") as stream:
                            size = 0
                            for chunk in response.iter_content(1024 * 1024):
                                size += len(chunk)
                                if size > 2 * 1024**3:
                                    raise ValueError("Detector download exceeds size limit.")
                                stream.write(chunk)
                        if file_hash(temporary) != entry["sha256"]:
                            raise ValueError("Downloaded detector checksum differs.")
                        temporary.replace(destination)
                    finally:
                        temporary.unlink(missing_ok=True)
            else:
                raise ValueError("Artifact requires local_path or url.")
            if entry.get("executable"):
                destination.chmod(0o700)
        immutable_json(root / "profile.json", profile)
    return root, profile


def profile_root(storage, profile):
    root = external(storage) / "tools" / profile["language"] / digest(profile)
    if read_json(root / "profile.json") != profile:
        raise ValueError("Installed profile differs.")
    for entry in profile["artifacts"]:
        if file_hash(root / relative(entry["name"])) != entry["sha256"]:
            raise ValueError("Installed detector binary changed.")
    return root


def csv_report(output, specification):
    pattern = specification["file"]
    if Path(pattern).is_absolute() or ".." in Path(pattern).parts:
        raise ValueError("Report glob must stay inside the detector output.")
    paths = sorted(Path(output).glob(pattern))
    if len(paths) != 1 or paths[0].is_symlink():
        raise ValueError(f"Expected exactly one report for {pattern}; found {len(paths)}.")
    with paths[0].open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        headers = set(reader.fieldnames or [])
        required = set(specification.get("required_columns", []))
        required.update(specification[name] for name in ("path_column", "smell_column")
                        if specification.get(name))
        if not headers or required - headers:
            raise ValueError(f"Unexpected {pattern} schema: {sorted(headers)}")
        return list(reader)


def source_index(source, language):
    suffix = next(extension for extension, value in LANGUAGES.items() if value == language)
    paths = [path for path in source.rglob("*" + suffix) if path.is_file() and not path.is_symlink()]
    index = defaultdict(set)
    for path in paths:
        name = path.relative_to(source).as_posix()
        index[name].add(name)
        if language == "java":
            text = path.read_text(encoding="utf-8")
            # Only unique qualified declarations are usable; ambiguous or absent attribution fails.
            text = re.sub(r"/\*.*?\*/|//[^\n]*|\"(?:\\.|[^\"\\])*\"", " ", text, flags=re.S)
            package = re.search(r"\bpackage\s+([\w.]+)\s*;", text)
            prefix = package.group(1) + "." if package else ""
            for declaration in re.findall(r"\b(?:class|interface|enum|record)\s+(\w+)", text):
                index[prefix + declaration].add(name)
        elif language == "python":
            module = name[:-3].replace("/", ".")
            index[module].add(name)
            if module.endswith(".__init__"):
                index[module[:-9]].add(name)
    return index


def report_path(row, spec, source, index, ambiguous=None):
    if spec.get("path_column"):
        value = row[spec["path_column"]].strip().replace("\\", "/")
        base = source.as_posix().rstrip("/") + "/"
        if value.startswith(base):
            value = value[len(base):]
        source_relative(value)
        matches = index.get(value, set())
    else:
        columns = spec.get("qualified_columns", [])
        if not columns:
            raise ValueError("Report requires a path column or qualified entity columns.")
        value = ".".join(row[column].strip() for column in columns if row[column].strip())
        matches = index.get(value, set())
    if len(matches) > 1 and ambiguous is not None:
        ambiguous[value] = sorted(matches)
        return None
    if len(matches) != 1:
        raise ValueError(f"Ambiguous/unresolved detector entity: {value!r}")
    return next(iter(matches))


def parse_reports(output, source, profile):
    index = source_index(source, profile["language"])
    coverage, ambiguous = set(), {}
    for spec in profile["coverage"]:
        for row in csv_report(output, spec):
            path = report_path(row, spec, source, index, ambiguous)
            if path is not None:
                coverage.add(path)
    findings = {}
    for category, spec in profile["reports"].items():
        allowed = set(profile["catalog"][category])
        for row in csv_report(output, spec):
            smell = row[spec["smell_column"]].strip()
            if smell not in allowed:
                raise ValueError(f"Unregistered native smell: {category}/{smell}")
            path = report_path(row, spec, source, index, ambiguous)
            if path is None:
                continue
            columns = spec.get("entity_columns") or sorted(set(row) - {spec["smell_column"], spec.get("path_column")})
            entity = "|".join(row[column].strip() for column in columns)
            finding = {"language": profile["language"], "category": category,
                       "smell": smell, "path": path, "entity": entity}
            findings[digest(finding)] = finding
    # A file may contain both unique and ambiguous types. No result for that file
    # is complete if any of its reported entities cannot be attributed uniquely.
    blocked = {path for paths in ambiguous.values() for path in paths}
    coverage -= blocked
    findings = [value for value in findings.values() if value["path"] not in blocked]
    if any(value["path"] not in coverage for value in findings):
        raise ValueError("Finding is outside reported analyzed-file coverage.")
    if not coverage:
        raise ValueError("Detector reported no unambiguously analyzed source files.")
    result = {"coverage": sorted(coverage), "findings": findings}
    if ambiguous:
        result["ambiguous_entities"] = [
            {"entity": value, "candidate_paths": paths} for value, paths in sorted(ambiguous.items())]
    return result


def execute(tool_root, profile, source, output):
    if profile["platform"] != platform.system():
        raise ValueError(f"Detector requires {profile['platform']}; use the matching worker.")
    output.mkdir(parents=True, exist_ok=False)
    print(f"Native reports: {output}; logs: {output}.out and {output}.err", flush=True)
    input_path = source
    if profile["language"] == "csharp":
        projects = sorted(source.rglob("*.csproj"))
        if not projects:
            raise ValueError("C# snapshot has no project file; analysis is unsupported, not clean.")
        input_path = output.parent / "projects.batch"
        input_path.write_text("[Projects]\n" + "\n".join(str(path) for path in projects) + "\n")
    substitutions = {"tool": str(tool_root), "input": str(input_path), "output": str(output)}
    command = [arg.format(**substitutions) for arg in profile["command"]]
    # No Jira/GitHub tokens are inherited by analyzers or project build processes.
    allowed = ("PATH", "JAVA_HOME", "DOTNET_ROOT", "SYSTEMROOT", "WINDIR",
               "TEMP", "TMP", "LANG", "LC_ALL", "HOME", "USERPROFILE")
    environment = {key: os.environ[key] for key in allowed if key in os.environ}
    with (output.parent / (output.name + ".out")).open("w") as out, (
            output.parent / (output.name + ".err")).open("w") as err:
        subprocess.run(command, check=True, stdout=out, stderr=err, cwd=output.parent,
                       env=environment, timeout=profile.get("timeout_seconds", 14400))
    messages = "\n".join((output.parent / (output.name + suffix)).read_text(errors="replace")
                         for suffix in (".out", ".err"))
    for pattern in profile.get("failure_patterns", [
            r"(?i)trial", r"(?i)license.*(?:invalid|expired|restrict)", r"(?i)parse error",
            r"(?i)failed to (?:parse|analy[sz]e|load)", r"(?i)exception"]):
        if re.search(pattern, messages):
            raise ValueError("Detector reports incomplete/restricted analysis; inspect its logs.")
    result = parse_reports(output, source, profile)
    if result.get("ambiguous_entities"):
        write_json(output / "attribution.json", {
            "ambiguous_entities": result["ambiguous_entities"],
            "policy": "All candidate files are excluded from usable coverage and findings.",
        })
    return result


def qualify(storage, profile_path, fixture, expected_path):
    profile = load_profile(profile_path)
    tool = profile_root(storage, profile)
    fixture = Path(fixture).resolve()
    expected = read_json(expected_path)
    if set(expected) != {"positive", "clean_files"} or not expected["clean_files"]:
        raise ValueError("Qualification needs positive findings and known-clean file controls.")
    if {item["category"] for item in expected["positive"]} != {"design", "implementation"}:
        raise ValueError("Qualification must exercise both smell categories.")
    fixture_files = tree_manifest(fixture)
    fingerprint = digest({"profile": profile, "fixture": fixture_files, "expected": expected})
    destination = tool / "qualification" / fingerprint
    with lock(destination.with_suffix(".lock")):
        if (destination / "qualification.json").exists():
            qualification = read_json(destination / "qualification.json")
            verify_tree(destination / "reports", qualification["reports"])
            immutable_json(tool / "qualified.json", {"qualification": fingerprint, **qualification})
            return qualification
        destination.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="qualify-", dir=destination) as scratch:
            source = Path(scratch) / "source"
            shutil.copytree(fixture, source)
            output = destination / "attempts" / uuid.uuid4().hex / "output"
            result = execute(tool, profile, source, output)
            verify_original_files(source, fixture_files)
            observed = {(value["path"], value["category"], value["smell"]) for value in result["findings"]}
            positives = {(value["path"], value["category"], value["smell"]) for value in expected["positive"]}
            if not positives <= observed:
                raise ValueError(f"Qualification misses expected findings: {sorted(positives - observed)}")
            if not set(expected["clean_files"]) <= set(result["coverage"]):
                raise ValueError("Known-clean controls were not analyzed.")
            if any(item["path"] in expected["clean_files"] for item in result["findings"]):
                raise ValueError("Clean qualification control contains reported smells.")
            if (destination / "reports").exists():
                verify_tree(destination / "reports", tree_manifest(output))
            else:
                shutil.copytree(output, destination / "reports")
        qualification = {"profile_sha256": digest(profile), "fixture_sha256": digest(fixture_files),
                         "expected": expected, "status": "succeeded",
                         "reports": tree_manifest(destination / "reports"),
                         "platform": platform.platform()}
        immutable_json(destination / "qualification.json", qualification)
        immutable_json(tool / "qualified.json", {"qualification": fingerprint, **qualification})
        return qualification


def qualified(storage, profile):
    tool = profile_root(storage, profile)
    result = read_json(tool / "qualified.json")
    if result["status"] != "succeeded" or result["profile_sha256"] != digest(profile):
        raise ValueError("A matching successful qualification is required.")
    verify_tree(tool / "qualification" / result["qualification"] / "reports", result["reports"])
    return tool


def evidence_records(root, source):
    require_stage(root, "fetch-code", source)
    manifest = read_json(root / "evidence" / source / "manifest.json")
    if file_hash(root / "splits" / f"{source}.json") != manifest["split_sha256"]:
        raise ValueError("Evidence belongs to another split.")
    for row_id, expected in manifest["records"].items():
        path = root / "evidence" / source / (row_id.split(":", 1)[1] + ".json")
        if file_hash(path) != expected:
            raise ValueError("Evidence record changed.")
        yield read_json(path)


def detection_key(evidence, profile):
    return digest({"repository": evidence["repository"], "revision": evidence["revision"],
                   "snapshot_sha256": evidence["snapshot_manifest_sha256"], "profile": profile})


def register_profile(root, profile):
    immutable_json(root / "detection/profiles" / (profile["language"] + ".json"), profile)


def detect(root, storage, source, profile_path):
    verify_study(root)
    profile = load_profile(profile_path)
    tool = qualified(storage, profile)
    register_profile(root, profile)
    for record in evidence_records(root, source):
        if record["status"] != "complete":
            continue
        for evidence in record["evidence"]:
            required = {item["path"] for item in evidence["files"] if item["language"] == profile["language"]}
            if not required:
                continue
            key = detection_key(evidence, profile)
            destination = root / "detection/results" / key
            with lock(destination.with_suffix(".lock"), wait=True):
                if (destination / "result.json").exists():
                    value = read_json(destination / "result.json")
                    if value["key"] != key or not required <= set(value["coverage"]):
                        raise ValueError("Cached detector result is incomplete.")
                    verify_tree(destination / "reports", value["reports"])
                    continue
                cache = Path(evidence["snapshot"])
                if file_hash(cache / "manifest.json") != evidence["snapshot_manifest_sha256"]:
                    raise ValueError("Snapshot manifest changed.")
                snapshot = read_json(cache / "manifest.json")
                verify_tree(cache / "source", snapshot["files"])
                destination.mkdir(parents=True, exist_ok=True)
                with tempfile.TemporaryDirectory(prefix="analysis-", dir=destination) as scratch:
                    workspace = Path(scratch) / "source"
                    shutil.copytree(cache / "source", workspace)
                    output = destination / "attempts" / uuid.uuid4().hex / "output"
                    result = execute(tool, profile, workspace, output)
                    verify_original_files(workspace, snapshot["files"])
                    if not required <= set(result["coverage"]):
                        raise ValueError("Detector did not analyze every associated changed file.")
                    raw_output = destination / "reports"
                    if raw_output.exists():
                        verify_tree(raw_output, tree_manifest(output))
                    else:
                        shutil.copytree(output, raw_output)
                immutable_json(destination / "result.json", {
                    "key": key, "profile_sha256": digest(profile), **result,
                    "reports": tree_manifest(raw_output), "status": "succeeded",
                })


def labels(root, exclusions_path=None):
    manifest = verify_study(root)
    exclusions = read_json(exclusions_path) if exclusions_path else {}
    if not isinstance(exclusions, dict) or any(
            not isinstance(reason, str) or not reason.strip() for reason in exclusions.values()):
        raise ValueError("Reviewed exclusions must map row IDs to nonempty reasons.")
    if (root / "labels/manifest.json").exists():
        if read_json(root / "labels/exclusions.json") != exclusions:
            raise ValueError("Reviewed exclusions are frozen; use a new study to change them.")
    acknowledged = set()
    profiles = {path.stem: read_json(path) for path in (root / "detection/profiles").glob("*.json")}
    if not profiles:
        raise ValueError("No detector profiles registered.")
    catalog = {"any_supported_smell": {"language": None, "category": "any", "smell": "any"}}
    for language, profile in profiles.items():
        for category, names in profile["catalog"].items():
            for smell in names:
                target = language + "." + category + "." + digest(smell)[:16]
                catalog[target] = {"language": language, "category": category, "smell": smell}
    rows, statuses = [], []
    for source in manifest["sources"]:
        for record in evidence_records(root, source):
            languages, found, missing = set(), set(), []
            if record["status"] != "complete":
                statuses.append({"row_id": record["row_id"], "status": "excluded",
                                 "reason": record["reason"]})
                continue
            for evidence in record["evidence"]:
                required_languages = {item["language"] for item in evidence["files"]}
                languages.update(required_languages)
                for language in required_languages:
                    if language not in profiles:
                        missing.append(f"unconfigured_language:{language}")
                        continue
                    profile = profiles[language]
                    key = detection_key(evidence, profile)
                    directory = root / "detection/results" / key
                    if not (directory / "result.json").exists():
                        missing.append(key)
                        continue
                    result = read_json(directory / "result.json")
                    if (result["status"] != "succeeded" or result["key"] != key or
                            result["profile_sha256"] != digest(profile)):
                        raise ValueError("Detector manifest is invalid.")
                    verify_tree(directory / "reports", result["reports"])
                    required = {item["path"] for item in evidence["files"] if item["language"] == language}
                    if not required <= set(result["coverage"]):
                        missing.append(key)
                        continue
                    for value in result["findings"]:
                        if value["path"] in required:
                            found.add((language, value["category"], value["smell"],
                                       evidence["repository"], evidence["revision"], value["path"], value["entity"]))
            if missing or not languages:
                status = {"row_id": record["row_id"], "status": "incomplete", "missing": missing}
                if record["row_id"] in exclusions:
                    acknowledged.add(record["row_id"])
                    status.update(status="excluded", reason="reviewed_incomplete_detection",
                                  review_reason=exclusions[record["row_id"]])
                statuses.append(status)
                continue
            values = {}
            for target, description in catalog.items():
                language = description["language"]
                if language is None:
                    values[target] = int(bool(found))
                elif language not in languages:
                    values[target] = None
                else:
                    values[target] = int(any(item[:3] == (language, description["category"], description["smell"])
                                             for item in found))
            rows.append({"row_id": record["row_id"], "source": source, "partition": record["partition"],
                         **values})
            statuses.append({"row_id": record["row_id"], "status": "complete",
                             "languages": sorted(languages), "distinct_findings": len(found)})
    if set(exclusions) != acknowledged:
        raise ValueError("Reviewed exclusions contain unknown or already complete/excluded row IDs.")
    coverage = {
        "rows": statuses, "status_counts": dict(Counter(row["status"] for row in statuses)),
        "source_labeled_counts": dict(Counter(row["source"] for row in rows)),
    }
    if (root / "labels/manifest.json").exists():
        immutable_json(root / "labels/coverage.json", coverage)
    else:
        write_json(root / "labels/coverage.json", coverage)
    # A partial run cannot be frozen as the final primary cohort without noticing the missing jobs.
    if any(row["status"] == "incomplete" for row in statuses):
        raise ValueError("Required detector results are missing/incomplete; inspect labels/coverage.json.")
    if not rows:
        raise ValueError("No completely labeled stories.")
    frame = pd.DataFrame(rows)
    content = frame.to_csv(index=False).encode()
    destination = root / "labels/story_labels.csv"
    if destination.exists() and destination.read_bytes() != content:
        raise ValueError("Labels are immutable; use a new study for changed evidence.")
    from .common import atomic_bytes
    atomic_bytes(destination, content)
    immutable_json(root / "labels/catalog.json", catalog)
    immutable_json(root / "labels/exclusions.json", exclusions)
    immutable_json(root / "labels/manifest.json", {
        "schema": SCHEMA, "labels_sha256": file_hash(destination), "catalog_sha256": digest(catalog),
        "coverage_sha256": digest(coverage), "exclusions_sha256": digest(exclusions),
        "profiles": {name: digest(value) for name, value in profiles.items()},
        "source_counts": dict(Counter(frame.source)), "min_source_rows": manifest["min_rows"],
        "splits": {name: file_hash(root / "splits" / f"{name}.json") for name in manifest["sources"]},
    })
