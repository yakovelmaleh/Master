"""Resolve delivered GitHub evidence and safely cache immutable source snapshots."""

from collections import Counter, defaultdict
import json
import os
from pathlib import Path
import re
import shutil
import tarfile
import tempfile
import time
from urllib.parse import quote, urlparse

import requests

from .common import (
    LANGUAGES, digest, external, file_hash, immutable_json, lock, now, read_json,
    relative, tree_manifest, verify_study, verify_tree, write_json,
)
from .prepare import frozen_frame


LINK = re.compile(r"https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/(pull/\d+|commit/[0-9a-fA-F]{7,40})(?![A-Za-z0-9])")
SHA = re.compile(r"[0-9a-f]{40}")


class EvidenceExcluded(ValueError):
    pass


class GitHub:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/vnd.github+json",
                                     "X-GitHub-Api-Version": "2022-11-28"})
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"

    def get(self, path, params=None):
        if not path.startswith("/repos/") or "://" in path:
            raise ValueError("Only GitHub repository API paths are allowed.")
        for attempt in range(5):
            try:
                response = self.session.get("https://api.github.com" + path, params=params,
                                            timeout=60, allow_redirects=False)
            except requests.exceptions.SSLError:
                raise
            except (requests.ConnectionError, requests.Timeout) as error:
                if attempt == 4:
                    raise
                delay = 2 ** attempt
                print(f"GitHub {type(error).__name__}; retrying request "
                      f"({attempt + 2}/5) in {delay}s.", flush=True)
                time.sleep(delay)
                continue
            if response.status_code in (429, 502, 503, 504) or (
                    response.status_code == 403 and response.headers.get("X-RateLimit-Remaining") == "0"):
                if attempt == 4:
                    response.raise_for_status()
                time.sleep(min(60, max(1, int(response.headers.get("Retry-After", "10")))))
                continue
            if response.status_code in (404, 410):
                raise EvidenceExcluded("repository_or_revision_unavailable")
            if response.status_code == 409 and re.fullmatch(r"/repos/[^/]+/[^/]+/commits/[^/]+", path):
                try:
                    payload = response.json()
                except ValueError:
                    response.raise_for_status()
                if isinstance(payload, dict) and payload.get("message") == "Git Repository is empty.":
                    raise EvidenceExcluded("repository_empty")
            response.raise_for_status()
            if 300 <= response.status_code < 400:
                raise EvidenceExcluded("repository_redirect_requires_review")
            return response.json()
        raise RuntimeError("GitHub retry loop exhausted")

    def files(self, repository, kind, number, expected=None):
        results = []
        for page in range(1, 32):
            payload = self.get(f"/repos/{repository}/{kind}/{number}" +
                               ("/files" if kind == "pulls" else ""),
                               {"per_page": 100, "page": page})
            values = payload if kind == "pulls" else payload.get("files")
            if not isinstance(values, list):
                raise ValueError("Invalid changed-file response.")
            results.extend(values)
            if len(values) < 100:
                break
        else:
            raise EvidenceExcluded("changed_file_api_limit")
        if len(results) >= 3000 or expected is not None and len(results) != expected:
            raise EvidenceExcluded("incomplete_changed_file_inventory")
        if len({value["filename"] for value in results}) != len(results):
            raise EvidenceExcluded("duplicate_changed_file_pages")
        return results

    def resolve(self, url):
        match = LINK.fullmatch(url)
        if match is None:
            raise EvidenceExcluded("unsupported_evidence_url")
        owner, name, reference = match.groups()
        repository = owner + "/" + name
        repository_info = self.get(f"/repos/{repository}")
        default = self.get(f"/repos/{repository}/commits/" +
                           quote(repository_info["default_branch"], safe=""))["sha"]
        if reference.startswith("pull/"):
            number = reference.split("/")[1]
            info = self.get(f"/repos/{repository}/pulls/{number}")
            if not info.get("merged") or not info.get("merged_at"):
                raise EvidenceExcluded("pr_not_merged")
            revision = info["head"]["sha"]
            merge_sha = info["merge_commit_sha"]
            files = self.files(repository, "pulls", number, info["changed_files"])
            provenance = {"merged_at": info["merged_at"], "merge_sha": merge_sha,
                          "pr_base_sha": info["base"]["sha"]}
        else:
            info = self.get(f"/repos/{repository}/commits/{reference.split('/')[1]}")
            revision = info["sha"]
            comparison = self.get(f"/repos/{repository}/compare/{revision}...{default}")
            if comparison["status"] not in ("ahead", "identical"):
                raise EvidenceExcluded("commit_not_on_default_history")
            if len(info.get("parents", [])) > 1:
                parent = info["parents"][0]["sha"]
                compared = self.get(f"/repos/{repository}/compare/{parent}...{revision}")
                files = compared.get("files", [])
                # Compare endpoints cap files; refusing is safer than inventing a complete negative.
                if len(files) >= 300:
                    raise EvidenceExcluded("merge_diff_api_limit")
            else:
                files = self.files(repository, "commits", revision)
            provenance = {"committed_at": info["commit"]["committer"]["date"],
                          "parents": [item["sha"] for item in info.get("parents", [])],
                          "diff_policy": "first_parent"}
        if not SHA.fullmatch(revision) or not SHA.fullmatch(default):
            raise ValueError("Expected full immutable Git commit IDs.")
        changed = []
        for item in files:
            path = relative(item["filename"]).as_posix()
            status = item["status"]
            if status not in ("added", "modified", "removed", "renamed", "changed", "copied", "unchanged"):
                raise EvidenceExcluded("unsupported_file_status")
            previous = item.get("previous_filename")
            if previous:
                relative(previous)
            language = LANGUAGES.get(Path(path).suffix.lower())
            changed.append({"path": path, "previous_path": previous, "status": status,
                            "language": language, "blob_sha": item.get("sha")})
        return {"url": url, "repository": repository, "revision": revision,
                "default_branch_sha": default, "provenance": provenance, "files": changed,
                "resolved_at": now()}


