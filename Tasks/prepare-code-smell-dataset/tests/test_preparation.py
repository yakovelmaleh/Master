import io
import json
from pathlib import Path
import tarfile
from unittest import mock

import pandas as pd

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

    def test_adf_links_and_deduplication(self):
        url = "https://github.com/owner/repo/pull/123"
        record = {"issue": {"fields": {"description": {"marks": [{"attrs": {"href": url}}]}}},
                  "comments": [{"body": url + "#discussion_r22"}]}
        self.assertEqual([url], evidence.links(record))
        self.assertEqual([], evidence.links({"issue": {"fields": {"description": "https://github.com/a/b"}}}))
