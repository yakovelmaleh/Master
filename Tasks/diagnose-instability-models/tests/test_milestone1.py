import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

TASK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TASK / "scripts"))

from support import (
    CHANGES, COUNT, HF, LEVELS, PROJECTS, REPO, TEXT_COLUMNS, align_predictions,
    calculate_metrics, digest, file_hash, label_column, load_table, np, pd,
    read_json, row_hash, save_table, sha_bytes, write_json,
)
from data_profile import characteristics, histories_at, profile, sample_plan
from errors import errors, misranking, paired, paired_interval, reviewed_annotations
from evidence import neural, verify_population
from run_diagnostics import initialize, validate_config
from token_coverage import token_coverage

spec = importlib.util.spec_from_file_location("diagnostic_launcher", TASK / "cluster/submit_jobs.py")
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)

CONFIG = read_json(TASK / "configuration/milestone1.json")


def frame(rows=12):
    counts = np.resize([0, 4, 5, 9, 10, 14, 15, 19, 20, 22, 30, 0], rows)
    data = pd.DataFrame({
        "row_id": [f"Apache:X-{i}" for i in range(rows)],
        "issue_key": [f"X-{i}" for i in range(rows)],
        "project": "Apache", "split": "test",
        "time_add_to_sprint": pd.date_range("2020-01-01", periods=rows).astype(str),
        COUNT: counts, CHANGES: (counts > 0).astype(int),
    })
    for k in LEVELS:
        data[label_column(k)] = ((counts >= k) & (data[CHANGES] > 0)).astype(int)
    for c in TEXT_COLUMNS:
        data[c] = [f"Original requirement {i}" for i in range(rows)]
    data["model_text"] = data[TEXT_COLUMNS].agg(" ".join, axis=1)
    return data


def predictions(canonical, level=5):
    p = np.linspace(.05, .95, len(canonical))
    return pd.DataFrame({
        "row_id": canonical.row_id, "actual_label": canonical[label_column(level)],
        "instability_probability": p, "predicted_label": (p >= .5).astype(int),
    })


def run_root(root):
    write_json(root / "run.json", {
        "run_id": "fixture", "source_sha256": "fixture", "configuration_sha256": digest(CONFIG)
    })


class AlignmentTests(unittest.TestCase):
    def test_alignment_is_identity_based_and_fail_closed(self):
        canonical = frame()
        prediction = predictions(canonical)
        actual = align_predictions(prediction.sample(frac=1, random_state=3), canonical, 5)
        self.assertEqual(list(actual.row_id), list(canonical.row_id))
        for bad in (
            prediction.iloc[:-1], pd.concat([prediction, prediction.iloc[:1]]),
            prediction.assign(row_id=[*prediction.row_id.iloc[:-1], "Apache:extra"]),
            prediction.assign(actual_label=1 - prediction.actual_label),
            prediction.assign(actual_label=.5),
            prediction.assign(instability_probability=np.nan),
            prediction.assign(instability_probability=1.1),
            prediction.assign(source_dataset="Qt"),
        ):
            with self.assertRaises(ValueError):
                align_predictions(bad, canonical, 5)

    def test_auc_prc_is_not_ap_and_constant_control_is_preserved(self):
        metric = calculate_metrics([0, 0, 0, 1], [.5] * 4, .5)
        self.assertEqual(metric["auc_prc"], .625)
        self.assertEqual(metric["average_precision"], .25)
        self.assertIsNone(calculate_metrics([1, 1], [.2, .8], .5)["auc_prc"])

    def test_frozen_hashes_nesting_and_label_formula(self):
        data = frame()
        frames = [data.iloc[:4], data.iloc[4:8], data.iloc[8:]]
        expected = {"partitions": {
            split: {"rows": len(part), "row_ids_sha256": row_hash(part.row_id),
                    "labels_sha256": {str(k): sha_bytes("\n".join(
                        f"{r}\t{int(v)}" for r, v in zip(part.row_id, part[label_column(k)])
                    ).encode()) for k in LEVELS}}
            for split, part in zip(("train", "validation", "test"), frames)
        }}
        verify_population(data, frames, expected)
        with self.assertRaisesRegex(ValueError, "identity"):
            verify_population(data, [frames[0].iloc[::-1], *frames[1:]], expected)
        changed = [p.copy() for p in frames]
        changed[0].iloc[1, changed[0].columns.get_loc(COUNT)] = 100
        with self.assertRaisesRegex(ValueError, "implemented rule"):
            verify_population(data, changed, expected)
        changed = [p.copy() for p in frames]
        changed[0][label_column(5)] = changed[0][label_column(5)].astype(float)
        changed[0].iloc[0, changed[0].columns.get_loc(label_column(5))] = .5
        with self.assertRaisesRegex(ValueError, "Nonbinary"):
            verify_population(data, changed, expected)


