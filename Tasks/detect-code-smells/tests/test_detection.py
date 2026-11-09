import copy
import os
from pathlib import Path
import platform
import sys
from unittest import mock

import pandas as pd

from Code_Smells_Detection.runtime import cli, cluster, common, detectors, models, windows
from Code_Smells_Detection.runtime.tests.support import RuntimeCase


class DetectionTests(RuntimeCase):
    def bounded_fixture(self, kinds):
        _, assignment = self.frozen_study(len(kinds))
        profile = self.profile()
        profile.update(platform=platform.system(), command=[sys.executable, "{input}", "{output}"])
        profile["artifacts"] = [{"name": "DesigniteJavaCommunity.jar", "sha256": detectors.JAVA_COMMUNITY_SHA256}]
        profile_path = self.storage / "profile.json"
        common.write_json(profile_path, profile)
        snapshots = {}
        for kind in set(kinds):
            cache = self.storage / kind
            source = cache / "source"
            (source / "src").mkdir(parents=True)
            for name in ("Bad", "Clean", "Gap"):
                (source / "src" / (name + ".java")).write_text("class " + name + " {}")
            (source / "kind.txt").write_text(kind)
            common.write_json(cache / "manifest.json", {"files": common.tree_manifest(source)})
            snapshots[kind] = {
                "repository": "example/" + kind, "revision": "a" * 40, "snapshot": str(cache),
                "snapshot_manifest_sha256": common.file_hash(cache / "manifest.json"),
                "files": [{"path": "src/Gap.java" if kind == "gap" else "src/Clean.java",
                           "language": "java", "status": "modified"}],
            }
        records, manifest = [], {}
        for index, kind in enumerate(kinds):
            row_id = f"Apache:TEST-{index}"
            record = {"row_id": row_id, "source": "Apache", "partition": assignment[row_id],
                      "status": "complete", "evidence": [copy.deepcopy(snapshots[kind])]}
            if kind in ("native", "unconfigured"):
                record["evidence"][0]["files"].append(
                    {"path": "script.py", "language": "python", "status": "modified"})
            records.append(record)
            path = self.root / "evidence/Apache" / f"TEST-{index}.json"
            common.write_json(path, record)
            manifest[row_id] = common.file_hash(path)
        common.write_json(self.root / "evidence/Apache/manifest.json", {
            "records": manifest, "split_sha256": common.file_hash(self.root / "splits/Apache.json")})
        self.succeeded("fetch-code", "Apache")
        return profile_path, profile, records

    def bounded_native(self, command, **kwargs):
        source, output = map(Path, command[1:])
        if (source / "kind.txt").read_text() == "native":
            kwargs["stdout"].write(
                'Exception while parsing literal number (during Magic Number detection). '
                'For input string: "ffffffffffffffff"\nDone.\n')
            kwargs["stderr"].write("Ancestors analysis skipped due to memory overflow.")
        else:
            self.native_output(output)

    def test_bounded_exclusion_continues_caches_and_excludes_whole_multilanguage_story(self):
        path, profile, records = self.bounded_fixture(["native", "gap", "clean"])
        before = (self.root / "splits/Apache.json").read_bytes()
        with mock.patch.object(detectors, "qualified", return_value=self.storage), mock.patch.object(
                detectors.subprocess, "run", side_effect=self.bounded_native) as runner:
            detectors.detect(self.root, self.storage, "Apache", path, 10)
            self.assertEqual(3, runner.call_count)
            runner.reset_mock()
            detectors.detect(self.root, self.storage, "Apache", path, 10)
            runner.assert_not_called()
            with self.assertRaisesRegex(ValueError, "Immutable manifest differs"):
                detectors.detect(self.root, self.storage, "Apache", path)
        ledger = common.read_json(self.root / "detection/exclusions/Apache.json")
        self.assertEqual(2, ledger["count"])
        self.assertEqual({"Apache:TEST-0", "Apache:TEST-1"}, set(ledger["stories"]))
        failure_dir = self.root / "detection/results" / detectors.detection_key(records[0]["evidence"][0], profile)
        self.assertFalse((failure_dir / "result.json").exists(), "Native failures must have no findings/coverage result.")
        failure = common.read_json(failure_dir / "failure.json")
        self.assertEqual(["ancestor_memory_overflow", "magic_number_literal"], failure["reasons"])
        detectors.labels(self.root)
        labels = pd.read_csv(self.root / "labels/story_labels.csv")
        self.assertEqual(["Apache:TEST-2"], labels.row_id.tolist())
        self.assertEqual([0], labels.any_supported_smell.tolist())
        self.assertEqual(before, (self.root / "splits/Apache.json").read_bytes())
        detectors.labels(self.root)
        self.succeeded("labels")
        matrix = models.validate(self.root)
        self.assertTrue(all(x["reason"] == "fewer_than_100_fully_labeled_stories" for x in matrix["matrix"]))
        policy_path = self.root / "detection/policies/Apache.json"
        original_policy = policy_path.read_bytes()
        policy = common.read_json(policy_path)
        policy["max_incomplete_stories"] = 9
        common.write_json(policy_path, policy)
        with self.assertRaisesRegex(ValueError, "policy changed"):
            models.load_labels(self.root)
        policy_path.write_bytes(original_policy)
        log = failure_dir / failure["attempt"] / "output.err"
        log.write_text("changed")
        with mock.patch.object(detectors, "qualified", return_value=self.storage):
            with self.assertRaisesRegex(ValueError, "Artifact tree changed"):
                detectors.detect(self.root, self.storage, "Apache", path, 10)
        with self.assertRaisesRegex(ValueError, "Artifact tree changed"):
            detectors.labels(self.root)

    def test_cap_counts_unique_stories_not_snapshots_and_stops_before_later_work(self):
        path, profile, records = self.bounded_fixture(["native"] * 11 + ["clean"])
        with mock.patch.object(detectors, "qualified", return_value=self.storage), mock.patch.object(
                detectors.subprocess, "run", side_effect=self.bounded_native) as runner:
            with self.assertRaisesRegex(ValueError, "cap exceeded: 11 stories, limit 10"):
                detectors.detect(self.root, self.storage, "Apache", path, 10)
            self.assertEqual(1, runner.call_count, "One failed snapshot affects eleven unique stories.")
        ledger = common.read_json(self.root / "detection/exclusions/Apache.json")
        self.assertEqual("cap_exceeded", ledger["status"])
        self.assertEqual(11, ledger["count"])
        self.assertFalse(common.read_json(self.root / "detection/coverage/Apache-java.json")["scan_complete"])
        with self.assertRaisesRegex(ValueError, "cap exceeded"):
            detectors.labels(self.root)
        self.assertFalse((self.root / "labels/story_labels.csv").exists())

    def test_unconfigured_language_is_not_an_automatic_exclusion(self):
        path, profile, records = self.bounded_fixture(["gap", "unconfigured", "clean"])
        with mock.patch.object(detectors, "qualified", return_value=self.storage), mock.patch.object(
                detectors.subprocess, "run", side_effect=self.bounded_native):
            detectors.detect(self.root, self.storage, "Apache", path, 10)
        with self.assertRaisesRegex(ValueError, "missing/incomplete"):
            detectors.labels(self.root)
        ledger = common.read_json(self.root / "detection/exclusions/Apache.json")
        self.assertEqual(["Apache:TEST-0"], list(ledger["stories"]))
        self.assertFalse((self.root / "labels/story_labels.csv").exists())

    def test_source_modification_with_known_native_error_still_aborts(self):
        path, profile, records = self.bounded_fixture(["native", "clean"])
        def mutate(command, **kwargs):
            self.bounded_native(command, **kwargs)
            (Path(command[1]) / "src/Clean.java").write_text("modified")
        with mock.patch.object(detectors, "qualified", return_value=self.storage), mock.patch.object(
                detectors.subprocess, "run", side_effect=mutate) as runner:
            with self.assertRaisesRegex(ValueError, "Analyzer modified original"):
                detectors.detect(self.root, self.storage, "Apache", path, 10)
            self.assertEqual(1, runner.call_count)
        self.assertEqual([], list((self.root / "detection/results").glob("*/failure.json")))

    def test_ten_story_boundary_and_duplicate_evidence_count_once(self):
        path, profile, records = self.bounded_fixture(["gap"] * 10 + ["clean"])
        for record in records[:10]:
            record["evidence"] *= 2
        with mock.patch.object(detectors, "qualified", return_value=self.storage), mock.patch.object(
                detectors, "evidence_records", return_value=records), mock.patch.object(
                detectors.subprocess, "run", side_effect=self.bounded_native) as runner:
            detectors.detect(self.root, self.storage, "Apache", path, 10)
            self.assertEqual(2, runner.call_count)
        detectors.labels(self.root)
        self.assertEqual(10, len(common.read_json(self.root / "labels/exclusions.json")))
        self.assertEqual(["Apache:TEST-10"], pd.read_csv(self.root / "labels/story_labels.csv").row_id.tolist())

    def test_cap_combines_languages_and_cannot_be_bypassed_by_manual_review(self):
        path, profile, records = self.bounded_fixture(["gap"] * 6 + ["clean"] * 6)
        with mock.patch.object(detectors, "qualified", return_value=self.storage), mock.patch.object(
                detectors.subprocess, "run", side_effect=self.bounded_native):
            detectors.detect(self.root, self.storage, "Apache", path, 10)
        policy = detectors.exclusion_policy(self.root, "Apache")
        python = self.profile("python")
        extra = copy.deepcopy(records)
        for record in extra[6:11]:
            record["evidence"][0]["files"].append({"path": "missing.py", "language": "python"})
        item = extra[6]["evidence"][0]
        key = detectors.detection_key(item, python)
        directory = self.root / "detection/results" / key
        (directory / "reports").mkdir(parents=True)
        common.write_json(directory / "result.json", {
            "key": key, "status": "analyzed", "profile_sha256": common.digest(python),
            "reports": {}, "coverage": [], "findings": [],
        })
        with self.assertRaisesRegex(ValueError, "cap exceeded: 11"):
            detectors.bounded_exclusions(self.root, "Apache", extra, {"java": profile, "python": python}, policy)
        review = self.storage / "review.json"
        common.write_json(review, {f"Apache:TEST-{i}": "reviewed" for i in range(6, 11)})
        with self.assertRaisesRegex(ValueError, "cap exceeded including reviewed"):
            detectors.labels(self.root, review)

    def test_native_allowlist_never_swallows_license_unknown_or_configuration_errors(self):
        profile = self.profile()
        profile["artifacts"] = [{"name": "DesigniteJavaCommunity.jar", "sha256": detectors.JAVA_COMMUNITY_SHA256}]
        known = ('Exception while parsing literal number (during Magic Number detection). '
                 'For input string: "8000000000000000"\n'
                 'Ancestors analysis skipped due to memory overflow.'
                 'Cyclic dependency analysis skipped due to memory overflow.')
        with self.assertRaises(detectors.NativeAnalysisIncomplete) as raised:
            detectors.check_native_messages(known, profile)
        self.assertEqual(set(detectors.NATIVE_GAPS), set(raised.exception.reasons))
        for message in ("Trial edition", "License expired", "ClassNotFoundException",
                        "Unexpected exception", "failed to load configuration",
                        "java.lang.NoClassDefFoundError", "java.lang.OutOfMemoryError", "Error: missing runtime"):
            with self.subTest(message=message):
                with self.assertRaises(ValueError) as raised:
                    detectors.check_native_messages(known + "\n" + message, profile)
                self.assertNotIsInstance(raised.exception, detectors.NativeAnalysisIncomplete)
        profile["artifacts"][0]["sha256"] = "b" * 64
        with self.assertRaises(ValueError) as raised:
            detectors.check_native_messages(known, profile)
        self.assertNotIsInstance(raised.exception, detectors.NativeAnalysisIncomplete)

    def test_native_failure_is_strict_without_opt_in_and_hard_failures_block_opt_in_labels(self):
        path, profile, records = self.bounded_fixture(["native", "clean"])
        with mock.patch.object(detectors, "qualified", return_value=self.storage), mock.patch.object(
                detectors.subprocess, "run", side_effect=self.bounded_native):
            with self.assertRaises(detectors.NativeAnalysisIncomplete):
                detectors.detect(self.root, self.storage, "Apache", path)
        self.assertEqual([], list((self.root / "detection/results").glob("*/failure.json")))
        self.root = self.storage / "runs/opt-in"
        self.frozen_study(2)
        def fail(*args, **kwargs):
            self.bounded_native(*args, **kwargs)
            kwargs["stderr"].write("\nLicense expired\n")
        with mock.patch.object(detectors, "qualified", return_value=self.storage), mock.patch.object(
                detectors, "evidence_records", return_value=records), mock.patch.object(
                detectors.subprocess, "run", side_effect=fail):
            with self.assertRaisesRegex(ValueError, "license/trial"):
                detectors.detect(self.root, self.storage, "Apache", path, 10)
            with self.assertRaisesRegex(ValueError, "completed detector scan"):
                detectors.labels(self.root)
        self.assertEqual([], list((self.root / "detection/results").glob("*/failure.json")))

    def test_bounded_flag_validates_source_limit_and_cluster_forwarding(self):
        base = ["--stage", "detect", "--storage", str(self.storage), "--run-id", "test",
                "--profile", str(self.storage / "profile.json"), "--source", "Apache"]
        for limit in ("-1", "11"):
            with self.assertRaisesRegex(ValueError, "cap of 1-10"):
                cli.validate_arguments(cli.parser("detect").parse_args(base + ["--max-incomplete-stories", limit]))
        for source in ("RedHat", "MongoDB"):
            args = cli.parser("detect").parse_args(base + ["--source", source, "--max-incomplete-stories", "10"])
            with self.assertRaisesRegex(ValueError, "source Apache"):
                cli.validate_arguments(args)
        common.write_json(self.storage / "profile.json", self.profile())
        import contextlib
        import io
        output = io.StringIO()
        with mock.patch.object(sys, "argv", ["cluster", *base, "--max-incomplete-stories", "10", "--dry-run"]), (
                contextlib.redirect_stdout(output)):
            cluster.main("detect")
        self.assertIn("--max-incomplete-stories 10", output.getvalue())

    def ambiguous_java_fixture(self):
        source = self.storage / "snapshot/source"
        files = {
            "one/BucketService.java": "package demo; interface BucketService {} class OtherOne {}",
            "two/BucketService.java": "package demo; interface BucketService {} class OtherTwo {}",
            "src/Changed.java": "package demo; class Changed {}",
        }
        for name, content in files.items():
            path = source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        profile = self.profile()
        profile["platform"] = platform.system()
        profile["command"] = [sys.executable, "{input}", "{output}"]
        profile["coverage"] = [{"file": "coverage.csv", "qualified_columns": ["Package", "Type"]}]
        for category in profile["reports"]:
            profile["reports"][category] = {
                "file": category + ".csv", "smell_column": "Smell",
                "qualified_columns": ["Package", "Type"], "entity_columns": ["Type"],
            }
        return source, profile

    def ambiguous_java_reports(self, output, ambiguous_coverage=True):
        output.mkdir(parents=True, exist_ok=True)
        types = ["OtherOne", "OtherTwo", "Changed"]
        if ambiguous_coverage:
            types += ["BucketService", "BucketService"]
        pd.DataFrame([{"Package": "demo", "Type": name} for name in types]).to_csv(
            output / "coverage.csv", index=False)
        pd.DataFrame([{"Package": "demo", "Type": name, "Smell": "Long Method"}
                      for name in ("OtherOne", "Changed")]).to_csv(output / "implementation.csv", index=False)
        pd.DataFrame([{"Package": "demo", "Type": "BucketService", "Smell": "Deficient Encapsulation"}]).to_csv(
            output / "design.csv", index=False)

    def test_ambiguous_entities_remove_all_candidate_files_not_just_the_ambiguous_rows(self):
        source, profile = self.ambiguous_java_fixture()
        output = self.storage / "output"
        for coverage in (True, False):
            with self.subTest(ambiguous_coverage=coverage):
                self.ambiguous_java_reports(output, ambiguous_coverage=coverage)
                result = detectors.parse_reports(output, source, profile)
                self.assertEqual(["src/Changed.java"], result["coverage"])
                self.assertEqual(["src/Changed.java"], [item["path"] for item in result["findings"]])
                self.assertEqual([{"entity": "demo.BucketService", "candidate_paths": [
                    "one/BucketService.java", "two/BucketService.java"]}], result["ambiguous_entities"])

    def test_unresolved_entities_unknown_smells_and_uncovered_unique_findings_still_fail(self):
        source, profile = self.ambiguous_java_fixture()
        output = self.storage / "output"
        for category in ("coverage", "implementation", "design"):
            with self.subTest(category=category):
                self.ambiguous_java_reports(output)
                path = output / f"{category}.csv"
                rows = pd.read_csv(path)
                rows.loc[0, "Type"] = "Missing"
                rows.to_csv(path, index=False)
                with self.assertRaisesRegex(ValueError, "Ambiguous/unresolved"):
                    detectors.parse_reports(output, source, profile)
        self.ambiguous_java_reports(output)
        path = output / "design.csv"
        rows = pd.read_csv(path)
        rows.loc[0, "Smell"] = "Unknown smell"
        rows.to_csv(path, index=False)
        with self.assertRaisesRegex(ValueError, "Unregistered native smell"):
            detectors.parse_reports(output, source, profile)
        self.ambiguous_java_reports(output)
        pd.DataFrame([{"Package": "demo", "Type": "OtherOne"}]).to_csv(output / "coverage.csv", index=False)
        with self.assertRaisesRegex(ValueError, "outside reported"):
            detectors.parse_reports(output, source, profile)
        self.ambiguous_java_reports(output)
        pd.DataFrame(columns=["Package", "Type", "Smell"]).to_csv(output / "implementation.csv", index=False)
        pd.DataFrame([{"Package": "demo", "Type": "BucketService"}]).to_csv(output / "coverage.csv", index=False)
        result = detectors.parse_reports(output, source, profile)
        self.assertEqual([], result["coverage"])
        self.assertEqual([], result["findings"])
        self.assertTrue(result["ambiguous_entities"])
        (output / "coverage.csv").write_text("Wrong,Headers\n")
        with self.assertRaisesRegex(ValueError, "Unexpected .* schema"):
            detectors.parse_reports(output, source, profile)

    def test_detection_accepts_unrelated_ambiguity_but_never_covers_affected_changed_files(self):
        source, profile = self.ambiguous_java_fixture()
        files = common.tree_manifest(source)
        common.write_json(source.parent / "manifest.json", {"files": files})
        profile_path = self.storage / "profile.json"
        common.write_json(profile_path, profile)
        for required in ("src/Changed.java", "one/BucketService.java", "two/BucketService.java"):
            with self.subTest(required=required):
                self.root = self.storage / "runs" / required.split("/")[0]
                self.frozen_study(1)
                item = {"repository": "a/b", "revision": "a" * 40, "snapshot": str(source.parent),
                        "snapshot_manifest_sha256": common.file_hash(source.parent / "manifest.json"),
                        "files": [{"path": required, "language": "java", "status": "modified"}]}
                def execute_native(*args, **kwargs):
                    self.ambiguous_java_reports(Path(kwargs["cwd"]) / "output")
                with mock.patch.object(detectors, "qualified", return_value=self.storage), mock.patch.object(
                        detectors, "evidence_records", return_value=[
                            {"row_id": "Apache:TEST-0", "status": "complete", "evidence": [item]}]), mock.patch.object(
                        detectors.subprocess, "run", side_effect=execute_native):
                    if required == "src/Changed.java":
                        detectors.detect(self.root, self.storage, "Apache", profile_path)
                    else:
                        with self.assertRaisesRegex(ValueError, "coverage incomplete"):
                            detectors.detect(self.root, self.storage, "Apache", profile_path)
                directory = self.root / "detection/results" / detectors.detection_key(item, profile)
                attribution = list(directory.glob("attempts/*/output/attribution.json"))
                self.assertEqual(1, len(attribution), "Ambiguity diagnostics survive successful and failed attempts")
                self.assertEqual("demo.BucketService", common.read_json(attribution[0])["ambiguous_entities"][0]["entity"])
                result = common.read_json(directory / "result.json")
                self.assertEqual("analyzed", result["status"])
                self.assertEqual(["src/Changed.java"], result["coverage"])
                self.assertIn("attribution.json", result["reports"])
                coverage = common.read_json(self.root / "detection/coverage/Apache-java.json")
                self.assertTrue(coverage["scan_complete"])
                self.assertEqual([] if required == "src/Changed.java" else [required],
                                 coverage["items"][0]["missing_files"])
                self.assertFalse((self.root / "labels/story_labels.csv").exists())
                self.assertEqual(files, common.tree_manifest(source))

    def test_coverage_gaps_continue_resume_and_require_review_before_whole_story_exclusion(self):
        _, assignment = self.frozen_study(4)
        split_before = (self.root / "splits/Apache.json").read_bytes()
        source, profile = self.ambiguous_java_fixture()
        (source / "src/Action.java").write_text("package demo; enum Action { CREATE }")
        common.write_json(source.parent / "manifest.json", {"files": common.tree_manifest(source)})
        first = {"repository": "a/b", "revision": "a" * 40, "snapshot": str(source.parent),
                 "snapshot_manifest_sha256": common.file_hash(source.parent / "manifest.json")}
        records = []
        requests = [
            (first, ["one/BucketService.java", "src/Action.java", "src/Changed.java"]),
            (first, ["src/Changed.java"]),
        ]
        for repository, name, content in (
                ("a/clean", "Control.java", "package demo; class Control {}"),
                ("a/enum", "Action.java", "package demo; enum Action { CREATE }")):
            snapshot = self.storage / repository / "snapshot"
            (snapshot / "source/src").mkdir(parents=True)
            (snapshot / "source/src" / name).write_text(content)
            common.write_json(snapshot / "manifest.json", {"files": common.tree_manifest(snapshot / "source")})
            requests.append(({
                "repository": repository, "revision": "b" * 40, "snapshot": str(snapshot),
                "snapshot_manifest_sha256": common.file_hash(snapshot / "manifest.json"),
            }, ["src/" + name]))
        for index, (snapshot, paths) in enumerate(requests):
            item = {**snapshot, "files": [
                {"path": path, "language": "java", "status": "modified"} for path in paths]}
            row_id = f"Apache:TEST-{index}"
            records.append({"row_id": row_id, "source": "Apache", "partition": assignment[row_id],
                            "status": "complete", "evidence": [item]})
        manifest = {}
        for record in records:
            path = self.root / "evidence/Apache" / (record["row_id"].split(":")[1] + ".json")
            common.write_json(path, record)
            manifest[record["row_id"]] = common.file_hash(path)
        common.write_json(self.root / "evidence/Apache/manifest.json", {
            "records": manifest, "split_sha256": common.file_hash(self.root / "splits/Apache.json")})
        self.succeeded("fetch-code", "Apache")
        profile_path = self.storage / "profile.json"
        common.write_json(profile_path, profile)

        def execute_native(*args, **kwargs):
            output = Path(kwargs["cwd"]) / "output"
            if (Path(args[0][1]) / "one").exists():
                self.ambiguous_java_reports(output)
            else:
                types = ["Control"] if (Path(args[0][1]) / "src/Control.java").exists() else []
                pd.DataFrame([{"Package": "demo", "Type": name} for name in types],
                             columns=["Package", "Type"]).to_csv(output / "coverage.csv", index=False)
                for category in ("implementation", "design"):
                    pd.DataFrame(columns=["Package", "Type", "Smell"]).to_csv(
                        output / f"{category}.csv", index=False)

        with mock.patch.object(detectors, "qualified", return_value=self.storage), mock.patch.object(
                detectors.subprocess, "run", side_effect=execute_native) as runner:
            with self.assertRaisesRegex(ValueError, "coverage incomplete for 2 stories"):
                with common.stage_state(self.root, "detect", "Apache-java", "fixture"):
                    detectors.detect(self.root, self.storage, "Apache", profile_path)
            self.assertEqual(3, runner.call_count, "Continue after gaps; shared snapshots run only once.")
            self.assertEqual("failed", common.read_json(self.root / "status/detect-Apache-java.json")["status"])
            runner.reset_mock()
            with self.assertRaisesRegex(ValueError, "coverage incomplete for 2 stories"):
                detectors.detect(self.root, self.storage, "Apache", profile_path)
            runner.assert_not_called()
        coverage = common.read_json(self.root / "detection/coverage/Apache-java.json")
        self.assertTrue(coverage["scan_complete"])
        self.assertEqual(["Apache:TEST-0", "Apache:TEST-3"], coverage["incomplete_stories"])
        self.assertEqual(["one/BucketService.java", "src/Action.java"], coverage["items"][0]["missing_files"])
        self.assertEqual(["incomplete", "complete", "complete", "incomplete"],
                         [item["status"] for item in coverage["items"]])
        self.assertEqual([], common.read_json(
            self.root / "detection/results" / coverage["items"][3]["key"] / "result.json")["coverage"])
        with self.assertRaisesRegex(ValueError, "missing/incomplete"):
            detectors.labels(self.root)
        self.assertFalse((self.root / "labels/story_labels.csv").exists())
        self.assertEqual({"complete": 2, "incomplete": 2},
                         common.read_json(self.root / "labels/coverage.json")["status_counts"])
        exclusions = self.storage / "exclusions.json"
        for review in ({"Apache:TEST-0": "Reviewed ambiguity and missing enum coverage"},
                       {"Apache:TEST-1": "Cannot exclude this completely covered story"}):
            common.write_json(exclusions, review)
            with self.assertRaises(ValueError):
                detectors.labels(self.root, exclusions)
            self.assertFalse((self.root / "labels/story_labels.csv").exists())
        common.write_json(exclusions, {
            "Apache:TEST-0": "Reviewed ambiguity and missing enum coverage",
            "Apache:TEST-3": "Reviewed empty native enum coverage",
        })
        detectors.labels(self.root, exclusions)
        labels = pd.read_csv(self.root / "labels/story_labels.csv")
        self.assertEqual(["Apache:TEST-1", "Apache:TEST-2"], labels.row_id.tolist())
        self.assertEqual([1, 0], labels.any_supported_smell.tolist())
        self.assertEqual(split_before, (self.root / "splits/Apache.json").read_bytes())
        self.assertEqual(100, common.read_json(self.root / "study.json")["min_rows"])
        incomplete_report = (self.root / "detection/results" / coverage["items"][0]["key"]
                             / "reports/coverage.csv")
        incomplete_report.write_text("changed")
        with mock.patch.object(detectors, "qualified", return_value=self.storage), mock.patch.object(
                detectors.subprocess, "run") as runner:
            with self.assertRaisesRegex(ValueError, "Artifact tree changed"):
                detectors.detect(self.root, self.storage, "Apache", profile_path)
            runner.assert_not_called()
        with self.assertRaisesRegex(ValueError, "Artifact tree changed"):
            detectors.labels(self.root, exclusions)

    def test_native_execution_errors_still_abort_without_claiming_completed_scan(self):
        self.frozen_study(2)
        source, profile = self.ambiguous_java_fixture()
        common.write_json(source.parent / "manifest.json", {"files": common.tree_manifest(source)})
        item = {"repository": "a/b", "revision": "a" * 40, "snapshot": str(source.parent),
                "snapshot_manifest_sha256": common.file_hash(source.parent / "manifest.json"),
                "files": [{"path": "src/Changed.java", "language": "java", "status": "modified"}]}
        profile_path = self.storage / "profile.json"
        common.write_json(profile_path, profile)
        records = [{"row_id": f"Apache:TEST-{index}", "status": "complete", "evidence": [item]}
                   for index in range(2)]
        with mock.patch.object(detectors, "qualified", return_value=self.storage), mock.patch.object(
                detectors, "evidence_records", return_value=records), mock.patch.object(
                detectors.subprocess, "run", side_effect=RuntimeError("Native execution failed")) as runner:
            with self.assertRaisesRegex(RuntimeError, "Native execution failed"):
                detectors.detect(self.root, self.storage, "Apache", profile_path)
            self.assertEqual(1, runner.call_count)
        self.assertFalse(common.read_json(self.root / "detection/coverage/Apache-java.json")["scan_complete"])
        self.assertEqual([], list((self.root / "detection/results").glob("*/result.json")))

    def test_posix_names_survive_native_analysis_and_integrity_verification(self):
        if os.name == "nt":
            self.skipTest("POSIX-only source filenames")
        self.frozen_study(1)
        source = self.storage / "snapshot/source"
        (source / "src").mkdir(parents=True)
        name = "src/time:module.py"
        fixture = "applications?maxDate=2015-02-03T10:42:40.000CST"
        (source / name).write_text("pass\n")
        (source / fixture).write_text("[]\n")
        files = common.tree_manifest(source)
        manifest = source.parent / "manifest.json"
        common.write_json(manifest, {"files": files})
        item = {"repository": "a/b", "revision": "a" * 40, "snapshot": str(source.parent),
                "snapshot_manifest_sha256": common.file_hash(manifest),
                "files": [{"path": name, "language": "python", "status": "modified"}]}
        profile = self.profile("python")
        profile_path = self.storage / "profile.json"
        common.write_json(profile_path, profile)

        def execute(tool, spec, copied, output):
            self.assertEqual(files, common.tree_manifest(copied))
            output.mkdir(parents=True)
            pd.DataFrame([{"Path": name}]).to_csv(output / "coverage.csv", index=False)
            for category, smell in (("implementation", "Long Method"), ("design", "Deficient Encapsulation")):
                pd.DataFrame([{"Path": name, "Smell": smell, "Entity": "module"}]).to_csv(
                    output / f"{category}.csv", index=False)
            return detectors.parse_reports(output, copied, spec)

        with mock.patch.object(detectors, "qualified", return_value=self.storage), mock.patch.object(
                detectors, "evidence_records", return_value=[
                    {"row_id": "Apache:TEST-0", "status": "complete", "evidence": [item]}]), mock.patch.object(
                detectors, "execute", side_effect=execute):
            detectors.detect(self.root, self.storage, "Apache", profile_path)
        key = detectors.detection_key(item, profile)
        result = common.read_json(self.root / "detection/results" / key / "result.json")
        self.assertEqual("analyzed", result["status"])
        self.assertEqual([name], result["coverage"])
        self.assertEqual(files, common.tree_manifest(source))

    def test_windows_export_rejects_incompatible_context_before_copying(self):
        profile = self.profile("csharp")
        profile["platform"] = "Windows"
        profile_path = self.storage / "profile.json"
        common.write_json(profile_path, profile)
        cache = self.storage / "snapshot"
        for index, name in enumerate(("fixtures/query?date=1", "fixtures/time:12")):
            with self.subTest(name=name):
                manifest = cache / "manifest.json"
                common.write_json(manifest, {"files": {"src/A.cs": "a" * 64, name: "b" * 64}})
                item = {"repository": "a/b", "revision": "a" * 40, "snapshot": str(cache),
                        "snapshot_manifest_sha256": common.file_hash(manifest),
                        "files": [{"path": "src/A.cs", "language": "csharp"}]}
                with mock.patch.object(windows, "evidence_records", return_value=[
                        {"status": "complete", "evidence": [item]}]), mock.patch.object(windows.shutil, "copytree") as copytree:
                    with self.assertRaisesRegex(ValueError, "not representable on Windows"):
                        windows.export_work(self.root, "Apache", profile_path, self.storage / f"export-{index}")
                    copytree.assert_not_called()
                self.assertFalse((self.root / "detection").exists())

    def test_dpy_178_native_csv_schema_and_absolute_file_paths(self):
        source = self.storage / "python"
        source.mkdir()
        for name in ("bad.py", "clean.py"):
            (source / name).write_text("pass\n")
        output = self.storage / "native"
        output.mkdir()
        pd.DataFrame([
            {"Project": "python", "Package": "python", "Module": name[:-3],
             "Class": "", "File": str(source / name)}
            for name in ("bad.py", "clean.py")
        ]).to_csv(output / "python_class_module_metrics.csv", index=False)
        for category, smell in (("implementation", "Long parameter list"), ("design", "Deep hierarchy")):
            pd.DataFrame([{
                "Project": "python", "Package": "python", "Module": "bad", "Class": "Bad",
                "Smell": smell, "Method": "combine", "Line no": "2 - 3",
                "File": str(source / "bad.py"), "Description": "Native schema fixture",
            }]).to_csv(output / ("python_" + category + "_smells.csv"), index=False)
        profile = common.read_json(
            common.REPO / "Tasks/detect-code-smells/profiles/python.example.json")
        parsed = detectors.parse_reports(output, source, profile)
        self.assertEqual(["bad.py", "clean.py"], parsed["coverage"])
        self.assertEqual({"Long parameter list", "Deep hierarchy"},
                         {item["smell"] for item in parsed["findings"]})
        self.assertEqual({"bad.py"}, {item["path"] for item in parsed["findings"]})

    def test_qualification_runs_pinned_tool_and_preserves_failed_attempts(self):
        fixture = self.storage / "fixture"
        (fixture / "src").mkdir(parents=True)
        for name in ("Bad", "Clean"):
            (fixture / "src" / (name + ".java")).write_text("class " + name + " {}")
        tool = self.storage / "fake_tool.py"
        tool.write_text(
            "import pathlib, sys\n"
            "output = pathlib.Path(sys.argv[2])\n"
            "(output / 'coverage.csv').write_text('Path\\nsrc/Bad.java\\nsrc/Clean.java\\n')\n"
            "(output / 'implementation.csv').write_text("
            "'Path,Smell,Entity\\nsrc/Bad.java,Long Method,Bad\\n')\n"
            "(output / 'design.csv').write_text("
            "'Path,Smell,Entity\\nsrc/Bad.java,Deficient Encapsulation,Bad\\n')\n"
            "print('fixture analyzer complete')\n"
        )
        profile = self.profile()
        profile.update(platform=platform.system(), command=[
            sys.executable, "{tool}/fake_tool.py", "{input}", "{output}"])
        profile["artifacts"] = [{"name": "fake_tool.py", "local_path": str(tool),
                                 "sha256": common.file_hash(tool)}]
        profile_path = self.storage / "profile.json"
        common.write_json(profile_path, profile)
        installed, _ = detectors.install_profile(self.storage, profile_path)
        expected = {"positive": [
            {"path": "src/Bad.java", "category": category, "smell": names[0]}
            for category, names in profile["catalog"].items()
        ], "clean_files": ["src/Clean.java"]}
        expected_path = self.storage / "expected.json"
        common.write_json(expected_path, expected)
        result = detectors.qualify(self.storage, profile_path, fixture, expected_path)
        self.assertEqual("succeeded", result["status"])
        self.assertEqual(installed, detectors.qualified(self.storage, profile))
        self.assertEqual(result, detectors.qualify(self.storage, profile_path, fixture, expected_path))
        self.assertEqual(1, len(list((installed / "qualification").glob("*/attempts/*/output.out"))))

        (fixture / "src/Action.java").write_text("enum Action { CREATE }")
        expected["clean_files"].append("src/Action.java")
        common.write_json(expected_path, expected)
        with self.assertRaisesRegex(ValueError, "Known-clean controls were not analyzed"):
            detectors.qualify(self.storage, profile_path, fixture, expected_path)
        expected["clean_files"].remove("src/Action.java")
        expected["positive"][0]["smell"] = "Missing expected smell"
        common.write_json(expected_path, expected)
        with self.assertRaisesRegex(ValueError, "misses expected"):
            detectors.qualify(self.storage, profile_path, fixture, expected_path)
        logs = list((installed / "qualification").glob("*/attempts/*/output.out"))
        self.assertEqual(3, len(logs), "Failed qualification must preserve raw logs.")
        self.assertTrue(all("fixture analyzer complete" in path.read_text() for path in logs))
        qualified = common.read_json(installed / "qualified.json")
        report = installed / "qualification" / qualified["qualification"] / "reports/design.csv"
        report.write_text("changed report")
        with self.assertRaises(ValueError):
            detectors.qualified(self.storage, profile)

    def test_windows_worker_round_trip_resume_and_tamper_rejection(self):
        bundle = self.storage / "exchange"
        source = bundle / "snapshots" / "one"
        (source / "src").mkdir(parents=True)
        for name in ("Bad", "Clean"):
            (source / "src" / (name + ".cs")).write_text("class " + name + " {}")
        profile = self.profile("csharp")
        profile["platform"] = "Windows"
        files = common.tree_manifest(source)
        work = {"profile": profile, "jobs": {"one": {"required": ["src/Bad.cs"], "files": files}}}
        common.write_json(bundle / "work.json", work)
        common.write_json(self.root / "detection/windows" / (common.digest(work) + ".json"), work)
        tool = self.storage / "tool"
        common.write_json(tool / "qualified.json", {
            "status": "succeeded", "profile_sha256": common.digest(profile)})

        def fake_execute(tool_root, spec, copied, output):
            self.native_output(output, "csharp")
            return detectors.parse_reports(output, copied, spec)

        with mock.patch.object(windows, "qualified", return_value=tool), mock.patch.object(
                windows, "execute", side_effect=fake_execute) as runner:
            windows.run_work(bundle, self.storage)
            windows.run_work(bundle, self.storage)
            self.assertEqual(1, runner.call_count)
        windows.import_work(self.root, bundle)
        windows.import_work(self.root, bundle)
        imported = common.read_json(self.root / "detection/results/one/result.json")
        self.assertEqual(2, len(imported["findings"]))
        self.assertEqual(files, common.tree_manifest(source))
        (bundle / "results/one/reports/design.csv").write_text("tampered")
        with self.assertRaises(ValueError):
            windows.import_work(self.root, bundle)

    def test_parsers_cover_each_language_and_preserve_categories(self):
        for language, extension in (("java", ".java"), ("python", ".py"), ("csharp", ".cs")):
            source = self.storage / language
            (source / "src").mkdir(parents=True)
            for name in ("Bad", "Clean"):
                (source / "src" / (name + extension)).write_text("class " + name + " {}")
            output = self.storage / ("output-" + language)
            self.native_output(output, language)
            parsed = detectors.parse_reports(output, source, self.profile(language))
            self.assertEqual(2, len(parsed["coverage"]))
            self.assertEqual({"implementation", "design"}, {row["category"] for row in parsed["findings"]})
            with (output / "implementation.csv").open("a") as stream:
                stream.write("src/Bad" + extension + ",Long Method,Bad\n")
            self.assertEqual(2, len(detectors.parse_reports(output, source, self.profile(language))["findings"]))

    def test_missing_report_and_unregistered_smell_fail(self):
        source = self.storage / "source"
        (source / "src").mkdir(parents=True)
        for name in ("Bad", "Clean"):
            (source / "src" / (name + ".java")).write_text("class " + name + " {}")
        output = self.storage / "output"
        self.native_output(output)
        (output / "design.csv").unlink()
        with self.assertRaisesRegex(ValueError, "exactly one"):
            detectors.parse_reports(output, source, self.profile())
        self.native_output(output)
        (output / "design.csv").write_text("Path,Smell,Entity\nsrc/Bad.java,Unknown smell,Bad\n")
        with self.assertRaisesRegex(ValueError, "Unregistered"):
            detectors.parse_reports(output, source, self.profile())

    def test_java_qualified_names_reject_ambiguity(self):
        source = self.storage / "source"
        for parent in ("one", "two"):
            (source / parent).mkdir(parents=True)
            (source / parent / "A.java").write_text("package demo; public class A {}")
        index = detectors.source_index(source, "java")
        with self.assertRaisesRegex(ValueError, "Ambiguous"):
            detectors.report_path({"Package": "demo", "Type": "A"},
                                  {"qualified_columns": ["Package", "Type"]}, source, index)

    def test_trial_and_unpinned_tools_rejected(self):
        profile = self.profile()
        path = self.storage / "profile.json"
        profile["license"] = "trial"
        common.write_json(path, profile)
        with self.assertRaisesRegex(ValueError, "trials"):
            detectors.load_profile(path)
        profile["license"] = "community"
        profile["artifacts"][0]["sha256"] = "unverified"
        common.write_json(path, profile)
        with self.assertRaisesRegex(ValueError, "SHA256"):
            detectors.load_profile(path)

    def test_windows_import_rejects_missing_jobs(self):
        bundle = self.storage / "exchange"
        profile = self.profile("csharp")
        profile["platform"] = "Windows"
        work = {"profile": profile, "jobs": {"one": {"required": ["A.cs"], "files": {"A.cs": "abc"}}}}
        common.write_json(bundle / "work.json", work)
        common.write_json(self.root / "detection/windows" / (common.digest(work) + ".json"), work)
        common.write_json(bundle / "completed.json", {"work_sha256": common.digest(work), "results": {}})
        with self.assertRaisesRegex(ValueError, "incomplete"):
            windows.import_work(self.root, bundle)
