#!/usr/bin/env python3
"""Run a saved classifier locally using only verified cached base weights."""

import argparse
from pathlib import Path

import common
import pandas as pd

from run_experiment import predict_checkpoint
from unstable_model.data import prepare_feature_frame


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--cache", required=True)
    parser.add_argument("--input-csv", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    frame = prepare_feature_frame(pd.read_csv(args.input_csv, low_memory=False))
    probabilities = predict_checkpoint(args.checkpoint, args.cache, frame)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"issue_key": frame.issue_key, "instability_probability": probabilities}).to_csv(
        args.output, index=False
    )
