import contextlib
import io
import platform
from pathlib import Path
import shutil
import sys
import tempfile
from unittest import mock

import pandas as pd

from Code_Smells_Detection.runtime import cli, cluster, common, detectors, models, streaming
from Code_Smells_Detection.runtime.tests.support import RuntimeCase


class StreamingTests(RuntimeCase):
    def setUp(self):
        super().setUp()
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.scratch = Path(temporary.name)
        self.paths, self.profiles = {}, {}
        for language in ("java", "python"):
            profile = self.profile(language)
            profile.update(platform=platform.system(), command=[sys.executable, "{input}", "{output}"])
            if language == "java":
                profile["artifacts"] = [{"name": "DesigniteJavaCommunity.jar", "sha256": detectors.JAVA_COMMUNITY_SHA256}]
            path = self.storage / (language + ".json")
            common.write_json(path, profile)
            self.paths[language], self.profiles[language] = path, profile
        self.snapshot_calls, self.native_calls, self.workspaces = [], [], []
        self.modes = {}
        patch = mock.patch.object(detectors, "qualified", return_value=self.storage)
        patch.start()
        self.addCleanup(patch.stop)
        patch = mock.patch.object(detectors.subprocess, "run", side_effect=self.native)
        patch.start()
        self.addCleanup(patch.stop)

    def stories(self, specs):
        self.frozen_study(len(specs))
        common.write_json(self.root / "streaming/mode.json", {
            "protocol": streaming.PROTOCOL, "study_sha256": common.file_hash(self.root / "study.json")})
        saved = common.read_json(self.root / "raw/Apache/manifest.json")
        self.metadata = {}
        for index, revisions in enumerate(specs):
            urls = []
            for number, files in revisions:
                revision = f"{number:040x}"
                url = "https://github.com/a/b/commit/" + revision
                urls.append(url)
                self.metadata[url] = {
                    "url": url, "repository": "a/b", "revision": revision,
                    "files": [{"path": name, "language": common.LANGUAGES[Path(name).suffix], "status": "modified"}
                              for name in files]}
            path = self.root / "raw/Apache" / f"TEST-{index}.json"
            record = common.read_json(path)
            record["comments"] = [{"body": " ".join(urls)}]
            common.write_json(path, record)
            saved["records"][f"TEST-{index}"] = common.file_hash(path)
        common.write_json(self.root / "raw/Apache/manifest.json", saved)
        self.github = mock.Mock()
        self.github.resolve.side_effect = lambda url: self.metadata[url]

    def loader(self, temporary, repository, revision):
        self.assertTrue(all(not p.exists() for p in self.workspaces), "Previous source survived into next revision")
        self.snapshot_calls.append(revision)
        cache = temporary / "snapshot"
        source = cache / "source"
        self.workspaces.append(source)
        for extension in ("java", "py"):
            for name in ("Bad", "Clean", "Gap"):
                common.atomic_bytes(source / "src" / (name + "." + extension), b"class Fixture {}\n")
        (source / "mode.txt").write_text(self.modes.get(revision, "ok"))
        snapshot = {"repository": repository, "revision": revision, "files": common.tree_manifest(source)}
        common.write_json(cache / "manifest.json", snapshot)
        return cache, snapshot

    def native(self, command, **kwargs):
        source, output = map(Path, command[1:])
        language = output.parent.name
        self.native_calls.append(language)
        mode = (source / "mode.txt").read_text()
        if mode == "fatal":
            raise OSError(122, "Disk quota exceeded")
        if mode == "native":
            kwargs["stderr"].write("Inheritance depth analysis step skipped due to memory overflow.")
            return
        self.native_output(output, language)
        if mode == "attribution":
            (output / "coverage.csv").write_text("Path\nsrc/Unknown.java\n")
        if mode == "mutate":
            (source / "src/Bad.java").write_text("changed")

    def run_source(self, languages=("java",)):
        streaming.process(self.root, self.storage, "Apache", [self.paths[x] for x in languages],
                          self.scratch, self.github, self.loader)

    def checkpoint(self, index):
        return common.read_json(self.root / "streaming/stories/Apache" / f"TEST-{index}.json")["value"]

    def test_serial_sources_shared_revision_restart_and_final_model_contract(self):
        self.stories([[(1, ["src/Bad.java"])], [(1, ["src/Bad.java"])],
                      [(2, ["src/Clean.java"])], [(3, ["src/Clean.py"])]])
        before = (self.root / "splits/Apache.json").read_bytes()
        self.run_source(("java", "python"))
        self.assertEqual(3, len(self.snapshot_calls))
        self.assertEqual(["java", "java", "python"], self.native_calls)
        self.assertFalse(any(self.scratch.iterdir()))
        for directory in (self.root / "streaming/revisions").iterdir():
            self.assertFalse(list(directory.rglob("*.java")))
            self.assertFalse(list(directory.rglob("*.py")))
        self.github.resolve.side_effect = AssertionError("Completed stories must not request metadata again")
        self.run_source(("java", "python"))
        self.assertEqual(3, len(self.snapshot_calls))
        with mock.patch.object(sys, "argv", ["stories", "--stage", "labels", "--storage", str(self.storage),
                                             "--run-id", "test"]):
            cli.main("stories")
        labels, catalog, manifest = models.load_labels(self.root)
        self.assertEqual([1, 1, 0, 0], labels.any_supported_smell.tolist())
        java = next(key for key, value in catalog.items() if value["language"] == "java")
        self.assertTrue(pd.isna(labels.iloc[3][java]))
        self.assertEqual(100, manifest["min_source_rows"])
        self.assertEqual(before, (self.root / "splits/Apache.json").read_bytes())
        matrix = models.validate(self.root)
        self.assertTrue(all(x["reason"] == "fewer_than_100_fully_labeled_stories" for x in matrix["matrix"]))

    def test_multi_revision_multi_language_story_and_later_tool_completion(self):
        self.stories([[(1, ["src/Bad.java", "src/Clean.py"]), (2, ["src/Clean.java"])],
                      [(3, ["src/Clean.java"])]])
        self.run_source()
        self.assertEqual("pending", self.checkpoint(0)["status"])
        self.assertEqual("complete", self.checkpoint(1)["status"])
        csv = pd.read_csv(self.root / "streaming/Apache.csv")
        self.assertTrue(pd.isna(csv.iloc[0]["any_supported_smell"]))
        with self.assertRaisesRegex(ValueError, "prerequisites"):
            streaming.finalize(self.root)
        self.run_source(("python",))
        self.assertEqual("complete", self.checkpoint(0)["status"])
        self.assertEqual(3, self.native_calls.count("java"), "Do not repeat cached Java to add Python")
        self.assertEqual(1, self.native_calls.count("python"))
        self.assertEqual(4, len(self.snapshot_calls))
        streaming.finalize(self.root)
        labels, _, _ = models.load_labels(self.root)
        self.assertEqual([1, 0], labels.any_supported_smell.tolist())

    def test_more_than_100_incomplete_stories_continue_without_source_retention(self):
        self.stories([[(1, ["src/Gap.java"])]] * 101 + [[(2, ["src/Clean.java"])]])
        self.run_source()
        self.assertEqual(2, len(self.snapshot_calls))
        self.assertEqual(101, sum(self.checkpoint(i)["status"] == "excluded" for i in range(102)))
        streaming.finalize(self.root)
        labels, _, _ = models.load_labels(self.root)
        self.assertEqual(["Apache:TEST-101"], labels.row_id.tolist())

    def test_portable_failures_revalidate_without_deleted_source(self):
        self.stories([[(1, ["src/Clean.java"])], [(2, ["src/Clean.java"])], [(3, ["src/Clean.java"])]])
        self.modes = {f"{1:040x}": "native", f"{2:040x}": "attribution"}
        self.run_source()
        self.assertEqual(["excluded", "excluded", "complete"], [self.checkpoint(i)["status"] for i in range(3)])
        self.run_source()
        self.assertEqual(3, len(self.native_calls))
        streaming.finalize(self.root)
        labels, _, _ = models.load_labels(self.root)
        self.assertEqual(["Apache:TEST-2"], labels.row_id.tolist())

    def test_interrupted_csv_commit_repairs_from_checkpoint_without_reanalysis(self):
        self.stories([[(1, ["src/Clean.java"])], [(2, ["src/Bad.java"])]])
        original = streaming.export_progress
        def interrupted(root, source, rows, catalog):
            if rows:
                raise OSError("interrupted CSV write")
            return original(root, source, rows, catalog)
        with mock.patch.object(streaming, "export_progress", side_effect=interrupted):
            with self.assertRaisesRegex(OSError, "CSV write"):
                self.run_source()
        self.assertEqual("complete", self.checkpoint(0)["status"])
        self.assertFalse(any(self.scratch.iterdir()))
        self.run_source()
        self.assertEqual(2, len(self.native_calls))
        self.assertEqual(2, len(pd.read_csv(self.root / "streaming/Apache.csv")))

    def test_failed_story_commit_reuses_durable_revision(self):
        self.stories([[(1, ["src/Bad.java"])]])
        original = streaming.write_json
        def interrupted(path, value):
            if Path(path).parent.name == "Apache" and Path(path).name == "TEST-0.json":
                raise OSError("interrupted checkpoint")
            return original(path, value)
        with mock.patch.object(streaming, "write_json", side_effect=interrupted):
            with self.assertRaisesRegex(OSError, "checkpoint"):
                self.run_source()
        self.assertFalse(any(self.scratch.iterdir()))
        self.run_source()
        self.assertEqual(1, len(self.native_calls))
        self.assertEqual(1, len(self.snapshot_calls))
        self.assertEqual("complete", self.checkpoint(0)["status"])

    def test_fatal_error_cleanup_and_integrity_failures_are_not_exclusions(self):
        for mode in ("fatal", "mutate"):
            with self.subTest(mode=mode):
                # No result/checkpoint is committed for either failure.
                self.stories([[(1, ["src/Clean.java"])]])
                self.modes = {f"{1:040x}": mode}
                with self.assertRaises((OSError, ValueError)):
                    self.run_source()
                self.assertFalse((self.root / "streaming/stories/Apache/TEST-0.json").exists())
                self.assertFalse(any(self.scratch.iterdir()))

    def test_tampered_portable_report_blocks_resume(self):
        self.stories([[(1, ["src/Clean.java"])]])
        self.run_source()
        report = next((self.root / "streaming/revisions").glob("*/audit/reports/design.csv"))
        report.write_text("corrupt")
        with self.assertRaisesRegex(ValueError, "Artifact tree"):
            self.run_source()
        self.assertEqual(1, len(self.native_calls))

    def test_legacy_result_and_failures_become_independent_of_original_source(self):
        for number, mode in enumerate(("ok", "native", "attribution"), 1):
            with self.subTest(mode=mode):
                profile = self.profiles["java"]
                revision = f"{number:040x}"
                cache, _ = self.loader(self.storage / str(number), "a/b", revision)
                if mode == "native":
                    (cache / "source/src/Bad.java").write_bytes(b"\xff")
                    snapshot = common.read_json(cache / "manifest.json")
                    snapshot["files"] = common.tree_manifest(cache / "source")
                    common.write_json(cache / "manifest.json", snapshot)
                item = {"repository": "a/b", "revision": revision, "snapshot": str(cache),
                        "snapshot_manifest_sha256": common.file_hash(cache / "manifest.json")}
                key = detectors.detection_key(item, profile)
                legacy = self.storage / "legacy" / key
                output = legacy / "attempts/one/output"
                self.native_output(output)
                (output.parent / "output.out").write_text("")
                (output.parent / "output.err").write_text(
                    "Inheritance depth analysis step skipped due to memory overflow." if mode == "native" else "")
                if mode == "attribution":
                    (output / "coverage.csv").write_text("Path\nsrc/Unknown.java\n")
                if mode == "ok":
                    shutil.copytree(output, legacy / "reports")
                    common.write_json(legacy / "result.json", {
                        "key": key, "profile_sha256": common.digest(profile), "status": "analyzed",
                        **detectors.parse_reports(output, cache / "source", profile),
                        "reports": common.tree_manifest(output)})
                else:
                    common.write_json(legacy / "failure.json", {
                        "key": key, "profile_sha256": common.digest(profile), "status": "incomplete",
                        "reasons": ["inheritance_depth_memory_overflow" if mode == "native" else "report_attribution"],
                        "best_effort": True, "attempt": "attempts/one", "reports": common.tree_manifest(output.parent),
                        "snapshot": str(cache), "snapshot_manifest_sha256": item["snapshot_manifest_sha256"]})
                value = streaming.import_legacy(self.root, item, profile, legacy)
                shutil.rmtree(cache)
                self.assertEqual(value, streaming.load_revision(self.root, "a/b", revision, profile))
                self.assertEqual("analyzed" if mode == "ok" else "incomplete", value["status"])
        self.assertEqual([], self.native_calls)

    def test_failed_revision_persistence_does_not_publish_story_or_keep_source(self):
        self.stories([[(1, ["src/Bad.java"])]])
        original = streaming.immutable_json
        def fail(path, value):
            if Path(path).name == "result.json":
                raise OSError("result commit failed")
            return original(path, value)
        with mock.patch.object(streaming, "immutable_json", side_effect=fail):
            with self.assertRaisesRegex(OSError, "result commit"):
                self.run_source()
        self.assertFalse(any(self.scratch.iterdir()))
        self.assertFalse((self.root / "streaming/stories/Apache/TEST-0.json").exists())
        self.run_source()
        self.assertEqual(2, len(self.native_calls))
        self.assertEqual("complete", self.checkpoint(0)["status"])

    def test_missing_evidence_excludes_whole_story_without_download(self):
        self.stories([[(1, ["src/Clean.java"]), (2, ["src/Bad.java"])], [(3, ["src/Clean.java"])]])
        def resolve(url):
            if url.endswith(f"{2:040x}"):
                raise streaming.evidence.EvidenceExcluded("commit_not_found")
            return self.metadata[url]
        self.github.resolve.side_effect = resolve
        self.run_source()
        self.assertEqual("excluded", self.checkpoint(0)["status"])
        self.assertEqual("complete", self.checkpoint(1)["status"])
        self.assertEqual(1, len(self.snapshot_calls))

    def test_inherited_evidence_is_not_reresolved_or_reclassified(self):
        self.stories([[(1, ["src/Bad.java"])], [(2, ["src/Bad.java"])]])
        split = common.read_json(self.root / "splits/Apache.json")
        hashes = {}
        for index in range(2):
            path = self.root / "evidence/Apache" / f"TEST-{index}.json"
            record = {"row_id": f"Apache:TEST-{index}", "source": "Apache",
                      "partition": split["assignment"][f"Apache:TEST-{index}"],
                      "status": "complete" if index == 0 else "excluded",
                      "reason": None if index == 0 else "no_complete_supported_evidence",
                      "exclusions": [], "evidence": [{**next(iter(self.metadata.values())), "revision": f"{9:040x}"}]
                      if index == 0 else []}
            common.write_json(path, record)
            hashes[record["row_id"]] = common.file_hash(path)
        common.write_json(self.root / "evidence/Apache/manifest.json", {
            "records": hashes, "split_sha256": common.file_hash(self.root / "splits/Apache.json")})
        self.succeeded("fetch-code", "Apache")
        self.github.resolve.side_effect = AssertionError("Preserve inherited evidence instead of re-resolving")
        self.run_source()
        self.assertEqual([f"{9:040x}"], self.snapshot_calls)
        self.assertEqual(["complete", "excluded"], [self.checkpoint(i)["status"] for i in range(2)])
        (self.root / "evidence/Apache/TEST-0.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "Inherited evidence record changed"):
            self.run_source()

    def test_worker_prerequisites_and_scratch_do_not_silently_exclude_stories(self):
        self.stories([[(1, ["src/Bad.java"])]])
        with mock.patch.object(detectors, "qualified", side_effect=ValueError("License required")):
            with self.assertRaisesRegex(ValueError, "License"):
                self.run_source()
        with self.assertRaisesRegex(ValueError, "Scratch must"):
            streaming.process(self.root, self.storage, "Apache", [self.paths["java"]],
                              self.storage, self.github, self.loader)
        self.assertEqual([], self.snapshot_calls)

    def test_cross_partition_revision_audit_and_completed_raw_integrity(self):
        self.stories([[(1, ["src/Clean.java"])]] * 3)
        self.run_source()
        audit = common.read_json(self.root / "streaming/Apache-progress.json")
        self.assertEqual(["test", "train"], audit["cross_partition_revisions"][0]["partitions"])
        self.assertEqual(1, len(self.native_calls))
        (self.root / "raw/Apache/TEST-0.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "Frozen Jira record changed"):
            self.run_source()

    def test_cluster_dispatch_uses_new_task_and_multiple_profiles(self):
        args = ["--stage", "process", "--source", "Apache", "--storage", str(self.storage), "--run-id", "test",
                "--profiles", str(self.paths["java"]), str(self.paths["python"]), "--scratch", str(self.scratch)]
        parsed = cli.parser("stories").parse_args(args)
        cli.validate_arguments(parsed)
        with mock.patch.object(streaming, "process") as process:
            cli.dispatch(parsed, self.root)
            self.assertEqual([self.paths["java"], self.paths["python"]], process.call_args.args[3])
        output = io.StringIO()
        with mock.patch.object(sys, "argv", ["cluster", *args, "--dry-run"]), contextlib.redirect_stdout(output):
            cluster.main("stories")
        self.assertIn("Tasks/process-code-smell-stories/run_task.py", output.getvalue())
        self.assertIn("--profiles", output.getvalue())
        self.assertIn("--scratch", output.getvalue())
