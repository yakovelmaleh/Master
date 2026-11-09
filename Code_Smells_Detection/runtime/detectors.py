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


JAVA_COMMUNITY_SHA256 = "92b17ae9d286a6d932d3bc67a5b1763e876ea4776275619a18fb3ede48765dc4"
NATIVE_GAPS = {
    "magic_number_literal": r'Exception while parsing literal number \(during Magic Number detection\)\. '
                            r'For input string: "[^\r\n"]*"',
    "ancestor_memory_overflow": r"Ancestors analysis skipped due to memory overflow\.",
    "cyclic_dependency_memory_overflow": r"Cyclic dependency analysis skipped due to memory overflow\.",
}


class NativeAnalysisIncomplete(ValueError):
    def __init__(self, reasons):
        self.reasons = sorted(reasons)
        super().__init__("Incomplete native analysis: " + ", ".join(self.reasons))


def check_native_messages(messages, profile):
    # Licensing and unknown errors must never be swallowed by the bounded policy.
    if re.search(r"(?i)trial|licen[cs]e.*(?:invalid|expired|restrict|missing|fail|not found|not valid|required)",
                 messages):
        raise ValueError("Detector reports a license/trial message; inspect its logs.")
    reasons = []
    remaining = messages
    if profile["language"] == "java" and any(
            item["name"] == "DesigniteJavaCommunity.jar" and item["sha256"] == JAVA_COMMUNITY_SHA256
            for item in profile["artifacts"]):
        for reason, pattern in NATIVE_GAPS.items():
            if re.search(pattern, messages):
                reasons.append(reason)
                remaining = re.sub(pattern, "", remaining)
    patterns = [
        r"(?i)parse error", r"(?i)failed to (?:parse|analy[sz]e|load)", r"(?i)exception",
        r"(?i)analysis skipped|memory overflow",
        r"\b[A-Za-z_$][\w.$]*Error\b", r"(?im)^\s*(?:fatal|error)\b",
    ]
    for pattern in patterns + profile.get("failure_patterns", []):
        if re.search(pattern, remaining):
            raise ValueError("Detector reports incomplete/restricted analysis; inspect its logs.")
    if reasons:
        raise NativeAnalysisIncomplete(reasons)


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
        required.update(specification.get("qualified_columns", []))
        required.update(specification.get("entity_columns", []))
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
    check_native_messages(messages, profile)
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


def load_result(directory, key, profile):
    value = read_json(directory / "result.json")
    if (value["status"] not in ("analyzed", "succeeded") or value["key"] != key or
            value["profile_sha256"] != digest(profile)):
        raise ValueError("Detector manifest is invalid.")
    verify_tree(directory / "reports", value["reports"])
    return value


def load_failure(directory, key, profile):
    value = read_json(directory / "failure.json")
    if (value["status"] != "incomplete" or value["key"] != key or
            value["profile_sha256"] != digest(profile) or not value["reasons"] or
            set(value["reasons"]) - set(NATIVE_GAPS)):
        raise ValueError("Native failure manifest is invalid.")
    attempt = directory / relative(value["attempt"])
    verify_tree(attempt, value["reports"])
    messages = "\n".join((attempt / name).read_text(errors="replace") for name in ("output.out", "output.err"))
    try:
        check_native_messages(messages, profile)
    except NativeAnalysisIncomplete as error:
        if error.reasons == value["reasons"]:
            return value
    raise ValueError("Native failure reasons differ from preserved logs.")


def exclusion_policy(root, source, limit=None):
    path = root / "detection/policies" / f"{identifier(source)}.json"
    if limit is None:
        if not path.exists():
            return None
        limit = read_json(path)["max_incomplete_stories"]
    if type(limit) is not int or not 0 <= limit <= 10 or limit and source != "Apache":
        raise ValueError("Bounded exclusions require Apache and a cap from 1 to 10 (0 disables).")
    policy = {
        "source": source, "max_incomplete_stories": limit,
        "study_sha256": file_hash(root / "study.json"),
        "split_sha256": file_hash(root / "splits" / f"{source}.json"),
    }
    immutable_json(path, policy)
    return policy


