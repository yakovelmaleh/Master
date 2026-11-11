"""Analysis configuration validation shared with the dependency-free launcher."""

REVIEW_POLICY = {
    "schema": "instability-first-human-review-v1",
    "seed": 20261111,
    "per_category": 5,
    "split": "test",
    "families": ["SLM1", "SLM2"],
    "good_max_inversion": 0.25,
    "poor_min_inversion": 0.5,
    "categories": ["classical_good_slm_poor", "slm_good_classical_poor",
                   "both_poor", "both_good"],
    "ci_targets": [["MariaDB", 15], ["IntelDAOS", 5]],
}


def validate_config(config):
    for key in ("seed", "boundary_radius", "review_per_stratum", "minimum_slice_rows",
                "minimum_slice_positives", "minimum_slice_negatives", "bootstrap_samples", "time_block_rows"):
        if type(config[key]) is not int or config[key] < (0 if key in ("seed", "boundary_radius") else 1):
            raise ValueError(f"Invalid analysis setting: {key}")
    if not 0 <= config["independent_review_fraction"] <= 1:
        raise ValueError("Invalid independent review fraction.")
    if not 0 < config["metric_tolerance"] <= 1e-8:
        raise ValueError("Metric tolerance must be positive and tight.")
    if set(config["reports"]) != {"SLM1", "SLM2", "Jev"}:
        raise ValueError("All three original reports are required.")


def validate_milestone2(config):
    if config["schema"] != "instability-diagnostics-m2-v1":
        raise ValueError("Unknown milestone-two configuration schema.")
    for key in ("seed", "minimum_slice_rows", "minimum_slice_positives",
                "minimum_slice_negatives", "bootstrap_samples", "time_block_rows",
                "neighbor_bank_rows", "neighbors", "distance_batch_rows", "clusters",
                "cluster_fit_rows", "cluster_iterations", "stability_seed_offset",
                "maximum_embedding_dimensions", "maximum_project_rows"):
        if type(config[key]) is not int or config[key] < (0 if key == "seed" else 1):
            raise ValueError(f"Invalid milestone-two setting: {key}")
    if config["bootstrap_samples"] < 100 or not 0 < config["metric_tolerance"] <= 1e-8:
        raise ValueError("Uncertainty requires >=100 draws and tight metric tolerance.")
    quantiles = config["length_quantiles"]
    if (not quantiles or len(quantiles) > 4 or any(not 0 < q < 1 for q in quantiles)
            or sorted(set(quantiles)) != quantiles):
        raise ValueError("Length quantiles must be increasing, unique and bounded.")
    if config["embedding_preference"] != ["modernbert", "qwen_embedding"]:
        raise ValueError("Only the predeclared label-independent frozen encoders are supported.")
    if not 0 < config["similarity_quantile"] < 1 or not 0 < config["outlier_quantile"] < 1:
        raise ValueError("Invalid training similarity quantile.")
    if not config["neighbors"] < config["neighbor_bank_rows"] <= 4096:
        raise ValueError("Neighbor bank must exceed k and is capped at 4096 training rows.")
    if (config["clusters"] > 16 or config["cluster_fit_rows"] > 4096
            or config["cluster_fit_rows"] < config["clusters"]
            or config["cluster_iterations"] > 100 or config["distance_batch_rows"] > 256
            or config["maximum_embedding_dimensions"] > 8192
            or config["maximum_project_rows"] > 30000):
        raise ValueError("Requested embedding analysis exceeds bounded CPU limits.")
