# Local community Jev-style instability benchmark

This task evaluates **`com-kotobalabs/open-jev-deberta-v3-large`**, an independent
community model, **not official TypeSafe Jev**. It runs entirely on the cluster.
No TypeSafe API, API key, external issue-data transfer or API charges are involved.
Only model artifacts and their reviewed loader are fetched from Hugging Face at
runtime; none of them is committed to Git.

| Item | This task |
| --- | --- |
| Research question | Can this community typed-decision model predict future issue-text instability without task-specific training? |
| Training data | No local model training. The publisher's pretrained backbone, native scoring head and temperature are retained. |
| Split | Exact #357 per-repository 60/20/20 contract; validation chooses F1 thresholds only, training rows are not used as examples. |
| Models | One pinned DeBERTa-based community Jev-style checkpoint. |
| Test coverage | All six repositories and levels 5/10/15/20: 24 cells. |
| Results | Native probability of yes; PR area, AP, ROC, thresholded metrics, matched classical baseline, controls, uncertainty and token coverage. |
| Completed outputs | Implementation and offline checks only. No real Jev/GPU benchmark results are supplied. |

## Why this is separate

The published model has a custom span-matching decision head and a native
`noul` (yes/no probability) interface. Loading only its encoder and attaching a
fresh generic classifier would not evaluate the published Jev-style model.
This task uses its native head and probability of **yes**, not its confidence.

It is a **zero-shot benchmark with validation-selected decision thresholds**,
not a supervised fine-tuning run. Report it as such alongside the existing
trained models; equal test rows do not imply equal training protocols.
Do not claim community performance is official TypeSafe Jev performance.

The publisher's limits are 256 state tokens and 512 tokens overall.
We submit one level-specific question at a time, use the native right-truncation
policy, and report affected rows. Truncated rows are not silently removed.
The fixed prompt asks about future changes of at least K words after sprint entry,
not whether an issue discusses changing software. Its label definition follows
`Using_CSV_files/Load_Data_From_Jira_To_CSV/ChooseFeaturesColumns.py`.
Only concatenated original pre-sprint text is supplied; identifiers and labels
stay outside the model input. All four existing labels remain unchanged.

## Task contents

- `model.json`: immutable checkpoint revision, identity/license, native limits,
  and SHA-256 values of the reviewed publisher loader/config files.
- `jev_backend.py`: runtime preparation, verified local loading, native scoring.
- `run_evaluation.py`: profile, validation, selection seal, test and reporting.
- `cluster/submit_jobs.sh` and `.py`: master-launcher integration and SLURM jobs.
- `requirements.txt`: existing isolated HF stack plus pinned tokenizer dependencies.
- `tests/`: no-download contract, probability, launcher and mocked workflow tests.

## Run through the master launcher

Use the existing Python 3.11 `master-hf` environment. **Wait for the current
ModernBERT job to finish.** This task uses the same submission lock and refuses
to overlap another active Master HF array, including its setup stage.

The task is discovered automatically:

```bash
./Master/Tasks/run_cluster_task.sh --list
```

First install this task's extra dependencies **as a CPU job**, not in a blocking
login-terminal command:

```bash
./Master/Tasks/run_cluster_task.sh evaluate-hf-instability-jev \
  --stage setup --partition main --conda-env master-hf \
  --cache "$HOME/master-hf/cache" --storage "$HOME/master-hf"
```

After setup completes successfully, submit preparation on a node with Hub access:

```bash
./Master/Tasks/run_cluster_task.sh evaluate-hf-instability-jev \
  --stage prepare --partition main --conda-env master-hf \
  --cache "$HOME/master-hf/cache" --storage "$HOME/master-hf"
```

After the `.out` log says `READY jev_deberta: ...`, profile **one GPU**:

```bash
./Master/Tasks/run_cluster_task.sh evaluate-hf-instability-jev \
  --stage profile --partition main --gres gpu:rtx_3090:1 \
  --conda-env master-hf --mem 32G --time 02:00:00 \
  --cache "$HOME/master-hf/cache" --storage "$HOME/master-hf"
```

The profile exercises all four questions, maximum-state truncation, reload
equivalence and measured GPU memory. Because this is a zero-shot model,
profiling does not perform backward/optimizer steps. The RTX 3090 request is a
starting allocation, not a promise of measured compatibility.

Once profiling succeeds:

