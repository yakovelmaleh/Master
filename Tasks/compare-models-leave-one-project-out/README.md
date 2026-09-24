# Leave-one-project-out model comparison

**Separate from the combined chronological experiment.** For each excluded
dataset, train on the other five datasets and test on all eligible rows in the
excluded dataset. Split the training datasets globally by time: first 80%
fitting, last 20% validation. The excluded dataset never enters preprocessing
fitting, model selection or threshold selection.

This tests transfer across projects, not prediction into a strictly later time
window: training dates may overlap held-out-project dates. Project-specific
categorical values not seen in training receive the transformer's unknown
encoding.

Default: six held-out datasets x four unstable levels = 24 jobs. Each runs
RF/RF, legacy GradientBoosting/GradientBoosting, and NN/NN baseline/refactored
pairs. See the [shared methodology](../verify-refactored-instability-model/README.md)
for balancing, unweighted AUC-PRC, candidates, and the distinction between
controlled reruns and published historical references.

```bash
python3 -m pip install -r Tasks/compare-models-leave-one-project-out/requirements.txt
bash Tasks/run_cluster_task.sh compare-models-leave-one-project-out --dry-run
bash Tasks/run_cluster_task.sh compare-models-leave-one-project-out --only Qt
```

`--only Qt` holds out Qt; it does not train on Qt. All six source datasets must
be configured. Repeat `--label-threshold` to narrow levels explicitly.

Outputs and logs stay in this task:
`cluster_runs/<run-id>/<held-out-project>/words_<level>/{results,logs,submit.sbatch}`.
The job plan and split manifests identify every model, level and held-out row.

```bash
bash Tasks/create-task-summary-pr/create_task_summary_pr.sh \
  --task compare-models-leave-one-project-out --run-id <run-id>
```
