# Story detail sufficiency as a predictor of instability

This is a **new exploratory ten-shot prompt experiment**, not a rerun or mutation
of the completed Azure study. GPT-4.1-mini acts as a senior software engineer at
the organization responsible for the named project and answers:

> Does this story contain enough detail to implement the requested work and
> determine whether the task is done?

`1` means **insufficient detail**, used as the positive instability score.
`0` means **sufficient detail**. K remains the original observed changed-word
label (5 or 20); it is **never explicit prompt metadata**, but determines which
training examples and labels are selected. The hypothesis is that missing
detail predicts instability, not that those two concepts are ground-truth
equivalents. No manually annotated sufficiency accuracy is claimed.

The System message includes **10 fixed training examples per project/K**:
five stable (`0`) and five unstable (`1`). Both input variants use the same
example identities. A fixed seed and SHA-256 ranking of training row IDs select
and order them, without looking at validation/test scores. Labels are proxy
judgments, not human assessments of detail sufficiency.

Each example's story is capped at **256 tokens**; the structured variant keeps
its original structured fields. The target story keeps its original prepared
text budget. The complete system-plus-user prompt must fit **10,240 tokens**.
Preparation stops if it cannot fit, rather than dropping examples, selecting
shorter stories, changing the request limit, or dropping evaluation rows.
Preparation also stops if a project/K has fewer than five training rows of
either class or if training and held-out row identities overlap.

## Files

- `sufficiency.py`: exact system/user prompt, provenance, matched-data preparation,
  fixed training-example selection, and separate approval contract.
- `backend.py`: the original Azure request/scoring settings with the new exact
  prompt guard; no training or repository retrieval.
- `input_plan.py`: read-only sizing of all prompts, including oversized prompts,
  with explicitly historical-rate cost estimates.
- `ledger.py`: new-run-only accounting, preserving existing global reservations,
  historical recovery evidence, and unknown training quarantine.
- `renew_storage.py`: separately reviewed, bounded storage renewal on the existing
  recovered authority; never bootstraps or resets existing state.
- `run_experiment.py`: preparation, preflight, smoke, bounded validation/test,
  sealing, reporting, and receipt-only reconciliation.
- `run.sh`: short entry point using the existing `master-openai` interpreter.
- `cluster/submit_jobs.sh` and `cluster/submit_jobs.py`: standard master-launcher
  integration for one preparation or explicitly approved storage-inspection job,
  with email and saved status.
- `cluster/inspect_storage.py`: 100-request storage-only inspection with
  conservative, once-only accounting for the uncertain renewal recovery.
- `tests/test_sufficiency.py`: offline prompt, provenance, workflow, and
  accounting regression tests with synthetic data and fake transports.

## Matched design

Same versioned `gpt-4.1-mini-2025-04-14`, Jira/Qt, K=5/20, text/structured
variants, original splits, target/example text limits, input truncation, train-fitted
features, scoring settings, validation threshold selection, and metrics.
The source is the completed `openai-prompt-01` study, including its original
seal and final recovery-annotated report.

The reviewed configuration overrides are `max_input_tokens: 10240`, raised
from the source study's 8,192 after measurement found a maximum of 9,677, and
`total_limit_usd: 100`, raised from 80 by explicit budget review.
Both are bound into the new study signature and its approval hash. Source
validation still requires the unchanged original config. Three total attempts,
the cumulative pilot limit of 9, the protected reserve of 20, and all historical
reservations remain unchanged. The new total cap includes previous reservations
and storage; it is not an additional allowance for this run.

Preparation reads only the original prepared prompts/sidecars. It preserves
the target's exact already-truncated story and structured feature values.
It adds the project name and the sufficiency question, replaces the system
prompt with the rubric plus ten demonstrations, and removes
`unstable_word_threshold`. Only selected **training labels** appear in the
System examples; the target's label stays in its private sidecar.
There are exactly two messages, System and User, with no assistant messages.
Across K the target input is unchanged, but demonstration selection and labels
can differ. Each cell is scored separately, as in the prior experiment.
K-specific thresholds are selected on validation only.

