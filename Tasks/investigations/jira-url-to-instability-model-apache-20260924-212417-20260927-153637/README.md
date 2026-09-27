# Investigation: jira-url-to-instability-model / Apache

This folder contains a size-limited investigation bundle for one cluster
dataset run. Files above 90 MiB are omitted, not compressed.

## Source

- Task: `jira-url-to-instability-model`
- Dataset: `Apache`
- Cluster run: `20260924-212417`
- Original run directory: `/home/yakovelm/Master/Tasks/jira-url-to-instability-model/cluster_runs/20260924-212417`
- Original dataset directory: `/home/yakovelm/Master/Tasks/jira-url-to-instability-model/cluster_runs/20260924-212417/apache`
- Dataset status: `complete`
- Bundle created: `2026-09-27T12:36:45Z`

## Included artifacts

- Result files and SLURM `.out` logs at or below 90 MiB each.
- The generated `submit.sbatch` file, when present.
- The run-level `submitted_jobs.tsv` manifest, when present.
- Complete or partial result files produced before the failure.
- `OMITTED_FILES.csv` lists every omitted artifact, original size, and reason.
- `DATASET_STATUS.txt` distinguishes missing datasets from size exclusions.

- The complete `features_labels_table_os.csv` dataset.

Files larger than 90 MiB (including already compressed files) are excluded
before copying. Original cluster files are unchanged. This PR is for
investigation only; it does not change model or pipeline behavior.
