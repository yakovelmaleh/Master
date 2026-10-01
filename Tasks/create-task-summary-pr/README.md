# Create a task summary PR

This cluster utility creates one GitHub pull request containing a complete,
self-contained review bundle for a task.

The generated branch targets `main`. Files are copied under
`Tasks/task-summaries/`, so merging the PR preserves the summary without
overwriting the task's original code or runtime directories.

## Basic command

Run from `/home/yakovelm`:

```bash
./Master/Tasks/create-task-summary-pr/create_task_summary_pr.sh \
  --task jira-url-to-instability-model
```

The script includes:

- All task-definition files under `Tasks/<task>/`.
- Tracked task files, including tracked sample outputs.
- The run referenced by `cluster_runs/latest_run.txt`, when present.
- A generated README with source metadata, file count, and bundle size.
- `FILES.txt`, containing the exact committed file inventory.

Runtime caches, bytecode, untracked `runs/`, and unrelated historical
`cluster_runs/` are excluded automatically.

## Select a cluster run

```bash
./Master/Tasks/create-task-summary-pr/create_task_summary_pr.sh \
  --task jira-url-to-instability-model \
  --run-id 20260917-204018
```

Model-comparison batches now contain all four unstable levels by default.
New batches group the levels into one job per project, with a shared log and
separate `results/model/words_<level>/` artifacts. Summaries expand the job's
`levels` list to check every model/level/variant. Older single-level jobs remain
supported, including mixed collections of old and new runs.
The entire run tree is copied, including every model, level, `.out` log,
prediction file, metrics file and manifest. Shared runner/model code is also
included automatically for the model tasks.

For older batches where levels were run separately, repeat `--run-id`:

```bash
bash Tasks/create-task-summary-pr/create_task_summary_pr.sh \
  --task validate-refactored-model-per-dataset \
  --run-id level-5-run --run-id level-10-run \
  --run-id level-15-run --run-id level-20-run
```

Multiple runs are preserved under `artifacts/cluster-runs/<id>/`; no level
overwrites another. A single run retains `artifacts/cluster-run/`.

Every summary includes:

- `LEVELS.csv`: expected project/level/model/variant entries and missing files.
- `RESULTS.csv`: available unweighted test AUC-PRC, average precision, accuracy,
  ROC AUC and supporting metrics.
- `LEVEL_SUMMARY.md`: missing standard levels and incomplete/unverified entries.

Partial and failed runs can still be summarized; they are visibly marked
incomplete. Older runs without a job plan have **unknown** completeness, not
assumed success. The summary never fabricates missing level results or replaces
AUC-PRC with average precision.

### Hugging Face runtime tasks

HF tasks are an exception to full-tree copying: their bundles contain source and
explicitly allowlisted operational metadata only. Pretrained weights, adapters,
checkpoints, embedding caches and symlinked model directories are excluded
regardless of size. `HF_OMITTED_FILES.csv` records exclusions. HF `--include`
accepts allowlisted directories, not individual files.

Run the training task's `report` stage first, then select that submission ID.
`hf_report.json` must identify final-test results and contain all 24 cells.
Coverage is verified from checkpoint/prediction references, not a nonexistent
`model.joblib`; validation sweeps are not reported as completed test experiments.
The scientific target flags remain in `hf_report.json`, independently of artifact
completeness. Large weights stay on cluster storage or in an explicitly approved
private HF repository, never in the summary PR.

To summarize only the task definition:

```bash
./Master/Tasks/create-task-summary-pr/create_task_summary_pr.sh \
  --task jira-url-to-instability-model \
  --no-run
```

## Include related files

Use `--include` repeatedly with repository-relative or absolute paths:

```bash
./Master/Tasks/create-task-summary-pr/create_task_summary_pr.sh \
  --task jira-url-to-instability-model \
  --include Source/jira_data_for_instability_cluster.json \
  --include Data/Qt/features_labels_table_os.csv
```

Included paths are copied under `artifacts/included/` while preserving their
repository-relative paths.

## Add a short explanation

```bash
./Master/Tasks/create-task-summary-pr/create_task_summary_pr.sh \
  --task jira-url-to-instability-model \
  --summary "Qt and IntelDAOS were rerun after fixing Jira Cloud discovery."
```

## Validate without Git changes

```bash
./Master/Tasks/create-task-summary-pr/create_task_summary_pr.sh \
  --task jira-url-to-instability-model \
  --no-run \
  --dry-run
```

Dry-run mode builds and validates the complete temporary bundle, then prints
every file that would be committed. It does not create a branch, commit, push,
or pull request.

## Git and GitHub behavior

The script:

1. Builds the bundle from the current cluster checkout.
2. Rejects common credential files and credential patterns.
3. Compresses files larger than 90 MiB and rejects files still above 95 MiB.
4. Fetches the latest `origin/main`.
5. Creates a branch in a temporary Git worktree:

   ```text
   user/yakovelmaleh/summarize-<task>-<timestamp>
   ```

6. Commits the bundle under:

   ```text
   Tasks/task-summaries/<task>-<timestamp>/
   ```

7. Pushes the branch and creates a PR targeting `main`.
8. Removes the temporary worktree and leaves the primary checkout on `main`.

GitHub CLI is optional. With authenticated `gh`, the PR is created
automatically. Without it, the branch is still pushed and the script prints a
GitHub comparison URL for creating the PR manually.

Tracked changes are allowed when the primary checkout is already on `main`;
they are copied into the summary but left untouched in the primary checkout.
A dirty checkout on another branch is blocked to avoid losing work while
switching to `main`.
