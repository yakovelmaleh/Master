import argparse
import copy
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import test_milestone1 as fixtures
from support import (
    FAMILIES, HF, LEVELS, PROJECTS, TASK, digest, emit, file_hash, label_column,
    np, pd, read_json, row_hash, save_table, sha_bytes, write_json,
)
from errors import misranking
from diagnostic_config import validate_milestone2
from milestone2_text import (
    assign_lengths, exact_duplicate_disagreement, fit_lengths, metric_slices,
    profiles_and_shift, reference_only, text_features,
)
from milestone2_embeddings import (
    adjusted_rand, assign_project, bank_indices, cluster_fit, fit_project,
    historical_source_fingerprint, inventory, load_partition, nearest,
)
from run_milestone2 import execute, verify_inputs

CONFIG = {**read_json(TASK / "configuration/milestone2.json"), "bootstrap_samples": 100}


def all_predictions(population):
    rows = []
    for (project, split), group in population[population.split.ne("train")].groupby(["project", "split"]):
        for k in LEVELS:
            y = group[label_column(k)].to_numpy()
            for family in FAMILIES:
                scores = .2 + .6 * (1 - y if family == "classical" else y)
                rows.append(pd.DataFrame({
                    "row_id": group.row_id, "project": project, "split": split, "level": k,
                    "family": family, "model": family + "-fixture", "actual_label": y,
                    "instability_probability": scores, "threshold": .5,
                    "opposite_class_misranking_fraction": misranking(y, scores),
                }))
    return pd.concat(rows, ignore_index=True)


def make_source(base, with_embeddings=False):
    source = base / "source"
    populations = []
    for project in PROJECTS:
        data = fixtures.frame(60).assign(project=project)
        data.row_id = project + ":" + data.issue_key
        data["split"] = np.repeat(["train", "validation", "test"], 20)
        data["original_description_sprint"] = ["word " * (i % 7) for i in range(len(data))]
        data["model_text"] = data[fixtures.TEXT_COLUMNS].agg(" ".join, axis=1)
        populations.append(data)
    population = pd.concat(populations, ignore_index=True)
    reference = {"projects": {}}
    for project, group in population.groupby("project"):
        reference["projects"][project] = {"partitions": {
            split: {"rows": len(part), "row_ids_sha256": row_hash(part.row_id),
                    "labels_sha256": {str(k): sha_bytes("\n".join(
                        f"{r}\t{int(y)}" for r, y in zip(part.row_id, part[label_column(k)])
                    ).encode()) for k in LEVELS}} for split, part in group.groupby("split")
        }}
    reference_dir = base / "reference"
    write_json(reference_dir / "reference_contract.json", reference)
    write_json(source / "run.json", {
        "run_id": source.name, "source_sha256": "original-source",
        "configuration": fixtures.CONFIG, "configuration_sha256": digest(fixtures.CONFIG),
        "reference_sha256": file_hash(reference_dir / "reference_contract.json"),
        "artifact_roots": [str(base / "cache")], "histories": None,
    })
    for stage in ("inventory", "profile", "errors"):
        emit(source, f"manifest/{stage}_status.json", stage, "succeeded")
    study = {
        "source_sha256": historical_source_fingerprint(),
        "models": {"modernbert": {"id": "test/frozen", "revision": "a" * 40, "pooling": "mean"}},
        "config": {"max_length": 512}, "versions": {"numpy": "fixture"},
    }
    cells = [{"project": p, "level": k, "family": f, "status": "succeeded",
              "protocol": {"study": study}} for p in PROJECTS for k in LEVELS for f in FAMILIES]
    emit(source, "manifest/integrity_checks.json", "T1", "succeeded", cells=cells)
    emit(source, "manifest/artifact_manifest.json", "T1", "succeeded", artifacts=[])
    emit(source, "error-analysis/error_slices.json", "T3", "succeeded", comparisons=[])
    predictions = all_predictions(population)
    for name, table in (("manifest/population.csv", population), ("manifest/predictions.csv", predictions),
                        ("error-analysis/row_diagnostics.csv", predictions)):
        save_table(source, name, table, "fixture")
    ci_dir = source / "error-analysis/human-review-01"
    write_json(ci_dir / "ci_reconciliation.json", {
        "run_id": source.name, "cells": [
            {"project": p, "level": k, "status": "succeeded",
             "configurations": {"diagnostic": fixtures.CONFIG}}
            for p, k in (("MariaDB", 15), ("IntelDAOS", 5))
        ],
    })
    write_json(ci_dir / "status.json", {
        "run_id": source.name, "status": "succeeded",
        "input_sha256": {"run.json": file_hash(source / "run.json")},
        "outputs_sha256": {"ci_reconciliation.json": file_hash(ci_dir / "ci_reconciliation.json")},
    })
    if with_embeddings:
        cache = base / "cache/embeddings"
        cache.mkdir(parents=True)
        for (project, split), group in population[population.split.ne("test")].groupby(["project", "split"]):
            key = digest({"model": study["models"]["modernbert"], "texts": group.model_text.tolist(),
                          "config": study["config"], "versions": study["versions"]})
            values = np.random.RandomState(9 if split == "train" else 10).normal(size=(len(group), 6)).astype("float32")
            np.save(cache / (key + ".npy"), values, allow_pickle=False)
    return source, reference_dir, population, predictions, {"cells": cells}


