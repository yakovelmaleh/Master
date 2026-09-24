# 5. Model training, outputs, and reruns

The generated dataset is passed to the self-contained code under
`unstable_model/`.

## Chronological split

Rows are sorted by `time_add_to_sprint` and split into:

- 60% training.
- 20% validation.
- 20% final test.

This avoids random future-to-past leakage.

## Feature fitting

The feature transformer is fitted only on the training partition:

1. Missing numeric values use training medians.
2. Numeric values are standardized with training means and scales.
3. Extreme standardized values are clipped.
4. Categorical values are one-hot encoded from training categories.
5. Unknown categories in newer data are safely ignored.

The fitted transformer is saved for later prediction.

## Model

The model is a dependency-light logistic regression implemented with NumPy.
It uses:

- Balanced class weights.
- L2 regularization.
- Decaying learning rate.
- Gradient clipping.
- Validation-loss early stopping.
- Finite-value checks.

## Decision threshold

The model produces an instability probability.

The classification threshold is selected on the validation partition by
maximum F1. The final test partition is not used for fitting or threshold
selection. Training stops with an explicit error if the training or validation
partition contains only one class. Dataset diagnostics are still saved; the
runner does not silently substitute a `0.50` threshold for an unusable
validation set. A single-class test partition has undefined PR/ROC metrics.

## Model output

Artifacts are written to:

```text
model/<repository-or-project>_words_<threshold>/
```

The folder contains:

- `model.npz` — coefficients and intercept.
- `feature_transformer.json` — fitted preprocessing state.
- `run_metadata.json` — model, split, label, and threshold configuration.
- `metrics.json` — train, validation, and test metrics.
- `validation_predictions.csv`
- `test_predictions.csv`
- `feature_coefficients.csv`
- `report.html`

## Rerunning

Run with `--refresh` to download current Jira data again:

```bash
python3 run_pipeline.py \
  --jira-url https://issues.apache.org/jira \
  --refresh
```

Run without `--refresh` to reuse the raw JSONL with the same selection settings
and repeat only preprocessing and training:

```bash
python3 run_pipeline.py \
  --jira-url https://issues.apache.org/jira
```

Use another label:

```bash
python3 run_pipeline.py \
  --jira-url https://issues.apache.org/jira \
  --label-threshold 10
```

Changing the URL, project, query, or issue limit requires `--refresh` or a new
run folder. Changing only the label threshold can reuse the same raw issues.

## Cluster execution

Install the small dependency set:

```bash
python3 -m pip install -r requirements.txt
```

Then use the task's SLURM launcher. From the repository root:

```bash
./Tasks/run_cluster_task.sh --pull jira-url-to-instability-model --refresh
```

This optionally updates the checkout, then submits one independent job per
repository from the existing cluster source JSON. Each submission and Jira
source has separate results, generated sbatch files, and `.out` logs.

To use the current checkout without pulling:

```bash
./Tasks/run_cluster_task.sh jira-url-to-instability-model --refresh
```

See `cluster/README.md` for the timestamped output layout, job manifest,
bounded test runs, source overrides, and sequential local execution.

## Offline validation

The test suite does not contact Jira:

```bash
PYTHONPATH=. python3 -m unittest discover -s tests -v
```

It covers Jira text conversion, query construction, sprint reconstruction,
comment filtering, labels, creator history, chronological splitting, numeric
stability, training, artifact saving, and prediction loading.
