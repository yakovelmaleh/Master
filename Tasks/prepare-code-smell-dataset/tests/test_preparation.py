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
        github.get = mock.Mock(side_effect=[
            {"default_branch": "main"}, {"sha": "a" * 40}, {"merged": False},
        ])
        with self.assertRaisesRegex(evidence.EvidenceExcluded, "pr_not_merged"):
            github.resolve("https://github.com/a/b/pull/1")

    def test_commit_must_be_on_default_history(self):
        github = object.__new__(evidence.GitHub)
        github.get = mock.Mock(side_effect=[
            {"default_branch": "main"}, {"sha": "b" * 40},
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
            self.github_response(200, {"default_branch": "main"}),
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