The train partition is retained for coverage/provenance compatibility with
existing helpers. Selected training stories are sent as in-context examples;
there is no model training, fine-tuning, or training-set evaluation.
The runtime exposes no training, file-upload, deployment-creation, or deletion
stages. Project/company knowledge is not assumed from the role alone.

The original task, recovery task, original results, and sprint presentation
are unchanged. Existing scientific helpers are imported read-only; there are
no runtime prompt monkey-patches.

## Offline sizing before preparation

If an earlier preparation stopped at the 8,192-token guard, keep that partial run untouched.
Do not delete its markers, shorten examples, or raise its limit silently.
Run the sizing-only command, which does not need a completed new preparation:

```bash
bash Tasks/evaluate-openai-story-sufficiency/run.sh plan
```

It reads the frozen source study and constructs the same ten demonstrations
using the same shared selection/truncation logic. It measures **every**
train/validation/test prompt and both synthetic capability prompts without
calling Azure, writing prepared data, or altering any run or approval.
The result is written to
`$HOME/master-openai/openai-sufficiency-input-plan.json`; use `--output` with
a new external path if a previous plan already exists.

The summary gives the maximum required token count, validation/test maximum,
over-limit counts by split, and a rounded-up **hypothetical** limit used only
for cost calculations. The detailed report includes each cell/partition's
token counts, system lengths, example hashes, and estimated JSONL payload bytes.
It contains no story text, example identities, or account/resource identifiers.

If the source authorization is available, the cost worksheet uses its
**historical, unverified-for-current-use** input/output prices, rate margin,
storage reserve, and unchanged three-attempt bounds. The source approval may
be expired: these numbers are illustrative, not permission to spend.
The full-scope bound already includes the pilot; do not add them together.
It does not establish available global capacity or account for all prior
reservations. Current rates, credit, and storage retention/capacity still
require separate review. If the historical authorization is missing,
the sizing report still works and reports cost estimates as unavailable.

The implemented input limit is now 10,240; sizing uses that same new-experiment
config. The planner still cannot approve or install a larger hypothetical value.
The earlier sizing report remains evidence for its original implementation.
Keep earlier partial runs and plans; prepare under the new default
**`openai-sufficiency-04`** rather than rewriting the old study. Preserve the
successfully prepared runs `02` and `03`: the pilot-budget change requires a
new configuration identity, not different prompts or data.

The earlier bound exceeded the old total cap. The reviewed cap is now 100,
but that alone is not spending permission or a guarantee of affordability.
Fresh rates, credit, storage capacity/retention, and cumulative reservations
must still be checked. In particular, prior pilot allocations continue to
count against the reviewed cumulative pilot cap of 16; insufficient pilot headroom
must stop for separate review, never trigger full-scope authorization as a bypass.
The total cap remains 100 and the protected reserve remains 20. No previous
reservation is released. The input limit, three-attempt ceiling, examples,
target inputs, and evaluation scope are unchanged.

## Offline preparation through the cluster launcher

Use the normal `--pull` workflow after the launcher PR is merged. From the
cluster login node, on the intended `main` branch:

```bash
cd "$HOME/Master"
git switch main
bash Tasks/run_cluster_task.sh --pull evaluate-openai-story-sufficiency --stage prepare
```

The master launcher runs `git pull --ff-only`, then submits **one CPU sbatch
job** using the existing `master-openai` environment. No environments or
dependencies are installed. The job prepares the new study only: it never
runs preflight, smoke, validation, or any Azure stage. Email uses `MailType=ALL`
and the existing launcher recipient; `--mail-user` can override it.

If Git reports local changes or untracked files from earlier archive installs,
stop and inspect them; do not reset, clean, delete files, or force the pull.
Source provenance is checked before submission and again on the worker.
A pull that changes the frozen source/config/dependencies will therefore block
preparation, not silently rewrite the original experiment.

