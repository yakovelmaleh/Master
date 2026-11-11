import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import test_milestone1 as fixtures
from test_milestone1 import CONFIG, TASK, frame, launcher
from support import (
    LEVELS, calculate_metrics, digest, emit, file_hash, label_column,
    np, pd, read_json, row_hash, save_table, sha_bytes, write_json,
)
from diagnostic_config import REVIEW_POLICY
from errors import misranking, paired
from evaluate import final_metrics
from prepare_review import (
    candidate_pairs, enrich, execute, load_inputs, render_html, select_batch, write_batch,
)
from reconcile_intervals import reconcile_cell, replay


def fixture():
    populations, predictions, diagnostics, checks = [], [], [], []
    rng = np.random.RandomState(3)
    for project in ("Apache", "MariaDB", "IntelDAOS"):
        data = frame(96).assign(project=project)
        data["row_id"] = project + ":" + data.issue_key
        populations.append(data)
        for level in LEVELS:
            y = data[label_column(level)].to_numpy()
            for family in ("classical", "SLM1", "SLM2"):
                i = np.arange(len(data))
                good = i % 2 == 0 if family == "classical" else i % 4 < 2
                if family == "SLM2":
                    good = ~good
                high = (y == 1) == good
                probability = np.round(np.where(high, .75, .01) + rng.uniform(0, .23, len(data)), 6)
                scored = pd.DataFrame({
                    "row_id": data.row_id, "project": project, "level": level, "family": family,
                    "split": "test", "actual_label": y, "instability_probability": probability,
                    "model": family + "-fixture", "threshold": .5,
                })
                predictions.append(scored)
                diagnostics.append(scored.assign(
                    opposite_class_misranking_fraction=misranking(y, probability),
                    tokens="100.0", limit="512.0", truncated="False",
                ))
                checks.append({"family": family, "project": project, "level": level, "status": "succeeded"})
    return (pd.concat(populations, ignore_index=True), pd.concat(predictions, ignore_index=True),
            pd.concat(diagnostics, ignore_index=True), {"cells": checks})


def write_source(root):
    population, predictions, diagnostics, integrity = fixture()
    run = {"run_id": root.name, "source_sha256": "original-producer",
           "configuration": CONFIG, "configuration_sha256": digest(CONFIG), "histories": None}
    write_json(root / "run.json", run)
    for stage in ("inventory", "profile", "errors"):
        emit(root, f"manifest/{stage}_status.json", stage, "succeeded")
    emit(root, "manifest/integrity_checks.json", "T1", "succeeded", **integrity)
    emit(root, "manifest/artifact_manifest.json", "T1", "succeeded", artifacts=[])
    emit(root, "error-analysis/error_slices.json", "T3", "succeeded", comparisons=[])
    for path, data in (("manifest/population.csv", population), ("manifest/predictions.csv", predictions),
                       ("error-analysis/row_diagnostics.csv", diagnostics)):
        save_table(root, path, data, "fixture")
    return population, predictions, diagnostics, integrity


