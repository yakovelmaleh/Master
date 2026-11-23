# Offline sufficiency smoke diagnostics

This task investigates the *validation code*, not the historical Azure response.
It makes no network calls, constructs no Azure/OpenAI client, and cannot retry,
reconcile, release reservations, or authorize a cloud operation. It leaves the
prepared sufficiency study and all historical task implementations unchanged.

## Contents

- `diagnostics.py`: exact local failure/request audit and fake-client probe of
  the existing sufficiency backend, with safe response summaries.
- `tests/test_diagnostics.py`: synthetic response, argument parity, privacy,
  failure-identity, non-overwrite, and scoring-contract checks.

## Use

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

This tooling does **not** install live diagnostic hooks or change the runner.
The failed operation remains unresolved. Storage inspection, an instrumented
attempt, and resolution need additional implementation and separate approval.
Do not use the historical sealed HTTP-500 recovery for an unsealed smoke failure.
Do not change prompts/scoring, remove rows, or retry until a valid sample appears.

## Offline validation

```bash
python -m unittest discover -s Tasks/recover-openai-sufficiency-smoke/tests -q
```

Tests substitute transport and guard failures and synthetic responses. Neither
tests nor the CLI instantiate the real cloud clients.