def bounded_exclusions(root, source, records, profiles, policy):
    if not policy or not policy["max_incomplete_stories"]:
        return {}
    reasons, cached = {}, {}
    for record in records:
        if record["status"] != "complete":
            continue
        gaps = []
        for evidence in record["evidence"]:
            for language, profile in profiles.items():
                required = {f["path"] for f in evidence["files"] if f["language"] == language}
                if not required:
                    continue
                key = detection_key(evidence, profile)
                if key not in cached:
                    directory = root / "detection/results" / key
                    if (directory / "failure.json").exists():
                        if (directory / "result.json").exists():
                            raise ValueError("Conflicting native result and failure.")
                        cached[key] = load_failure(directory, key, profile)
                    elif (directory / "result.json").exists():
                        cached[key] = load_result(directory, key, profile)
                    else:
                        cached[key] = None
                value = cached[key]
                if value is None:
                    continue
                if value["status"] == "incomplete":
                    gaps.append(f"{language}/{key}: " + ", ".join(value["reasons"]))
                elif not required <= set(value["coverage"]):
                    gaps.append(f"{language}/{key}: uncovered files " +
                                ", ".join(sorted(required - set(value["coverage"]))))
        if gaps:
            reasons[record["row_id"]] = "; ".join(sorted(set(gaps)))
    limit = policy["max_incomplete_stories"]
    write_json(root / "detection/exclusions" / f"{source}.json", {
        "policy_sha256": digest(policy), "limit": limit, "count": len(reasons),
        "status": "cap_exceeded" if len(reasons) > limit else "within_cap",
        "stories": reasons,
    })
    if len(reasons) > limit:
        raise ValueError(f"{source} exclusion cap exceeded: {len(reasons)} stories, limit {limit}.")
    return reasons


def detect(root, storage, source, profile_path, max_incomplete_stories=0):
    with lock(root / "detection/policies" / f"{identifier(source)}.lock", wait=True):
        return detect_source(root, storage, source, profile_path, max_incomplete_stories)


def detect_source(root, storage, source, profile_path, max_incomplete_stories):
    verify_study(root)
    profile = load_profile(profile_path)
    tool = qualified(storage, profile)
    policy = exclusion_policy(root, source, max_incomplete_stories)
    register_profile(root, profile)
    records = list(evidence_records(root, source))
    profiles = {p.stem: read_json(p) for p in (root / "detection/profiles").glob("*.json")}
    coverage_path = root / "detection/coverage" / f"{source}-{profile['language']}.json"
    items = []

    def save_coverage(scan_complete=False):
        incomplete = sorted({item["row_id"] for item in items if item["missing_files"]})
        write_json(coverage_path, {
            "source": source, "language": profile["language"],
            "study_sha256": file_hash(root / "study.json"),
            "split_sha256": file_hash(root / "splits" / f"{source}.json"),
            "profile_sha256": digest(profile), "scan_complete": scan_complete,
            "items": items, "incomplete_stories": incomplete,
        })
        return incomplete

    save_coverage()
    bounded_exclusions(root, source, records, profiles, policy)
    for record in records:
        if record["status"] != "complete":
            continue
        for evidence in record["evidence"]:
            required = {item["path"] for item in evidence["files"] if item["language"] == profile["language"]}
            if not required:
                continue
            key = detection_key(evidence, profile)
            destination = root / "detection/results" / key
            with lock(destination.with_suffix(".lock"), wait=True):
                if (destination / "failure.json").exists():
                    if (destination / "result.json").exists():
                        raise ValueError("Conflicting native result and failure.")
                    result = load_failure(destination, key, profile)
                    if not max_incomplete_stories:
                        raise NativeAnalysisIncomplete(result["reasons"])
                elif (destination / "result.json").exists():
                    result = load_result(destination, key, profile)
                else:
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
                        try:
                            result = execute(tool, profile, workspace, output)
                        except NativeAnalysisIncomplete as error:
                            verify_original_files(workspace, snapshot["files"])
                            if not max_incomplete_stories:
                                raise
                            result = {
                                "key": key, "profile_sha256": digest(profile), "status": "incomplete",
                                "reasons": error.reasons,
                                "attempt": output.parent.relative_to(destination).as_posix(),
                                "reports": tree_manifest(output.parent),
                            }
                            immutable_json(destination / "failure.json", result)
                        verify_original_files(workspace, snapshot["files"])
                        if result.get("status") != "incomplete":
                            raw_output = destination / "reports"
                            if raw_output.exists():
                                verify_tree(raw_output, tree_manifest(output))
                            else:
                                shutil.copytree(output, raw_output)
                    if result.get("status") != "incomplete":
                        immutable_json(destination / "result.json", {
                            "key": key, "profile_sha256": digest(profile), **result,
                            "reports": tree_manifest(raw_output), "status": "analyzed",
                        })
                missing = sorted(required - set(result.get("coverage", [])))
                items.append({
                    "row_id": record["row_id"], "key": key, "required_files": sorted(required),
                    "missing_files": missing, "status": "incomplete" if missing else "complete",
                })
            save_coverage()
            if missing:
                bounded_exclusions(root, source, records, profiles, policy)
    excluded = bounded_exclusions(root, source, records, profiles, policy)
    incomplete = save_coverage(scan_complete=True)
    if set(incomplete) - set(excluded):
        raise ValueError(f"Detector coverage incomplete for {len(incomplete)} stories after processing "
                         f"remaining snapshots; inspect {coverage_path}")