Defaults:

- Storage: `$HOME/master-openai`.
- Source: `openai-runs/openai-prompt-01`.
- New run: `openai-sufficiency-runs/openai-sufficiency-04`.
- Partition: `main`; time: `04:00:00`; memory: `8G`; CPUs: `2`.

Optional `--storage`, `--run-id`, `--source-run`, `--partition`, `--time`,
and `--mail-user` follow the task name. Add `--dry-run` to render the job
without submitting it (omit master `--pull` if no Git update is wanted).
Source files and dependency versions must still match the old study fingerprint.
Changed or missing source data fail closed; do not regenerate or edit old
provenance to work around that failure.

Job evidence lives under the new run's `jobs/prepare/`: `submission.json`,
`submit.sbatch`, `slurm-<job-id>.out/.err`, `worker.started`, and
`worker-status.json`. The launcher records intent before calling sbatch and
refuses repeated submission, including after an ambiguous scheduler response.
Inspect the saved job/status before any retry; keep its markers. A failed
job needs investigation and an explicitly chosen fresh run ID, not automatic
resubmission. `--no-requeue` also prevents automatic scheduler requeue.

The worker makes **no Azure calls**. It writes the new `study.json`, private
prepared payloads/sidecars/transformers, `demonstrations.json`, `prepared.json`, and
`approval.template.json`. Template checks default to false, rates are unset,
and expiry is empty. Do not upload these private files to Git.
`demonstrations.json` records selected row identities, proxy labels, example
truncation, and exact system messages; its hash is bound into the preparation
manifest and the cell's model reference. Changed examples invalidate reuse.

For diagnostics only, direct offline preparation remains available:
`bash Tasks/evaluate-openai-story-sufficiency/run.sh prepare`.

## Approval and execution

**The November 6, 2026 approvals and November 7 storage retention have expired.**
Preparation is safe offline, but `lets do it` does not renew financial limits
or authorize current Azure access. Before any live stage:

1. Review the new private study hash and exact prompt.
2. Separately renew storage access, retention, capacity, and current credit/rate
   evidence for the existing authority. Preserve all prior reservations and
   quarantine; do not bootstrap a new ledger to bypass them.
3. Use this task's explicit `renew_storage.py` for the recovered authority.
   The old `control_admin.py extend-storage` rejects that recovered schema;
   this task leaves it unchanged and does not auto-renew storage.
4. Approve a new model allocation bound to this study, including
   `story_sufficiency_experiment_approved`. Old study/recovery approval is not
   reusable. The cumulative total/pilot caps are 100/16; the protected reserve
   remains 20.

The fresh approval explicitly binds `prompt_method: ten-shot-system-user`.
It also records `budget_limits` and requires `cumulative_budget_approved`.
This check defaults to false. Model and storage review files must both match
the new study's total/pilot/protected limits; old approvals cannot be reused.
The original transport/accounting protocol identifiers are retained only for
compatibility with the unchanged cost-control helpers; the new study and all
scientific results identify the actual ten-shot method. Recalculate both
token and storage bounds: examples are included in every request and private
prepared payload, and the previous cost estimate does not cover this design.

Each model-workflow stage additionally requires `--execute-approved-stage`.
That flag does not replace the reviewed model or storage approval. Only after
the private approvals and this specific preflight have been reviewed:

```bash
bash Tasks/run_cluster_task.sh --pull evaluate-openai-story-sufficiency --stage preflight \
  --approval /absolute/private/new-approval.json --execute-approved-stage
```

Each validation/test invocation handles at most the original 400-row batch.
Complete the Jira/20 pilot, review it, then use a separately approved full-scope
preflight. Complete all eight validation entries, `seal`, run the reviewed
number of `test` batches, then `report`.
No stage loop, approval expansion, or retry after ambiguous failure is included.

### Bounded model-stage jobs

