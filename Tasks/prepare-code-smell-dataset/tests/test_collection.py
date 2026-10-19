import copy
import json
from unittest import mock

import pandas as pd

from Code_Smells_Detection.runtime import collection, common, migration, prepare
from Code_Smells_Detection.runtime.tests.support import RuntimeCase


class Client:
    def __init__(self, failures=None):
        self.failures = failures or {}
        self.requested = []

    def fields(self):
        return {"Sprint": "sprint"}

    def issue(self, key, fields):
        self.requested.append(key)
        if key in self.failures:
            raise self.failures[key]
        return {"key": key, "fields": {
            "created": "2020-01-01", "sprint": [{"startDate": "2020-01-02"}],
            "summary": "Implement safely", "creator": {"name": "fixture"},
            "issuetype": {"name": "Story"}, "project": {"key": "T"}}}

    def comments(self, key):
        return [{"id": key, "created": "2020-01-01T12:00:00"}]

    def changelog(self, key):
        return []


class CollectionTests(RuntimeCase):
    def setUp(self):
        super().setUp()
        self.make_study(120)

    def make_study(self, count, last_key=None):
        self.candidates = self.storage / "candidates.csv"
        self.sources = self.storage / "sources.csv"
        pd.DataFrame([{"source": "Apache", "issue_key": last_key if last_key and i == count - 1 else f"T-{i}", "issue_type": "Story",
                       "created": "2020-01-01"} for i in range(count)]).to_csv(self.candidates, index=False)
        pd.DataFrame([{"source": "Apache", "candidate_count": count,
                       "base_url": "https://example.invalid", "jql": "test"}]).to_csv(self.sources, index=False)
        for name, value in (("CANDIDATE_HASH", common.file_hash(self.candidates)), ("SOURCES", {"Apache": count})):
            patch = mock.patch.object(prepare, name, value)
            patch.start()
            self.addCleanup(patch.stop)
        prepare.audit(self.root, self.candidates, self.sources)
        self.raw = self.root / "raw/Apache"

    def diagnose(self, failures=None):
        client = Client(failures or {"T-119": collection.CollectionError("not_found_or_not_visible", 404)})
        prepare.enrich(self.root, "Apache", lambda _: client, diagnose=True)
        return client

    def approval(self):
        ledger = common.read_json(self.raw / "missing_records.proposed.json")
        ledger.update(approved=True, reviewed_at=common.now(), review_note="Reviewed issue-level collection evidence.")
        path = self.storage / "approved.json"
        common.write_json(path, ledger)
        return path

    def test_strict_default_and_approved_missing_preserve_candidate_accounting(self):
        client = Client({"T-119": collection.CollectionError("authentication_or_permission_denied", 401)})
        with self.assertRaisesRegex(ValueError, "1 incomplete"):
            prepare.enrich(self.root, "Apache", lambda _: client)
        self.assertFalse((self.raw / "manifest.json").exists())
        with self.assertRaisesRegex(ValueError, "Required stage"):
            prepare.freeze(self.root, "Apache")
        approval = self.approval()
        prepare.enrich(self.root, "Apache", lambda _: self.fail("Approval must not perform network calls"),
                       missing_records=approval)
        self.succeeded("enrich", "Apache")
        prepare.freeze(self.root, "Apache")
        self.succeeded("freeze", "Apache")
        frame, split = prepare.frozen_frame(self.root, "Apache")
        self.assertEqual(119, len(frame))
        self.assertNotIn("Apache:T-119", split["assignment"])
        decisions = common.read_json(self.root / "features/Apache/filter_decisions.json")
        self.assertEqual(120, len(decisions))
        self.assertEqual("jira_unavailable", next(row["reason"] for row in decisions if row["row_id"] == "Apache:T-119"))
        saved, approved = collection.load_manifest(self.root, "Apache", set(prepare.source_candidates(self.root, "Apache").issue_key))
        counts = collection.summary(prepare.source_candidates(self.root, "Apache"), saved["records"], approved)
        self.assertEqual((120, 119, 1, 0), tuple(counts[key] for key in
                                              ("candidates", "collected_complete", "approved_unavailable", "unresolved")))
        before = (self.root / "splits/Apache.json").read_bytes()
        prepare.freeze(self.root, "Apache")
        self.assertEqual(before, (self.root / "splits/Apache.json").read_bytes())
        common.write_json(self.raw / "T-119.json", {"collection_complete": True})
        with self.assertRaisesRegex(ValueError, "appeared after finalization"):
            prepare.frozen_frame(self.root, "Apache")
        (self.raw / "T-119.json").unlink()
        common.write_json(self.raw / "collection_exclusions.json", {})
        with self.assertRaisesRegex(ValueError, "provenance changed"):
            prepare.frozen_frame(self.root, "Apache")

    def test_diagnosis_recovers_only_missing_records_and_does_not_finalize(self):
        self.diagnose()
        before = common.file_hash(self.raw / "T-0.json")
        client = Client()
        prepare.enrich(self.root, "Apache", lambda _: client, diagnose=True)
        self.assertEqual(["T-119"], client.requested)
        self.assertEqual(before, common.file_hash(self.raw / "T-0.json"))
        self.assertFalse((self.raw / "manifest.json").exists())
        prepare.enrich(self.root, "Apache", lambda _: self.fail("All records are cached"))
        self.assertEqual(120, len(common.read_json(self.raw / "manifest.json")["records"]))

    def test_approval_rejects_unknown_transient_and_non_issue_failures(self):
        self.diagnose()
        diagnostic_path = self.raw / "collection_diagnostics.json"
        original = common.read_json(diagnostic_path)
        for operation, status, reason in (
                ("issue", 503, "http_failure"),
                ("issue", None, "unclassified_collection_failure"),
                ("changelog", 404, "not_found_or_not_visible"),
                ("comments", 403, "authentication_or_permission_denied")):
            with self.subTest(operation=operation, status=status):
                diagnostics = copy.deepcopy(original)
                diagnostics["missing"]["T-119"].update(operation=operation, http_status=status, reason=reason)
                common.write_json(diagnostic_path, diagnostics)
                ledger = common.read_json(self.approval())
                ledger["diagnostics_sha256"] = common.file_hash(diagnostic_path)
                ledger["records"]["T-119"] = reason
                common.write_json(self.storage / "approved.json", ledger)
                with self.assertRaisesRegex(ValueError, "cannot be approved"):
                    prepare.enrich(self.root, "Apache", missing_records=self.storage / "approved.json")
                self.assertFalse((self.raw / "manifest.json").exists())

    def test_review_requires_current_inventory_exact_ids_and_explicit_approval(self):
        self.diagnose()
        path = self.approval()
        original = common.read_json(path)
        for change in (
                {"approved": False}, {"review_note": ""}, {"reviewed_at": "2020-01-01"},
                {"candidate_ids_sha256": "changed"}, {"records": {"OTHER-1": "not_found_or_not_visible"}},
                {"records": {"T-0": "not_found_or_not_visible", "T-119": "not_found_or_not_visible"}},
                {"diagnostics_sha256": "changed"}):
            with self.subTest(change=change):
                common.write_json(path, {**original, **change})
                with self.assertRaises(ValueError):
                    prepare.enrich(self.root, "Apache", missing_records=path)
        common.write_json(path, original)
        record = common.read_json(self.raw / "T-0.json")
        record["collected_at"] = common.now()
        common.write_json(self.raw / "T-0.json", record)
        with self.assertRaisesRegex(ValueError, "inventory changed"):
            prepare.enrich(self.root, "Apache", missing_records=path)
        path.write_text('{"records":{"T-119":"one","T-119":"two"}}')
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            collection.read_review(path)

    def test_access_controls_block_global_failure_and_require_project_review(self):
        self.diagnose()
        path = self.raw / "collection_diagnostics.json"
        original = common.read_json(path)
        for scope in ("source", "T"):
            diagnostics = copy.deepcopy(original)
            control = diagnostics["controls"]["source"] if scope == "source" else diagnostics["controls"]["projects"][scope]
            control["status"] = "failed"
            common.write_json(path, diagnostics)
            ledger = common.read_json(self.approval())
            ledger["diagnostics_sha256"] = common.file_hash(path)
            approved_path = self.storage / "approved.json"
            common.write_json(approved_path, ledger)
            with self.assertRaisesRegex(ValueError, "access control failed"):
                prepare.enrich(self.root, "Apache", missing_records=approved_path)
        self.root = self.storage / "runs/no-project-control"
        self.make_study(120, last_key="OTHER-119")
        self.diagnose({"OTHER-119": collection.CollectionError("not_found_or_not_visible", 404)})
        approved_path = self.approval()
        ledger = common.read_json(approved_path)
        with self.assertRaisesRegex(ValueError, "Explicitly review"):
            prepare.enrich(self.root, "Apache", missing_records=approved_path)
        ledger["reviewed_uncontrolled_projects"] = ["OTHER"]
        common.write_json(approved_path, ledger)
        prepare.enrich(self.root, "Apache", missing_records=approved_path)

    def test_changed_required_field_mapping_is_not_mixed_with_cache(self):
        self.diagnose()
        client = Client()
        client.fields = lambda: {"Sprint": "new_sprint"}
        with self.assertRaisesRegex(ValueError, "field mappings changed"):
            prepare.enrich(self.root, "Apache", lambda _: client, diagnose=True)
        self.assertEqual([], client.requested)

    def test_http_diagnostics_do_not_persist_response_text(self):
        response = mock.Mock(status_code=404, text="sensitive response", url="https://example.invalid/?token=secret")
        with self.assertRaises(collection.CollectionError) as caught:
            prepare.CompleteJiraClient.response_json(response)
        observed = collection.failure(caught.exception, "issue")
        self.assertEqual(404, observed["http_status"])
        self.assertNotIn("secret", json.dumps(observed))
        self.assertNotIn("sensitive", str(caught.exception))

    def test_migration_preserves_frozen_bytes_and_parent_and_rejects_changes(self):
        self.root = self.storage / "runs/parent758"
        self.make_study(758)
        prepare.enrich(self.root, "Apache", lambda _: Client())
        self.succeeded("enrich", "Apache")
        prepare.freeze(self.root, "Apache")
        self.succeeded("freeze", "Apache")
        self.assertEqual({"train": 454, "validation": 151, "test": 153},
                         common.read_json(self.root / "splits/Apache.json")["counts"])
        # Build the exact supported old artifact shape, without new diagnostic files.
        for name in ("collection_diagnostics.json", "missing_records.proposed.json"):
            (self.raw / name).unlink()
        parent_hash = common.read_json(self.root / "study.json")["source_sha256"]
        before = common.tree_manifest(self.root)
        target = self.storage / "runs/migrated"
        with mock.patch.object(migration, "PARENT_SOURCE_SHA256", parent_hash):
            migration.migrate(target, self.root)
            migration.migrate(target, self.root)
        self.assertEqual(before, common.tree_manifest(self.root))
        self.assertFalse((target / "status/freeze-Apache.json").exists())
        split_before = (target / "splits/Apache.json").read_bytes()
        features_before = (target / "features/Apache/features.csv").read_bytes()
        prepare.freeze(target, "Apache")
        self.assertEqual(split_before, (target / "splits/Apache.json").read_bytes())
        self.assertEqual(features_before, (target / "features/Apache/features.csv").read_bytes())
        self.assertEqual(before["raw/Apache/T-0.json"], common.file_hash(target / "raw/Apache/T-0.json"))
        (target / "raw/Apache/T-0.json").write_text("{}")
        with mock.patch.object(migration, "PARENT_SOURCE_SHA256", parent_hash):
            with self.assertRaisesRegex(ValueError, "destination changed"):
                migration.migrate(target, self.root)
        self.assertEqual(before, common.tree_manifest(self.root))
        record = common.read_json(self.raw / "T-0.json")
        record["issue"]["fields"]["summary"] = "changed"
        common.write_json(self.raw / "T-0.json", record)
        with mock.patch.object(migration, "PARENT_SOURCE_SHA256", parent_hash):
            with self.assertRaisesRegex(ValueError, "Parent raw manifest differs"):
                migration.migrate(self.storage / "runs/rejected", self.root)
        self.assertFalse((self.storage / "runs/rejected/study.json").exists())

    def test_partial_migration_is_resumable_and_old_code_hash_remains_enforced(self):
        self.diagnose()
        for name in ("collection_diagnostics.json", "missing_records.proposed.json"):
            (self.raw / name).unlink()
        parent_hash = common.read_json(self.root / "study.json")["source_sha256"]
        before = common.tree_manifest(self.root)
        target = self.storage / "runs/migrated"
        with self.assertRaisesRegex(ValueError, "Unsupported parent"):
            migration.migrate(target, self.root)
        with mock.patch.object(migration, "PARENT_SOURCE_SHA256", parent_hash):
            original_copy = migration.atomic_bytes
            def interrupted_copy(path, content):
                if path.name == "T-20.json":
                    raise OSError("interrupted")
                return original_copy(path, content)
            with mock.patch.object(migration, "atomic_bytes", side_effect=interrupted_copy):
                with self.assertRaisesRegex(OSError, "interrupted"):
                    migration.migrate(target, self.root)
            with self.assertRaisesRegex(ValueError, "migration is incomplete"):
                common.verify_study(target)
            migration.migrate(target, self.root)
        self.assertEqual(before, common.tree_manifest(self.root))
        self.assertFalse((target / "status/enrich-Apache.json").exists())
        client = Client()
        prepare.enrich(target, "Apache", lambda _: client)
        self.assertEqual(["T-119"], client.requested)
        study = common.read_json(target / "study.json")
        study["source_sha256"] = "changed"
        common.write_json(target / "study.json", study)
        with self.assertRaisesRegex(ValueError, "code/schema changed"):
            common.verify_study(target)
