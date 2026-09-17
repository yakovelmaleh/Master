# Validate the refactored model per dataset

This task runs an independent refactored weighted model for every existing
processed Jira dataset. It does not combine datasets into one cross-dataset
model.

It also does not download new Jira issues and does not compare the new outputs
with the original model. Those are separate tasks.

## Input data

The task-owned `datasets.json` points to the existing CSV files under the
repository's `Data/` folder:

```text
Data/Apache/features_labels_table_os.csv
Data/Hyperledger/features_labels_table_os.csv
Data/IntelDAOS/features_labels_table_os.csv
Data/Jira/features_labels_table_os.csv
Data/MariaDB/features_labels_table_os.csv
Data/Qt/features_labels_table_os.csv
```

The CSV files remain in place and are not modified or copied.

## What runs

The launcher reads every key from `datasets.json` and submits one independent
SLURM job per dataset:

```text
Apache dataset      -> Apache job      -> Apache model
Hyperledger dataset -> Hyperledger job -> Hyperledger model
IntelDAOS dataset   -> IntelDAOS job   -> IntelDAOS model
Jira dataset        -> Jira job        -> Jira model
MariaDB dataset     -> MariaDB job     -> MariaDB model
Qt dataset          -> Qt job          -> Qt model
```

All six jobs can run in parallel. Each job uses only its own dataset.

The jobs call the validated runner from:

```text
Tasks/verify-refactored-instability-model/run_verification.py
```

That runner records the source CSV path, byte size, and SHA-256 hash before
training the refactored model with balanced class-based sample weights.

## Run from the `yakovelm` folder

```bash
cd /sise/home/yakovelm

./Master/Tasks/run_cluster_task.sh \
  --pull \
  validate-refactored-model-per-dataset
```

`--pull` updates the current Git branch with `git pull --ff-only` before
submitting jobs. Omit it to use the current checkout.

## Run selected datasets

`--only` may be repeated:

```bash
./Master/Tasks/run_cluster_task.sh \
  validate-refactored-model-per-dataset \
  --only Apache \
  --only Qt
```

## Preview without submitting

```bash
./Master/Tasks/run_cluster_task.sh \
  validate-refactored-model-per-dataset \
  --dry-run
```

This creates all generated sbatch files and the job manifest without calling
`sbatch`.

## Results and logs

All generated files stay inside this task:

```text
./Master/Tasks/validate-refactored-model-per-dataset/cluster_runs/<run-id>/
├── submitted_jobs.tsv
├── apache/
│   ├── submit.sbatch
│   ├── logs/
│   │   └── job-<SLURM_JOB_ID>.out
│   └── results/
│       ├── verification_manifest.json
│       ├── input_layout/
│       │   └── Apache/features_labels_table_os.csv
│       └── model/
│           └── apache_words_5/
│               ├── model.npz
│               ├── feature_transformer.json
│               ├── metrics.json
│               ├── run_metadata.json
│               ├── validation_predictions.csv
│               ├── test_predictions.csv
│               ├── feature_coefficients.csv
│               └── report.html
├── hyperledger/
│   └── ...
└── qt/
    └── ...
```

`submitted_jobs.tsv` maps every dataset to its SLURM job ID, results directory,
`.out` log, and generated sbatch file.

`cluster_runs/latest_run.txt` contains the newest run directory. Generated
`cluster_runs/` content is ignored by Git.

## Different label threshold

The default model uses `is_change_text_num_words_5`. To use another supported
threshold for every dataset:

```bash
./Master/Tasks/run_cluster_task.sh \
  validate-refactored-model-per-dataset \
  --label-threshold 10
```