class TextDiagnosticsTests(unittest.TestCase):
    def test_training_bins_do_not_use_future_lengths_or_labels(self):
        data = fixtures.frame(60)
        data["split"] = np.repeat(["train", "validation", "test"], 20)
        data["original_description_sprint"] = ["x " * i for i in range(60)]
        features = text_features(data)
        definitions = fit_lengths(features, CONFIG)
        changed = data.copy()
        changed.loc[changed.split.ne("train"), "original_description_sprint"] = "x " * 10000
        for k in LEVELS:
            changed[label_column(k)] = 1 - changed[label_column(k)]
        self.assertEqual(definitions, fit_lengths(text_features(changed), CONFIG))
        assigned = assign_lengths(features, definitions)
        self.assertTrue(assigned.length_bin.ge(0).all())
        self.assertEqual(len(definitions["Apache"]["cutpoints"]), 3)

    def test_empty_duplicate_and_reference_flags_are_literal(self):
        data = fixtures.frame(6)
        data["split"] = ["train", "train", "validation", "test", "test", "test"]
        data["original_summary_sprint"] = ["Same", "Same", "Same", " SEE HTTPS://example.org ",
                                            "equal", "empty"]
        data["original_description_sprint"] = ["", "", "", "see https://example.org", " EQUAL ", ""]
        data["original_acceptance_criteria_sprint"] = ""
        features = text_features(data)
        self.assertTrue(features.empty_description.iloc[0])
        self.assertTrue(features.seen_in_train.iloc[:3].all())
        self.assertFalse(features.seen_in_train.iloc[4])
        self.assertTrue(features.summary_equals_description.iloc[4])
        self.assertFalse(features.summary_equals_description.iloc[0])
        self.assertTrue(features.reference_only_description.iloc[3])
        self.assertTrue(reference_only("See ABC-42 and https://example.org"))
        self.assertFalse(reference_only("Implement a retry for ABC-42"))
        self.assertFalse(reference_only(""))
        features.loc[0, label_column(5)] = 0
        features.loc[1, label_column(5)] = 1
        results = exact_duplicate_disagreement(features, CONFIG)
        train = next(r for r in results if r["split"] == "train" and r["level"] == 5)
        self.assertEqual(train["mean_training_duplicate_label_disagreement"], 1)
        self.assertFalse(train["adequate_support"])

    def test_supported_metrics_preserve_auc_prc_ap_and_no_repeat_of_all_slice(self):
        data = fixtures.frame(60)
        features = text_features(data)
        definitions = fit_lengths(features.assign(split="train"), CONFIG)
        features = assign_lengths(features, definitions)
        result = metric_slices(data, all_predictions(data), features, definitions, CONFIG)
        self.assertFalse(any(c["slice"] == "all" for c in result))
        supported = [c for c in result if c["adequate_support"]]
        self.assertTrue(supported)
        self.assertTrue(all(c["auc_prc_difference_model_minus_classical"] > 0 for c in supported))
        self.assertTrue(all("average_precision" in c["metrics"]["model"] for c in supported))
        self.assertTrue(all(c["uncertainty"]["interval_95"] is not None for c in supported))
        self.assertTrue(any(c["interpretation"] == "empty_slice" for c in result))
        data["split"] = np.repeat(["train", "validation", "test"], 20)
        traits = assign_lengths(text_features(data), definitions)
        profiles, shifts = profiles_and_shift(traits, definitions, CONFIG)
        self.assertTrue(all(p["prevalence_interval_95"] is None for p in profiles))
        self.assertTrue(all(s["rows"] == 20 for s in shifts))


