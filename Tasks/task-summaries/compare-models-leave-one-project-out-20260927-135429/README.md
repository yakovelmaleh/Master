# Task summary: compare-models-leave-one-project-out

This folder is a review bundle generated from the cluster checkout. It copies
the selected task files into this summary folder; merging the PR does not
overwrite the original task implementation or runtime directories.

## Source

- Task: `compare-models-leave-one-project-out`
- Original task directory: `/home/yakovelm/Master/Tasks/compare-models-leave-one-project-out`
- Source branch: `main`
- Source commit: `9577c7d289981e082ec8c75936c2c5114cb68418`
- Bundle created: `2026-09-27T10:54:51Z`
- Included files: `856`
- Bundle size: `1138992 KiB`
- Cluster run: `20260924-212328-564730`
- Original cluster run directory: `/home/yakovelm/Master/Tasks/compare-models-leave-one-project-out/cluster_runs/20260924-212328-564730`

## Included content

- `artifacts/task/` contains the task definition and tracked task files.
- `artifacts/cluster-run/` contains the selected cluster run, when present.
- `artifacts/cluster-runs/<id>/` is used when multiple run IDs were selected.
- `artifacts/dependencies/` contains shared comparison/model code.
- `artifacts/included/` contains paths supplied with `--include`, when present.
- `LEVELS.csv` lists planned project/level/model/variant outputs and missing files.
- `RESULTS.csv` contains available unweighted test metrics with separate AP and AUC-PRC.
- `LEVEL_SUMMARY.md` describes coverage, including incomplete/failed jobs.
- `FILES.txt` is the exact committed file inventory.

Runtime caches, Python bytecode, and unrelated historical cluster runs are not
included automatically. Files larger than 90 MiB are gzip-compressed.

## Unstable-level coverage

- Levels present/planned: 5, 10, 15, 20.
- Standard levels absent: none.
- Incomplete or unverified model/level entries: 0 of 144.
- Published historical reference CSVs are kept separately; they are not matched rerun scores.
- AUC-PRC is trapezoidal PR area; average precision is a separate metric. Blank means not recorded.