The standard launcher supports `preflight`, `smoke`, `validate`, `seal`, `test`,
and `report`. Every invocation submits **one CPU job running one stage once**;
it never chains or queues the next stage. Wait for the saved worker status and
review the result before submitting another job.

Preflight reads Azure account/deployment metadata and checks data-plane access,
then records a cumulative pilot/full allocation in Storage. It makes no inference
request, but is not an offline or read-only operation. `smoke` performs at most
22 logical capability/control predictions; `validate` and `test` each handle at
most one 400-row batch under the existing attempt and uncertain-call rules.
Sealing and final test require full-study approval, not merely a pilot approval.

Use `--approval` only for preflight. Other stages require the already-created
`authorization.json` and still check the cloud authority. The launcher checks
model and storage approvals offline before submission, pins their file hashes
and the prepared-manifest hash, and rechecks them before worker dispatch.
Changed/expired approvals stop the queued job rather than silently using new
permission. Even `--dry-run` requires valid review files but submits nothing.
No private approval contents are embedded in the sbatch script or manifest.

For repeated validation/test batches or a separately reviewed full preflight,
use a unique `--job-label`. For example, only after smoke succeeds and this
pilot batch is explicitly authorized:

```bash
bash Tasks/run_cluster_task.sh --pull evaluate-openai-story-sufficiency --stage validate \
  --job-label pilot-01 --execute-approved-stage
```

The label identifies job evidence, not a row selection or a new spending scope.
The runner chooses the next unfinished work under the existing authorization.
Evidence is saved in `jobs/<stage>-<label>/`, or `jobs/<stage>/` without a label,
including `worker-status.json` and a job-local `result.json`.
Do not change labels or remove markers to retry failed or uncertain work without
review. Duplicate submission and worker reentry remain blocked.

This launcher-only change preserves prepared run `04` and the study signature.
Do not prepare another run just to use these stages. Model execution still needs
its own explicit approval; merging the launcher does not grant it.

Known 429 rejections retain the original bounded attempt policy. HTTP 500,
timeouts, and other ambiguous outcomes stop with reservations retained.
The previous sealed-study HTTP-500 recovery permission does **not** extend to
this new experiment. `reconcile` consumes an exact existing receipt; it cannot
replay an uncertain inference. Fresh current approvals are required for cloud
access even during reconciliation in this task.

The recovered authority's immutable historical review is checked as provenance,
not reused as spending consent. New-run writes cannot target historical runs.
If renewals or capacity checks fail, stop; do not reset counters or drop rows.

### Separate storage-renewal review

After preparation, generate a false-default template from the existing local
storage approval, without cloud access:

```bash
"$HOME/.conda/envs/master-openai/bin/python" \
  Tasks/evaluate-openai-story-sufficiency/renew_storage.py template \
  --root "$HOME/master-openai/openai-sufficiency-runs/openai-sufficiency-04" \
  --output "$HOME/.local/state/master-openai/sufficiency-04-storage-template.json"
```

Review current credit, pricing, all previous reservations, worker termination,
and expired-retention implications. Set new explicit access/retention deadlines
and sufficient cumulative request/session limits in a separate approved copy.
The template preserves the installed storage bounds; the pilot-cap code change
does not increase them or install an approval. Review the full request/session
envelope plus administrative and recovery capacity, not just token costs.
The historical `zero_use_migration_verified` check refers to the original
bootstrap evidence, not a claim that the now-used authority is empty.

Only after explicit approval:

```bash
"$HOME/.conda/envs/master-openai/bin/python" \
  Tasks/evaluate-openai-story-sufficiency/renew_storage.py renew \
  --root "$HOME/master-openai/openai-sufficiency-runs/openai-sufficiency-04" \
  --review /absolute/private/approved-storage-renewal.json \
  --output /absolute/private/storage-renewal-result.json \
  --storage-renewal-approved
```

