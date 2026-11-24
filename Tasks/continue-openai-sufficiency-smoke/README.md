# Lease-safe sufficiency smoke continuation

Continue only the 21 remaining smoke predictions after the reviewed resolution
of `smoke-0`. The accepted attempt-2 sample is reused from the authority without
another model call. This task does not authorize validation or final testing.
Implementation/PR approval is not permission to run a model job.

## Contents

- `continuation.py`: private offline review, pre-lease authentication, restricted
  smoke ledger/backend, and one explicitly approved continuation.
- `tests/test_continuation.py`: fake-client end-to-end smoke, exact request and
  cached-result preservation, authentication ordering, token expiry, retry limits,
  uncertain failures and consent checks.

The standard sufficiency cluster launcher exposes `continue-smoke`. The
scientific task-root Python files and all completed diagnostic/resolution task
files are unchanged, preserving their existing fingerprints. This task calls
the unchanged smoke function and inherits the unchanged System/User contract,
generation settings, scorer and verified-429 handling. It replaces construction
of the live authentication/client objects, not the scientific protocol.

## Offline review

First generate a private false-default template:

```bash
"$HOME/.conda/envs/master-openai/bin/python" \
  "$HOME/Master/Tasks/continue-openai-sufficiency-smoke/continuation.py" template \
  --root "$HOME/master-openai/openai-sufficiency-runs/openai-sufficiency-04" \
  --resolution-review "$HOME/.local/state/master-openai/sufficiency-04-resolution-approved.json" \
  --output "$HOME/.local/state/master-openai/sufficiency-04-continuation-template.json"
```

The template binds the exact prior private review, resolution/worker evidence,
source/preparation, captured resolution owner and new helper version. It
constructs no cloud clients or tokenizer. Checks default false, current credit
defaults to zero, and expiry is blank. Preserve the template; approve a separate
private copy only after reviewing current credit, Storage, stopped workers,
retained uncertainty, fixed scope and retry policy. Approval cannot outlive the
existing resolution/model/Storage approvals.

The live envelope is **21 new logical predictions, at most 63 new SDK calls,
3,640 Storage requests and one session**. Three total attempts per new prediction
is a ceiling: only the unchanged verified-429 rejection policy permits a retry.
No 500, connection failure, timeout, scoring failure or missing class probability
permits automatic replay. There is no new model allocation: each remaining
operation reserves its unchanged bound inside the existing pilot allocation.
All original UNKNOWN accounting and full financial reservations remain held.

## Separately approved execution

Only after explicit live approval:

```bash
bash "$HOME/Master/Tasks/run_cluster_task.sh" --pull evaluate-openai-story-sufficiency \
  --stage continue-smoke \
  --continuation-review "$HOME/.local/state/master-openai/sufficiency-04-continuation-approved.json" \
  --execute-approved-continuation
```

The helper initializes the existing tokenizer and checks the complete 20-row
validation control before cloud access. It then acquires management, Storage and
model tokens **before the lease**, using explicit CLI credentials and at most
three token acquisitions, each with a 60-second timeout. Storage account metadata
is verified against the existing authority. Tokens are cached; no CLI refresh
can happen under the lease. Expiring tokens stop work rather than refreshing.
Model-token lifetime is checked before each new dispatch as well as by the SDK
token callable. SDK retries remain disabled and its request timeout stays 60s.

Before session bookkeeping, the cloud state must still match the exact successful
resolution: owner, accepted result, grant, diagnostic, UNKNOWN note, receipt
fences, allocation, original attempt and renewal. Global pending must be empty
and no remaining smoke operation, completed smoke or seal may exist. Changes
stop the job instead of silently adopting new progress or refreshing approval.

The ledger prohibits dispatching `smoke-0`, any non-smoke operation, training,
validation or testing. It runs only `smoke-1` and `base-control-0` through
`base-control-19`, retaining the original rows/order, prompts, seed, model,
token limits, probabilities and metrics. The existing smoke function produces
the normal `base_control.json`, cloud smoke artifact and `smoke.json` only after
all required scores are available.

## Evidence and stopping rules

`jobs/continue-smoke/` contains the fixed submission/worker markers,
`continuation.started`, per-attempt sanitized `responses/` summaries saved before
scoring, `failure-diagnostic.json` for non-retryable backend failures,
`failure.json` for a failed helper invocation, and `continuation.json` after
successful completion. No raw stories, tokens, arbitrary provider bodies or
credential values are written to the diagnostic summaries.

The old failed `status/smoke.json` and prior failure evidence are deliberately not
rewritten. Use the new job status and authoritative smoke artifact to distinguish
this separately reviewed continuation. A successful summary states
`smoke_complete: true` and `authorizes_validation: false`.

There are no job labels, automatic resubmissions or stage chaining. Preserve all
markers and partial outputs after failure; do not run the old smoke command or
repeat this job. A provider/storage/lease/local-write failure can leave a pending
outcome or committed progress even when the worker reports failure. Review saved
evidence before any further cloud action. This task does not resolve a new
uncertain attempt or explain the original failure.

## Offline checks

```bash
python -m unittest discover -s Tasks/continue-openai-sufficiency-smoke/tests -q
python -m unittest discover -s Tasks/resolve-openai-sufficiency-smoke/tests -q
python -m unittest discover -s Tasks/recover-openai-sufficiency-smoke/tests -q
python -m unittest discover -s Tasks/evaluate-openai-story-sufficiency/tests -q
```

Tests use fake conditional Storage and SDK clients, not Azure or model calls.
No dependencies are added. These checks are not live-service validation.
