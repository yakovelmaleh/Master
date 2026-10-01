"""Verify historical input bytes and exact row/label assignment before training."""

import io
import shutil

from common import LEVELS, REPO, TASK, exclusive_lock, external_path, file_hash, read_json
from freeze_reference import git_bytes, label_hash
from model_comparison import load_frames, row_hash, split_frames


def verify_frames(frames, expected):
    for name, frame in zip(("train", "validation", "test"), frames):
        reference = expected["partitions"][name]
        if len(frame) != reference["rows"] or row_hash(frame) != reference["row_ids_sha256"]:
            raise ValueError(f"#357 row-order/split mismatch: {name}")
        rows = frame.to_dict("records")
        for level in LEVELS:
            if label_hash(rows, level) != reference["labels_sha256"][str(level)]:
                raise ValueError(f"#357 label mismatch: {name}/{level}")


def load_project(project, storage):
    reference = read_json(TASK / "reference_contract.json")["projects"][project]
    source = REPO / "Data" / project / "features_labels_table_os.csv"
    root = external_path(storage) / "data"
    snapshot = root / project / source.name
    if file_hash(source) != reference["input_sha256"]:
        raise ValueError(f"{project} input differs from #357; do not regenerate splits.")
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    with exclusive_lock(snapshot.with_suffix(".lock")):
        if not snapshot.exists():
            temporary = snapshot.with_suffix(".copying")
            with temporary.open("wb") as output, source.open("rb") as stream:
                shutil.copyfileobj(stream, output)
            if file_hash(temporary) != reference["input_sha256"]:
                raise ValueError(f"Input changed while snapshotting {project}.")
            temporary.rename(snapshot)
    if file_hash(snapshot) != reference["input_sha256"]:
        raise ValueError(f"Corrupt data snapshot for {project}.")
    frames = split_frames(load_frames(root, [project], LEVELS), "within-project", project)
    verify_frames(frames, reference)
    return frames


def baseline_predictions(project, level, test):
    import hashlib
    import pandas as pd
    import numpy as np

    reference = read_json(TASK / "reference_contract.json")["projects"][project]["baseline"][str(level)]
    content = git_bytes(reference["predictions_git_path"])
    if hashlib.sha256(content).hexdigest() != reference["predictions_sha256"]:
        raise ValueError("Archived baseline prediction hash mismatch.")
    frame = pd.read_csv(io.BytesIO(content))
    if frame.row_id.tolist() != test.row_id.tolist():
        raise ValueError("Archived baseline test order differs.")
    if not np.array_equal(frame.actual_label, test[f"is_change_text_num_words_{level}"]):
        raise ValueError("Archived baseline test labels differ.")
    return frame.instability_probability.to_numpy(), reference
