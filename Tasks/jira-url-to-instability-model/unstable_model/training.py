from datetime import datetime, timezone
from pathlib import Path

from .artifacts import (
    save_model,
    write_feature_coefficients,
    write_html_report,
    write_json,
    write_predictions,
)
from .data import chronological_split, label_column, load_dataset
from .evaluation import calculate_metrics, select_threshold
from .features import FeatureTransformer
from .model import StableLogisticRegression


def partition_summary(frame, target):
    return {
        "row_count": int(len(frame)),
        "positive_count": int(frame[target].sum()),
        "positive_rate": float(frame[target].mean()),
        "first_sprint_entry": frame["time_add_to_sprint"].min().isoformat(),
        "last_sprint_entry": frame["time_add_to_sprint"].max().isoformat(),
    }


def train_model(
    data_root,
    output_root,
    project,
    threshold,
    config,
):
    target = label_column(threshold)
    data = load_dataset(data_root, project, threshold)
    train, validation, test = chronological_split(
        data,
        config.train_fraction,
        config.validation_fraction,
    )
    for name, partition in (("training", train), ("validation", validation)):
        if partition[target].nunique() != 2:
            raise ValueError(
                f"The {name} partition must contain both stable and unstable "
                "issues. Collect more data or revise the split explicitly; "
                "do not use a single-class partition to select a model."
            )
    transformer = FeatureTransformer()
    train_features = transformer.fit_transform(train)
    validation_features = transformer.transform(validation)
    test_features = transformer.transform(test)
    model = StableLogisticRegression(
        learning_rate=config.learning_rate,
        maximum_iterations=config.maximum_iterations,
        l2_regularization=config.l2_regularization,
        early_stopping_patience=config.early_stopping_patience,
    )
    model.fit(
        train_features,
        train[target].to_numpy(),
        validation_features,
        validation[target].to_numpy(),
    )

    validation_probability = model.predict_proba(validation_features)
    selected_threshold = select_threshold(
        validation[target], validation_probability
    )
    train_probability = model.predict_proba(train_features)
    test_probability = model.predict_proba(test_features)

    metrics = {
        "train": {
            **partition_summary(train, target),
            **calculate_metrics(
                train[target],
                train_probability,
                selected_threshold,
            ),
        },
        "validation": {
            **partition_summary(validation, target),
            **calculate_metrics(
                validation[target],
                validation_probability,
                selected_threshold,
            ),
        },
        "test": {
            **partition_summary(test, target),
            **calculate_metrics(
                test[target],
                test_probability,
                selected_threshold,
            ),
        },
    }

    run_name = f"{project.casefold()}_words_{threshold}"
    run_dir = Path(output_root) / run_name
    run_dir.mkdir(parents=True, exist_ok=True)
    metadata = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "project": project,
        "label_column": target,
        "data_root": str(Path(data_root).resolve()),
        "model": "dependency_light_logistic_regression",
        "split_strategy": "chronological_60_20_20",
        "threshold_strategy": "maximum_validation_f1",
        "selected_threshold": selected_threshold,
        "feature_policy": "pre_sprint_only",
        "training_iterations": model.iterations,
        "best_validation_log_loss": model.best_validation_loss,
    }

    save_model(run_dir / "model.npz", model)
    write_json(run_dir / "feature_transformer.json", transformer.to_dict())
    write_json(run_dir / "run_metadata.json", metadata)
    write_json(run_dir / "metrics.json", metrics)
    write_predictions(
        run_dir / "validation_predictions.csv",
        validation,
        validation[target],
        validation_probability,
        selected_threshold,
    )
    write_predictions(
        run_dir / "test_predictions.csv",
        test,
        test[target],
        test_probability,
        selected_threshold,
    )
    write_feature_coefficients(
        run_dir / "feature_coefficients.csv",
        transformer.feature_names,
        model.coefficients,
    )
    write_html_report(run_dir / "report.html", metadata, metrics)
    return run_dir, metrics
