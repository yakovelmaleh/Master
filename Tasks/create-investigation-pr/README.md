# Create an investigation PR

This task creates a GitHub pull request containing size-limited investigation
artifacts for one dataset from one cluster task.

The script is general: the task name and dataset name are command-line
arguments. It currently supports the output structure used by:

- `jira-url-to-instability-model`
- `validate-refactored-model-per-dataset`
- `verify-refactored-instability-model`

## What the PR contains

The generated investigation folder includes:

- The selected dataset's result files at or below 90 MiB each.
- SLURM `.out` logs at or below 90 MiB each.
- The generated `submit.sbatch` file.
- The run-level `submitted_jobs.tsv` manifest.
- The complete `features_labels_table_os.csv` dataset when created and within
  the per-file limit.
- Logs and partial results when the job failed before creating the final CSV.
- A generated README and exact file inventory.
- `OMITTED_FILES.csv`: omitted artifact paths, original byte sizes, and reasons.
- `DATASET_STATUS.txt`: whether dataset CSVs were included, not created, or
  excluded by the size limit.

If the dataset is represented by a symbolic link, the real CSV content is
copied into the PR rather than the link.

**Files larger than 90 MiB (94,371,840 bytes) are skipped before copying.**
Files exactly at the limit are included. This applies to every artifact,
including raw downloads, datasets, logs, model binaries, and already compressed
files. Large files are not compressed or split. Originals remain unchanged on
the cluster, and every exclusion is printed and recorded in the bundle.
Selection uses the target size for symlinked files; included targets are copied
as real files. A file growing beyond the limit during copying stops publication.

The script stops if common credential patterns are detected in
operational files such as logs, sbatch scripts, manifests, and non-raw
metadata. Public Jira issue text and processed model datasets are not scanned
for generic words such as `password`, which can legitimately appear in issue
descriptions and caused false positives.

Size filtering is not credential sanitization. A smaller raw file can still
contain secrets; resolve any known credential findings before publishing.

## Requirements

The cluster environment must provide:

```text
git
python3
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

Dry-run mode validates the selected run and prints `INCLUDE` or `SKIP` for
every file using exactly the same size selection as publication. It does not
switch branches, copy files, commit, push, or create a PR. It does not run the
publication credential scan.

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

If the URL pipeline failed before creating
`features_labels_table_os.csv`, the script still creates the investigation
bundle. It includes the `.out` logs, sbatch file, run manifest, and every
partial result produced before the failure. The generated investigation README
explicitly records the dataset status as `not_created` and does not claim that
a complete dataset is present.

If a final CSV exists but exceeds 90 MiB, the bundle records `omitted_size`
instead, or `partial_omitted_size` when some final CSVs are included and others
are too large. This does not mean dataset creation failed.

## Local checks

```bash
python3 -m unittest discover -s Tasks/create-investigation-pr/tests
bash -n Tasks/create-investigation-pr/create_investigation_pr.sh
```