def links(record):
    # Serialized ADF preserves link-mark attributes that plain-text conversion drops.
    serialized = json.dumps({"fields": record["issue"].get("fields", {}),
                             "comments": record.get("comments", [])})
    found = {match.group(0) for match in LINK.finditer(serialized)}
    for url in re.findall(r"https?://[^\s\"<>]+", serialized):
        if re.search(r"/(?:pulls?|pull-requests|merge_requests|commits?)/", url) and not LINK.match(url):
            found.add(url.rstrip(".,);"))
    found = sorted(found)
    return found


def extract_archive(archive, destination, max_bytes=20 * 1024**3):
    total, seen, prefix = 0, set(), None
    with tarfile.open(archive, "r:gz") as stream:
        for item in stream:
            original = relative(item.name.rstrip("/"))
            if prefix is None:
                prefix = original.parts[0]
            if original.parts[0] != prefix:
                raise ValueError("Archive has multiple repository roots.")
            if len(original.parts) == 1:
                continue
            name = "/".join(original.parts[1:])
            path = destination / relative(name)
            if item.isdir():
                path.mkdir(parents=True, exist_ok=True)
                continue
            if not item.isfile():
                raise EvidenceExcluded("snapshot_contains_link_or_special_file")
            if name in seen:
                raise ValueError("Duplicate archive path.")
            seen.add(name)
            total += item.size
            if total > max_bytes:
                raise EvidenceExcluded("snapshot_size_limit")
            path.parent.mkdir(parents=True, exist_ok=True)
            with stream.extractfile(item) as source, path.open("wb") as output:
                shutil.copyfileobj(source, output)
    if not seen:
        raise EvidenceExcluded("empty_snapshot")


