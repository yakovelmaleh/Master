# Runtime HF within-project instability experiments

**The PR contains code/configuration/documentation/tests only. Models are
downloaded on the cluster at runtime and never pushed to the Git repository.**

| Item | This task |
| --- | --- |
| Research question | Can pretrained semantic text representations improve prediction of a repository's newer unstable issues using its own older issues? |
| Training data | Historical Apache, Hyperledger, IntelDAOS, Jira, MariaDB and Qt CSVs from #357. |
| Split | Exact independent chronological 60/20/20 row order and labels from #357, at levels 5/10/15/20. |
| Models | Frozen text representations + logistic heads; validation-selected language-only LoRA/QLoRA heads, maximum two families per cell. |
| Test coverage | Latest 20% of each repository: all 24 repository/level combinations. |
| Results | Per-cell metrics, baseline comparisons, uncertainty, controls and target flags; no target guarantee. |
| Completed outputs | Runtime workflow and historical data contract. No real HF training scores are included. |

## Setup and task order

Use an **isolated** environment, not the existing `master` environment:

```bash
module load anaconda
conda create -n master-hf python=3.11
source activate master-hf
python -m pip install -r Tasks/train-hf-instability-within-project/requirements.txt
git fetch origin refs/pull/357/head
```

The last command obtains the archived baseline prediction Git objects needed for
paired final comparisons; it does not check out #357 or download HF models.
The package pins require compatible cluster CUDA/drivers and must pass the actual
GPU profile; they do not imply every architecture has already been tested.

If `master-hf` already exists and installing requirements failed, do not recreate
the environment. After pulling the corrected requirements, rerun only installation
and the dependency check:

```bash
conda run -n master-hf python -m pip install \
  -r "$HOME/Master/Tasks/train-hf-instability-within-project/requirements.txt" &&
conda run -n master-hf python -m pip check
```

The Hub client is pinned to 1.33.0: Transformers 5.18.0 requires Hub >=1.31.0,
while its Tokenizers 0.23 dependency requires Hub <2.0. Installing Hub 2.x
separately does not resolve this conflict. Continue to model preparation only
after installation and `pip check` succeed; that check does not validate CUDA.

1. Run `research-hf-instability-models --stage probe`.
2. Run `prepare-hf-instability-models` on a network-enabled node.
3. Run `research-hf-instability-models --stage profile --models <one-model>`
   separately for every selected model.
4. Run this task's `frozen`, `finetune`, `seal`, `test`, then `report` stages,
   waiting for each array to finish successfully before the next.
5. Optionally run `publish-hf-instability-models` with an explicitly approved
   private destination.

The existing master script discovers all four launchers automatically. Its
syntax is a positional task name, not `--task`. `--pull` performs `git pull
--ff-only` before submission; it does not decide which experiment to run.

```bash
bash Tasks/run_cluster_task.sh --list
bash Tasks/run_cluster_task.sh --pull train-hf-instability-within-project \
  --stage frozen --run-id hf-study-01 --models modernbert qwen_embedding \
  --partition YOUR_GPU_PARTITION --gres gpu:YOUR_TYPE:1 \
  --cache /cluster/storage/master-hf/cache --storage /cluster/storage/master-hf \
  --mail-user YOUR_CLUSTER_EMAIL --dry-run
```

Remove `--dry-run` only after checking allocation and paths. For `finetune` and
`test`, repeat the same command with the corresponding stage and same run ID,
models, configuration and storage. `seal` and `report` use a CPU partition and
do not need `--gres`. Never run training after sealing.

The launcher permits one active Master HF array per user, across storage roots.
Training arrays use `%2`; profiles require exactly one model/job. It checks
`squeue` under an advisory submission lock and refuses overlapping arrays. Do
not manually bypass the launcher with separate uncoordinated `sbatch` calls.
This protects quota without presuming unlimited resources.

## Storage and logs