class FrozenEmbeddingTests(unittest.TestCase):
    def test_neighbors_exclude_self_and_duplicate_sensitivity_uses_training_only(self):
        values = np.array([[1., 0.], [1., 0.], [0., 1.]])
        config = {**CONFIG, "neighbors": 1}
        ids = np.array(["a", "b", "c"])
        hashes = np.array(["same", "same", "other"])
        primary, _ = nearest(values, values, ids, ids, hashes, hashes, config, False)
        self.assertEqual(primary[0, 0], 1)
        dedup, _ = nearest(values, values, ids, ids, hashes, hashes, config, True)
        self.assertEqual(dedup[0, 0], 2)
        self.assertFalse(np.any(dedup[:, 0] == np.arange(3)))
        self.assertEqual(bank_indices(ids, 2, 7, "bank").tolist(),
                         bank_indices(ids, 2, 7, "bank").tolist())

    def test_cluster_fit_repeatability_degeneracy_and_partition_invariant_stability(self):
        x = np.random.RandomState(4).normal(size=(40, 4))
        x /= np.linalg.norm(x, axis=1, keepdims=True)
        a, info = cluster_fit(x, CONFIG, 7)
        b, _ = cluster_fit(x, CONFIG, 7)
        np.testing.assert_array_equal(a, b)
        self.assertLessEqual(info["iterations"], CONFIG["cluster_iterations"])
        self.assertEqual(adjusted_rand([0, 0, 1, 1], [1, 1, 0, 0]), 1)
        self.assertAlmostEqual(adjusted_rand([0, 0, 1, 1], [0, 1, 0, 1]), -.5)
        with self.assertRaisesRegex(ValueError, "distinct"):
            cluster_fit(np.ones((8, 2)), CONFIG, 7)

    def test_provenance_row_order_missing_test_and_mutated_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            source, _, population, _, integrity = make_source(base, with_embeddings=True)
            roots = [base / "cache"]
            catalog = inventory(population, integrity, roots, CONFIG)
            self.assertEqual(set(catalog["selected"]), set(PROJECTS))
            rep = catalog["selected"]["Apache"]
            self.assertNotIn("test", rep["partitions"])
            features = text_features(population)
            group = population[population.project.eq("Apache")]
            train = group[group.split.eq("train")]
            fitted = fit_project(train, features, rep, CONFIG)
            assignments = assign_project(group, features, rep, fitted, CONFIG)
            self.assertEqual(set(assignments.split), {"train", "validation"})
            self.assertFalse(assignments.row_id.isin(group[group.split.eq("test")].row_id).any())
            changed_labels = train.copy()
            for k in LEVELS:
                changed_labels[label_column(k)] = 1 - changed_labels[label_column(k)]
            same = fit_project(changed_labels, features, rep, CONFIG)
            self.assertEqual(fitted["contract"], same["contract"])
            np.testing.assert_array_equal(fitted["centers"], same["centers"])
            shuffled = population.iloc[::-1].reset_index(drop=True)
            blocked = inventory(shuffled, integrity, roots, CONFIG)
            self.assertFalse(blocked["selected"])
            path = Path(rep["partitions"]["train"]["path"])
            with path.open("ab") as f: f.write(b"changed")
            with self.assertRaisesRegex(ValueError, "changed"):
                load_partition(rep["partitions"]["train"])
            wrong_producer = copy.deepcopy(integrity)
            for cell in wrong_producer["cells"]:
                cell["protocol"]["study"]["source_sha256"] = "unverified"
            self.assertFalse(inventory(population, wrong_producer, roots, CONFIG)["selected"])