```bash
./Master/Tasks/run_cluster_task.sh evaluate-hf-instability-jev \
  --stage validate --run-id jev-study-01 \
  --partition main --gres gpu:rtx_3090:1 --conda-env master-hf \
  --cache "$HOME/master-hf/cache" --storage "$HOME/master-hf"
```

Wait for all validation jobs, then submit `--stage seal` using the same command
without `--gres`. Next submit `--stage test` using the GPU command, and finally
`--stage report` without `--gres`. Keep the same run ID throughout.
Validation/test each use one sequential four-level job per repository,
with at most two jobs active. `setup`, `prepare`, `profile`, `seal` and `report`
each submit a single job. All submissions return a job ID promptly.

Start/completion/failure mail is requested by default using the same recipient
as the existing Jira task; `--mail-user` overrides it. Arrays send array-level
notifications. Use `--dry-run` on any stage to inspect sbatch without side effects.

## Outputs

| Artifact | Location |
| --- | --- |
| SLURM `.out` / `.err` | `Tasks/evaluate-hf-instability-jev/cluster_runs/<submission-id>/logs/` |
| Array/project commands and job ID | Same submission's `hf_job_plan.json` |
| Cached native model and reviewed loader | `<cache>/models--com-kotobalabs--open-jev-deberta-v3-large/snapshots/<revision>/` |
| Verified readiness | `<cache>/ready/jev_deberta.json` |
| GPU profile | `<storage>/jev-profiles/<protocol-hash>/profile.json` |
| Study/validation/test/predictions | `<storage>/jev-runs/<run-id>/` |
| Per-project status | `<storage>/jev-runs/<run-id>/status/` |
| Lightweight final summary | Report submission's `results/hf_report.json` |

The existing `create-task-summary-pr` understands this report and uses its
HF allowlist: no weights, native heads, raw datasets or loader snapshots enter
Git summaries. Checkpoint hashes/revisions remain in the report as references.
Results belong in the **new sprint's PowerPoint (October 8, 2026)**, in a separate
experiment section; leave the prior sprint deck unchanged.

## Reproducibility, failures and limits

- All six input files and ordered labels/splits must match #357.
- The fixed prompt, native code hashes, environment versions and source hashes
  are recorded. Changed provenance requires a new run ID and a matching profile.
- Sealing requires all 24 validation cells. Test results never select the
  prompt, model, threshold or native temperature.
- Completed level outputs may resume only with matching hashes; partial levels
  rerun. Exceptions produce failed status and an error log, not default scores.
- Reports show missing test cells explicitly and require all 24 approved
  PR/AP/ROC gates for overall success.
- Historical baseline predictions must be available from the fetched #357 Git
  objects, as described in the shared HF task README.
- Issue-bootstrap confidence intervals do not account for temporal dependence.
  Pretraining contamination, truncation and historical holdout reuse remain caveats.
- No guarantee is made about AUC-PRC >0.5 or native calibration on this new domain.
- Current ModernBERT/Qwen/Phi/Gemma code, registry and profile hashes are unchanged.

## Reviewed external code

This model requires its publisher's Python loader. Preparation downloads only
four explicitly listed source files at revision
`188ee67a5c93122b916e5acd5bdb0cb3623e380a`; they were read before integration and
their hashes are pinned in `model.json`. Loading verifies those hashes and all
cached model files, imports the package under a private module name without
writing bytecode into the Hub snapshot, and runs with Hub offline mode enabled.
There is no blanket `trust_remote_code=True` and no arbitrary repository import.
Changing a loader revision requires a new source review and explicit hash update.

The code-only PR does not contain copies of the model weights or publisher code.
The native model/loader's GPU execution has not yet been verified on the cluster;
the profile is a required acceptance gate, not a claimed result.

## Further candidate

`autotrust/JEV-9B` remains a later research candidate. It is not prepared or
scheduled by this task. It requires separate review of its Qwen backbone,
adapter/head loading, resources and licensing. Do not substitute official
TypeSafe API results or another similarly named model without a new experiment.

## References

- Model and native interface: https://huggingface.co/com-kotobalabs/open-jev-deberta-v3-large
- Pinned loader: https://huggingface.co/com-kotobalabs/open-jev-deberta-v3-large/tree/188ee67a5c93122b916e5acd5bdb0cb3623e380a/typed_decisions
- Later candidate: https://huggingface.co/autotrust/JEV-9B
- Official TypeSafe Jev (different model): https://docs.typesafe.ai/models
