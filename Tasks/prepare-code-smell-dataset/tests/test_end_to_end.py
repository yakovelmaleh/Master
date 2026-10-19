from pathlib import Path
from unittest import mock

import pandas as pd

from Code_Smells_Detection.runtime import collection, common, detectors, evidence, models, prepare
from Code_Smells_Detection.runtime.tests.support import RuntimeCase


class EndToEndTests(RuntimeCase):
    def test_fixed_cohort_to_held_out_predictions(self):
        self.run_pipeline()

    def test_approved_missing_candidate_never_enters_features_labels_or_models(self):
        self.run_pipeline(unavailable=True)

    def run_pipeline(self, unavailable=False):
        candidates = self.storage / "candidates.csv"
        sources = self.storage / "sources.csv"
        pd.DataFrame([{"source": "Apache", "issue_key": f"T-{index}", "issue_type": "Story",
                       "created": str(pd.Timestamp("2020-01-01") + pd.Timedelta(days=index))}
                      for index in range(120)]).to_csv(candidates, index=False)
        pd.DataFrame([{"source": "Apache", "candidate_count": 120,
                       "base_url": "https://example.invalid", "jql": "type != Bug"}]).to_csv(sources, index=False)
        with mock.patch.object(prepare, "CANDIDATE_HASH", common.file_hash(candidates)), mock.patch.object(
                prepare, "SOURCES", {"Apache": 120}):
            prepare.audit(self.root, candidates, sources)
        class Client:
            def fields(self):
                return {"Sprint": "sprint"}

            def issue(self, key, fields):
                if unavailable and key == "T-119":
                    raise collection.CollectionError("not_found_or_not_visible", 404)
                index = int(key.split("-")[1])
                date = pd.Timestamp("2020-01-01") + pd.Timedelta(days=index)
                return {"key": key, "fields": {
                    "created": str(date), "sprint": [{"startDate": str(date + pd.Timedelta(hours=3))}],
                    "summary": "TODO" if index % 2 else "Please implement safe behavior",
                    "description": "acceptance criteria", "issuetype": {"name": "Story"},
                    "project": {"key": "TEST"}, "priority": {"name": "High"},
                    "creator": {"name": "fixture"},
                }}

            def comments(self, key):
                index = int(key.split("-")[1])
                date = pd.Timestamp("2020-01-01") + pd.Timedelta(days=index, hours=1)
                return [{"id": key, "created": str(date), "body": f"https://github.com/example/project/pull/{index + 1}"}]

            def changelog(self, key):
                return []

        if unavailable:
            with self.assertRaisesRegex(ValueError, "1 incomplete"):
                prepare.enrich(self.root, "Apache", lambda _: Client())
            ledger = common.read_json(self.root / "raw/Apache/missing_records.proposed.json")
            ledger.update(approved=True, reviewed_at=common.now(), review_note="Reviewed missing fixture.")
            approval = self.storage / "approved.json"
            common.write_json(approval, ledger)
            prepare.enrich(self.root, "Apache", missing_records=approval)
        else:
            prepare.enrich(self.root, "Apache", lambda _: Client())
        self.succeeded("enrich", "Apache")
        prepare.freeze(self.root, "Apache")
        self.succeeded("freeze", "Apache")
        before = common.read_json(self.root / "splits/Apache.json")
        snapshot = self.storage / "snapshot"
        (snapshot / "source/src").mkdir(parents=True)
        for name in ("Bad", "Clean"):
            (snapshot / "source/src" / (name + ".java")).write_text("class " + name + " {}")
        common.write_json(snapshot / "manifest.json", {
            "repository": "example/project", "revision": "a" * 40,
            "files": common.tree_manifest(snapshot / "source"),
        })
        class GitHub:
            def resolve(self, url):
                number = int(url.rsplit("/", 1)[1])
                return {"url": url, "repository": "example/project", "revision": "a" * 40,
                        "files": [{"path": "src/" + ("Bad" if number % 2 else "Clean") + ".java",
                                   "language": "java", "status": "modified"}]}
        evidence.fetch_code(self.root, self.storage, "Apache", github=GitHub(),
                            snapshot_loader=lambda *_: (snapshot, common.read_json(snapshot / "manifest.json")))
        self.succeeded("fetch-code", "Apache")
        profile = self.profile()
        profile_path = self.storage / "profile.json"
        common.write_json(profile_path, profile)
        def fake_execute(tool, spec, workspace, output):
            self.native_output(output)
            return detectors.parse_reports(output, workspace, spec)
        with mock.patch.object(detectors, "qualified", return_value=self.storage), mock.patch.object(
                detectors, "execute", side_effect=fake_execute) as runner:
            detectors.detect(self.root, self.storage, "Apache", profile_path)
            self.assertEqual(1, runner.call_count, "Shared commit must be analyzed once.")
        detectors.labels(self.root)
        self.succeeded("labels")
        self.assertEqual(before, common.read_json(self.root / "splits/Apache.json"))
        labels = pd.read_csv(self.root / "labels/story_labels.csv")
        self.assertEqual(119 if unavailable else 120, len(labels))
        if unavailable:
            self.assertNotIn("Apache:T-119", before["assignment"])
            self.assertNotIn("Apache:T-119", labels.row_id.tolist())
        self.assertEqual(60, labels.any_supported_smell.sum())
        config = self.storage / "config.json"
        common.write_json(config, {"seed": 7, "bootstrap_samples": 2, "models": {
            "RF": [{"n_estimators": 2, "max_depth": 2}],
            "XGboost": [{"n_estimators": 2, "max_depth": 2}],
            "NN": [{"hidden_layer_sizes": [3], "max_iter": 5}],
        }})
        expected = models.validate(self.root, config)
        self.assertEqual(18, len(expected["matrix"]))
        models.train(self.root, "Apache")
        self.succeeded("train", "Apache")
        models.seal(self.root)
        self.succeeded("seal")
        models.test(self.root, "Apache")
        self.succeeded("test", "Apache")
        report = models.report(self.root)
        self.assertTrue(report["complete"])
        self.assertEqual(not unavailable, report["collection_complete"])
        self.assertEqual(int(unavailable), report["retention"]["sources"]["Apache"]["collection"]["approved_unavailable"])
        if unavailable:
            self.assertIn("complete_with_approved_missing", (self.root / "reports/report.html").read_text())
            for path in (self.root / "models").rglob("test_predictions.csv"):
                self.assertNotIn("Apache:T-119", pd.read_csv(path).row_id.tolist())
        self.assertEqual(18, sum(item["status"] == "succeeded" for item in report["results"]))
        self.assertEqual(45, len(report["paired_comparisons"]))
        self.assertEqual(6, len(report["multilabel"]))
