# Audited recovery of sealed Azure prompt inference

This task continues a **sealed, full-scope, prompt-only** study after an HTTP 500
left an inference attempt dispatched without a completion receipt. It is an
explicit **execution-policy amendment**, not a claim that the original request
failed before acceptance, was free, or can be executed exactly once.

The original `train-openai-instability-within-project` directory is unchanged.
Its study/source/package fingerprints, prepared data, validation thresholds,
selection seal, completed predictions, and run identity remain authoritative.
No training, uploads, new deployments, prompt changes, or validation changes are
supported here.

## Files and behavior

- `recovery.py`: versioned authority transition, immutable approval and unknown
  attempt records, conditional retry grants, captured-attempt receipts, and the
  narrowly scoped provider adapter.
- `run_recovery.py`: explicit inspection, local approval, activation, one test
  batch, or reporting. Imports the original scientific implementation read-only.
- `tests/test_recovery.py`: offline transactional/fault and full-study fixtures.
- `tests/check_backend_sdk.py`: actual pinned OpenAI SDK using memory-only HTTP.

Only HTTP **500**, verified from the actual SDK exception, is newly retryable.
Timeouts, other 5xx errors, malformed scores, refusals, authorization failures,
and uncertain Storage commits still stop. Existing verified 429 handling is
unchanged. There are at most **three total dispatched attempts per row**, counting
the original uncertain attempt and any 429 attempts. SDK retries remain disabled.
Backoff is bounded. An exhausted row stays unresolved; it is never dropped.

Unknown attempts and their complete operation reservations are retained.
No reservations, used bounds, attempt counters, global caps, or the original
training quarantine are reset or refunded. Each retry grant is committed with
the operation/root transition under the existing lease, epoch, and ETag checks.
The original unknown attempt is not relabeled as rejected or succeeded.

Activation changes the root to `azure-table-control-inference-recovery-v1`.
Old runners reject that schema, and the new runner requires the exact immutable
review and recovery implementation fingerprint. **All old workers must already
be stopped.** Schema fencing cannot cancel a provider request or prevent an
already-running old client from attempting a late receipt write.

A matching receipt observed before replacement is recovered without inference.
New receipts use the captured attempt identity, not the operation's mutable
latest attempt number. A late older receipt cannot finish a newer attempt.
There remains an unavoidable cross-service race: a result can arrive after a
replacement is approved. The consent explicitly accepts possible duplicate
execution/charges; it never promises exactly-once behavior or selects the better
score from multiple attempts.

## Deployment and offline checks

Use the existing pinned `master-openai` environment. Do not install new model
dependencies, modify the frozen task, overwrite `study.json`, or edit the seal.
Deploy **only this new task directory** from the reviewed source revision.
Do not blindly pull unrelated changes into an active study checkout.

From the repository root, these checks make no Azure calls:

```bash
"$HOME/.conda/envs/master-openai/bin/python" -m unittest discover \
  -s Tasks/recover-openai-instability-inference/tests -q
"$HOME/.conda/envs/master-openai/bin/python" \
  Tasks/recover-openai-instability-inference/tests/check_backend_sdk.py
```

Both must pass before recovery approval. The second explicitly requires
`openai==2.6.1` and tests real exception wrapping and unchanged successful request
parameters with an in-memory transport. It is not a live-service test.

## Explicit operational sequence

The examples use the existing study. Private review/evidence files remain outside
Git. Set the normal CLI credential environment on the cluster:

```bash
export PATH="$PATH:$HOME/.local/share/master-azure-cli/bin"
export AZURE_TOKEN_CREDENTIALS=AzureCliCredential
cd "$HOME/Master/Tasks/recover-openai-instability-inference"
```

1. Stop/verify termination of all old experiment workers. Separately approve
   **one storage-only inspection**, at most 1,000 requests and one session:

   ```bash
   "$HOME/.conda/envs/master-openai/bin/python" run_recovery.py plan \
     --storage "$HOME/master-openai" --run-id openai-prompt-01 \
     --storage-inspection-approved \
     --output "$HOME/.local/state/master-openai/recovery-template.json"
   ```

   This checks the exact pending attempt, immutable seal, existing allocation,
   receipt absence, and capacity for the **remaining** batches plus report.
   All consent fields default false. It does not activate recovery.

2. Review the template and private failure evidence, including the sanitized
   log proving HTTP 500 (the legacy JSON wrapper lost that status). Explicitly
   accept the policy amendment, unknown outcomes, possible duplicate charges,
   retained reservations, stopped workers, and passing offline SDK checks.
   Choose an expiry no later than existing model/storage approvals and retention.
   Then create an exclusive, private approved copy, **locally only**:

   ```bash
   "$HOME/.conda/envs/master-openai/bin/python" run_recovery.py approve-local \
     --storage "$HOME/master-openai" --run-id openai-prompt-01 \
     --review "$HOME/.local/state/master-openai/recovery-template.json" \
     --evidence /absolute/path/to/the/reviewed/failure.json \
     --expires-at REVIEWED_UTC_EXPIRY \
     --accept-unknown-outcome-retries \
     --output "$HOME/.local/state/master-openai/recovery-approved.json"
   ```

   This flag accepts **all** listed checks, not just spending. Do not use it
   until they are true. Source changes after inspection invalidate the review.

