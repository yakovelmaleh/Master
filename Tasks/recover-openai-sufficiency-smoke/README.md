# Sufficiency smoke diagnostics, inspection, and one-shot review

The offline diagnostic investigates the *validation code*, not the historical
Azure response. A separately gated Storage inspection can check whether an
exact completion receipt exists. Neither grants recovery permission. A separate
one-shot execution-policy amendment can permit exactly one diagnostic attempt
after an absent-receipt inspection. No tool completes smoke, reconciles, releases
financial reservations, or authorizes continued evaluation. The prepared study
and historical task implementations remain unchanged.

## Contents

- `diagnostics.py`: exact local failure/request audit and fake-client probe of
  the existing sufficiency backend, with safe response summaries.
- `tests/test_diagnostics.py`: synthetic response, argument parity, privacy,
  failure-identity, non-overwrite, and scoring-contract checks.
- `inspect_failure.py`: explicit 100-request Storage-only snapshot and
  false-default review template, not a recovery executor.
- `inspection_auth.py`: bounded CLI token acquisition before the lease, with
  cache-only credential use during inspection.
- `tests/test_inspection.py`: offline Storage fault-injection tests.
- `tests/test_inspection_auth.py`: credential lifetime, no-refresh, and timeout tests.
- `one_shot.py`: offline false-default review template and separately gated,
  single diagnostic attempt 2, never a full smoke rerun.
- `tests/test_one_shot.py`: exact request, conditional grant, uncertainty
  preservation, stale-worker and lost-response tests.

## Offline diagnostic

Use the existing `master-openai` environment. No installation or new preparation
is needed. This is a local offline diagnostic, not a model job:

```bash
cd "$HOME/Master"
"$HOME/.conda/envs/master-openai/bin/python" \
  Tasks/recover-openai-sufficiency-smoke/diagnostics.py \
  --root "$HOME/master-openai/openai-sufficiency-runs/openai-sufficiency-04" \
  --failure "$HOME/master-openai/openai-sufficiency-runs/openai-sufficiency-04/failures/<saved-failure-file>.json" \
  --output "$HOME/.local/state/master-openai/sufficiency-04-offline-diagnostic"
```

Select the exact failure path recorded in `status/smoke.json`. The command checks
its checksum, study/run identity, original authorization/prepared-manifest
binding, smoke operation/attempt, and reconstructed request hash. It exercises
the real backend with a no-op guard and fake transport. A successful boundary
check does **not** establish whether the historical request reached Azure.
Historical approvals need not be unexpired to inspect them offline; they are
never treated as permission to spend.

An optional `--response-fixture /private/synthetic-response.json` exercises the
unchanged response scorer with synthetic Chat Completions-shaped JSON. It uses
`choices`, `message.content/refusal`, `finish_reason`, `logprobs.content` with
token/top-logprobs, `usage`, `model`, and `id`; see the test fixture. It does not
load the original missing response. Never present fixture results as recovered
predictions or as proof of the historical cause.

## Outputs and limits

The command exclusively creates a new private output directory outside the run:

- `request.json`: hash of fake SDK request arguments, not prompts or identifiers.
- `response.json`: optional bounded summary, persisted before fixture scoring.
- `result.json`: phase and allowlisted reason, never arbitrary exception text.

Each file is marked `simulation: true`, `cloud_access: false`,
`authorizes_execution: false`, and `historical_outcome: UNKNOWN`, and binds the
exact failure/request/study/attempt and diagnostic implementation hashes.
No scores, arbitrary model output, refusal text, account details, or credentials
are exported. Unexpected failures use `unclassified_error`; this is not evidence
of a provider rejection. Persistence failure stops the diagnostic; keep partial
output rather than overwriting it.

This tooling does **not** install live model diagnostic hooks or change the runner.
The failed operation remains unresolved. An instrumented attempt requires the
separate one-shot review below. Resolution still needs additional implementation
and separate approval.
Do not use the historical sealed HTTP-500 recovery for an unsealed smoke failure.
Do not change prompts/scoring, remove rows, or retry until a valid sample appears.

## Separately approved Storage inspection

Only after explicit approval for **one inspection, at most 100 Storage requests
and one session**, use the standard launcher:

```bash
bash Tasks/run_cluster_task.sh --pull evaluate-openai-story-sufficiency \
  --stage inspect-failure \
  --failure "$HOME/master-openai/openai-sufficiency-runs/openai-sufficiency-04/failures/<saved-failure-file>.json" \
  --execute-approved-inspection
```

This submits one CPU job in the existing environment. Before any lease or
Storage request, it obtains management and Storage tokens using explicit
`AzureCliCredential(process_timeout=60)`, once per scope with no retry loop.
Tokens stay in memory and must have more than five minutes remaining.
During inspection, the shared credential serves only these cached tokens;
an unexpected scope/challenge or token within two minutes of expiry stops
the job without invoking the CLI again. This avoids extending authentication
waits inside the coordinator's lease-safe window.

It verifies the Storage account through its management API, then acquires the coordinator lease and
reserves exactly 100 Storage requests/one session using the existing ledger.
Thus this is **not read-only**: normal session/request counters and ownership
change. Financial reservations, pending state, attempt/operation records,
training quarantine, and historical recovery records do not change.
It neither bootstraps storage nor repeats the old renewal-recovery accounting.

The inspection checks the exact failed `smoke-0` attempt 1, pilot allocation,
installed renewal receipt, and completion receipt presence. It rechecks entity
versions, including the receipt independently of the root, under the lease.
A mismatched pending operation, conflicting receipt, expired approval, missing
capacity, lost lease, or changing snapshot stops the job without reconciliation.
The transport limit cannot exceed 100 even if a larger allowance is assigned.

