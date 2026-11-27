# Lease-safe sufficiency evaluation jobs

Execute one separately reviewed preflight, validation batch, seal, final-test batch
or report. This task reuses the existing sufficiency functions and scientific
gates, but constructs credentials before the lease and never refreshes them
under the lease. Code/PR approval authorizes no live job.

## Contents

- `evaluation.py`: offline private reviews, cached authentication, per-job
  cloud grants, bounded evaluation ledger/backend and stage dispatch.
- `tests/test_evaluation.py`: fake-client pilot/full lifecycle, source/scoring
  preservation, budget and seal gates, authentication order and uncertain writes.

The existing sufficiency cluster launcher exposes `eval-preflight`,
`eval-validate`, `eval-seal`, `eval-test` and `eval-report`. Use these reviewed
paths rather than the older normal authentication path. No scientific task-root,
completed smoke/recovery/diagnostic/resolution code, data, model or scoring
configuration changes. No dependencies are added.

## Review one job offline

For the first pilot validation job:

```bash
"$HOME/.conda/envs/master-openai/bin/python" \
  "$HOME/Master/Tasks/run-openai-sufficiency-evaluation/evaluation.py" template \
  --root "$HOME/master-openai/openai-sufficiency-runs/openai-sufficiency-04" \
  --stage validate --job-label pilot-01 \
  --output "$HOME/.local/state/master-openai/sufficiency-04-pilot-01-template.json"
```

Only a preflight template also requires `--approval /absolute/private/model-approval.json`.
Other stages bind the installed `authorization.json`. Templates bind the exact
stage, unique label, source/preparation, model approval, Storage approval, authority,
helper hashes, scope and computed request envelope. All checks default false,
current credit defaults to zero, and expiry is blank. Templates construct no
cloud clients and are created exclusively outside the run and Git.

Review current credit and coverage, stopped workers and previous job outcomes,
the exact operation scope and limits, and retained UNKNOWN accounting and
reservations. For full preflight, review the pilot results and full allocation
bound as a separate expansion decision. The scope estimate includes Storage and
is **not** a fresh additional allocation or proof of cumulative affordability;
the original cloud ledger checks retained allocations, cumulative caps and
protected credit before accepting expansion.

Save a separate approved copy. Its expiry cannot exceed model, Storage or
retention approvals. Every subsequent job needs its own label and explicitly
reviewed copy. Labels are identifiers, not a way to select favorable cells:
evaluation processes the next incomplete batch chosen by the unchanged runner.

## Separately approved execution

Example for that one pilot validation job:

```bash
bash "$HOME/Master/Tasks/run_cluster_task.sh" --pull evaluate-openai-story-sufficiency \
  --stage eval-validate --job-label pilot-01 \
  --evaluation-review "$HOME/.local/state/master-openai/sufficiency-04-pilot-01-approved.json" \
  --execute-approved-evaluation
```

There is no automatic chaining, array submission, retry of the command or
approval for the next job.

| Stage | Existing gates and bounded work |
| --- | --- |
| `eval-preflight` | Exact approved model/deployment/access checks and model allocation only; full scope requires completed, matching pilot validation. No predictions. |
| `eval-validate` | Matching smoke, unsealed study, pilot/full authorized cells; at most one cell's configured batch (400 rows in this study). |
| `eval-seal` | Full scope and all eight complete validation selections with matching hashes. No model client. |
| `eval-test` | Full scope, exact cloud seal and frozen selections; at most one cell's configured batch. |
| `eval-report` | Existing report reconstruction and comparison; no model client and no selection changes. |

Validation/test allow at most three total attempts per prediction, retrying only
the unchanged verified-429 policy. With 400 rows this is at most 1,200 SDK
prediction calls, often fewer for short or already-cached batches. SDK retries
are disabled. Timeouts, connection errors, 500s and scoring failures stop and
retain uncertainty. Missing class probabilities have no fallback.

Storage request/session envelopes come directly from the unchanged
`control_requests` estimator and are immutable in each review. Every command
reserves one session and its complete envelope, not merely its observed usage.
The installed cumulative Storage allowance must still fit. No budget cap or
reservation is reset or reduced.

## Authentication and authority

Management and Storage tokens are acquired before the lease; preflight and
prediction stages also acquire one model token. Thus there are at most two or
three CLI token acquisitions respectively, each with a 60-second timeout.
Prepared tokens must initially have more than 300 seconds remaining and are
never refreshed under the lease. Model-token expiry is checked before each
dispatch; expiring credentials stop the command even if a batch is incomplete.

Each job verifies the Storage account. Preflight additionally performs the
unchanged model-account, deployment and data-plane model-list checks, plus the
core's Storage-account check: two Storage-account metadata reads, two model ARM
reads and one SDK model-list request in total. These are metadata checks, not
prediction calls, and are separate from Storage transaction counters.

Under the lease, create a one-use, stage/label-bound cloud grant before invoking
the selected function. Pending outcomes, a breach, insufficient current credit
or an already-consumed label block the job. The current review's credit balance
also constrains the original ledger during full allocation expansion; an older
approval's larger balance cannot override it.

The ledger allows only the reviewed split and authorized cells, one batch per
command, and the original three-attempt ceiling. Only preflight may change model
allocation; only seal may create a seal. Training, smoke/recovery, cross-split
inference and other-stage scientific artifacts are prohibited.

## Outputs and failures

Evidence lives in `jobs/eval-<stage>-<label>/`: submission/worker markers,
`evaluation.started`, sanitized pre-scoring `responses/`, optional
`failure-diagnostic.json` and `failure.json`, and `result.json` after confirmed
completion. Standard validation, seal, test and report outputs are produced by
the unchanged functions. The result always states `authorizes_next_job: false`.

Do not delete markers, reuse a consumed label, or resubmit automatically.
A lost grant response stops before any inference. A later provider, lease,
Storage or local-write failure may leave partial or committed progress.
Review the evidence first. A pending unknown outcome must be resolved separately;
it cannot be bypassed with another label. A separately approved later job can
reuse matching successful operation/batch caches without resampling.

Smoke completion is not pilot performance success; pilot completion is not
full-study approval; sealing is required before final testing; complete execution
does not imply the metric gates passed. Original UNKNOWN attempts and all their
financial reservations remain retained.

## Offline validation

```bash
python -m unittest discover -s Tasks/run-openai-sufficiency-evaluation/tests -q
python -m unittest discover -s Tasks/evaluate-openai-story-sufficiency/tests -q
```

Tests use fake SDK/conditional Storage clients and a synthetic pilot/full
validation-seal-test-report lifecycle. They make no Azure or model calls and do
not constitute live-service validation.