3. After separate approval of activation and continuation, activate once
   (at most 1,000 Storage requests, no model call):

   ```bash
   "$HOME/.conda/envs/master-openai/bin/python" run_recovery.py activate \
     --storage "$HOME/master-openai" --run-id openai-prompt-01 \
     --review "$HOME/.local/state/master-openai/recovery-approved.json" \
     --output "$HOME/.local/state/master-openai/recovery-activation.json"
   ```

   Activation preserves the pending operation and all money. It records the
   policy and initial unknown outcome; a test command consumes the retry grant.
   The result states the remaining number of test invocations. If activation's
   response is lost, inspect its durable result under the same review; never
   reset the schema or generate a new approval to work around ambiguity.

4. Submit CPU work using the existing cluster environment, **serially**. Each
   invocation processes only the next unfinished batch and uses the existing
   per-session Storage allowance (80,000 requests for the current study):

   ```bash
   "$HOME/.conda/envs/master-openai/bin/python" run_recovery.py test \
     --storage "$HOME/master-openai" --run-id openai-prompt-01 \
     --review "$HOME/.local/state/master-openai/recovery-approved.json"
   ```

   Reuse completed cells and earlier rows of the interrupted batch. Do not rerun
   validation, sealing, smoke, the old full-study job, or a full-scope preflight.
   Stop on any command failure; do not automatically resubmit failed jobs.
   Approval expiry remains authoritative regardless of scheduler walltime.

5. After the reviewed number of batches completes, run `report` with the same
   arguments. The private output is
   `openai-runs/<run-id>/recovery/llm_report.json`. A complete report and its
   performance gates are separate outcomes.

### One-command cluster launcher after activation

From the repository root, no long pasted job script is needed:

```bash
bash Tasks/recover-openai-instability-inference/cluster/submit_jobs.sh
```

Defaults match the existing `openai-prompt-01` study and `master-openai`
environment: main partition, two CPUs, 8 GB RAM, 48-hour walltime, no requeue,
and **MailType=ALL** to the existing configured university email address.
Use `--mail-user ADDRESS` to override the recipient or `--dry-run` to inspect
the generated script without querying the scheduler or submitting.

The launcher finds the private `recovery-approved*.json` file whose exact hash
matches the successful local activation record; it never chooses by date.
If multiple copies match, supply the exact `--review PATH`. `--storage` and
`--run-id` override the default study location explicitly.

It submits only the activated remaining test batches, followed by the annotated
report. Each batch still uses the approved recovery CLI and its cloud authority;
the launcher performs no new inspection, authorization, activation, or model
call on the login node.

An empty queue alone is not proof that a pasted script never ran. The launcher
also rejects an existing recovery `*.started` marker, including the previous
hand-pasted script's marker, and retains a submission journal before calling
`sbatch`. A failed or ambiguous submission is never retried automatically.
Keep all markers and journals if an error occurs.

The generated job script, submission journal, per-job progress, and SLURM logs
are stored privately under `recovery/jobs/<review-hash>/`. The worker rejects
changed launch files, source/review mismatches, and duplicate starts. It stops
at the first command failure without scheduling further batches.

Only the new `cluster/` directory and launcher tests/documentation are involved.
They are outside the already-approved recovery implementation fingerprint;
installing the launcher does not require changing or regenerating the active
recovery approval. Do not overwrite the task-root Python files or frozen study.
For an already-activated checkout, fetch the reviewed merge revision and extract
only `Tasks/recover-openai-instability-inference/cluster/` from it with
`git archive`, rather than pulling the whole repository. Then use the short
launcher command above; do not repeat inspection or activation.

## Evidence and reporting

Stage status is written under `recovery/status/`, leaving original failure/status
files intact. The approved review is stored immutably in the authority; each
unknown attempt and retry grant has a separate durable record. Model requests
and raw SDK exception bodies are never printed.

Reports use `openai-instability-prompt-recovery-report-v1`, retaining original
metrics and adding the approved execution manifest, unknown-attempt evidence,
retry grants, and an explicit incomplete-actual-cost caveat. The unchanged
scientific report is also preserved privately as `recovery/frozen-report.json`.
Do not publish that unannotated intermediate report as if no recovery occurred.

Existing summary consumers do not yet accept the new report schema. Do not
relabel it as the original schema or strip its audit evidence. Publication or
summary integration is a separate reviewed step; private approvals and
account identifiers must not enter Git or public report bundles.

If another error remains unresolved, a lease/epoch changes, receipts conflict,
the attempt limit is exhausted, or approval expires, stop and retain all
evidence. Never edit control rows manually, remove start markers to replay a
job, fabricate a completion receipt, raise caps implicitly, or delete the
original training quarantine.
