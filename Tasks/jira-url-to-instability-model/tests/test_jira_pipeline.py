import unittest
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd

from cluster.run_cluster import load_sources
from jira_pipeline.client import JiraClient
from jira_pipeline.orchestrator import (
    build_jql,
    default_run_name,
    repository_name,
)
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
        self.assertIn("Sprint is not EMPTY", basic)
        self.assertNotIn("github.com", basic)

        strict = build_jql("DEMO", None, True, True)
        self.assertIn("statusCategory = Done", strict)
        self.assertIn('comment ~ "https://github.com"', strict)

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
