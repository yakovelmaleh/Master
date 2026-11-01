import copy
import os
from pathlib import Path
import platform
import sys
from unittest import mock

import pandas as pd

from Code_Smells_Detection.runtime import common, detectors, windows
from Code_Smells_Detection.runtime.tests.support import RuntimeCase


class DetectionTests(RuntimeCase):
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
                detectors, "evidence_records", return_value=[{"status": "complete", "evidence": [item]}]), mock.patch.object(
                detectors, "execute", side_effect=execute):
            detectors.detect(self.root, self.storage, "Apache", profile_path)
        key = detectors.detection_key(item, profile)
        result = common.read_json(self.root / "detection/results" / key / "result.json")
        self.assertEqual("succeeded", result["status"])
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

        expected["positive"][0]["smell"] = "Missing expected smell"
        common.write_json(expected_path, expected)
        with self.assertRaisesRegex(ValueError, "misses expected"):
            detectors.qualify(self.storage, profile_path, fixture, expected_path)
        logs = list((installed / "qualification").glob("*/attempts/*/output.out"))
        self.assertEqual(2, len(logs), "Failed qualification must preserve raw logs.")
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