| Content | Location |
| --- | --- |
| Pretrained weights/tokenizer | `<cache>/models--.../snapshots/<immutable-revision>/` |
| Immutable historical CSV snapshot | `<storage>/runs/<run-id>/data/<project>/` |
| Embedding cache | `<storage>/embeddings/` |
| Training-text token coverage/truncation | `<storage>/runs/<run-id>/length_reports/<project>-<model>.json` |
| Candidate heads/adapters | `<storage>/runs/<run-id>/{frozen,finetune}/<project>/<model>/<level>/<candidate>/checkpoint/` |
| Candidate validation predictions | Same candidate directory, outside Git |
| Sealed selections | `<storage>/runs/<run-id>/sealed.json` |
| Test predictions/metrics | `<storage>/runs/<run-id>/final/<project>/<level>/` |
| Per-job stage states | `<storage>/runs/<run-id>/status/` |
| SLURM logs | `Tasks/<task>/cluster_runs/<submission-id>/logs/slurm-<array>_<index>.{out,err}` |
| Array index/project/model command mapping | Same submission's `hf_job_plan.json`; also printed at the start of each log |
| Lightweight final report | Report submission's `results/hf_report.json` |

No symlinks to checkpoints are created inside the repository. Keep the external
storage root stable and accessible to all jobs. Source/config/model/environment
changes invalidate resume. Completed candidate manifests allow restarting a failed
stage; incomplete candidates are rerun, not silently accepted. Interrupted jobs
can leave a `running` state; inspect SLURM before resubmitting. No automatic
resubmission or hidden OOM adjustment is performed.

## Fairness, target and interpretation

`reference_contract.json` was generated from immutable #357 commit
`028b4e40f81ce29f00ae561f795a6df8a52adb7b`. Input bytes, ordered row IDs and
all four label arrays must match. The known boundary timestamp tie is preserved,
not silently repaired. Only original pre-sprint summary/description/acceptance
text is encoded. Structured ablations use the old train-fitted feature transform.
Labels/current text/issue IDs do not enter model text.

`experiment.json` fixes the seed and bounded search. The frozen stage compares
class weighting, regularization, and text-only/structured variants. The fine-tuning
stage keeps the best frozen structured-feature choice and tunes at most two
families per cell. Validation ranking prioritizes AP above prevalence and ROC
above 0.5, then trapezoidal PR area, then AP. Thresholds maximize validation F1.
Final-test predictions are never used to select a model, seed or threshold.

For **each of 24 cells**, the final target requires:

- Trapezoidal AUC-PRC strictly greater than 0.5.
- AP above test prevalence and the matched #357 comparator's AP.
- ROC AUC strictly greater than 0.5.

The comparator is chosen among #357's families/variants by validation AUC-PRC,
never by its test result. Constant-score PR area is `(1 + prevalence) / 2`,
so PR area above 0.5 alone is not useful ranking evidence. AP and PR area remain
different metrics. Null/missing/failed cells cannot pass. Report individual gates
and paired-bootstrap intervals; issue bootstrap does not model temporal dependence.
These are retrospective holdout comparisons, with possible pretrained-model
exposure to public Jira text, not a pristine prospective evaluation.

No result slide is created until real results exist. Append results to the
maintained sprint deck with this task's own overview, data, results and conclusions.

## Inference and code-only review

```bash
python Tasks/train-hf-instability-within-project/predict.py \
  --checkpoint /cluster/storage/master-hf/runs/RUN/frozen/PROJECT/MODEL/LEVEL/CANDIDATE/checkpoint \
  --cache /cluster/storage/master-hf/cache \
  --input-csv /path/to/historical-feature-rows.csv --output /path/to/predictions.csv

python Tasks/train-hf-instability-within-project/check_git_artifacts.py
python -m unittest discover -s Tasks/train-hf-instability-within-project/tests -v
```

Tiny-model tests use randomly initialized configurations, never `from_pretrained`
downloads. Pure CPU contract/report/launcher tests can run in the existing
comparison environment; actual HF adapter tests require the isolated dependencies.
Real GPU compatibility and performance remain cluster acceptance gates.

Implementation validation on the development machine: the pure-CPU tests and
mocked complete 24-cell workflow pass. Actual tiny HF backend tests have not run:
the private package feed required authentication and the public wheel host timed
out, so the isolated ML dependencies could not be installed. Real model loading,
architecture/QLoRA support, CUDA memory and private upload are **not yet verified**.
No pretrained weights were downloaded to perform these checks.

The summary helper understands `hf_report.json` and does not require fake joblib
files. Its HF allowlist excludes weights/adapters/cache directories regardless of
size, including symlinks. PR creation is a separate explicit action. The
investigation helper also excludes model artifacts for HF tasks; the normal
dataset-centric investigation layout is not produced by these array jobs, so
use the final report summary for this workflow.