def snapshot(storage, repository, revision):
    cache = external(storage) / "cache" / digest(repository) / revision
    with lock(cache.with_suffix(".lock"), wait=True):
        if (cache / "manifest.json").exists():
            manifest = read_json(cache / "manifest.json")
            verify_tree(cache / "source", manifest["files"])
            return cache, manifest
        cache.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="snapshot-", dir=cache.parent) as directory:
            temporary = Path(directory)
            archive = temporary / "source.tar.gz"
            # Public source only. Never forward API credentials to an archive host.
            url = f"https://codeload.github.com/{repository}/tar.gz/{revision}"
            with requests.get(url, stream=True, timeout=120, allow_redirects=False) as response:
                if response.status_code != 200:
                    raise EvidenceExcluded(f"archive_http_{response.status_code}")
                size = 0
                with archive.open("wb") as output:
                    for chunk in response.iter_content(1024 * 1024):
                        size += len(chunk)
                        if size > 4 * 1024**3:
                            raise EvidenceExcluded("compressed_snapshot_size_limit")
                        output.write(chunk)
            output = temporary / "source"
            output.mkdir()
            extract_archive(archive, output)
            manifest = {"repository": repository, "revision": revision,
                        "archive_sha256": file_hash(archive), "files": tree_manifest(output)}
            cache.mkdir(exist_ok=True)
            if (cache / "source").exists():
                raise ValueError("Incomplete snapshot exists; inspect it before retrying.")
            shutil.move(str(output), cache / "source")
            immutable_json(cache / "manifest.json", manifest)
        return cache, manifest


def fetch_code(root, storage, source, github=None, snapshot_loader=snapshot):
    verify_study(root)
    frame, split = frozen_frame(root, source)
    github = github or GitHub()
    destination = root / "evidence" / source
    records = []
    saved = read_json(root / "raw" / source / "manifest.json")
    for row in frame.itertuples():
        cached = root / "raw" / source / f"{row.issue_key}.json"
        if file_hash(cached) != saved["records"][row.issue_key]:
            raise ValueError("Raw input changed before evidence resolution.")
        urls = links(read_json(cached))
        evidence, exclusions = [], []
        for url in urls:
            metadata_path = root / "evidence/resolved" / f"{digest(url)}.json"
            with lock(metadata_path.with_suffix(".lock"), wait=True):
                if metadata_path.exists():
                    item = read_json(metadata_path)
                else:
                    try:
                        item = {"status": "resolved", "value": github.resolve(url)}
                    except EvidenceExcluded as error:
                        item = {"status": "excluded", "url": url, "reason": str(error)}
                    immutable_json(metadata_path, item)
            if item["status"] == "excluded":
                exclusions.append(item)
                continue
            value = item["value"]
            files = [entry for entry in value["files"]
                     if entry["language"] and entry["status"] != "removed"]
            if not files:
                exclusions.append({"url": url, "reason": "no_supported_post_change_files"})
                continue
            try:
                cache, snap = snapshot_loader(storage, value["repository"], value["revision"])
                for entry in files:
                    if entry["path"] not in snap["files"]:
                        raise EvidenceExcluded("changed_file_missing_from_snapshot")
                evidence.append({**value, "files": files, "snapshot": str(cache),
                                 "snapshot_manifest_sha256": file_hash(cache / "manifest.json")})
            except EvidenceExcluded as error:
                exclusions.append({"url": url, "reason": str(error)})
        # Unresolved/unavailable links may hide additional relevant code.
        benign = {"pr_not_merged", "commit_not_on_default_history", "no_supported_post_change_files"}
        complete = bool(evidence) and all(item["reason"] in benign for item in exclusions)
        record = {"row_id": row.row_id, "source": source, "partition": split["assignment"][row.row_id],
                  "status": "complete" if complete else "excluded",
                  "reason": None if complete else "no_complete_supported_evidence",
                  "links": urls, "evidence": evidence, "exclusions": exclusions}
        immutable_json(destination / f"{row.issue_key}.json", record)
        records.append(record)
    shared = defaultdict(set)
    for record in records:
        for item in record["evidence"]:
            shared[(item["repository"], item["revision"])].add(record["partition"])
    write_json(destination / "audit.json", {
        "counts": dict(Counter(record["status"] for record in records)),
        "cross_partition_revisions": [
            {"repository": key[0], "revision": key[1], "partitions": sorted(value)}
            for key, value in shared.items() if len(value) > 1
        ],
        "interpretation": "Retrospective linked-code labels; label availability may postdate story splits.",
    })
    immutable_json(destination / "manifest.json", {
        "split_sha256": file_hash(root / "splits" / f"{source}.json"),
        "records": {row["row_id"]: file_hash(destination / f"{row['row_id'].split(':', 1)[1]}.json")
                    for row in records},
    })
