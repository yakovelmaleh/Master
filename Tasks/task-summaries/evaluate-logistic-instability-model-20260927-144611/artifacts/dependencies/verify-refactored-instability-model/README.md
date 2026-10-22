# Combined chronological model-family comparison

This task replaces the previous logistic-only verification. It runs **RF,
legacy XGboost, and NN**, each at unstable levels **5, 10, 15, 20**.
Logistic regression now has its own task:
`Tasks/evaluate-logistic-instability-model/`.

## What is compared

Each family is run twice on identical rows and the same pre-sprint features:

| Variant | Training | Validation/test |
| --- | --- | --- |
| baseline | Unweighted family rerun | Original unweighted distribution |
| refactored | Balanced training sample weights (RF/boosting); training-only oversampling (NN) | Original unweighted distribution |

**These are controlled family reruns, not a replay of the old NLP/topic/document
vector pipeline.** Published old scores from `Models/results_best_para/` are
exported separately as `historical_reference.csv`, explicitly marked not
directly comparable. They must never be mixed with matched rerun scores.

Historical `XGboost` is actually `sklearn.ensemble.GradientBoostingClassifier`
in `Utils/ml_algorithms_run_best_parameters.py`; we preserve that class and
record the exact estimator class. RF uses `RandomForestClassifier`, NN uses
`MLPClassifier`. An actual `XGBClassifier` experiment requires a separate task.

## Data and selection

`datasets.json` points to the six original `Data/<project>/features_labels_table_os.csv`
files. They are fingerprinted, not modified. Invalid sprint timestamps are
excluded by the existing loader. Non-binary labels, duplicate issue keys, and
different eligible rows between selected levels fail explicitly.

The pooled task trains on the first 60% of globally chronological rows,
validates on the next 20%, and tests on the last 20%. Both variants use exactly
the same partitions. `split_manifest.json` records counts, class counts, source
composition, row-ID hashes, and software versions. Saved row lists prove membership.
This is a **pooled temporal** experiment, not held-out-project generalization.

`comparison_config.json` defines the seed and a small validation search for each
family. Both variants use the same search space. Selection maximizes
**unweighted validation trapezoidal AUC-PRC**; average precision is also recorded
and is not substituted for AUC-PRC. The decision threshold maximizes validation
F1. Final models remain fitted on training only. There is no test-set selection
or weighting. One-class test PR/ROC metrics are null; one-class train/validation
fails. NN convergence warnings are printed and retained in candidate metadata.

## Run

From the repository root:

```bash
python3 -m pip install -r Tasks/verify-refactored-instability-model/requirements.txt
bash Tasks/run_cluster_task.sh verify-refactored-instability-model --dry-run
bash Tasks/run_cluster_task.sh verify-refactored-instability-model
```

Default: **one job** running levels 5, 10, 15, and 20 sequentially, evaluating all
three model families and both variants. The comparison runner loads the inputs,
splits the rows, and fits the feature transformer once for the job; model
training remains separate for each label level. Narrow explicitly:

```bash
bash Tasks/run_cluster_task.sh verify-refactored-instability-model \
  --label-threshold 5 --label-threshold 20 --models RF XGboost
```

All four model tasks using the shared launcher request SLURM email notifications
to `yakovelm@post.bgu.ac.il` with `--mail-type=ALL`, matching the Jira launcher. Notifications are
per grouped job, not per unstable level. This applies to new submissions only;
pulling updated code does not change already queued or running jobs.

`--project Apache` pools only Apache; use the per-dataset task to run all projects
independently. `--comparison-config PATH` supplies a different candidate grid.
`--validate-only` validates inputs/labels and fingerprints without fitting.
Local equivalent:

```bash
python3 Tasks/verify-refactored-instability-model/run_verification.py \
  --protocol pooled --output-root /tmp/master-comparison-run
```

## Other protocols

- `validate-refactored-model-per-dataset`: chronological split within each dataset.
- `compare-models-leave-one-project-out`: excluded project never enters fitting or validation.
- `evaluate-logistic-instability-model`: separate logistic experiment.

## Outputs

```text
cluster_runs/<run-id>/
  datasets.json                 # resolved snapshot
  comparison_config.json        # candidate snapshot
  job_plan.json                 # every expected project/level/model/variant
  submitted_jobs.tsv
  all/
    submit.sbatch
    logs/job-<SLURM_ID>.out
    results/
      verification_manifest.json
      input_layout/<project>/features_labels_table_os.csv  # symlink
      model/
        comparison_results.csv
        historical_reference.csv
        historical_sources.json
        split_manifest.json
        train_rows.csv
        validation_rows.csv
        test_rows.csv
        feature_transformer.json
        words_5/RF/baseline/
          model.joblib
          run_metadata.json
          metrics.json
          validation_predictions.csv
          test_predictions.csv
        words_5/RF/refactored/
        words_5/XGboost/...
        words_5/NN/...
        words_10/...
        words_15/...
        words_20/...
```

Model files are trusted local artifacts; do not load untrusted joblib files.
Run IDs cannot be reused. Partial submission errors and fitting errors remain
in manifests; successfully written earlier results are preserved.
The shared job log marks each level's start and completion. A training failure
fails the grouped job and stops subsequent levels; the summary retains available
metrics but marks the run incomplete. The time limit applies to the whole job,
not each level. Existing submitted jobs are not changed by this refactor.

`job_plan.json` stores a `levels` list per job; `submitted_jobs.tsv` has one row
per job and a comma-separated `levels` column. The summary utility also supports
older one-level-per-job runs.

## Summarize the complete batch

```bash
bash Tasks/create-task-summary-pr/create_task_summary_pr.sh \
  --task verify-refactored-instability-model --run-id <run-id>
```

All levels, models, logs, and shared code are included. `LEVELS.csv` reports
missing/failed entries; `RESULTS.csv` contains available test metrics.

## Tests

```bash
PYTHONPATH=Tasks/verify-refactored-instability-model:Tasks/jira-url-to-instability-model \
  python3 -m unittest discover -s Tasks/verify-refactored-instability-model/tests
```
