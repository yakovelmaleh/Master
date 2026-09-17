# Create an investigation PR

This task creates a GitHub pull request containing the complete investigation
artifacts for one dataset from one cluster task.

The script is general: the task name and dataset name are command-line
arguments. It currently supports the output structure used by:

- `jira-url-to-instability-model`
- `validate-refactored-model-per-dataset`
- `verify-refactored-instability-model`

## What the PR contains

The generated investigation folder includes:

- The selected dataset's complete `results/` directory.
- Every available SLURM `.out` log for that dataset.
- The generated `submit.sbatch` file.
- The run-level `submitted_jobs.tsv` manifest.
- At least one complete `features_labels_table_os.csv` dataset.
- A generated README and exact file inventory.

If the dataset is represented by a symbolic link, the real CSV content is
copied into the PR rather than the link.

Files larger than 90 MiB are gzip-compressed. The script stops if a file is
still larger than 95 MiB or if common credential patterns are detected in
operational files such as logs, sbatch scripts, manifests, and non-raw
metadata. Public Jira issue text and processed model datasets are not scanned
for generic words such as `password`, which can legitimately appear in issue
descriptions and caused false positives.

## Requirements

The cluster environment must provide:

```text
git
gzip
```

GitHub CLI is optional. When it is installed and authenticated, the script
creates the PR automatically:

```bash
gh auth status
```

When `gh` is unavailable, the script still creates and pushes the complete
investigation branch. It then prints a GitHub comparison URL that opens the
pre-populated PR creation page.

Tracked changes are allowed when the primary `Master` checkout is already on
`main`; they remain untouched because the investigation branch uses a separate
temporary worktree. A dirty checkout on another branch is blocked because
switching it to `main` could overwrite work.

## Create a PR for the latest run

Run from `/home/yakovelm`:

```bash
./Master/Tasks/create-investigation-pr/create_investigation_pr.sh \
  --task jira-url-to-instability-model \
  --dataset Apache
```

The script reads:

```text
./Master/Tasks/jira-url-to-instability-model/cluster_runs/latest_run.txt
```

to locate the latest run.

## Select a specific run

```bash
./Master/Tasks/create-investigation-pr/create_investigation_pr.sh \
  --task jira-url-to-instability-model \
  --dataset Apache \
  --run-id 20260917-210000
```

## Validate before creating a PR

```bash
./Master/Tasks/create-investigation-pr/create_investigation_pr.sh \
  --task jira-url-to-instability-model \
  --dataset Apache \
  --dry-run
```

Dry-run mode validates the selected run and prints every file that would be
included. It does not switch branches, copy files, commit, push, or create a
PR.

## Git behavior

Before creating the PR, the script:

1. Preserves tracked changes when the primary checkout is already on `main`.
2. Switches a clean primary checkout to `main` when necessary.
3. Fetches the latest `origin/main` for the temporary PR worktree.
4. Creates the investigation branch in a temporary Git worktree.
5. Copies, checks, commits, and pushes the investigation bundle.
6. Creates a GitHub PR targeting `main` when authenticated `gh` is available.
   Otherwise, prints the exact URL for creating the PR from the pushed branch.
7. Removes the temporary worktree and leaves the primary checkout on `main`.

Investigation branches use:

```text
user/yakovelmaleh/investigate-<task>-<dataset>-<run-id>-<timestamp>
```

Investigation artifacts are committed under:

```text
Tasks/investigations/<task>-<dataset>-<run-id>-<timestamp>/
```

## When dataset creation failed

The script requires a complete `features_labels_table_os.csv`. If the URL
pipeline failed before creating that dataset, the script stops and reports
that no complete dataset exists. The failure can still be investigated
manually from the `.out` log, but the automatic PR will not claim to include
a dataset that was never generated.
