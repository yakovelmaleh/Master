# Separate logistic regression experiment

Preserves the dependency-light weighted logistic model previously used by the
verification tasks. It is **not** an RF, legacy boosting, or NN refactor and
does not appear as a matched replacement for any of those models.

Runs all unstable levels **5, 10, 15, 20** sequentially in **one job** by default. Uses the
original pre-sprint feature transformer and global chronological 60/20/20 split.
Training is class-weighted; validation and test evaluation are unweighted.
Checkpoint selection uses validation log loss, threshold selection validation
F1. AUC-PRC and average precision are both recorded.

```bash
python3 -m pip install -r Tasks/evaluate-logistic-instability-model/requirements.txt
bash Tasks/run_cluster_task.sh evaluate-logistic-instability-model --dry-run
bash Tasks/run_cluster_task.sh evaluate-logistic-instability-model
bash Tasks/run_cluster_task.sh evaluate-logistic-instability-model --project Qt
```

`--project Qt` runs the same separate logistic experiment on Qt only. Repeat
`--label-threshold` to narrow levels. Shared runner:
`Tasks/verify-refactored-instability-model/run_verification.py --experiment logistic`.

Outputs are under this task's `cluster_runs/<run-id>/<project>/`,
with `results/verification_manifest.json`, per-level artifacts under
`results/model/words_<level>/`, and one shared `logs/job-<SLURM_ID>.out`.

```bash
bash Tasks/create-task-summary-pr/create_task_summary_pr.sh \
  --task evaluate-logistic-instability-model --run-id <run-id>
```
