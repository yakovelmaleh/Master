# Numeric sufficiency logprob diagnostics

Record the actual SDK-parsed log probabilities for binary tokens before the
unchanged scorer sees a response. This is diagnostic instrumentation, **not a
scoring fix, recovery grant or live execution path**.

The failed pilot response's existing summary records an invalid value but not
the number itself. This task cannot recover that missing value or establish
whether it was positive, NaN or infinite. Synthetic examples are explicitly
marked as simulations, never as evidence of the historical cause.

## Contents

- `numeric_diagnostics.py`: bounded numeric extraction, a pre-scoring capture
  function, exclusive private JSON writes and a synthetic-only CLI.
- `tests/test_numeric_diagnostics.py`: exact float representation, malformed
  values, privacy, capture limits, persistence failures and unchanged real-backend
  scoring/request behavior using fake responses.

No dependencies, existing runners, launchers, scorers or approved helper files
are changed. Existing job/review fingerprints and failed-job evidence remain
intact. The current evaluation runner does **not** automatically use this task.

## What is captured

For the generated binary token and every binary-token entry among the requested
20 top log probabilities, retain:

- The exact `0`/`1` label, generated/top origin and top-list index.
- Numeric type and category: positive, negative, zero, NaN or either infinity.
- The Python numeric representation as a string, plus hexadecimal representation
  for floats. Finite float values round-trip without loss, including signed zero
  and tiny positive values. NaN/infinities never become invalid JSON literals.

This preserves the **SDK-parsed numeric value**, not the original wire encoding
or precision that was already lost during parsing. Duplicate entries are kept
in order so conflicting values can be inspected. No clipping, rounding,
normalization, substitution or choice of a more favorable entry occurs.

The record also includes bounded usage counts, binary output label, finish
reason, refusal flag, model-match flag and structural counts. It excludes
prompts, story text, arbitrary generated/refusal text, other token strings,
token bytes, request IDs, model/deployment names and provider error bodies.
Unexpected nonnumeric values are identified by an allowlisted type category;
their contents and object representations are never copied.

At most 21 entries are captured: one generated token and 20 alternatives.
Oversized integer values (over 1,024 bits) or oversized alternative lists produce
bounded evidence and stop before scoring. `capture_complete` means capture was
not limited this way; it does **not** mean both classes were present or valid.
Missing or malformed values remain missing or malformed for the frozen scorer.

## Offline command

Run a built-in **synthetic** tiny-positive case in a new private directory:

```bash
"$HOME/.conda/envs/master-openai/bin/python" "$HOME/Master/Tasks/diagnose-openai-sufficiency-logprobs/numeric_diagnostics.py" --case tiny-positive --output "$HOME/.local/state/master-openai/numeric-logprobs-positive-simulation-01"
```

Other cases: `valid`, `nan`, `positive-infinity`, `negative-infinity`,
`conflicting`, `missing-class` and `non-numeric`. Use a new directory per case;
existing outputs are never overwritten.

This command constructs no SDK client, acquires no token, reads no experiment
run or private approval and makes no network requests. There is deliberately no
live flag, raw-response import, job submission or operation-replay command.

The output directory is private (0700), and JSON files are private (0600):

- `response.json`: numeric evidence, implementation/scorer hashes and explicit
  simulation/no-execution/no-historical-recovery flags, saved before scoring.
- `result.json`: whether the unchanged scorer accepted the synthetic response
  and its allowlisted failure reason. No raw exception or provider IDs.

The `tiny-positive` case is rejected with `invalid_logprob`. That demonstrates
the current scorer's behavior, **not** that the failed pilot had a tiny-positive
value. `finish_reason: length` is valid for a complete one-token binary output.
The CLI exercises the scorer; it does not certify live endpoint/model access.

## Capture contract and future integration

`capture_response(response, expected_model, record)` accepts an already-obtained
response and a persistence callback. It records numeric evidence synchronously,
then returns the **same unmodified response object** for the caller's existing
scorer. Failed persistence or capture limits raise `CaptureError` before that
scorer can run. The function neither obtains a response nor retries anything.

A future, separately reviewed live adapter would call this at the SDK-response
boundary before returning to the frozen backend. It must bind the evidence to
the exact reviewed request and captured operation/attempt identity, bind this
helper's implementation hash, and retain the existing authentication, lease,
request, budget, expiry and pending-state gates. The synthetic CLI's simulation
envelope must never be used for a real response.

That adapter, cloud-state inspection, any new diagnostic sample and any
resolution/continuation are **not implemented or authorized here**. A new model
call would produce a new sample, not restore the failed response. Do not retry
for a valid score, drop the row, release reservations, clear pending state or
edit the completed evaluation helper to inject this capture.

## Offline validation

```bash
python -m unittest discover -s Tasks/diagnose-openai-sufficiency-logprobs/tests -q
```

The tests pass synthetic responses through the actual frozen sufficiency backend
with a fake client. Request arguments, returned scores, exceptions and call counts
remain unchanged; evidence is captured before scoring. Persistence failures stop
scoring, and the CLI works with SDK modules unavailable and networking blocked.