class SealedEvidenceTests(unittest.TestCase):
    def make_study(self, root):
        canonical = frame()
        validation = canonical.copy().assign(split="validation")
        # Identity sets can match across fixture partitions; each split is verified independently.
        population = pd.concat([validation, canonical], ignore_index=True)
        model = {"id": "fixture/model", "revision": "a" * 40}
        study = {"reference_sha256": file_hash(HF / "reference_contract.json"), "models": {"fixture": model}}
        write_json(root / "study.json", study)
        checkpoint = root / "frozen/Apache/fixture/5/candidate/checkpoint"
        inference = {"project": "Apache", "level": 5, "model_key": "fixture", "model": model,
                     "config": {"max_length": 100}, "transformer": None}
        write_json(checkpoint / "inference.json", inference)
        selected = {
            "project": "Apache", "level": 5, "model": "fixture", "threshold": .5,
            "directory": "frozen/Apache/fixture/5/candidate",
            "checkpoint_files": {"inference.json": file_hash(checkpoint / "inference.json")},
        }
        prediction = predictions(canonical)
        prediction.sample(frac=1, random_state=2).to_csv(checkpoint.parent / "validation_predictions.csv", index=False)
        selected["validation_predictions_sha256"] = file_hash(checkpoint.parent / "validation_predictions.csv")
        metric = calculate_metrics(prediction.actual_label, prediction.instability_probability, .5)
        selected["validation"] = metric
        selections = [{**selected, "project": p, "level": k} for p in PROJECTS for k in LEVELS]
        write_json(root / "sealed.json", {"study_sha256": digest(study), "selections": selections})
        final = root / "final/Apache/5"
        final.mkdir(parents=True)
        prediction.to_csv(final / "test_predictions.csv", index=False)
        result = {
            "project": "Apache", "level": 5, "model": "fixture", "test": metric,
            "checkpoint_files": selected["checkpoint_files"], "selection_sha256": digest(selected),
            "test_predictions_sha256": file_hash(final / "test_predictions.csv"),
        }
        write_json(final / "metrics.json", result)
        report = {"study_sha256": digest(study), "cells": [result]}
        return population, report

    def test_seal_hash_prediction_hash_and_metric_reproduction(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            population, report = self.make_study(root)
            rows, details = neural("SLM1", root, report, "Apache", 5, population, 1e-10)
            self.assertEqual(len(rows), 2)
            self.assertEqual(details["status"], "succeeded")
            self.assertEqual(list(rows[0].row_id), list(population[population.split == "validation"].row_id))
            changed = read_json(root / "study.json")
            write_json(root / "study.json", {**changed, "changed": True})
            with self.assertRaisesRegex(ValueError, "identity"):
                neural("SLM1", root, report, "Apache", 5, population, 1e-10)
            write_json(root / "study.json", changed)
            path = root / "final/Apache/5/test_predictions.csv"
            original = path.read_bytes()
            path.write_bytes(original + b"\n")
            with self.assertRaisesRegex(ValueError, "prediction hash"):
                neural("SLM1", root, report, "Apache", 5, population, 1e-10)
            path.write_bytes(original)
            result = read_json(path.parent / "metrics.json")
            result["test"]["auc_prc"] += .001
            write_json(path.parent / "metrics.json", result)
            forged_report = {"study_sha256": report["study_sha256"], "cells": [result]}
            with self.assertRaisesRegex(ValueError, "Metric mismatch"):
                neural("SLM1", root, forged_report, "Apache", 5, population, 1e-10)


class ProfileTests(unittest.TestCase):
    def test_sampling_is_repeatable_deduplicated_and_tracks_probabilities(self):
        traits = characteristics(frame(120))
        first, strata = sample_plan(traits, CONFIG)
        second, _ = sample_plan(traits.iloc[::-1], CONFIG)
        self.assertEqual(list(first.row_id), list(second.row_id))
        self.assertFalse(first.row_id.duplicated().any())
        self.assertTrue(first.inclusion_probability.between(0, 1, inclusive="right").all())
        for row in first.itertuples():
            groups = [s for s in strata if row.row_id in s["selected_row_ids"]]
            self.assertTrue(groups)
            belonging = []
            data = traits[traits.row_id == row.row_id].iloc[0]
            for s in strata:
                is_boundary = abs(data[COUNT] - s["level"]) <= CONFIG["boundary_radius"]
                if data[label_column(s["level"])] == s["label"] and is_boundary == s["boundary"]:
                    belonging.append(s)
            self.assertAlmostEqual(row.inclusion_probability, 1 - np.prod([
                1 - s["stratum_probability"] for s in belonging
            ]))
        self.assertEqual(sum(s["sampled"] for s in strata), sum(len(s["selected_row_ids"]) for s in strata))

    def test_history_coverage_and_real_diffs_no_automatic_human_review(self):
        data = frame()
        record = {"row_id": data.row_id.iloc[0], "project": "Apache",
                  "observation_start": "2019-12-01", "observation_end": "2021-01-01",
                  "history_complete": True,
                  "events": [{"field": "summary", "at": "2020-01-02", "before": "old", "after": "new"}]}
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "histories.jsonl"
            path.write_text(json.dumps(record) + "\n")
            histories, coverage = histories_at(path, data)
            self.assertIn("-old", histories[record["row_id"]]["events"][0]["unified_diff"])
            self.assertEqual(coverage["complete_rows"], 1)
            self.assertNotEqual(coverage["status"], "human_reviewed")
            path.write_text(json.dumps({**record, "observation_end": "2019-01-01"}) + "\n")
            with self.assertRaisesRegex(ValueError, "coverage"):
                histories_at(path, data)
            path.write_text(json.dumps(record) + "\n" + json.dumps(record) + "\n")
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                histories_at(path, data)

    def test_offline_profiles_and_error_pipeline_leave_review_pending(self):
        data = frame(60)
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            run_root(root)
            save_table(root, "manifest/population.csv", data, "T1")
            write_json(root / "manifest/integrity_checks.json", {
                "populations": [{"project": p, "status": "succeeded"} for p in PROJECTS], "cells": []
            })
            self.assertEqual(profile(root, CONFIG), "succeeded")
            audit = pd.read_csv(root / "data-characterization/label_audit.csv")
            self.assertTrue(audit.review_status.eq("pending").all())
            packets = [json.loads(s) for s in (root / "data-characterization/review_examples.jsonl").read_text().splitlines()]
            self.assertTrue(all(p["model_scores_hidden"] for p in packets))
            self.assertTrue(all("instability_probability" not in p for p in packets))
            outputs = []
            for family in ("classical", "SLM1", "SLM2", "Jev"):
                for k in LEVELS:
                    p = predictions(data, k)
                    p = p.assign(project="Apache", level=k, family=family, model="fixture",
                                 split="test", threshold=.5, provenance="fixture")
                    outputs.append(p)
            save_table(root, "manifest/predictions.csv", pd.concat(outputs), "T1")
            self.assertEqual(errors(root, {**CONFIG, "bootstrap_samples": 100}), "blocked")
            result = read_json(root / "error-analysis/error_slices.json")
            matched = [c for c in result["comparisons"] if c["slice"] == "all"]
            self.assertEqual(len(matched), 12)
            self.assertTrue(all(c["auc_prc_difference_model_minus_classical"] == 0 for c in matched))
            self.assertEqual(len(result["four_family_fixed_threshold"]), 4)
            self.assertEqual(result["review_status"], "pending; candidates are not a reviewed example set")
            path = root / "manifest/predictions.csv"
            path.write_text(path.read_text() + "\n")
            with self.assertRaisesRegex(ValueError, "changed"):
                load_table(root, "manifest/predictions.csv")

    def test_completed_reviews_require_frozen_sample_identity_and_rubric(self):
        data = frame()
        sample, _ = sample_plan(characteristics(data), CONFIG)
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            run_root(root)
            save_table(root, "data-characterization/label_audit.csv", sample, "T2")
            annotated = sample[["row_id", "sample_id"]].head(1).assign(
                review_status="reviewed", reviewer_id="reviewer-A", edit_category="editorial_formatting",
                evidence_quality="partial", extraction_assessment="cannot_verify", rationale="Actual edit inspected."
            )
            path = root / "annotations.csv"
            annotated.to_csv(path, index=False)
            self.assertEqual(len(reviewed_annotations(root, path)), 1)
            annotated.assign(sample_id="forged").to_csv(path, index=False)
            with self.assertRaisesRegex(ValueError, "identity changed"):
                reviewed_annotations(root, path)
            annotated.assign(edit_category="invented").to_csv(path, index=False)
            with self.assertRaisesRegex(ValueError, "rubric"):
                reviewed_annotations(root, path)

    def test_tokenizer_only_coverage_checks_pinned_cache_and_supports_hf_blob_links(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            run_root(root)
            model = {"id": "fixture/model", "revision": "a" * 40}
            cache = root / "cache"
            snapshot = cache / "snapshots" / model["revision"]
            snapshot.mkdir(parents=True)
            blob = cache / "blobs/tokenizer"
            blob.parent.mkdir()
            blob.write_text("{}")
            (snapshot / "tokenizer.json").symlink_to(blob)
            write_json(cache / "ready/fixture.json", {
                "model": model, "snapshot": str(snapshot),
                "files": {"tokenizer.json": file_hash(blob)},
            })
            write_json(root / "manifest/integrity_checks.json", {"cells": [{
                "project": "Apache", "level": 5, "family": "SLM1", "status": "succeeded",
                "protocol": {"inference": {"model": model, "model_key": "fixture",
                                          "config": {"max_length": 4}}},
            }]})

            class Tokenizer:
                truncation_side = "right"

                def __call__(self, text, **options):
                    self.options = options
                    return {"input_ids": text.split()}

            tokenizer = Tokenizer()
            factory = types.SimpleNamespace(from_pretrained=lambda *a, **k: tokenizer)
            with patch.dict(sys.modules, {"transformers": types.SimpleNamespace(AutoTokenizer=factory)}):
                result = token_coverage(root, frame(), cache)
                self.assertEqual(len(result), 12)
                self.assertTrue(result.truncated.all())
                blob.write_text("changed")
                result = token_coverage(root, frame(), cache)
                self.assertTrue(result.empty)
                checks = read_json(root / "data-characterization/token_coverage.json")["cells"]
                self.assertEqual(checks[0]["status"], "blocked")


class ErrorTests(unittest.TestCase):
    def test_tied_rank_errors_are_order_independent(self):
        y = np.array([0, 1, 0, 1])
        p = np.array([.5, .5, .1, .9])
        np.testing.assert_allclose(misranking(y, p), [.25, .25, 0, 0])
        order = np.array([3, 0, 2, 1])
        np.testing.assert_allclose(misranking(y[order], p[order]), misranking(y, p)[order])
        self.assertTrue(np.isnan(misranking([1, 1], [.1, .9])).all())

    def test_uncertainty_is_paired_repeatable_and_small_slices_are_flagged(self):
        data = pd.DataFrame({
            "actual_label": [0, 1] * 40, "classical_probability": [.2, .7] * 40,
            "model_probability": [.2, .7] * 40,
            "classical_threshold": .5, "model_threshold": .5,
        })
        interval = paired_interval(data, CONFIG)
        self.assertEqual(interval, paired_interval(data, CONFIG))
        self.assertEqual(interval["interval_95"], [0, 0])
        small = paired(data.iloc[:4], CONFIG, uncertainty=True)
        self.assertFalse(small["adequate_support"])
        self.assertIsNone(small["uncertainty"]["interval_95"])
        one = paired(data[data.actual_label == 1], CONFIG)
        self.assertIsNone(one["metrics"]["classical"]["auc_prc"])


class LauncherTests(unittest.TestCase):
    def args(self):
        return argparse.Namespace(
            stage="inventory", run_id="test", output_root=Path("/tmp/diagnostics"),
            artifact_root=[Path("/tmp/absent-studies")], histories=None, tokenizer_cache=None,
            reviews=None,
            config=TASK / "configuration/milestone1.json", cpus=4, mem="16G", time="02:00:00",
            partition="work", mail_user="test@example.invalid", conda_env="master-hf",
            module="anaconda", dry_run=False,
        )

    def test_dispatcher_discovery_and_dry_run_never_submit(self):
        listed = subprocess.check_output(["bash", str(REPO / "Tasks/run_cluster_task.sh"), "--list"], text=True)
        self.assertIn("diagnose-instability-models", listed)
        text = subprocess.check_output([
            "bash", str(REPO / "Tasks/run_cluster_task.sh"), "diagnose-instability-models",
            "--stage", "inventory", "--run-id", "launcher-test", "--partition", "work",
            "--dry-run",
        ], text=True)
        for expected in ("#SBATCH --array=0-0%1", "#SBATCH --mail-type=ALL",
                         "slurm-%A_%a.out", "slurm-%A_%a.err", "--stage inventory"):
            self.assertIn(expected, text)
        self.assertNotIn("--gres", text)
        subprocess.run(["bash", "-n"], input=text, text=True, check=True)

    def test_global_active_hf_guard_and_stage_mapping(self):
        args = self.args()
        with tempfile.TemporaryDirectory() as d:
            task = Path(d)
            with patch.object(launcher, "TASK", task), patch.object(
                launcher.subprocess, "check_output", return_value="master-hf-train\n"
            ) as output, patch.object(launcher, "exclusive_lock") as lock:
                lock.return_value.__enter__.return_value = None
                with self.assertRaisesRegex(ValueError, "Another Master HF"):
                    launcher.submit(args)
                self.assertEqual(output.call_count, 1)
                self.assertFalse((task / "cluster_runs").exists())
            with patch.object(launcher, "TASK", task), patch.object(
                launcher.subprocess, "check_output", side_effect=["", "12345;site\n"]
            ), patch.object(launcher, "exclusive_lock") as lock:
                lock.return_value.__enter__.return_value = None
                launcher.submit(args)
            manifest = read_json(next(task.glob("cluster_runs/*/job_manifest.json")))
            self.assertEqual(manifest["job_id"], "12345")
            self.assertEqual(manifest["stage_job_mapping"][0], {
                "array_index": 0, "job_id": "12345_0", "stages": ["T1"]
            })

    def test_external_output_and_immutable_provenance(self):
        with tempfile.TemporaryDirectory() as d:
            args = self.args()
            args.output_root = Path(d)
            root, *_ = initialize(args)
            self.assertTrue((root / "run.json").is_file())
            initialize(args)
            with patch("run_diagnostics.source_hash", return_value="changed"):
                with self.assertRaisesRegex(ValueError, "provenance changed"):
                    initialize(args)
            args.output_root = TASK
            with self.assertRaisesRegex(ValueError, "outside"):
                initialize(args)
        for value in ("work\n#SBATCH", "work #inject", ""):
            with self.assertRaises(ValueError):
                launcher.directive(value)


if __name__ == "__main__":
    unittest.main()