class ReviewBatchTests(unittest.TestCase):
    def test_balanced_unique_repeatable_ranking_categories(self):
        population, predictions, diagnostics, integrity = fixture()
        candidates = candidate_pairs(population, predictions, diagnostics, integrity)
        batch, manifest = select_batch(candidates)
        reverse, _ = select_batch(list(reversed(candidates)))
        self.assertEqual(batch, reverse)
        self.assertEqual(len(batch), 20)
        self.assertEqual(len({r["row_id"] for r in batch}), 20)
        self.assertFalse(manifest["shortages"])
        self.assertGreaterEqual(len(manifest["selected_by_project"]), 2)
        self.assertGreaterEqual(len(manifest["selected_by_K"]), 2)
        self.assertEqual(set(manifest["selected_by_family"]), {"SLM1", "SLM2"})
        for category in REVIEW_POLICY["categories"]:
            group = [r for r in batch if r["category"] == category]
            self.assertEqual(len(group), 5)
            for row in group:
                a, b = row["classical"]["inversion_fraction"], row["slm"]["inversion_fraction"]
                conditions = {
                    "classical_good_slm_poor": a <= .25 and b >= .5,
                    "slm_good_classical_poor": b <= .25 and a >= .5,
                    "both_poor": a >= .5 and b >= .5,
                    "both_good": a <= .25 and b <= .25,
                }
                self.assertTrue(conditions[category])
        _, short = select_batch([r for r in candidates if r["category"] == "both_good"])
        self.assertTrue(short["shortages"])

    def test_exact_input_mismatches_fail_closed(self):
        population, predictions, diagnostics, integrity = fixture()
        for bad in (predictions.iloc[1:],
                    predictions.assign(actual_label=1 - predictions.actual_label),
                    predictions[predictions.family != "SLM1"]):
            with self.assertRaises(ValueError):
                candidate_pairs(population, bad, diagnostics, integrity)
        broken = diagnostics.copy()
        broken.loc[0, "opposite_class_misranking_fraction"] = .12345678
        with self.assertRaisesRegex(ValueError, "ranking errors"):
            candidate_pairs(population, predictions, broken, integrity)

    def test_missing_history_escaping_and_blank_human_answers(self):
        population, predictions, diagnostics, integrity = fixture()
        batch, selection = select_batch(candidate_pairs(population, predictions, diagnostics, integrity))
        column = "original_description_sprint"
        population[column] = '<script>alert("not executable")</script>\n=malicious spreadsheet text'
        enrich(batch, population, {}, {"status": "unavailable"})
        self.assertTrue(all(r["label_verification"] == "unavailable" for r in batch))
        page = render_html(batch, selection)
        self.assertNotIn("<script>", page)
        self.assertIn("&lt;script&gt;", page)
        self.assertIn("Do not infer", page)
        with tempfile.TemporaryDirectory() as d:
            write_batch(Path(d), batch, selection)
            sheet = pd.read_csv(Path(d) / "review_sheet.csv", keep_default_na=False)
            self.assertTrue(sheet.review_status.eq("pending").all())
            self.assertTrue(sheet.reviewer_id.eq("").all())
            self.assertTrue(sheet.label_supported_yes_no_uncertain_unavailable.eq("").all())

    def test_available_history_is_shown_without_claiming_review(self):
        population, predictions, diagnostics, integrity = fixture()
        batch, selection = select_batch(candidate_pairs(population, predictions, diagnostics, integrity))
        event = {"at": "2021-01-03", "field": "summary", "before": "old text",
                 "after": "actual later text", "post_entry": True}
        history = {batch[0]["row_id"]: {"observation_start": "2020-01-01",
                   "observation_end": "2021-01-10", "history_complete": False, "events": [event]}}
        enrich(batch, population, history, {"status": "available_not_human_reviewed"})
        self.assertEqual(batch[0]["review_status"], "pending")
        page = render_html(batch, selection)
        self.assertIn("2021-01-03", page)
        self.assertIn("actual later text", page)
        self.assertEqual(batch[1]["label_verification"], "unavailable")

    def test_external_write_once_export_preserves_original_run_and_blocks_missing_ci(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "fixture"
            write_source(root)
            original = {str(p): p.read_bytes() for p in root.rglob("*") if p.is_file()}
            self.assertEqual(execute(root, "human-review-01"), 2)
            status = read_json(root / "error-analysis/human-review-01/status.json")
            self.assertEqual(status["prepared_stories"], 20)
            self.assertEqual(status["human_reviews_completed"], 0)
            self.assertTrue(all(c["status"] == "blocked" for c in status["reconciliation_status"]))
            for path, content in original.items():
                self.assertEqual(Path(path).read_bytes(), content)
            with self.assertRaises(FileExistsError):
                execute(root, "human-review-01")
            path = root / "manifest/population.csv"
            path.write_bytes(path.read_bytes() + b"\n")
            with self.assertRaisesRegex(ValueError, "input changed"):
                load_inputs(root)

    def test_dependency_free_launcher_routes_review_only(self):
        command = [sys.executable, "-S", str(TASK / "cluster/submit_jobs.py"),
                   "--stage", "review", "--run-id", "diag-m1-20261109-02", "--partition", "main",
                   "--dry-run"]
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        self.assertIn("prepare_review.py", result.stdout)
        self.assertNotIn("run_diagnostics.py", result.stdout)
        self.assertIn("--batch-id human-review-01", result.stdout)
        self.assertIn("#SBATCH --mail-type=ALL", result.stdout)
        self.assertIn("#SBATCH --array=0-0%1", result.stdout)
        subprocess.run(["bash", "-n"], input=result.stdout, text=True, check=True)
        bad = subprocess.run(command + ["--tokenizer-cache", "/tmp/cache"], capture_output=True, text=True)
        self.assertNotEqual(bad.returncode, 0)
        with tempfile.TemporaryDirectory() as d:
            args = fixtures.LauncherTests().args()
            args.stage, args.batch_id, args.config = "review", "human-review-01", None
            args.artifact_root = args.histories = args.tokenizer_cache = args.reviews = None
            args.output_root = Path(d) / "external"
            write_json(args.output_root / args.run_id / "run.json", {})
            with patch.object(launcher, "TASK", Path(d) / "task"), patch.object(
                launcher.subprocess, "check_output", side_effect=["", "12345;site\n"]
            ), patch.object(launcher, "exclusive_lock"):
                launcher.submit(args)
            manifest = read_json(next((Path(d) / "task").glob("cluster_runs/*/job_manifest.json")))
            self.assertEqual(manifest["outputs"], str(
                args.output_root / args.run_id / "error-analysis/human-review-01"))
            self.assertEqual(manifest["stage_job_mapping"][0]["stages"],
                             ["T2-review-preparation", "T3-interval-reconciliation"])
            self.assertIn(digest(REVIEW_POLICY), manifest["command"])


class ReconciliationTests(unittest.TestCase):
    def make_inputs(self):
        data = frame(96)
        rng = np.random.RandomState(11)
        paired_frame = data[["row_id", "time_add_to_sprint"]].copy()
        paired_frame["actual_label"] = data[label_column(5)]
        paired_frame["classical_probability"] = rng.uniform(0, 1, len(data))
        paired_frame["model_probability"] = rng.uniform(0, 1, len(data))
        paired_frame["classical_threshold"] = .3
        paired_frame["model_threshold"] = .5
        original_config = {"seed": 7, "bootstrap_samples": 120}
        config = {**CONFIG, "bootstrap_samples": 100}
        original = final_metrics(paired_frame.actual_label.to_numpy(),
                                 paired_frame.model_probability.to_numpy(),
                                 paired_frame.classical_probability.to_numpy(), .5, 120, 7)
        diagnostic = paired(paired_frame, config, uncertainty=True)
        return data, paired_frame, original_config, config, original, diagnostic

    def test_both_intervals_replay_and_original_disagreement_blocks(self):
        _, paired_frame, original_config, config, original, diagnostic = self.make_inputs()
        result = replay(paired_frame, original, diagnostic, original_config, config)
        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(len(result["fixed_bridge"]), 6)
        self.assertNotEqual(original["uncertainty"]["difference_95"]["auc_prc"],
                            diagnostic["uncertainty"]["interval_95"])
        original["uncertainty"]["difference_95"]["auc_prc"][0] += .01
        with self.assertRaisesRegex(ValueError, "interval replay mismatch"):
            replay(paired_frame, original, diagnostic, original_config, config)

    def test_archived_hash_order_selection_and_point_metrics_are_checked(self):
        data, pairs, original_config, config, original, diagnostic = self.make_inputs()
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            frames, blobs, normalized = {}, {}, []
            for family, name in (("classical", "classical"), ("SLM2", "model")):
                native = pd.DataFrame({
                    "row_id": data.row_id, "actual_label": pairs.actual_label,
                    "instability_probability": pairs[name + "_probability"],
                })
                blobs[name] = native.to_csv(index=False).encode()
                frames[name] = pd.read_csv(io.BytesIO(blobs[name]))
                normalized.append(frames[name].assign(
                    project="Apache", level=5, split="test", family=family,
                    model="fixture/baseline" if name == "classical" else "fixture",
                    threshold=.3 if name == "classical" else .5,
                ))
            path = root / "test_predictions.csv"
            path.write_bytes(blobs["model"])
            reference = {
                "source_commit": "archived-fixture", "projects": {"Apache": {
                    "partitions": {"test": {
                        "rows": len(data), "row_ids_sha256": row_hash(data.row_id),
                        "labels_sha256": {"5": sha_bytes("\n".join(
                            f"{r}\t{int(y)}" for r, y in zip(data.row_id, pairs.actual_label)).encode())},
                    }},
                    "baseline": {"5": {
                        "model": "fixture", "variant": "baseline", "predictions_git_path": "test_predictions.csv",
                        "predictions_sha256": sha_bytes(blobs["classical"]),
                        "metrics": {"test": calculate_metrics(pairs.actual_label, pairs.classical_probability, .3)},
                    }},
                }},
            }
            write_json(root / "reference_contract.json", reference)
            selection = {"model": "fixture", "threshold": .5}
            study = {"config": original_config}
            cell = {**original, "project": "Apache", "level": 5, "model": "fixture",
                    "baseline_identity": {"model": "fixture", "variant": "baseline"},
                    "artifact_reference": {"config_sha256": digest(original_config)},
                    "selection_sha256": digest(selection), "test_predictions_sha256": file_hash(path)}
            write_json(root / "report.json", {"study_sha256": digest(study), "cells": [cell]})
            config["reports"] = {**config["reports"], "SLM2": "report.json"}
            write_json(root / "run.json", {"configuration": config,
                                         "reference_sha256": file_hash(root / "reference_contract.json")})
            write_json(root / "manifest/artifact_manifest.json", {
                "artifacts": [{"kind": "aggregate_report", "family": "SLM2",
                               "sha256": file_hash(root / "report.json")}],
            })
            integrity = {"cells": [{
                "family": "SLM2", "project": "Apache", "level": 5, "status": "succeeded",
                "protocol": {"study": study, "selection": selection},
                "checks": [{"split": "test", "path": str(path), "sha256": file_hash(path)}],
            }]}
            slices = {"comparisons": [{**diagnostic, "family": "SLM2", "project": "Apache",
                                      "level": 5, "split": "test", "slice": "all"}]}
            predictions = pd.concat(normalized, ignore_index=True)
            with patch("reconcile_intervals.HF", root), patch("reconcile_intervals.REPORTS", root), \
                    patch("reconcile_intervals.git_bytes", return_value=blobs["classical"]):
                result = reconcile_cell(root, data, predictions, integrity, slices, "Apache", 5)
                self.assertEqual(result["status"], "succeeded")
                with self.assertRaisesRegex(ValueError, "population/order"):
                    reconcile_cell(root, data.assign(time_add_to_sprint=data.time_add_to_sprint.iloc[::-1].to_numpy()),
                                   predictions, integrity, slices, "Apache", 5)
                bad = predictions.copy()
                bad.loc[0, "instability_probability"] += .01
                with self.assertRaisesRegex(ValueError, "probabilities differ"):
                    reconcile_cell(root, data, bad, integrity, slices, "Apache", 5)
                path.write_bytes(blobs["model"] + b"\n")
                with self.assertRaisesRegex(ValueError, "bytes changed"):
                    reconcile_cell(root, data, predictions, integrity, slices, "Apache", 5)


if __name__ == "__main__":
    unittest.main()
