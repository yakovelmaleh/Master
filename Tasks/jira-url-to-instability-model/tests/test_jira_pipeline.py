import unittest
import json
import tempfile
import copy
import importlib.util
import re
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pandas as pd

from cluster.run_cluster import build_parser as cluster_parser, load_sources, run_cluster
from jira_pipeline.cli import build_parser as pipeline_parser
from jira_pipeline.client import JiraClient
from jira_pipeline.orchestrator import (
    build_jql,
    default_run_name,
    repository_name,
    dataset_analysis,
    run_pipeline,
)
from unstable_model.config import load_config


TASK = Path(__file__).resolve().parents[1]
REPO = TASK.parents[1]
from jira_pipeline.preprocessing import (
    add_previous_creator_counts,
    adf_to_text,
    preprocess_record,
)


class JiraPipelineTests(unittest.TestCase):
    def setUp(self):
        self.field_map = {
            "Sprint": "customfield_1",
            "Acceptance Criteria": "customfield_2",
            "Story Points": "customfield_3",
        }
        self.record = {
            "issue": {
                "key": "DEMO-1",
                "fields": {
                    "created": "2026-01-01T10:00:00.000+0000",
                    "summary": "one two three four five six seven",
                    "description": {
                        "type": "doc",
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [
                                    {"type": "text", "text": "description"}
                                ],
                            }
                        ],
                    },
                    "issuetype": {"name": "Story"},
                    "project": {"key": "DEMO", "name": "Demo"},
                    "priority": {"name": "Major"},
                    "creator": {"displayName": "Creator"},
                    "customfield_1": [
                        {"name": "Sprint 1", "startDate": "2026-01-03T09:00:00Z"}
                    ],
                    "customfield_2": "acceptance criteria",
                    "customfield_3": 5,
                },
            },
            "comments": [
                {"created": "2026-01-02T12:00:00.000+0000"},
                {"created": "2026-01-04T12:00:00.000+0000"},
            ],
            "changelog": [
                {
                    "created": "2026-01-04T10:00:00.000+0000",
                    "items": [
                        {
                            "field": "summary",
                            "fromString": "one two",
                            "toString": "one two three four five six seven",
                        }
                    ],
                }
            ],
        }

    def test_adf_to_text(self):
        text = adf_to_text(
            {
                "type": "doc",
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": "hello"}],
                    }
                ],
            }
        )
        self.assertEqual(text, "hello")

    def test_preprocessing_reconstructs_sprint_state_and_label(self):
        row, reason = preprocess_record(self.record, self.field_map)
        self.assertEqual(reason, "accepted")
        self.assertEqual(row["project_key"], "DEMO")
        self.assertEqual(row["original_summary_sprint"], "one two")
        self.assertEqual(row["num_comments_before_sprint"], 1)
        self.assertEqual(
            row["num_changes_summary_description_acceptance_sprint"], 1
        )
        self.assertEqual(row["num_different_words_all_text_sprint"], 5)
        self.assertEqual(row["is_change_text_num_words_5"], 1)
        self.assertEqual(row["is_change_text_num_words_10"], 0)

    def test_preprocessing_rejects_no_comment_before_sprint(self):
        record = {**self.record, "comments": []}
        row, reason = preprocess_record(record, self.field_map)
        self.assertIsNone(row)
        self.assertEqual(reason, "no_comment_before_sprint")

    def test_previous_creator_count_is_chronological(self):
        frame = pd.DataFrame(
            [
                {
                    "issue_key": "A-2",
                    "creator": "Alice",
                    "created": pd.Timestamp("2026-01-02"),
                    "time_add_to_sprint": pd.Timestamp("2026-01-03"),
                },
                {
                    "issue_key": "A-1",
                    "creator": "Alice",
                    "created": pd.Timestamp("2026-01-01"),
                    "time_add_to_sprint": pd.Timestamp("2026-01-02"),
                },
            ]
        )
        output = add_previous_creator_counts(frame)
        counts = dict(
            zip(output["issue_key"], output["num_issues_cretor_prev"])
        )
        self.assertEqual(counts, {"A-1": 0, "A-2": 1})

    def test_jql_options(self):
        basic = build_jql("DEMO", None, False, False)
        self.assertIn('project = "DEMO"', basic)
        self.assertIn("type != Bug", basic)
        self.assertNotIn("Sprint is not EMPTY", basic)
        self.assertNotIn("github.com", basic)

        strict = build_jql("DEMO", None, True, True)
        self.assertIn("statusCategory = Done", strict)
        self.assertIn('comment ~ "https://github.com"', strict)
        self.assertIn(
            "Sprint is not EMPTY",
            build_jql("DEMO", None, True, True, require_current_sprint=True),
        )

    def test_preprocessing_accepts_sprint_from_history_with_empty_current_field(self):
        record = copy.deepcopy(self.record)
        record["issue"]["fields"]["customfield_1"] = []
        record["changelog"].append({
            "created": "2026-01-03T09:00:00Z",
            "items": [{"field": "Sprint", "fromString": "", "toString": "Sprint 1"}],
        })
        row, reason = preprocess_record(record, self.field_map)
        self.assertEqual(reason, "accepted")
        self.assertEqual(row["time_add_to_sprint"], pd.Timestamp("2026-01-03T09:00:00"))

    def test_configured_status_and_evidence_conditions_match_original(self):
        spec = importlib.util.spec_from_file_location(
            "legacy_jql", REPO / "Data_Analysis/JQL_Queries.py"
        )
        legacy = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(legacy)
        payload = json.loads((REPO / "Source/jira_data_for_instability_cluster.json").read_text())

        def normalized(value):
            return re.sub(r"\s+", "", value).strip("()")

        for name, source in payload.items():
            expected = f"{legacy.filter_by_status(name)} OR {legacy.filter_by_resolution(name)}"
            self.assertEqual(normalized(source["terminal_jql"]), normalized(expected), name)
            if source.get("require_pr_evidence", True):
                evidence = source.get("pr_evidence_jql", 'comment ~ "https://github.com"')
                self.assertEqual(normalized(evidence), normalized(legacy.filter_byOptionalPR(name)), name)

    def test_cluster_uses_source_policy_and_explicit_cli_overrides(self):
        args = cluster_parser().parse_args(["--only", "Qt"])
        with tempfile.TemporaryDirectory() as directory, patch("cluster.run_cluster.run_pipeline") as run:
            args.output_root = Path(directory)
            run.return_value = {}
            run_cluster(args)
            settings = run.call_args.args[0]
            query = build_jql(
                settings.project, settings.jql, settings.terminal_only,
                settings.require_pr_evidence, settings.require_current_sprint,
                settings.pr_evidence_jql, settings.terminal_jql,
            )
            self.assertIn('"In Development"', query)
            self.assertNotIn("statusCategory", query)
            self.assertNotIn("Sprint is not EMPTY", query)
            self.assertIn("github.com", query)
            args = cluster_parser().parse_args([
                "--only", "Qt", "--no-terminal-only", "--no-require-pr-evidence",
                "--jql", "type = Story", "--output-root", directory,
            ])
            run_cluster(args)
            settings = run.call_args.args[0]
            self.assertFalse(settings.terminal_only)
            self.assertFalse(settings.require_pr_evidence)
            self.assertEqual(settings.jql, "type = Story")

    def test_repeated_source_options_do_not_override_each_other(self):
        args = cluster_parser().parse_args(["--only", "Apache", "--only", "Qt"])
        self.assertEqual(args.only, ["Apache", "Qt"])
        with self.assertRaises(SystemExit):
            cluster_parser().parse_args(["--on", "Qt"])
        args = cluster_parser().parse_args(["-jira", "Apache", "-jira", "Qt"])
        self.assertEqual(args.only, ["Apache", "Qt"])
        self.assertIsNone(cluster_parser().parse_args([]).only)

    def test_analysis_records_every_label_and_single_class_partitions(self):
        frame = pd.DataFrame({
            "issue_key": [f"TEST-{i}" for i in range(38)],
            "time_add_to_sprint": pd.date_range("2020-01-01", periods=38),
            **{
                f"is_change_text_num_words_{level}": [1] * positives + [0] * (38 - positives)
                for level, positives in [(5, 9), (10, 7), (15, 6), (20, 6)]
            },
        })
        result = dataset_analysis(frame, load_config(TASK / "model_config.json"))
        self.assertEqual(result["unique_issues"], 38)
        self.assertEqual(list(result["levels"]), ["5", "10", "15", "20"])
        self.assertEqual(result["levels"]["5"]["positive_count"], 9)
        self.assertEqual(result["levels"]["5"]["partitions"]["validation"]["row_count"], 7)
        self.assertEqual(result["levels"]["5"]["partitions"]["test"]["positive_count"], 0)
        self.assertTrue(result["warnings"])

    def test_pipeline_saves_funnel_and_rejects_stale_selection_cache(self):
        with tempfile.TemporaryDirectory() as directory, patch(
            "jira_pipeline.orchestrator.JiraClient"
        ) as client_class, patch("jira_pipeline.orchestrator.train_model") as train:
            args = pipeline_parser().parse_args([
                "--jira-url", "https://example.test", "--output-root", directory,
            ])
            client = client_class.return_value
            client.api_version = 2
            client.fields.return_value = self.field_map
            client.search_issue_keys.return_value = ["DEMO-1"]
            client.issue.return_value = self.record["issue"]
            client.comments.return_value = self.record["comments"]
            client.changelog.return_value = self.record["changelog"]
            train.return_value = (Path(directory) / "model", {"test": {}})
            result = run_pipeline(args)
            processed = Path(result["run_directory"]) / "processed"
            summary = json.loads((processed / "filter_summary.json").read_text())
            self.assertEqual(summary["selected_keys"], 1)
            self.assertEqual(summary["download_failed_records"], 0)
            self.assertTrue((processed / "filter_decisions.csv").exists())
            analysis = json.loads((processed / "dataset_analysis.json").read_text())
            self.assertEqual(analysis["levels"]["5"]["positive_count"], 1)
            run_pipeline(args)
            self.assertEqual(client.search_issue_keys.call_count, 1)
            config = Path(result["run_directory"]) / "run_config.json"
            previous = config.read_text()
            args.require_current_sprint = True
            with self.assertRaisesRegex(ValueError, "different selection"):
                run_pipeline(args)
            self.assertEqual(config.read_text(), previous)

    def test_pipeline_records_zero_rows_before_reporting_failure(self):
        with tempfile.TemporaryDirectory() as directory, patch(
            "jira_pipeline.orchestrator.JiraClient"
        ) as client_class, patch("jira_pipeline.orchestrator.train_model") as train:
            args = pipeline_parser().parse_args([
                "--jira-url", "https://example.test", "--output-root", directory,
            ])
            client = client_class.return_value
            client.api_version = 2
            client.fields.return_value = self.field_map
            client.search_issue_keys.return_value = []
            with self.assertRaisesRegex(RuntimeError, "No valid model rows"):
                run_pipeline(args)
            summary = json.loads((Path(directory) / "example/processed/filter_summary.json").read_text())
            self.assertEqual(summary["selected_keys"], 0)
            self.assertEqual(summary["accepted_records"], 0)
            train.assert_not_called()

    def test_incomplete_download_is_not_trained_or_reused(self):
        with tempfile.TemporaryDirectory() as directory, patch(
            "jira_pipeline.orchestrator.JiraClient"
        ) as client_class, patch("jira_pipeline.orchestrator.train_model") as train:
            args = pipeline_parser().parse_args([
                "--jira-url", "https://example.test", "--output-root", directory,
            ])
            client = client_class.return_value
            client.api_version = 2
            client.fields.return_value = self.field_map
            client.search_issue_keys.return_value = ["DEMO-1"]
            client.issue.side_effect = RuntimeError("download unavailable")
            with self.assertRaisesRegex(RuntimeError, "issues failed to download"):
                run_pipeline(args)
            root = Path(directory) / "example"
            summary = json.loads((root / "processed/filter_summary.json").read_text())
            self.assertEqual(summary["download_failed_records"], 1)
            self.assertFalse(json.loads((root / "run_config.json").read_text())["download_complete"])
            with self.assertRaisesRegex(ValueError, "cached download is incomplete"):
                run_pipeline(args)
            train.assert_not_called()

    def test_launcher_routes_selection_after_separator_and_preserves_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            task = Path(directory) / "Tasks/jira-url-to-instability-model"
            cluster = task / "cluster"
            cluster.mkdir(parents=True)
            launcher = cluster / "submit_jobs.sh"
            shutil.copyfile(TASK / "cluster/submit_jobs.sh", launcher)
            sources = Path(directory) / "sources.json"
            sources.write_text(json.dumps({
                "Apache": {"jira_url": "https://issues.apache.org/jira"},
                "Qt": {"jira_url": "https://bugreports.qt.io"},
            }))
            command = [
                "bash", str(launcher), "--sources-file", str(sources),
                "--run-id", "test", "--dry-run", "--only=qt", "--",
                "--only", "Qt", "--refresh",
            ]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            root = task / "cluster_runs/test"
            self.assertFalse((root / "apache").exists())
            submitted = (root / "qt/submit.sbatch").read_text()
            self.assertEqual(submitted.count("--only"), 1)
            self.assertIn("--only Qt", submitted)
            self.assertEqual(json.loads((root / "sources.json").read_text()), json.loads(sources.read_text()))
            manifest = (root / "submitted_jobs.tsv").read_text()
            self.assertEqual(len(manifest.splitlines()), 2)
            retry = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(retry.returncode, 0)
            self.assertEqual((root / "submitted_jobs.tsv").read_text(), manifest)
            rejected = subprocess.run(
                command[:-3] + ["--output-root=/tmp/wrong"],
                capture_output=True, text=True,
            )
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn("owned by the launcher", rejected.stderr)

    def test_launcher_defaults_to_separate_jobs_and_supports_jira_flag(self):
        with tempfile.TemporaryDirectory() as directory:
            task = Path(directory) / "Tasks/jira-url-to-instability-model"
            cluster = task / "cluster"
            cluster.mkdir(parents=True)
            launcher = cluster / "submit_jobs.sh"
            shutil.copyfile(TASK / "cluster/submit_jobs.sh", launcher)
            sources = Path(directory) / "sources.json"
            sources.write_text(json.dumps({
                "Apache": {"jira_url": "https://issues.apache.org/jira"},
                "Qt": {"jira_url": "https://bugreports.qt.io"},
                "Disabled": {"jira_url": "https://example.test", "enabled": False},
            }))
            base = ["bash", str(launcher), "--sources-file", str(sources), "--dry-run"]
            for run_id, flags, expected in (
                ("all", [], ["Apache", "Qt"]),
                ("qt", ["-jira", "Qt"], ["Qt"]),
                ("equals", ["-jira=Qt"], ["Qt"]),
                ("separator", ["--", "-jira", "Qt"], ["Qt"]),
                ("repeated", ["-jira", "Apache", "-jira", "Qt"], ["Apache", "Qt"]),
            ):
                with self.subTest(selection=run_id):
                    result = subprocess.run(
                        base + ["--run-id", run_id] + flags + ["--refresh"],
                        capture_output=True, text=True,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    root = task / "cluster_runs" / run_id
                    self.assertEqual(
                        sorted(path.name for path in root.iterdir() if path.is_dir()),
                        sorted(name.lower() for name in expected),
                    )
                    self.assertEqual(
                        len((root / "submitted_jobs.tsv").read_text().splitlines()),
                        len(expected) + 1,
                    )
                    for name in expected:
                        source_root = root / name.lower()
                        script = (source_root / "submit.sbatch").read_text()
                        self.assertEqual(script.count("--only"), 1)
                        self.assertIn(f"--only {name}", script)
                        self.assertIn(f"--output-root {source_root}/results", script)
                        self.assertIn(f"#SBATCH --output={source_root}/logs/job-%J.out", script)
            for flag in (["-jira"], ["-jira", "--refresh"], ["-jira", "Unknown"]):
                result = subprocess.run(
                    base + ["--run-id", "invalid"] + flag,
                    capture_output=True, text=True,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((task / "cluster_runs/invalid").exists())

    def test_cross_project_query_has_no_project_clause(self):
        query = build_jql(None, None, True, True)
        self.assertNotIn("project =", query)
        self.assertIn("type != Bug", query)

    def test_default_run_names(self):
        apache_url = "https://issues.apache.org/jira"
        self.assertEqual(repository_name(apache_url), "apache")
        self.assertEqual(default_run_name(apache_url, None), "apache")
        self.assertEqual(
            default_run_name(apache_url, "ARIA"),
            "apache-aria",
        )
        self.assertEqual(
            default_run_name("https://daosio.atlassian.net", None),
            "daosio",
        )

    def test_cluster_sources_support_cross_project_and_selection(self):
        payload = {
            "Apache": {
                "jira_url": "https://issues.apache.org/jira",
            },
            "Aria": {
                "jira_url": "https://issues.apache.org/jira",
                "project": "ARIA",
                "run_name": "apache-aria",
                "require_pr_evidence": False,
            },
            "Disabled": {
                "jira_url": "https://example.atlassian.net",
                "enabled": False,
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sources.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            sources = load_sources(path, ["Apache", "Aria"])

        self.assertIsNone(sources[0]["project"])
        self.assertEqual(sources[1]["project"], "ARIA")
        self.assertEqual(sources[1]["run_name"], "apache-aria")
        self.assertIsNone(sources[0]["require_pr_evidence"])
        self.assertFalse(sources[1]["require_pr_evidence"])

    def test_search_endpoint_uses_bounded_run_jql_for_jira_cloud(self):
        client = JiraClient.__new__(JiraClient)
        jql = (
            "(type != Bug) AND (Sprint is not EMPTY) "
            "AND (statusCategory = Done) ORDER BY created ASC"
        )

        def request(_method, path, params):
            if path == "/rest/api/2/search":
                return SimpleNamespace(
                    status_code=410,
                    headers={"content-type": "application/json"},
                    text="The requested API has been removed.",
                )
            self.assertEqual(path, "/rest/api/3/search/jql")
            self.assertEqual(params["jql"], jql)
            return SimpleNamespace(
                status_code=200,
                headers={"content-type": "application/json"},
                text='{"issues": []}',
            )

        client.request = Mock(side_effect=request)

        self.assertEqual(
            client._search_endpoint(jql),
            ("v3", "/rest/api/3/search/jql"),
        )
        for call in client.request.call_args_list:
            self.assertEqual(call.kwargs["params"]["jql"], jql)
            self.assertEqual(call.kwargs["params"]["fields"], "key")
            self.assertEqual(call.kwargs["params"]["maxResults"], 1)

    def test_search_endpoint_error_includes_both_responses(self):
        client = JiraClient.__new__(JiraClient)
        client.request = Mock(
            side_effect=[
                SimpleNamespace(
                    status_code=410,
                    headers={"content-type": "application/json"},
                    text="API removed",
                ),
                SimpleNamespace(
                    status_code=401,
                    headers={"content-type": "application/json"},
                    text="Authentication required",
                ),
            ]
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "v2 HTTP 410: API removed; v3 HTTP 401: Authentication required",
        ):
            client._search_endpoint("project = DEMO ORDER BY created ASC")


if __name__ == "__main__":
    unittest.main()
