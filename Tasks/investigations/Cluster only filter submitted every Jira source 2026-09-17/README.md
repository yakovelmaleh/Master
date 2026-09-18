# Cluster only filter submitted every Jira source 2026-09-17

## Status

Fixed in PR `#341`.

## Scope

- Task: `jira-url-to-instability-model`
- Command filter: `--only`
- Pull request: `#341`
- Investigation date: `2026-09-17`

## Symptom

Running:

```bash
./Master/Tasks/run_cluster_task.sh \
  jira-url-to-instability-model \
  --only Qt \
  --refresh
```

created six SLURM jobs instead of one Qt job.

## Root cause

`cluster/submit_jobs.sh` treated `--only Qt` only as arguments to forward to
`run_cluster.py`. Before Python ran, the shell launcher independently iterated
over every configured Jira source and submitted one job for each source.

Each generated command therefore contained both its launcher-selected source
and the forwarded user filter. The filter could affect Python execution, but
it was too late to prevent the extra SLURM submissions.

Confidence: high.

## Evidence

- The shell launcher read every enabled source directly from the JSON file.
- Its submission loop did not inspect `--only`.
- `--only` remained in the generic forwarded arguments.
- The run manifest contained six jobs after requesting only Qt.

## Impact

Filtered reruns wasted cluster capacity, created misleading result folders and
logs, and could run the same selected source more than once.

## Decision and actions

- `submit_jobs.sh` now parses `--only` as a launcher option.
- Source filtering happens before run folders or SLURM jobs are created.
- Multiple selected names still create one independent job per selected
  source.
- Unknown or disabled names fail before any partial submission.
- The generated Python command still receives exactly one source name.

## Fix and validation

- Pull request: `#341`
- Shell syntax: passed.
- Dry run with `--only Qt`: one Qt sbatch file and one manifest row.
- Dry run with `--only MariaDB Qt`: two sbatch files and two manifest rows.
- Unknown-source dry run: rejected before creating a run directory.

## Cleanup

Validation run directories were removed after their generated manifests and
sbatch files were checked.

## Follow-up

After merging PR `#341`, use the original filtered command. It will submit
only the requested source jobs.
