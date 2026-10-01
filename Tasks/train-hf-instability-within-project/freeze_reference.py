"""Generate a content-free contract from the immutable #357 Git artifacts."""

import csv
import hashlib
import io
import subprocess

from common import LEVELS, PROJECTS, REPO, TASK, write_json


REFERENCE = "028b4e40f81ce29f00ae561f795a6df8a52adb7b"
BUNDLE = "Tasks/task-summaries/validate-refactored-model-per-dataset-20260927-134055/artifacts/cluster-run"


def git_bytes(path):
    return subprocess.check_output(["git", "-C", str(REPO), "show", f"{REFERENCE}:{path}"])


def label_hash(rows, level):
    column = f"is_change_text_num_words_{level}"
    text = "\n".join(f"{row['row_id']}\t{int(float(row[column]))}" for row in rows)
    return hashlib.sha256(text.encode()).hexdigest()


def build():
    import json

    contract = {"source_commit": REFERENCE, "projects": {}}
    for project in PROJECTS:
        root = f"{BUNDLE}/{project.lower()}/results"
        manifest = json.loads(git_bytes(f"{root}/verification_manifest.json"))
        split = json.loads(git_bytes(f"{root}/model/split_manifest.json"))
        item = {"input_sha256": manifest["inputs"][project]["sha256"],
                "partitions": split["partitions"], "baseline": {}}
        for name, values in item["partitions"].items():
            rows = list(csv.DictReader(io.StringIO(git_bytes(f"{root}/model/{name}_rows.csv").decode())))
            values["labels_sha256"] = {str(k): label_hash(rows, k) for k in LEVELS}
        for level in LEVELS:
            candidates = []
            for model in ("RF", "XGboost", "NN"):
                for variant in ("baseline", "refactored"):
                    path = f"{root}/model/words_{level}/{model}/{variant}"
                    metrics = json.loads(git_bytes(f"{path}/metrics.json"))
                    candidates.append((metrics["validation"]["auc_prc"], model, variant, path, metrics))
            _, model, variant, path, metrics = max(candidates, key=lambda value: (value[0], value[1], value[2]))
            predictions = f"{path}/test_predictions.csv"
            item["baseline"][str(level)] = {
                "model": model, "variant": variant, "selection": "validation_auc_prc",
                "metrics": metrics, "predictions_git_path": predictions,
                "predictions_sha256": hashlib.sha256(git_bytes(predictions)).hexdigest(),
            }
        contract["projects"][project] = item
    return contract


if __name__ == "__main__":
    write_json(TASK / "reference_contract.json", build())
