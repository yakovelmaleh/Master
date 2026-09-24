from pathlib import Path

import pandas as pd


TEXT_COLUMNS = [
    "original_summary_sprint",
    "original_description_sprint",
    "original_acceptance_criteria_sprint",
]
CATEGORICAL_COLUMNS = ["issue_type", "project_key", "priority"]
NUMERIC_COLUMNS = [
    "original_story_points_sprint",
    "num_comments_before_sprint",
    "num_changes_text_before_sprint",
    "num_changes_story_point_before_sprint",
    "time_until_add_to_sprint",
    "num_issues_cretor_prev",
]
IDENTIFIER_COLUMNS = ["issue_key", "created", "time_add_to_sprint"]
PROJECTS = ["Apache", "Hyperledger", "IntelDAOS", "Jira", "MariaDB", "Qt"]


def label_column(threshold):
    if threshold not in (5, 10, 15, 20):
        raise ValueError("Label threshold must be one of: 5, 10, 15, 20.")
    return f"is_change_text_num_words_{threshold}"


def project_files(data_root, project):
    data_root = Path(data_root)
    selected = PROJECTS if project.casefold() == "all" else [project]
    paths = [
        data_root / project_name / "features_labels_table_os.csv"
        for project_name in selected
    ]
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            "Missing input dataset(s):\n" + "\n".join(missing)
        )
    return paths


def load_dataset(data_root, project, threshold):
    target = label_column(threshold)
    required = (
        IDENTIFIER_COLUMNS
        + TEXT_COLUMNS
        + CATEGORICAL_COLUMNS
        + NUMERIC_COLUMNS
        + [target]
    )
    frames = []
    for path in project_files(data_root, project):
        frame = pd.read_csv(path, low_memory=False)
        missing = [column for column in required if column not in frame.columns]
        if missing:
            raise ValueError(f"{path} is missing columns: {missing}")
        frames.append(frame[required].copy())

    data = pd.concat(frames, ignore_index=True)
    target_values = pd.to_numeric(data[target], errors="coerce")
    data = prepare_feature_frame(data)
    data[target] = target_values
    data = data.dropna(subset=["time_add_to_sprint", target]).copy()
    data[target] = data[target].astype(int)
    invalid_labels = sorted(set(data[target].unique()) - {0, 1})
    if invalid_labels:
        raise ValueError(f"Target contains non-binary values: {invalid_labels}")
    return data.sort_values("time_add_to_sprint").reset_index(drop=True)


def prepare_feature_frame(data):
    required = (
        IDENTIFIER_COLUMNS
        + TEXT_COLUMNS
        + CATEGORICAL_COLUMNS
        + NUMERIC_COLUMNS
    )
    missing = [column for column in required if column not in data.columns]
    if missing:
        raise ValueError(f"Input data is missing columns: {missing}")
    data = data[required].copy()
    data["time_add_to_sprint"] = pd.to_datetime(
        data["time_add_to_sprint"], format="mixed", errors="coerce"
    )
    data["created"] = pd.to_datetime(
        data["created"], format="mixed", errors="coerce"
    )
    for column in TEXT_COLUMNS:
        data[column] = data[column].fillna("").astype(str)
    data["model_text"] = data[TEXT_COLUMNS].agg(" ".join, axis=1)
    for column in CATEGORICAL_COLUMNS:
        data[column] = data[column].fillna("unknown").astype(str)
    for column in NUMERIC_COLUMNS:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    return data


def chronological_split(data, train_fraction, validation_fraction):
    row_count = len(data)
    if row_count < 30:
        raise ValueError(
            f"At least 30 rows are required; received {row_count}."
        )
    train_end = int(row_count * train_fraction)
    validation_end = train_end + int(row_count * validation_fraction)
    train = data.iloc[:train_end].copy()
    validation = data.iloc[train_end:validation_end].copy()
    test = data.iloc[validation_end:].copy()
    if min(len(train), len(validation), len(test)) == 0:
        raise ValueError("The configured split produced an empty partition.")
    return train, validation, test