def labels(root, exclusions_path=None):
    manifest = verify_study(root)
    exclusions = read_json(exclusions_path) if exclusions_path else {}
    if not isinstance(exclusions, dict) or any(
            not isinstance(reason, str) or not reason.strip() for reason in exclusions.values()):
        raise ValueError("Reviewed exclusions must map row IDs to nonempty reasons.")
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
    rows, statuses, automatic, policies = [], [], {}, {}
    for source in manifest["sources"]:
        records = list(evidence_records(root, source))
        policy = exclusion_policy(root, source)
        if policy:
            policies[source] = digest(policy)
        selected = bounded_exclusions(root, source, records, profiles, policy)
        automatic.update(selected)
        if policy and policy["max_incomplete_stories"]:
            reviewed_ids = {row for row in exclusions if row.startswith(source + ":")}
            if len(set(selected) | reviewed_ids) > policy["max_incomplete_stories"]:
                raise ValueError(f"{source} exclusion cap exceeded including reviewed exclusions.")
            for language, profile in profiles.items():
                if not any(f["language"] == language for record in records if record["status"] == "complete"
                           for evidence in record["evidence"] for f in evidence["files"]):
                    continue
                path = root / "detection/coverage" / f"{source}-{language}.json"
                scan = read_json(path) if path.exists() else {}
                if (not scan.get("scan_complete") or scan.get("profile_sha256") != digest(profile) or
                        scan.get("study_sha256") != policy["study_sha256"] or
                        scan.get("split_sha256") != policy["split_sha256"]):
                    raise ValueError("Bounded exclusions require a completed detector scan for every configured language.")
        for record in records:
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
                    if (directory / "failure.json").exists():
                        if (directory / "result.json").exists():
                            raise ValueError("Conflicting native result and failure.")
                        load_failure(directory, key, profile)
                        missing.append(key)
                        continue
                    if not (directory / "result.json").exists():
                        missing.append(key)
                        continue
                    result = load_result(directory, key, profile)
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
                elif record["row_id"] in selected:
                    status.update(status="excluded", reason="bounded_incomplete_detection",
                                  review_reason=selected[record["row_id"]])
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
    exclusions = {**automatic, **exclusions}
    if (root / "labels/manifest.json").exists():
        if read_json(root / "labels/exclusions.json") != exclusions:
            raise ValueError("Reviewed exclusions are frozen; use a new study to change them.")
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
        "exclusion_policies": policies,
        "source_counts": dict(Counter(frame.source)), "min_source_rows": manifest["min_rows"],
        "splits": {name: file_hash(root / "splits" / f"{name}.json") for name in manifest["sources"]},
    })
