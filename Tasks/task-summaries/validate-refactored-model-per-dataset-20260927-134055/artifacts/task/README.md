# Within-project model-family comparison

Runs RF, legacy XGboost (`GradientBoostingClassifier`), and NN separately within
each of the six datasets at **5, 10, 15, 20**. Default: **six jobs**, one per
dataset. Each job runs all selected levels sequentially, with three model
families and baseline/refactored variants.

Uses the shared runner and training/evaluation policy documented in
[`verify-refactored-instability-model`](../verify-refactored-instability-model/README.md).
This is no longer the logistic-only task used in PR #349. Logistic has a
[separate task](../evaluate-logistic-instability-model/README.md).

Each dataset has its own chronological 60/20/20 split; both variants have the
same feature matrix, class labels and held-out rows. Baseline is an unweighted
family rerun, **not the old rich-feature pipeline**. Published old per-project
metrics are separately labeled historical references.

```bash
python3 -m pip install -r Tasks/validate-refactored-model-per-dataset/requirements.txt
bash Tasks/run_cluster_task.sh validate-refactored-model-per-dataset --dry-run
bash Tasks/run_cluster_task.sh validate-refactored-model-per-dataset --only Qt
```

`--only` and `--label-threshold` can each be repeated. `--only Qt` creates
exactly one Qt job running all four levels by default, never six-project submissions.
`--label-threshold 5` narrows explicitly to one level.

Outputs: `cluster_runs/<run-id>/<dataset>/results/model/words_<level>/`.
Each dataset has one shared `logs/job-<SLURM_ID>.out` and `submit.sbatch`
under `cluster_runs/<run-id>/<dataset>/`. The run root stores
`job_plan.json`, configuration snapshots, and `submitted_jobs.tsv`.

```bash
bash Tasks/create-task-summary-pr/create_task_summary_pr.sh \
  --task validate-refactored-model-per-dataset --run-id <run-id>
```

This collects the whole batch, with completeness and metric tables for every
planned level/model/variant, including missing outputs.
