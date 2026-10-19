import tempfile
import unittest
from pathlib import Path

import pandas as pd

from Code_Smells_Detection.runtime import common, prepare


class RuntimeCase(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.storage = Path(self.temporary.name)
        self.root = self.storage / "runs/test"
        self.root.mkdir(parents=True)

    def succeeded(self, stage, unit="all"):
        common.write_json(self.root / "status" / f"{stage}-{unit}.json", {"status": "succeeded"})

    def frozen_study(self, count=120):
        common.write_json(self.root / "study.json", {
            "schema": common.SCHEMA, "source_sha256": common.source_hash(), "inputs": {},
            "sources": {"Apache": {"url": "https://example.invalid", "jql": "test"}},
            "prior": {}, "min_rows": 100,
        })
        rows = []
        for index in range(count):
            date = pd.Timestamp("2020-01-01") + pd.Timedelta(days=index)
            rows.append({
                "row_id": f"Apache:TEST-{index}", "source": "Apache", "issue_key": f"TEST-{index}",
                "created": str(date), "time_add_to_sprint": str(date + pd.Timedelta(hours=2)),
                "original_summary_sprint": "Please implement safely" if index % 2 else "TODO",
                "original_description_sprint": "description", "original_acceptance_criteria_sprint": "",
                "issue_type": "Story", "project_key": "TEST", "priority": "High",
                "original_story_points_sprint": index % 2, "num_comments_before_sprint": 1,
                "num_changes_text_before_sprint": 0, "num_changes_story_point_before_sprint": 0,
                "time_until_add_to_sprint": 120, "num_issues_cretor_prev": index,
            })
        frame = pd.DataFrame(rows)
        common.write_csv(self.root / "cohort/candidates.csv", frame[["source", "issue_key", "issue_type", "created"]])
        common.write_json(self.root / "raw/Apache/field_map.json", {})
        records = {}
        for row in rows:
            raw_path = self.root / "raw/Apache" / f"{row['issue_key']}.json"
            common.write_json(raw_path, {"issue": {"key": row["issue_key"], "fields": {}},
                                        "comments": [], "changelog": [], "collection_complete": True})
            records[row["issue_key"]] = common.file_hash(raw_path)
        common.write_json(self.root / "raw/Apache/manifest.json", {
            "records": records, "field_map": common.file_hash(self.root / "raw/Apache/field_map.json")})
        path = self.root / "features/Apache/features.csv"
        common.write_csv(path, frame)
        train_end, val_end = int(count * .6), int(count * .6) + int(count * .2)
        assignment = {row_id: "train" if i < train_end else "validation" if i < val_end else "test"
                      for i, row_id in enumerate(frame.row_id)}
        common.write_json(self.root / "splits/Apache.json", {
            "feature_sha256": common.file_hash(path), "rows": frame.row_id.tolist(),
            "assignment": assignment,
        })
        common.write_json(self.root / "cohort/retention.json", {"selected_candidates": count})
        common.write_json(self.root / "features/Apache/filter_decisions.json", [
            {"row_id": row_id, "reason": None} for row_id in frame.row_id])
        common.write_json(self.root / "evidence/Apache/audit.json", {
            "counts": {"complete": count}, "cross_partition_revisions": []})
        self.succeeded("freeze", "Apache")
        return frame, assignment

    def profile(self, language="java"):
        return {
            "language": language, "edition": "community", "version": "fixture",
            "origin": "offline test fixture", "platform": "Linux", "license": "community",
            "artifacts": [{"name": "tool", "sha256": "a" * 64}],
            "command": ["tool", "{input}", "{output}"],
            "catalog": {"implementation": ["Long Method"], "design": ["Deficient Encapsulation"]},
            "reports": {
                category: {"file": category + ".csv", "smell_column": "Smell",
                           "path_column": "Path", "entity_columns": ["Entity"]}
                for category in ("implementation", "design")
            },
            "coverage": [{"file": "coverage.csv", "path_column": "Path"}],
        }

    def native_output(self, directory, language="java"):
        directory.mkdir(parents=True, exist_ok=True)
        extension = {"java": ".java", "python": ".py", "csharp": ".cs"}[language]
        files = ["src/Bad" + extension, "src/Clean" + extension]
        pd.DataFrame({"Path": files}).to_csv(directory / "coverage.csv", index=False)
        for category, smell in (("implementation", "Long Method"), ("design", "Deficient Encapsulation")):
            pd.DataFrame([{"Path": files[0], "Smell": smell, "Entity": "Bad"}]).to_csv(
                directory / (category + ".csv"), index=False)
        return files