class MilestoneTwoIntegrationTests(unittest.TestCase):
    def test_new_run_executes_independent_text_when_embedding_test_unavailable(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            source, reference_dir, *_ = make_source(base, with_embeddings=True)
            original = {str(p): p.read_bytes() for p in source.rglob("*") if p.is_file()}
            config_path = base / "config.json"
            write_json(config_path, CONFIG)
            args = argparse.Namespace(config=config_path, source_run=source, output_root=base / "outputs",
                                      run_id="new-m2", batch_id="human-review-01")
            with patch("run_milestone2.HF", reference_dir):
                self.assertEqual(execute(args), 2)
                with self.assertRaisesRegex(ValueError, "already exists"):
                    execute(args)
            root = args.output_root / args.run_id
            summary = read_json(root / "summary.json")
            self.assertEqual(summary["t5_text_status"], "succeeded")
            self.assertEqual(summary["schema"], "instability-diagnostics-m2-v1")
            self.assertTrue(all(b["split"] == "test" for b in summary["embedding_blocks"]))
            self.assertTrue(read_json(root / "manifest/analysis_contract.json")["length_bins"])
            self.assertTrue((root / "semantic-groups/assignments_and_neighbors.csv").is_file())
            self.assertTrue((root / "complexity/length_evidence.json").is_file())
            for name, content in original.items():
                self.assertEqual(Path(name).read_bytes(), content)
            args.run_id = "new-m2-no-embeddings"
            with patch("run_milestone2.HF", reference_dir), patch(
                "run_milestone2.inventory", return_value={"candidates": [], "selected": {}}
            ):
                self.assertEqual(execute(args), 2)
            empty_summary = read_json(args.output_root / args.run_id / "summary.json")
            self.assertEqual(empty_summary["t5_text_status"], "succeeded")
            self.assertEqual(empty_summary["embedding_comparisons"], 0)

    def test_input_ci_hashes_support_gates_and_label_contract_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            source, reference_dir, *_ = make_source(Path(d))
            with patch("run_milestone2.HF", reference_dir):
                verify_inputs(source, "human-review-01", CONFIG)
                with self.assertRaisesRegex(ValueError, "preserve"):
                    verify_inputs(source, "human-review-01", {**CONFIG, "minimum_slice_positives": 1})
                path = source / "error-analysis/human-review-01/ci_reconciliation.json"
                path.write_bytes(path.read_bytes() + b"\n")
                with self.assertRaisesRegex(ValueError, "hash differs"):
                    verify_inputs(source, "human-review-01", CONFIG)

    def test_stdlib_launcher_and_bounded_config(self):
        command = [sys.executable, "-S", str(TASK / "cluster/submit_jobs.py"),
                   "--stage", "milestone2", "--source-run", "/tmp/source-m1",
                   "--run-id", "new-m2", "--partition", "main", "--dry-run"]
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        self.assertIn("run_milestone2.py", result.stdout)
        self.assertNotIn("run_diagnostics.py", result.stdout)
        self.assertIn("--array=0-0%1", result.stdout)
        self.assertIn("--mail-type=ALL", result.stdout)
        subprocess.run(["bash", "-n"], input=result.stdout, text=True, check=True)
        same = subprocess.run(command + ["--output-root", "/tmp", "--run-id", "source-m1"],
                              capture_output=True, text=True)
        self.assertNotEqual(same.returncode, 0)
        for field, value in (("neighbor_bank_rows", 5000), ("clusters", 100),
                             ("length_quantiles", [.9, .1]), ("bootstrap_samples", 2)):
            with self.assertRaises(ValueError):
                validate_milestone2({**CONFIG, field: value})
        with tempfile.TemporaryDirectory() as d:
            args = fixtures.LauncherTests().args()
            args.stage, args.batch_id = "milestone2", "human-review-01"
            args.source_run, args.config = Path(d) / "source", TASK / "configuration/milestone2.json"
            args.output_root = Path(d) / "output"
            args.artifact_root = args.histories = args.tokenizer_cache = args.reviews = None
            with patch.object(fixtures.launcher, "TASK", Path(d) / "task"), patch.object(
                fixtures.launcher.subprocess, "check_output", side_effect=["", "12345;site\n"]
            ), patch.object(fixtures.launcher, "exclusive_lock"):
                fixtures.launcher.submit(args)
            manifest = read_json(next((Path(d) / "task").glob("cluster_runs/*/job_manifest.json")))
            self.assertEqual(manifest["stage_job_mapping"][0]["stages"],
                             ["T5-characteristics-and-shift", "T5-neighbors", "T4-frozen-groups"])


if __name__ == "__main__":
    unittest.main()