This reserves one session and at most 100 storage requests, checks exact old
plan/recovery hashes under a lease, and retains all model allocations, unknown
attempts, quarantine, and financial counters. It refuses pending operations,
cost breaches, cap violations, or reduced allowances. An ambiguous transaction
must be inspected; it never creates a replacement authority or a model allocation.
An identical approved review can recover its recorded successful result without
applying the extension again.

After confirmed success, preserve the old local `cloud-approval.json` and install
the reviewed renewal there. No local approval file is overwritten automatically.
Model preflight then separately checks whether the complete requested scope fits
the renewed capacity and existing global financial limits.
Renewal checks the new study's explicitly reviewed cap and protected reserve,
without reducing prior allocations or resetting session/request counters.

### Bounded storage inspection after renewal

After confirming the renewal receipt and backing up/installing its exact reviewed
approval as `cloud-approval.json`, obtain separate approval for **at most 100 new
storage requests**. Then use the usual launcher, without preparing the run again:

```bash
bash Tasks/run_cluster_task.sh --pull evaluate-openai-story-sufficiency \
  --stage inspect-storage --execute-approved-inspection
```

This submits one CPU job for the existing run. It validates the current study,
unexpired storage approval, fixed account, recovery history, and exact renewal
receipt. The transport cannot exceed 100 requests, even when accounting for
historical uncertainty. It never creates a model client or authorizes inference.
Its source is checksum-bound into the submission separately from the study;
adding this helper alone does not change study provenance. The subsequent
pilot-budget change does require the new run `04` and fresh approvals.

The earlier renewal recovery may have made requests without incrementing the
authority's counters. Conservatively retain **100 previous requests and one
previous session**, in addition to this inspection's 100-request/one-session
envelope. A conditional transaction records the extra session and a unique
marker tied to the exact renewal review. The request reservation includes both
envelopes. Once the marker commits, subsequent separately approved inspections
do not count that historical allowance twice. No financial allocation, pending
operation, quarantine, or historical record is reset or released.

Existing cumulative capacity must cover that bookkeeping. If it cannot, the job
stops for review rather than silently increasing limits. A lost response leaves
reservations and markers retained; do not retry automatically.

The numeric summary is in
`openai-sufficiency-runs/openai-sufficiency-04/jobs/inspect-storage/inspection.json`,
beside the worker status and private SLURM logs. It reports cumulative and pilot
reservations/headroom, remaining request/session capacity, stop flags, and the
retained recovery allowance. It omits account identifiers and story text.
These are reserved bounds and a dated snapshot, not actual billing or permission
to start inference.

## Reporting and interpretation

New output: `openai-sufficiency-runs/<run-id>/llm_report.json`, schema
`openai-story-sufficiency-report-v1`.

It includes the original per-cell metrics/gates and classical comparators,
plus matched descriptive AUC-PRC/AP/ROC-AUC differences from the previous
OpenAI report. The internal `private-core-report.json` is not a publication
artifact; use the sufficiency report with its exploratory caveats.

This compares the combined sufficiency framing plus ten training examples
against the previous zero-shot prompt; it does not isolate a persona-only,
framing-only, or example-only effect.

The holdout has already been examined and motivated this follow-up. An apparent
improvement is therefore **exploratory, not fresh independent confirmation**.
No paired confidence interval is claimed for the prompt-to-prompt differences.
The inherited issue-bootstrap intervals compare against classical baselines,
do not model temporal dependence, and do not adjust for multiple comparisons.
Conditional label-token scores are not calibrated event probabilities.
Preserve the newly sealed thresholds; do not reverse scores or tune on test.

## Offline checks

```bash
"$HOME/.conda/envs/master-openai/bin/python" -m unittest discover \
  -s Tasks/evaluate-openai-story-sufficiency/tests -q
```

Tests use synthetic records, a fake control store, and a mocked provider. They
exercise all eight cells through validation, sealing, test, and reporting,
without model calls or storage charges. Actual cluster preparation, renewed
approval, provider preflight, and capability smoke are separate live steps.
