import io
import json
from pathlib import Path
import tarfile
from unittest import mock

import pandas as pd
import requests

from Code_Smells_Detection.runtime import common, evidence, prepare
from Code_Smells_Detection.runtime.tests.support import RuntimeCase


class PreparationTests(RuntimeCase):
    def test_audit_pins_ids_and_rejects_changed_cohort(self):
        path = self.storage / "candidates.csv"
        source = self.storage / "sources.csv"
        pd.DataFrame([{"source": "Apache", "issue_key": f"A-{i}", "issue_type": "Task",
                       "created": "2020-01-01"} for i in range(120)]).to_csv(path, index=False)
        pd.DataFrame([{"source": "Apache", "candidate_count": 120,
                       "base_url": "https://example.invalid", "jql": "type != Bug"}]).to_csv(source, index=False)
        with mock.patch.object(prepare, "CANDIDATE_HASH", common.file_hash(path)), mock.patch.object(
                prepare, "SOURCES", {"Apache": 120}):
            prepare.audit(self.root, path, source)
            self.assertEqual(120, common.read_json(self.root / "cohort/retention.json")["selected_candidates"])
            path.write_text(path.read_text() + "\n")
            with self.assertRaisesRegex(ValueError, "frozen"):
                prepare.audit(self.root, path, source)

    def test_truncated_expanded_history_is_not_accepted(self):
        client = object.__new__(prepare.CompleteJiraClient)
        client.api_version = 2
        client.request = mock.Mock(return_value=mock.Mock(status_code=404))
        client.json_request = mock.Mock(return_value={"changelog": {"total": 200, "histories": [{"id": "1"}]}})
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            client.changelog("A-1")
        client.json_request.return_value = {"changelog": {"total": 1, "histories": [{"id": "1"}]}}
        self.assertEqual([{"id": "1"}], client.changelog("A-1"))

    def test_metadata_and_early_post_sprint_text_reconstructed(self):
        row = {"time_add_to_sprint": "2020-01-01T00:20:00", "original_summary_sprint": "future"}
        record = {"issue": {"fields": {"priority": {"name": "High"}}}, "changelog": [{
            "created": "2020-01-01T00:30:00Z",
            "items": [{"field": "priority", "fromString": "Low", "toString": "High"},
                      {"field": "summary", "fromString": "before", "toString": "future"}],
        }]}
        result = prepare.reconstruct_metadata(row, record)
        self.assertEqual("Low", result["priority"])
        self.assertEqual("before", result["original_summary_sprint"])

    def test_archive_rejects_traversal_and_symlinks(self):
        for name, kind in (("repo/../../escape", tarfile.REGTYPE), ("repo/link", tarfile.SYMTYPE)):
            archive = self.storage / "bad.tar.gz"
            with tarfile.open(archive, "w:gz") as stream:
                entry = tarfile.TarInfo(name)
                entry.type = kind
                entry.linkname = "../../escape"
                stream.addfile(entry)
            with self.assertRaises(ValueError):
                evidence.extract_archive(archive, self.storage / "extract")
        archive = self.storage / "good.tar.gz"
        with tarfile.open(archive, "w:gz") as stream:
            entry = tarfile.TarInfo("repo/src/A.java")
            entry.size = 7
            stream.addfile(entry, io.BytesIO(b"class A"))
        evidence.extract_archive(archive, self.storage / "extract")
        self.assertEqual("class A", (self.storage / "extract/src/A.java").read_text())

    def test_github_pagination_and_unmerged_pr(self):
        github = object.__new__(evidence.GitHub)
        github.get = mock.Mock(side_effect=[
            [{"filename": str(i)} for i in range(100)], [{"filename": "last"}],
        ])
        self.assertEqual(101, len(github.files("a/b", "pulls", "1", 101)))
        github.repository_info = mock.Mock(return_value=({"full_name": "a/b", "default_branch": "main"}, {}))
        github.get = mock.Mock(side_effect=[{"sha": "a" * 40}, {"merged": False}])
        with self.assertRaisesRegex(evidence.EvidenceExcluded, "pr_not_merged"):
            github.resolve("https://github.com/a/b/pull/1")

    def test_commit_must_be_on_default_history(self):
        github = object.__new__(evidence.GitHub)
        github.repository_info = mock.Mock(return_value=({"full_name": "a/b", "default_branch": "main"}, {}))
        github.get = mock.Mock(side_effect=[
            {"sha": "b" * 40},
            {"sha": "a" * 40, "parents": []}, {"status": "diverged"},
        ])
        with self.assertRaisesRegex(evidence.EvidenceExcluded, "default_history"):
            github.resolve("https://github.com/a/b/commit/" + "a" * 40)

    @staticmethod
    def github_response(status, payload):
        response = requests.Response()
        response.status_code = status
        response.url = "https://api.github.com/repos/a/b/commits/main"
        response._content = json.dumps(payload).encode()
        return response

    def test_empty_repository_is_explicit_missing_evidence_not_a_negative_label(self):
        self.frozen_study(1)
        split_before = (self.root / "splits/Apache.json").read_bytes()
        path = self.root / "raw/Apache/TEST-0.json"
        record = common.read_json(path)
        record["comments"] = [{"body": "https://github.com/a/b/pull/1"}]
        common.write_json(path, record)
        saved = common.read_json(self.root / "raw/Apache/manifest.json")
        saved["records"]["TEST-0"] = common.file_hash(path)
        common.write_json(self.root / "raw/Apache/manifest.json", saved)
        github = object.__new__(evidence.GitHub)
        github.session = mock.Mock()
        github.session.get.side_effect = [
            self.github_response(200, {"id": 123, "full_name": "a/b", "default_branch": "main"}),
            self.github_response(409, {"message": "Git Repository is empty."}),
        ]
        loader = mock.Mock(side_effect=AssertionError("An empty repository has no snapshot"))
        evidence.fetch_code(self.root, self.storage, "Apache", github=github, snapshot_loader=loader)
        result = common.read_json(self.root / "evidence/Apache/TEST-0.json")
        self.assertEqual("excluded", result["status"])
        self.assertEqual("repository_empty", result["exclusions"][0]["reason"])
        self.assertEqual([], result["evidence"])
        self.assertEqual({"excluded": 1}, common.read_json(self.root / "evidence/Apache/audit.json")["counts"])
        self.assertEqual(split_before, (self.root / "splits/Apache.json").read_bytes())
        github.session.get.reset_mock(side_effect=True)
        github.session.get.side_effect = AssertionError("Recorded empty repository must be reused")
        evidence.fetch_code(self.root, self.storage, "Apache", github=github, snapshot_loader=loader)

    def test_other_conflicts_and_auth_failures_are_not_excluded_or_retried(self):
        github = object.__new__(evidence.GitHub)
        github.session = mock.Mock()
        for status, payload, path in (
                (409, {"message": "A different conflict"}, "/repos/a/b/commits/main"),
                (409, ["Git Repository is empty."], "/repos/a/b/commits/main"),
                (409, {"message": "Git Repository is empty."}, "/repos/a/b/pulls/1"),
                (401, {"message": "Bad credentials"}, "/repos/a/b/commits/main"),
                (403, {"message": "Forbidden"}, "/repos/a/b/commits/main")):
            with self.subTest(status=status, payload=payload, path=path):
                github.session.get.reset_mock()
                github.session.get.return_value = self.github_response(status, payload)
                with mock.patch.object(evidence.time, "sleep") as sleep:
                    with self.assertRaises(requests.HTTPError):
                        github.get(path)
                    self.assertEqual(1, github.session.get.call_count)
                    sleep.assert_not_called()
        response = self.github_response(409, {})
        response._content = b"not json"
        github.session.get.return_value = response
        with self.assertRaises(requests.HTTPError):
            github.get("/repos/a/b/commits/main")

    def test_transport_errors_retry_boundedly_but_tls_errors_fail_immediately(self):
        github = object.__new__(evidence.GitHub)
        github.session = mock.Mock()
        github.session.get.side_effect = [
            requests.ConnectionError("closed"), requests.Timeout("timeout"),
            self.github_response(200, {"sha": "a" * 40}),
        ]
        with mock.patch.object(evidence.time, "sleep") as sleep:
            self.assertEqual({"sha": "a" * 40}, github.get("/repos/a/b/commits/main"))
            self.assertEqual(3, github.session.get.call_count)
            self.assertEqual([mock.call(1), mock.call(2)], sleep.call_args_list)
        github.session.get.reset_mock()
        github.session.get.side_effect = requests.ConnectionError("still closed")
        with mock.patch.object(evidence.time, "sleep") as sleep:
            with self.assertRaises(requests.ConnectionError):
                github.get("/repos/a/b/commits/main")
            self.assertEqual(5, github.session.get.call_count)
            self.assertEqual([mock.call(1), mock.call(2), mock.call(4), mock.call(8)], sleep.call_args_list)
        github.session.get.reset_mock()
        github.session.get.side_effect = requests.exceptions.SSLError("certificate verification failed")
        with mock.patch.object(evidence.time, "sleep") as sleep:
            with self.assertRaises(requests.exceptions.SSLError):
                github.get("/repos/a/b/commits/main")
            self.assertEqual(1, github.session.get.call_count)
            sleep.assert_not_called()

    def test_adf_links_and_deduplication(self):
        url = "https://github.com/owner/repo/pull/123"
        record = {"issue": {"fields": {"description": {"marks": [{"attrs": {"href": url}}]}}},
                  "comments": [{"body": url + "#discussion_r22"}]}
        self.assertEqual([url], evidence.links(record))
        self.assertEqual([], evidence.links({"issue": {"fields": {"description": "https://github.com/a/b"}}}))

    def test_actual_text_links_handle_jira_markup_adf_and_adjacent_urls(self):
        url = "https://github.com/apache/hudi/pull/12746"
        unsupported = "https://gitlab.example/a/b/merge_requests/12"
        record = {"issue": {"fields": {"description": {
            "content": [{"text": "[https://issues.example/T-1|Jira]\n" + url + url + "#comment"},
                        {"attrs": {"href": url + "/files?diff=split"}},
                        {"attrs": {"href": url + ".patch"}},
                        {"text": "[https://docs.example/a]\nhttps://github.com/a/b/commits/main"},
                        {"text": "https://app.codecov.io/gh/apache/hudi/pull/12746 " + unsupported},
                        {"text": "https://codecov.io/gh/apache/hudi/commit/abcde"},
                        {"text": "https://docs.example/?next=/pull/99"}]}}},
                  "comments": [{"body": "(" + url + ").\r\n" + unsupported}]}
        self.assertEqual(sorted([url, unsupported, "https://github.com/a/b/commits/main"]), evidence.links(record))
        for url in ("https://codecov.io.evil/gh/a/b/pull/1", "https://github.com/a/b/pull/1oops",
                    "http://github.com/a/b/pull/2"):
            self.assertEqual([url], evidence.links({"issue": {"fields": {"description": url}}}))

    def test_repository_redirect_uses_canonical_identity_for_pr_and_snapshot_metadata(self):
        github = object.__new__(evidence.GitHub)
        github.session = mock.Mock()
        redirect = self.github_response(301, {})
        redirect.headers["Location"] = "https://api.github.com/repositories/123"
        metadata = {"id": 123, "full_name": "new/repo", "default_branch": "main"}
        github.session.get.side_effect = [
            redirect, self.github_response(200, metadata), self.github_response(200, metadata),
            self.github_response(200, {"sha": "d" * 40}),
            self.github_response(200, {"merged": True, "merged_at": "2020-01-02", "changed_files": 1,
                                      "head": {"sha": "a" * 40}, "base": {"sha": "b" * 40},
                                      "merge_commit_sha": "c" * 40}),
            self.github_response(200, [{"filename": "src/A.java", "status": "modified", "sha": "e" * 40}]),
        ]
        result = github.resolve("https://github.com/old/repo/pull/1")
        self.assertEqual("new/repo", result["repository"])
        self.assertEqual("https://github.com/old/repo/pull/1", result["url"])
        self.assertEqual(123, result["repository_identity"]["repository_id"])
        self.assertEqual("old/repo", result["repository_identity"]["requested_repository"])
        self.assertEqual("a" * 40, result["revision"], "Normally merged PRs retain merged-head semantics")
        urls = [call.args[0] for call in github.session.get.call_args_list]
        self.assertEqual("https://api.github.com/repos/new/repo/pulls/1/files", urls[-1])
        self.assertTrue(all(call.kwargs["allow_redirects"] is False for call in github.session.get.call_args_list))

    def test_repository_redirect_rejects_unsafe_targets_loops_and_identity_mismatch(self):
        github = object.__new__(evidence.GitHub)
        github.session = mock.Mock()
        for target in ("http://api.github.com/repositories/123", "https://evil.example/repositories/123",
                       "https://api.github.com@evil.example/repositories/123",
                       "https://api.github.com/repos/new/repo?token=x",
                       "https://api.github.com/repos/new/repo#fragment",
                       "https://api.github.com/repos/../repo",
                       "https://api.github.com/repos/new/repo/pulls/1", "/repositories/123"):
            with self.subTest(target=target):
                response = self.github_response(301, {})
                response.headers["Location"] = target
                github.session.get.reset_mock()
                github.session.get.side_effect = [response]
                with self.assertRaisesRegex(evidence.EvidenceExcluded, "unsafe_repository_redirect"):
                    github.repository_info("old/repo")
                self.assertEqual(1, github.session.get.call_count)
        response = self.github_response(301, {})
        response.headers["Location"] = "https://api.github.com/repos/old/repo"
        github.session.get.side_effect = [response]
        with self.assertRaisesRegex(evidence.EvidenceExcluded, "repository_redirect_loop"):
            github.repository_info("old/repo")
        response.headers["Location"] = "https://api.github.com/repositories/123"
        for payloads in (
                [{"id": 456, "full_name": "new/repo"}],
                [{"id": 123, "full_name": "new/repo"}, {"id": 456, "full_name": "new/repo"}]):
            github.session.get.side_effect = [response] + [self.github_response(200, item) for item in payloads]
            with self.assertRaisesRegex(evidence.EvidenceExcluded, "repository_identity_mismatch"):
                github.repository_info("old/repo")
        responses = []
        for repo_id in range(1, 7):
            response = self.github_response(301, {})
            response.headers["Location"] = f"https://api.github.com/repositories/{repo_id}"
            responses.append(response)
        github.session.get.side_effect = responses
        with self.assertRaisesRegex(evidence.EvidenceExcluded, "repository_redirect_limit"):
            github.repository_info("old/repo")

    def landed_fixture(self):
        revision, default = "a" * 40, "d" * 40
        info = {"state": "closed", "merged": False, "closed_at": "2020-01-02T00:00:00Z",
                "merge_commit_sha": "c" * 40, "head": {"sha": "b" * 40}}
        event = {"id": 1234, "event": "closed", "created_at": info["closed_at"], "commit_id": revision,
                 "commit_url": f"https://api.github.com/repos/a/b/commits/{revision}"}
        commit = {"sha": revision, "parents": [{"sha": "f" * 40}], "commit": {
            "message": "Delivered change\n\nCloses #12 from author/branch and squashes the following commits:\n",
            "committer": {"date": info["closed_at"]}}}
        comparison = {"status": "ahead", "merge_base_commit": {"sha": revision}}
        github = object.__new__(evidence.GitHub)
        github.repository_info = mock.Mock(return_value=({"full_name": "a/b", "default_branch": "main"}, {}))
        files = [{"filename": "landed.py", "status": "modified", "sha": "e" * 40}]
        github.get = mock.Mock(side_effect=[{"sha": default}, info, [event], commit, comparison, {"files": files}])
        return github, info, event, commit, comparison

    def test_closed_pr_requires_delivery_proof_and_uses_landed_not_head_or_test_merge(self):
        github, info, event, commit, comparison = self.landed_fixture()
        result = github.resolve("https://github.com/a/b/pull/12")
        self.assertEqual(commit["sha"], result["revision"])
        self.assertNotIn(result["revision"], (info["head"]["sha"], info["merge_commit_sha"]))
        self.assertEqual("landed.py", result["files"][0]["path"])
        self.assertEqual("closed_pr_landed_commit", result["provenance"]["resolution"])
        self.assertFalse(result["provenance"]["github_merged"])
        self.assertEqual(event["id"], result["provenance"]["closure_event_id"])
        self.assertEqual(f"/repos/a/b/commits/{commit['sha']}", github.get.call_args_list[-1].args[0])
        self.assertFalse(any("/pulls/12/files" in call.args[0] for call in github.get.call_args_list))

    def test_corrected_links_fetch_landed_snapshot_but_unknown_code_still_blocks_completeness(self):
        self.frozen_study(2)
        split_before = (self.root / "splits/Apache.json").read_bytes()
        saved = common.read_json(self.root / "raw/Apache/manifest.json")
        url = "https://github.com/a/b/pull/12"
        for index in range(2):
            path = self.root / "raw/Apache" / f"TEST-{index}.json"
            record = common.read_json(path)
            record["comments"] = [{"body": "[https://issues.example/T-1|Jira]\n" + url + url +
                                   " https://codecov.io/gh/a/b/pull/12"}]
            if index:
                record["comments"].append({"body": "https://unknown.example/a/b/merge_requests/1"})
            common.write_json(path, record)
            saved["records"][f"TEST-{index}"] = common.file_hash(path)
        common.write_json(self.root / "raw/Apache/manifest.json", saved)
        snapshot = self.storage / "snapshot"
        (snapshot / "source").mkdir(parents=True)
        (snapshot / "source/landed.py").write_text("print('landed')\n")
        manifest = {"repository": "a/b", "revision": "a" * 40,
                    "files": common.tree_manifest(snapshot / "source")}
        common.write_json(snapshot / "manifest.json", manifest)
        loader = mock.Mock(return_value=(snapshot, manifest))
        github, _, _, _, _ = self.landed_fixture()
        evidence.fetch_code(self.root, self.storage, "Apache", github=github, snapshot_loader=loader)
        first = common.read_json(self.root / "evidence/Apache/TEST-0.json")
        second = common.read_json(self.root / "evidence/Apache/TEST-1.json")
        self.assertEqual("complete", first["status"])
        self.assertEqual([url], first["links"])
        self.assertEqual("excluded", second["status"])
        self.assertEqual(["unsupported_evidence_url"], [item["reason"] for item in second["exclusions"]])
        self.assertEqual("a" * 40, first["evidence"][0]["revision"])
        self.assertEqual([mock.call(self.storage, "a/b", "a" * 40)] * 2, loader.call_args_list)
        self.assertEqual(split_before, (self.root / "splits/Apache.json").read_bytes())
        self.assertEqual(100, common.read_json(self.root / "study.json")["min_rows"])

    def test_closed_pr_rejects_missing_ambiguous_or_wrong_closure_and_message(self):
        for mode in ("open", "null", "referenced", "old_closure", "ambiguous", "foreign_commit",
                     "wrong_sha", "mention_only", "other_pr", "multiple_prs", "diverged", "wrong_merge_base"):
            with self.subTest(mode=mode):
                github, info, event, commit, comparison = self.landed_fixture()
                events = [event]
                if mode == "open":
                    info["state"] = "open"
                elif mode == "null":
                    event["commit_id"] = None
                elif mode == "referenced":
                    event["event"] = "referenced"
                elif mode == "old_closure":
                    event["created_at"] = "2020-01-01T00:00:00Z"
                elif mode == "ambiguous":
                    events.append({**event, "id": 5678, "commit_id": "e" * 40})
                elif mode == "foreign_commit":
                    event["commit_url"] = event["commit_url"].replace("/a/b/", "/other/repo/")
                elif mode == "wrong_sha":
                    commit["sha"] = "e" * 40
                elif mode == "mention_only":
                    commit["commit"]["message"] = "Discuss #12; not delivered."
                elif mode == "other_pr":
                    commit["commit"]["message"] = commit["commit"]["message"].replace("#12", "#123")
                elif mode == "multiple_prs":
                    commit["commit"]["message"] *= 2
                elif mode == "diverged":
                    comparison["status"] = "diverged"
                elif mode == "wrong_merge_base":
                    comparison["merge_base_commit"]["sha"] = "f" * 40
                github.get.side_effect = [{"sha": "d" * 40}, info, events, commit, comparison]
                with self.assertRaises(evidence.EvidenceExcluded):
                    github.resolve("https://github.com/a/b/pull/12")

    def test_landed_pr_paginates_events_and_refuses_incomplete_file_inventories(self):
        github, info, event, commit, comparison = self.landed_fixture()
        first_page = [{"id": i, "event": "referenced"} for i in range(100)]
        github.get.side_effect = [first_page, [event], commit, comparison]
        resolved, _ = github.landed_pr("a/b", "12", info, "d" * 40)
        self.assertEqual(commit, resolved)
        self.assertEqual({"per_page": 100, "page": 2}, github.get.call_args_list[1].args[1])
        github.get.side_effect = None
        github.get.return_value = first_page
        with self.assertRaisesRegex(evidence.EvidenceExcluded, "pr_event_api_limit"):
            github.landed_pr("a/b", "12", info, "d" * 40)
        github.get.return_value = {"files": [{"filename": f"{i}.py"} for i in range(100)]}
        with self.assertRaisesRegex(evidence.EvidenceExcluded, "changed_file_api_limit"):
            github.commit_files("a/b", commit)
        commit["parents"].append({"sha": "e" * 40})
        github.get.return_value = {"files": [{"filename": f"{i}.py"} for i in range(300)]}
        with self.assertRaisesRegex(evidence.EvidenceExcluded, "merge_diff_api_limit"):
            github.commit_files("a/b", commit)
        github.get.return_value = {}
        with self.assertRaisesRegex(ValueError, "Invalid changed-file"):
            github.commit_files("a/b", commit)
