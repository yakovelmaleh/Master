"""Analysis configuration validation shared with the dependency-free launcher."""


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
