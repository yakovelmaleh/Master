# Reviewed sufficiency smoke diagnostic resolution

This separate task can accept the exact saved attempt-2 diagnostic for `smoke-0`.
It does not recover the missing original response, request another prediction,
complete smoke, or authorize continued evaluation. Code/PR approval is not live
resolution approval.

## Contents

- `resolution.py`: offline false-default review and separately approved,
  bounded Storage-only resolution.
- `tests/test_resolution.py`: real ledger transitions against fake Storage,
  conservative accounting, late-receipt races, lost writes and stale ownership.

The existing `evaluate-openai-story-sufficiency/cluster/submit_jobs.py` provides
the standard `resolve-smoke` CPU job. Scientific task-root files, the historical
recovery task and **all one-shot diagnostic files remain unchanged**. Putting this
helper in its own task preserves the completed diagnostic's implementation hash.

## Eligibility and review

Only the original one-shot review and its exact successful diagnostic qualify.
The helper validates local status, response summary, diagnostic copies, captured
run/request/attempt/epoch, the existing approvals, and preparation/source hashes.
The recorded score must be finite, within `[0,1]`, and accompanied by valid
one-token usage, both class log probabilities and the expected model identity.
It copies that exact previously scored result; it neither re-scores nor selects
another sample. `length` is accepted with the completed single binary token,
as in the unchanged scorer.

Generate the template offline using absolute paths:

```bash
"$HOME/.conda/envs/master-openai/bin/python" \
  "$HOME/Master/Tasks/resolve-openai-sufficiency-smoke/resolution.py" template \
  --root "$HOME/master-openai/openai-sufficiency-runs/openai-sufficiency-04" \
  --diagnostic-review "$HOME/.local/state/master-openai/sufficiency-04-one-shot-approved.json" \
  --output "$HOME/.local/state/master-openai/sufficiency-04-resolution-template.json"
```

The private output must remain outside the run and Git. Existing outputs are
never overwritten. Checks default false, credit defaults to zero, and expiry
is blank. A separately approved copy must confirm workers are stopped, acceptance
of this fixed sample without score-based selection, retained uncertainty and
reservations, conservative accounting, receipt fences, current credit/Storage
conditions, and **no further inference permission**. It cannot outlive the
one-shot review or its underlying approvals. No cloud client is constructed
by template generation or local review validation.

## Accounting and atomic resolution

Under the lease, verify the same pilot allocation, original attempt, renewal,
UNKNOWN note, grant, exact cloud diagnostic and attempt-2 operation. The authority
must still have the diagnostic's captured owner before the new session begins.
Any intervening ownership, pending, financial, quarantine or conflicting-receipt
change stops resolution instead of automatically refreshing the review.

The operation's existing bound covers three attempts. Record:

- Known token-usage cost at the already reviewed rates for attempt 2.
- An UNKNOWN-attempt allowance of one third of the original three-attempt bound.
  This retains the original safety margin; it is not an observed charge.
- Their sum as the accounted bound, with `actual_complete: false`.

The **entire original reservation remains held**, including the unused attempt
allowance. Neither run allocation nor global model/Storage reservations shrink.
This is conservative ledger accounting, not an Azure invoice reconciliation.

A single conditional transaction records resolution, updates the exact operation
and attempt 2 to succeeded, and clears only this operation's pending pointer.
It leaves attempt 1, its UNKNOWN note, diagnostic, grant, training quarantine and
financial reservations unchanged. The result retains a hashed request ID; no
missing raw provider identifier is fabricated.

The same transaction creates non-consumable fences at both legacy receipt keys.
Create-only conditions ensure a late receipt arriving after the final reads
causes the entire resolution transaction to fail. A later legacy receipt writer
also cannot overwrite a fence. These are explicitly **not provider completion
receipts**: their request-match field is null, so the old reconciler rejects them.
Existing receipts are never overwritten or silently adopted.

If known cost plus the UNKNOWN bound exceeds the reservation, persist the cost
and unreserved excess, latch the global breach, and **retain pending** rather than
accepting the result. No financial reservation is reduced or new spend authorized.
The helper reports failure and preserves a bounded resolution record for review.

## Separately approved execution

Only after reviewing the private template and explicitly approving one
Storage-only resolution:

```bash
bash "$HOME/Master/Tasks/run_cluster_task.sh" --pull evaluate-openai-story-sufficiency \
  --stage resolve-smoke \
  --resolution-review "$HOME/.local/state/master-openai/sufficiency-04-resolution-approved.json" \
  --execute-approved-resolution
```

One job allows at most **100 Storage requests / one session**, Storage-account
metadata verification, and two pre-lease CLI token acquisitions (management and
Storage), each with a 60-second timeout. Credentials are cached and cannot refresh
under the lease. It constructs no model client and makes **zero model calls**.
No dependency or model deployment changes are needed.

The launcher pins review, diagnostic evidence and helper hashes. It rejects
diagnostic/model/inspection flags as substitutes for resolution consent, allows
no job labels, and never chains another stage. Evidence is saved under
`jobs/resolve-smoke/`: submission/worker markers, `resolution.started`,
`worker-status.json`, and `resolution.json` after a confirmed transaction.

Do not remove markers or resubmit after failure. A lost transaction response
may mean resolution committed even if the job failed; a failed local write or
lease release likewise does not undo a committed transaction. Preserve evidence
and obtain a separately scoped inspection rather than replaying the mutation.

Successful resolution accepts only `smoke-0`. A future separately approved smoke
job can reuse its cached result without making that prediction again. This task
does not run the remaining 21 predictions, change the failed smoke status/files,
mark smoke complete, or authorize validation/test. No claim is made about the
original failure's cause or full smoke capability.

## Offline checks

```bash
python -m unittest discover -s Tasks/resolve-openai-sufficiency-smoke/tests -q
python -m unittest discover -s Tasks/recover-openai-sufficiency-smoke/tests -q
python -m unittest discover -s Tasks/evaluate-openai-story-sufficiency/tests -q
```

Tests inject fake clients and conditional Storage transactions. They do not make
Azure or model calls and do not constitute live-service validation.
