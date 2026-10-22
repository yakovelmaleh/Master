import json
from pathlib import Path

import numpy as np
import pandas as pd

from .data import prepare_feature_frame
from .features import FeatureTransformer
from .model import sigmoid


def load_json(path):
    with Path(path).open(encoding="utf-8") as input_file:
        return json.load(input_file)


def predict_file(model_dir, input_path, output_path):
    model_dir = Path(model_dir)
    metadata = load_json(model_dir / "run_metadata.json")
    transformer = FeatureTransformer.from_dict(
        load_json(model_dir / "feature_transformer.json")
    )
    artifact = np.load(model_dir / "model.npz")
    coefficients = artifact["coefficients"]
    intercept = float(artifact["intercept"][0])

    raw = pd.read_csv(input_path, low_memory=False)
    frame = prepare_feature_frame(raw)
    invalid_time = frame["time_add_to_sprint"].isna()
    if invalid_time.any():
        raise ValueError(
            f"{int(invalid_time.sum())} rows have invalid time_add_to_sprint."
        )
    features = transformer.transform(frame)
    probabilities = sigmoid(
        np.einsum("ij,j->i", features, coefficients, optimize=False)
        + intercept
    )
    threshold = float(metadata["selected_threshold"])
    output = frame[
        ["issue_key", "project_key", "issue_type", "created", "time_add_to_sprint"]
    ].copy()
    output["instability_probability"] = probabilities
    output["predicted_label"] = (probabilities >= threshold).astype(int)
    output.to_csv(output_path, index=False)
    return len(output), threshold
