# Sufficiency smoke diagnostics and bounded failure inspection

The offline diagnostic investigates the *validation code*, not the historical
Azure response. A separately gated Storage inspection can check whether an
exact completion receipt exists. Neither tool can retry inference, reconcile,
release financial reservations, or grant recovery permission. The prepared
sufficiency study and historical task implementations remain unchanged.

## Contents

- `diagnostics.py`: exact local failure/request audit and fake-client probe of
  the existing sufficiency backend, with safe response summaries.
- `tests/test_diagnostics.py`: synthetic response, argument parity, privacy,
  failure-identity, non-overwrite, and scoring-contract checks.
- `inspect_failure.py`: explicit 100-request Storage-only snapshot and
  false-default review template, not a recovery executor.
- `tests/test_inspection.py`: offline Storage fault-injection tests.

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
The failed operation remains unresolved. An instrumented attempt and resolution
need additional implementation and separate approval.
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

This submits one CPU job in the existing environment. It verifies the Storage
account through its management API, then acquires the coordinator lease and
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

Submission binds source, helper, local failure, prepared study and approval
provenance; changes before worker dispatch stop the job. The inspector also
creates a fixed `inspection.started` marker before constructing the Storage
client. Lost responses, failures, duplicate submission, and worker reentry do
not cause automatic retries. Do not remove markers or rerun under another label.
This stage accepts no model-stage flag or job label and never constructs a
model client.

Evidence is saved in run04's `jobs/inspect-failure/`: submission and SLURM logs,
`worker-status.json`, `inspection.started`, and `inspection.json`.
The inspection report includes only numeric accounting, status flags, and hashes,
plus a private `review_template` with empty expiry, false checks, and
`execution_approved: false`. It binds the operation/attempt/allocation/receipt,
authority, original failure, preparation, approvals, and helper versions.
Do not post the entire private template; use the numeric/status summary.

`receipt_present: true` means a request-matching receipt was found, **not**
that its response has been validated or the operation completed. Review it
before any reconciliation; never fabricate the original response.
`receipt_present: false` leaves the attempt UNKNOWN. Neither outcome grants
another prediction, a retry, or permission to clear pending state. There is no
live recovery implementation in this task.

## Offline validation

```bash
python -m unittest discover -s Tasks/recover-openai-sufficiency-smoke/tests -q
```

Tests substitute transport and guard failures, synthetic responses, and an
in-memory Storage implementation. Tests and `diagnostics.py` construct no cloud
clients. Only the explicitly approved `inspect_failure.py` path constructs a
Storage client.