Submission binds source, inspector/authentication helpers, local failure, prepared study and approval
provenance; changes before worker dispatch stop the job. The inspector also
creates a fixed `inspection.started` marker before constructing the Storage
client. Lost responses, failures, duplicate submission, and worker reentry do
not cause automatic retries. This stage accepts no model-stage flag and never
constructs a model client.

After a failed inspection, preserve the original directory and markers.
Only after diagnosing the failure and obtaining **fresh inspection consent**,
use `--job-label auth-02` (or another separately reviewed unique label) to save
a new attempt in `jobs/inspect-failure-auth-02/`. A label is not retry permission,
does not reset request/session counters, and does not change model attempt IDs.
Reusing a label is blocked. Never remove old evidence to submit again.

Evidence is saved in run04's `jobs/inspect-failure/`: submission and SLURM logs,
`worker-status.json`, `inspection.started`, and `inspection.json`.
`authentication.json` records authentication success/failure, elapsed time,
scope count and an allowlisted failure reason (`cli_timeout` or
`authentication_failed`), not tokens or provider messages. An authentication
failure stops before account verification, lease acquisition or ledger mutation.
Partial or missing output must not trigger an automatic rerun.
The inspection report includes only numeric accounting, status flags, and hashes,
plus a private `review_template` with empty expiry, false checks, and
`execution_approved: false`. It binds the operation/attempt/allocation/receipt,
authority, original failure, preparation, approvals, and helper versions.
Do not post the entire private template; use the numeric/status summary.

`receipt_present: true` means a request-matching receipt was found, **not**
that its response has been validated or the operation completed. Review it
before any reconciliation; never fabricate the original response.
`receipt_present: false` leaves the attempt UNKNOWN. Neither outcome grants
another prediction, a retry, or permission to clear pending state.

## Separate one-shot diagnostic review

This is an **execution-policy amendment**, not permission inherited from model
preflight, smoke, or inspection approval. Attempt 1 remains UNKNOWN and possibly
charged. Attempt 2 is a new sample and cannot establish the historical cause.
Both attempts' full original operation reservation remains held.

First generate the private false-default template offline:

```bash
"$HOME/.conda/envs/master-openai/bin/python" \
  Tasks/recover-openai-sufficiency-smoke/one_shot.py template \
  --root "$HOME/master-openai/openai-sufficiency-runs/openai-sufficiency-04" \
  --failure "$HOME/master-openai/openai-sufficiency-runs/openai-sufficiency-04/failures/<saved-failure-file>.json" \
  --inspection "$HOME/master-openai/openai-sufficiency-runs/openai-sufficiency-04/jobs/inspect-failure-auth-02/inspection.json" \
  --output "$HOME/.local/state/master-openai/sufficiency-04-one-shot-template.json"
```

Review the exact request, original failure, inspection, current credit/storage,
unchanged model/preparation, and diagnostic implementation hashes. Explicitly
confirm old workers are stopped, accept possible duplicate charging, and approve
**one new SDK prediction only**. All checks default false, current credit defaults
to zero, and expiry is blank. The approved copy cannot outlive existing model,
Storage, or retention approvals.

Only after that separate review and explicit execution consent:

```bash
bash Tasks/run_cluster_task.sh --pull evaluate-openai-story-sufficiency \
  --stage diagnose-smoke --review /absolute/private/approved-one-shot-review.json \
  --execute-approved-diagnostic
```

One CPU job performs at most three CLI token acquisitions (management, Storage,
model), each with a 60-second timeout, before the lease; no token refresh happens
under the lease. It verifies Storage account metadata and reserves at most
**100 Storage requests / one session**. It creates no new model allocation.

Under the lease, the exact inspection snapshot and entity versions must still
match. An atomic conditional transaction records the one-use grant, retains an
UNKNOWN note and the original attempt record, and increments the operation to
attempt 2. Pending stays on the same operation throughout; there is no reopened
`prepared` window. Conflicts or lost commit responses stop before the SDK call.
A late receipt detected before transport also stops the call.

The existing backend receives the same model, prompts, seed, generation settings
and scoring rules. The SDK has retries disabled. There is no loop for 429, 500,
timeout, malformed output, or missing class probabilities, and no attempt 3.
No rows, probability fallback, prompt adjustments, or score-based resampling
are introduced.

The helper saves a safe response summary before the unchanged scorer runs.
A valid diagnostic score and numeric usage, or a failure phase/reason, are
stored separately under `sufficiency-smoke-diagnostic`, never under the normal
completion-receipt namespace. The original UNKNOWN note and full reservations
remain intact. Even a valid score does **not** complete the operation or smoke.
The diagnostic does not settle billing: known usage plus the retained unknown
attempt bound must be reviewed before any future resolution.

Evidence lives in `jobs/diagnose-smoke/`: submission/worker markers,
`diagnostic.started`, optional `response-summary.json`, `local-diagnostic.json`,
and `diagnostic.json`. Local evidence alone does not prove a cloud write committed.
The final worker status means the diagnostic was recorded, not that smoke
succeeded. Provider receipt of a request cannot be inferred merely from the
recorded SDK call count.

Only one diagnostic directory/attempt is supported: no job labels or automatic
reentry. Do not remove markers or rerun after failure. The command always stops
after this diagnostic; it does not run the remaining 21 smoke predictions,
validation, final tests, or reconciliation. A separately reviewed resolution
implementation would be required to consume a new diagnostic result safely.

## Offline validation

```bash
python -m unittest discover -s Tasks/recover-openai-sufficiency-smoke/tests -q
```

Tests substitute transport and guard failures, synthetic responses, and an
in-memory Storage implementation. Tests and `diagnostics.py` construct no cloud clients. Only explicitly approved
inspection/one-shot execution paths construct real clients; template generation
is offline.
