# Azure OpenAI within-project instability experiment

**Objective: maximize trapezoidal AUC-PRC on the unchanged historical test rows,
using validation for decisions, not test results.** Two explicitly separate
protocols are available: legacy supervised fine-tuning (`experiment.json`) and
zero-shot **System + User prompting without LLM training** (`prompt_only.json`).
The cluster orchestrates Azure using CPU jobs; no OpenAI weights run on cluster GPUs.

## Prompt-only workflow

Select `--config Tasks/train-openai-instability-within-project/prompt_only.json`
and a **new run ID** for every prompt-only command. The default configuration
remains the legacy SFT protocol for compatibility; do not use its training commands
for this experiment. Changing source/configuration invalidates old study signatures,
not old costs. Keep the existing authority, old runs, reservations and failure evidence.

The prompt-only protocol pins the existing GPT-4.1-mini snapshot and its
`GlobalStandard` deployment. It sends exactly the frozen system instruction and
one user message containing original issue text, the instability threshold, and
optional train-fitted structured features. There are no assistant examples,
training uploads, fine-tuning jobs, deployment creation, or model deletion.
Structured preprocessing is fitted only on historical training rows; it does not
train the LLM. All Jira/Qt rows, chronological splits, labels at 5/20, and both
variants are retained (eight evaluation entries using one existing base model).
The existing frozen input-token truncation policy is unchanged.

Scores are normalized probabilities from the two class-token log probabilities,
not generated confidence or hard labels. Each cell's threshold is selected using
all validation rows. All eight selections must be sealed before any test scoring.
Final metrics, matched historical baseline comparison and paired bootstrap remain
unchanged. Prompt-only reports use `openai-instability-prompt-report-v1` and real
base-model/deployment references, never fabricated fine-tuning job IDs.

### Offline preparation first

After merging, run the existing `check-sdk` stage. Then prepare a new run:

```bash
./Tasks/run_cluster_task.sh train-openai-instability-within-project \
  --stage prepare --partition main --conda-env master-openai \
  --storage "$HOME/master-openai" --run-id openai-prompt-01 \
  --config Tasks/train-openai-instability-within-project/prompt_only.json
```

Preparation performs no Azure calls. It writes the exact partitions and a
private `approval.template.json`. Template checks are false and rates unknown:
**do not treat preparation, a merged PR, or an old approval as execution consent.**
Prompt approval requires explicit `protocol_schema`/`method`, verified existing
deployment and logprobs, current input/output rates, data-export permission,
credit eligibility/expiry, spending protection, and storage costs. Training rates
and SFT/developer-deployment checks are not used in this mode.

Generate the offline storage worksheet for this exact prepared manifest:

```bash
python Tasks/train-openai-instability-within-project/control_admin.py cost-plan \
  --storage "$HOME/master-openai" \
  --prepared "$HOME/master-openai/openai-runs/openai-prompt-01/prepared.json" \
  --config Tasks/train-openai-instability-within-project/prompt_only.json \
  --output "$HOME/master-openai/prompt-storage-plan.json"
```

The worksheet includes batch commands, completion-marker reads and score-cache
reconstruction. Add every preflight, quarantine review/action, status/recovery and
restart separately; failed/partial commands do not refund storage allowances.
Model cost estimation excludes all training charges for the **new** study but
does not subtract any prior reservations. The cumulative $9 pilot/$80 experiment
caps and protected $20 credit still apply across all runs. A new pilot may be
unaffordable after prior reservations; stop rather than raise caps or omit rows.

### Separately approved execution

Only after reviewing finances and obtaining fresh private model and storage
approvals, use `preflight`, then `smoke`, then `validate` with the same run/config.
`validate` processes **at most one 400-row batch per invocation**, including all
rows in the final partial batch. Explicitly invoke the stage again for each next
batch; there is no scheduler loop or automatic continuation. After both Jira/20
pilot variants are complete, review results and affordability before a full-scope
preflight. Finish validation for the remaining six entries, `seal`, then run
one `test` batch per invocation. `report` accounts for all eight entries and
labels unfinished entries as missing. A successful batch status is not a
complete-study result; check `cell_complete`/`scope_complete` and the final report.

Completion markers let later commands skip completed batches without scanning
every prior row. Missing local caches can be rebuilt from matching durable
per-row operations without paid replay. An uncertain inference response stops
the workflow; `reconcile` requires its exact persisted receipt. A missing receipt
never authorizes a retry. Base assets are not owned by this study, so `cleanup`,
`cancel`, `train-submit`, and `train-status` are prohibited in prompt-only mode.

### Explicit unresolved-training quarantine

Quarantine is **not automatic**, a refund, proof of rejection/cancellation, or
authorization to run inference. Use only after stopping all old workers and
reviewing private provider evidence and the full financial exposure. It preserves
the old dispatched operation, request hash, attempt, allocation, all monetary
totals, and training pointer. The outcome remains **UNKNOWN** and further training
stays blocked. The exact pending pointer is archived atomically into immutable
quarantine evidence; only a separately approved **new base-inference allocation**
can subsequently dispatch. Root schema fencing makes old clients fail closed.
Do not downgrade the schema or reset the ledger to resume an old worker.

With separately approved storage access (these commands consume storage):

```bash
python Tasks/train-openai-instability-within-project/control_admin.py quarantine-plan \
  --storage "$HOME/master-openai" --output "$HOME/master-openai/quarantine-review.json"
```

Review the exact authority/run/operation/attempt, request/operation/allocation/state
hashes and observed reservation totals in that private template. Supply an
expiry, SHA-256 of the privately reviewed evidence, and explicitly approve all
four checks only when verified. The plan itself does not change pending training.
After separate authorization to perform the quarantine:

```bash
python Tasks/train-openai-instability-within-project/control_admin.py quarantine \
  --storage "$HOME/master-openai" --review "$HOME/master-openai/quarantine-review.json" \
  --output "$HOME/master-openai/quarantine-result.json"
```

Any changed financial/dispatch evidence fails closed. Keep those files private;
they are excluded from report bundles. No automatic quarantine removal is
implemented, even if a provider job later appears: reconcile that separately.
Existing receipt-based recovery remains available for new base inference.

If existing storage bounds cannot cover the new batch envelopes, stop for a
separate storage extension review. The `extend` admin action supports a
pilot-scope extension only for the quarantined old run with
`prompt_only_extension_approved: true`, exact prior storage hash and all existing
storage checks. It may only increase bounds, keeps the same authority and all
reservations, and must fit the unchanged pilot/global/credit caps. Full extensions
still require both completed pilot validations. Neither an expired approval nor
insufficient storage is automatically renewed or extended.

## Legacy SFT protocol

| Contract | Experiment |
| --- | --- |
| Data | Exact immutable #357 CSV, ordered-row, and label hashes from the shared HF contract |
| Partitions | Unchanged independent chronological 60/20/20 for Jira and Qt |
| Labels | 5 and 20; separate model for each repository and level |
| Variants | Original pre-sprint text; text plus serialized train-fitted `FeatureTransformer` values |
| Full scope | 4 repository/level cells x 2 variants = 8 fine-tunes; no pooled model or automatic sweep |
| Pilot | Both Jira/20 variants, all 944 training and 314 validation rows; no early test |
| Cost ceilings | $9 pilot, $80 entire experiment including pilot, $20 credit reserve |
| Default candidate | `gpt-4.1-mini-2025-04-14`, one explicit epoch; subject to actual Azure availability and approval |
| Fine-tuned serving | `DeveloperTier`, capacity 50; verify model/region quota before approval |

**No real OpenAI scores or cloud-validation claims are included.** Offline tests
use synthetic provider responses; these are not research results.

## Reduced scope and cloud-control migration

Protocol `openai-instability-v2` deliberately selects Jira and Qt at levels 5 and
20, retaining both variants and every historical row in those cells. The other
four projects and levels 10 and 15 are outside this approved study, not missing
results. The shared historical reference contract and the HF experiment are
unchanged. "Full" approval now means all eight selected models, not the former
48-model study.

After updating the checkout, use the current checked-in `experiment.json` and a
**new run ID**, for example `openai-qt-jira-cloud-01`. Do not reuse the old
`openai-mini-study-01` run or its external `openai-mini.json` configuration: the
old schema and study signature cannot authorize the revised scope. Keep their
files and the global ledger; a new run never resets reservations or costs.
The `azure-table-control-v1` control contract changes the implementation signature,
not the eight-model scientific scope. Preserve `openai-qt-jira-01` too; do not
resume it under changed code. Update the existing environment's pinned
requirements, complete separately approved cloud-control setup below, then
prepare a new run. A code change is not authorization for paid calls.

The reviewed pilot ceiling is now $9 including storage; the $80 total ceiling
and protected $20 credit reserve are unchanged. Existing $7 study manifests and
approvals cannot be reused: prepare a new run and obtain a matching private
approval after reviewing current rates and affordability. Keep the same cloud
authority and all prior reservations; do not rerun bootstrap. This change does
not increase approved storage request/session allowances, the storage reserve,
or the separate storage-only bootstrap ceiling (strictly below $7).

Fine-tuned deployments now request capacity 50 rather than 1. This changes
the requested rate-limit allocation, not the model, dataset, token budget, or
token-billed serving tier. The completed deployment must report the approved
capacity before evaluation proceeds; missing or different capacity fails closed.
Capacity is part of the signed protocol: prepare a new run rather than editing
an existing manifest or reusing its approval. This does not resize the existing
base-model deployment or authorize paid work.

## Account and cost prerequisites

This is **not a free API**. Azure credit eligibility, remaining balance/expiry,
actual token rates, model/region quota, and no-overage protection must be verified.
The approval template starts with false checks and unknown rates. Do not fill it
with assumptions. Azure budgets alone are alerts, not a spending stop. Never remove
a spending limit, upgrade to pay-as-you-go, or switch to a paid provider to proceed.

Training defaults to the documented `GlobalStandard` API training type; its
actual training rate must be used in the approval. Do not confuse this with the
evaluation deployment SKU. Developer training is not silently selected using an
unverified API identifier.

Use only a personally approved Azure OpenAI/Foundry resource and an existing base
model deployment matching the exact snapshot. Resource group/account creation is
an explicit setup action outside these scripts; no VMs, AKS, or training GPUs are
required. The runner can create **DeveloperTier fine-tuned deployments only**,
and refuses an existing deployment with another SKU or owner. Availability and
SKU support are mandatory preflight checks, not guaranteed by the default config.
Developer deployments expire and are evaluation-only; inference tokens still cost
credit. No hourly-hosted fallback is implemented.

Use `DefaultAzureCredential` with non-interactive credentials authorized for both
data-plane training/inference and scoped management deployment operations. Use the
cluster's approved secret-injection mechanism; do not put secrets into source,
approval files, command arguments, or sbatch files. Do not assume a corporate
Azure login is the private credit subscription. The runner checks that the
explicit ARM resource ID and inference endpoint describe the same account.

Budget and remote-operation correctness no longer depends on NFS SQLite or file
locks. One Azure Table partition holds the experiment-wide authority, including
all run IDs and storage roots. Conditional transactions update reservations,
request intents, ownership and the breach latch together. A finite Blob lease
coordinates workers; a Table ownership epoch fences stale commits. A Blob lease
does **not** cancel or fence an already dispatched OpenAI request.

The shared filesystem still stores hashed datasets and rebuildable result
caches. Local scheduler/study locks are convenience, not spending authorization.
There is no SQLite or local-file fallback when Azure Storage is unavailable.
Never reset, delete or redirect the cloud authority to bypass pending work.

The implementation uses:

- Manual evidence checks for the credit offer, spending limit/exception review,
  rates, quota, Developer deployment, logprob support, approved data export, and
  actual compute-node network access.
- Read-only Azure checks for resource/endpoint identity, the exact base deployment
  snapshot/readiness, and data-plane authentication.
- A separately authorized, billable smoke test for actual scoring capability.

### Azure portal setup

1. In **Subscriptions**, select the subscription that actually contains the
   credit. Under its billing/cost settings, verify the offer, remaining credit,
   expiry, covered services, and enabled spending limit. Being eligible for an
   employee benefit alone does not verify these properties. Stop if enabling
   Azure OpenAI requires removing spending protection or paying out of pocket.
2. Create a dedicated resource group, for example `rg-master-openai`, then an
   **Azure OpenAI** resource with **Standard S0** pricing. Use a unique resource
   name. Select a region where your subscription exposes the required SFT model
   and Developer deployments. Prefer Israel Central if the required capabilities
   are available; otherwise check a nearby supported region such as Italy North.
   Global processing can occur outside the resource region; this location
   preference is not a data-residency requirement. Region support does not
   guarantee subscription quota. Do not create AKS, VMs, or GPU compute.
3. Open the resource's model deployment interface. Deploy the base
   **GPT-4.1-mini, version 2025-04-14**, for example named `gpt-4.1-mini`, with a
   token-billed deployment type such as Global Standard, not provisioned capacity.
   If that exact snapshot is unavailable, stop and review the configuration rather
   than    selecting a similarly named model. Record the actual deployment name in
   `base_deployment` in the approval file. Do not run playground requests yet.
4. Grant the cluster authentication identity **Cognitive Services OpenAI
   Contributor** at this resource, or the equivalent approved resource-scoped
   training/inference/deployment permissions. Verify access rather than assuming
   that management-plane Owner/Contributor includes the needed data-plane access.
5. Keep the resource endpoint, full resource ID, base deployment name, selected
   region, verified credit details, and model-specific rates for the private
   approval file. Do not paste credentials into that file or into Git.

The runner creates the fine-tuned Developer deployments later, after training
and approval. You do not need to create eight deployments manually.

### Cloud-control setup: separate spending approval required

The checked-in `control_store.json` is deliberately **unbound**. Normal commands
never create accounts, tables, containers or a replacement budget. Setup,
preparation, migration inventory and cost worksheets can run offline; bootstrap,
probes and even cloud status reads incur storage activity and require approval.

1. Stop old workers and stop submitting old paid-stage scripts. Keep all old
   runs and `$HOME/.local/state/master-openai/ledger.sqlite3`. Inventory the
   existing storage root with the read-only command below. Any old reservation,
   operation, breach, authorization or upload/deployment intent blocks this
   zero-use migration. Nonempty/uncertain migration needs a separate review.
2. Review exact storage rates, offer coverage, capacity/transfer assumptions,
   retention and cleanup charges. Reserve storage **inside** $9/$80. This
   implementation uses one cumulative storage reserve, included in scope
   estimates but counted only once globally. Reserve enough for the approved
   workflow, probes and recovery. Full-study expansion may increase it only
   through the separate reviewed extension below.
3. Only after provisioning approval, create a dedicated GPv2 `Standard_ZRS`
   account, Hot tier, a dedicated empty Table and private Blob container.
   Prefer Israel Central if available. Require HTTPS; disable public blob and
   Shared Key access; use service-scoped Table encryption with Microsoft-managed
   keys, no HNS. A different SKU/encryption mode needs review, not a silent fallback.
4. Use `DefaultAzureCredential` and grant Storage Table Data Contributor on that
   Table, Storage Blob Data Contributor on that container, and management Reader
   on that storage account. Account/resource creation and role assignment are
   separate provisioning actions, not privileges assumed by the runner.
5. Fill the single deployment-wide `control_store.json` with the exact storage
   ARM ID, Table/container, a newly generated fixed UUID, and the existing OpenAI
   resource ID/endpoint. All nodes/checkouts must use this same binding. There
   are no per-run or environment endpoint overrides. Keep the binding private
   if its resource metadata should not be published; artifact bundling excludes it.
6. Generate the private storage approval template, review its false checks and
   worksheet, and place the reviewed file at the fixed
   `$HOME/.local/state/master-openai/cloud-approval.json`. Its authority hash
   must match the binding, and `migration_sha256` must match a fresh inventory.
   Supply verified `remaining_credit_usd`; storage and model approvals must both
   cover global reservations plus the protected $20. Never put credentials in
   either file.

Offline inventory/template commands, run from the repository:

```bash
python Tasks/train-openai-instability-within-project/control_admin.py audit \
  --storage "$HOME/master-openai" --output "$HOME/master-openai/migration-audit.json"
python Tasks/train-openai-instability-within-project/control_admin.py template \
  --storage "$HOME/master-openai" \
  --output "$HOME/.local/state/master-openai/cloud-approval.json"
```

The template is not approval. Review **all** previous storage roots and remote
resources; the inventory scans only the supplied root and the fixed legacy
control directory. Do not overwrite an existing reviewed approval with a template.
The authority binding must be finalized before creating the new study signature.

The storage worksheet requires positive verified USD rates/allowances,
`max_requests`, `session_requests` (per-command ceiling), `max_sessions`,
`session_seconds` (at most four hours), and `retention_until`. The required reserve is:

```text
margin * (max_requests * request_usd
          + bootstrap_usd + capacity_usd + transfer_usd)
```

Use at least 1.25 for `margin`. `request_usd` must cover the most expensive
recurring Table entity operation or Blob lease request, including failed calls.
`bootstrap_usd` additionally covers setup, initial Blob writes and probes;
capacity/transfer allowances must cover the reviewed maximum bytes and retention,
not merely today's small ledger. SDK storage retries are disabled. Transaction
batches are conservatively counted per entity, and query pages separately.
Do not assume free bandwidth, free storage, or a batch discount.
Set `session_seconds` below the actual SLURM wall time with startup/cleanup
headroom. The runner stops starting new calls near its own deadline; an external
job kill can still leave an unconfirmed request requiring reconciliation.

Generate an **offline request-count worksheet** before provisioning. The existing
eight-cell `openai-qt-jira-01/prepared.json` may be used for counts only; this
does not authorize or resume that old study. The example uses the new preparation:

```bash
python Tasks/train-openai-instability-within-project/control_admin.py cost-plan \
  --storage "$HOME/master-openai" \
  --prepared "$HOME/master-openai/openai-runs/openai-qt-jira-cloud-01/prepared.json" \
  --output "$HOME/master-openai/cloud-cost-plan.json"
```

Include each planned stage, status poll, probe and restart. Command envelopes are
reserved cumulatively before work and never refunded; unused headroom cannot
silently authorize extra launches. Exhaustion stops work. Storage reads needed
to reject a launch and ongoing retained bytes can still cost money: this is not
a hard Azure subscription cap. Bound manual launches and review billing/retention;
retain the subscription spending protection.
Preflight also refuses a storage allowance that cannot cover the remaining
scope's conservative command envelopes; account for already reserved pilot
sessions when planning full-study approval.

Only after explicit live-storage approval, with `live_storage_test_approved`
set in the private approval, bootstrap the already-provisioned empty resources:

```bash
python Tasks/train-openai-instability-within-project/control_admin.py bootstrap \
  --storage "$HOME/master-openai" --output "$HOME/master-openai/cloud-bootstrap.json"
```

Bootstrap re-audits legacy state and never overwrites an existing Table authority.
Take the final inventory and review its hash after the binding and new preparation
are finalized: creating a study manifest changes the migration inventory.
If interrupted, preserve the evidence; only a matching partially created
coordinator blob may be resumed. No old budget data is imported or reset.

Then run the bounded, synthetic **two-node storage probe**, also separately
cost-approved. Submit from the repository, using the actual environment Python:

```bash
sbatch --partition main --time 04:00:00 \
  Tasks/train-openai-instability-within-project/cluster/check_cloud_control.sbatch \
  "$HOME/master-openai" "$(command -v python)"
```

It tests conditional batch atomicity, lease renewal and exclusion from a distinct
compute node. Only success marks the authority ready for model preflight.
It makes no model calls and uploads no dataset. Probe records are retained for
audit. Offline fault tests additionally cover crashes and uncertain responses;
the live probe is not a proof against all service outages or regional loss.

Holder startup and contender evidence each have a three-minute wait bound.
Each coordinator confirms a lease renewal after reserving its session and before
starting work; expired or unconfirmed startup still fails closed. Each probe
process is capped at 1,000 storage requests, or the smaller approved session
allowance. The atomicity and holder sessions reserve that bounded allowance,
not a full training-sized envelope; previous reservations remain unchanged.
Keep the job wall time above the private approval's `session_seconds`; the
four-hour example assumes a shorter approved session. If a probe fails, inspect
its logs and remaining request/session allowances before retrying: reservations
are not refunded. Never rerun bootstrap or reset the existing authority.

Keep the authority until all owned cloud work is terminal and billing is
reconciled. Storage expiry/cleanup needs explicit review; do not automatically
delete it on the retention deadline or switch to a potentially stale backup.

For an interactive development login, if Azure CLI is available on both login
and compute nodes, sign in on the cluster with `az login --use-device-code` and
explicitly select the intended credit subscription. `DefaultAzureCredential`
can use that login. Tenant policies can block device-code access; respect them.
For unattended jobs use an approved workload/environment credential instead.
An Azure API key alone is insufficient for this runner's management-plane
deployment operations. Never use a username/password workaround or weaken MFA.

## Setup and preparation

After the code has been published or otherwise transferred to your cluster
checkout, run from the Master repository:

```bash
git fetch origin refs/pull/357/head
```

The Git fetch makes archived comparator objects available without changing the
working tree. The following commands are run from the Master repository. Replace
the storage path and partition with cluster-approved values:

```bash
./Tasks/run_cluster_task.sh --list
./Tasks/run_cluster_task.sh train-openai-instability-within-project \
  --stage setup --partition main --storage "$HOME/master-openai" --dry-run
```

Inspect the dry-run, then remove `--dry-run` to submit. The **CPU setup job**
creates `master-openai` with Python 3.11 only if it is absent, then installs the
pinned requirements and runs `pip check`. It does not alter the existing HF
environment or recreate a failed environment. Resolve an installation failure and
rerun setup; an existing environment with another Python version fails explicitly.
CPU jobs request start/completion/failure notifications using the
repository's existing default recipient; `--mail-user` overrides it.

After setup succeeds, validate the installed SDKs on a CPU node:

```bash
./Tasks/run_cluster_task.sh train-openai-instability-within-project \
  --stage check-sdk --partition main --time 00:30:00 \
  --conda-env master-openai --storage "$HOME/master-openai"
```

This stage checks the pinned Python/package versions, exercises the actual
Table and Blob clients with a fake credential and in-memory HTTP transport,
then runs the workflow and summary regressions. It neither reads the real
cloud binding nor makes Azure requests. Success ends with
`SDK_OFFLINE_CHECKS_PASSED`. It is distinct from the separately approved live
storage probe. Stop on failure and preserve the job log; do not proceed to
provisioning or model stages.

Run `prepare` with the same command shape:

```bash
./Tasks/run_cluster_task.sh train-openai-instability-within-project \
  --stage prepare --partition main --run-id openai-qt-jira-cloud-01 \
  --storage "$HOME/master-openai"
```

Preparation makes no model API requests and writes all data outside Git. It
verifies the two selected historical CSVs and exact ordered splits/labels, fits structured
preprocessing on training rows only, and prepares hashed JSONL/row sidecars. The
tokenizer may need its public encoding tables on first use; this is not a model
weight download.

The frozen default truncates original text to its first 2,048 tokenizer tokens.
All rows remain; truncation counts are recorded. Structured fields are never
silently truncated. An oversized complete prompt blocks preparation and requires
a reviewed configuration/new run. Current text, issue identifiers, and other
outcome labels are never added to model input. Validation/test JSONL has no
assistant labels. Test prompts remain local until final sealing.

Changing source, dependencies, model snapshot, prompt, or configuration requires
a new run ID. Use a copied configuration file and `--config` consistently when
choosing a reviewed alternative. A new run does not reset the credit ledger.

## Approval and pilot

Preparation writes:

```text
<storage>/openai-runs/<run-id>/approval.template.json
```

Copy it to a private file outside the repository, fill it only after verifying
the evidence, and supply it to preflight. `study_sha256` binds the approval to
the exact code/config/environment. Set an expiry no later than credit validity.
Use actual remaining credit, not the original offer amount. Rates are USD per
million tokens, with at least a 25% accounting margin. Reserve all other applicable
charges, currency/tax differences, and cleanup costs explicitly.

```bash
./Tasks/run_cluster_task.sh train-openai-instability-within-project \
  --stage preflight --partition main --run-id openai-qt-jira-cloud-01 \
  --storage "$HOME/master-openai" --approval "$HOME/private/openai-approval.json"
```

The `pilot` approval must fit both Jira/20 fine-tunes, both complete validation
passes, retries, two synthetic scoring probes, an unfine-tuned diagnostic on
the first 20 Jira/20 validation rows, and the storage reserve into $9. This is
included within, not added to, the $80 total ceiling. A cost worksheet is
persisted before any training request. Unknown/insufficient funding blocks
execution, not just prints a warning.

Fill `control_schema`, `authority_sha256` and `storage_reserve_usd` from the
reviewed binding/storage approval. The reserve must equal the bootstrapped
allowance. `cloud_control_verified` replaces the old filesystem check; do not
pretend the NFS diagnostic established SQLite crash durability.

Submit these stages separately, waiting for each SLURM job to finish:

| Stage | Effect |
| --- | --- |
| `smoke` | Billable base-model logprob probes and the small validation-only control |
| `train-submit` | Submit the next not-yet-trained model in the approved scope, then exit |
| `train-status` | Retrieve/reconcile Azure jobs; it does not wait for a queued job or start another one |
| `reconcile` | Recover the global pending intent from exact provider evidence or a durable receipt; never replay an unknown request |
| `validate` | Score all models in the approved scope after their training has succeeded |

Use the same master-launcher command as `prepare`, replacing `--stage`. For the
pilot, complete `train-submit` / `train-status` for each of the two models before
`validate`. If status is queued/running, check it again later; do not resubmit
training. There is no implicit SLURM resubmission, paid sweep, or polling loop
holding a CPU job throughout the provider training queue.

The approval covers API operations, not a guarantee of useful predictions.
Inspect validation AUC-PRC/AP/ROC, token counts, and provider charges before
expanding. The small unfine-tuned control is diagnostic only, not a full baseline
or a test result.

## Full study, seal, and test

After the pilot, explicitly approve scope `full` using updated verified credit
evidence and run `preflight` again. It requires both pilot validation results and
reserves the complete training/validation/test scope, including the already
reserved pilot and retry bounds. If all eight fine-tunes cannot fit, stop for a scope
decision; do not drop data, variants, or repositories.

If more storage allowance is needed, first obtain **separate full-scope storage
approval**. Review an updated private `cloud-approval.json` with `scope: "full"`,
`storage_extension_approved: true`, the exact prior `previous_storage_sha256`,
the cloud run key (`run`), and its `study_sha256`. Keep the same authority.
Increase cumulative request/capacity/transfer/reserve bounds; never subtract
pilot usage or reduce prior reservations. Record fresh credit/rate evidence.

```bash
python Tasks/train-openai-instability-within-project/control_admin.py extend \
  --storage "$HOME/master-openai" --output "$HOME/master-openai/cloud-extension.json"
```

The extension requires both cloud-recorded pilot validations, enforces $80 plus
the protected $20, and cannot clear a breach, pending request or model reservation.
It is a conditional update of the same ledger, not a new bootstrap. Until the
extension is confirmed, a changed private storage plan makes ordinary commands
fail closed. A lost confirmation can be checked by repeating the exact reviewed
extension; it recognizes its immutable review record instead of resetting state.
Then renew the model approval with the new `storage_reserve_usd` and run full
preflight. Old model approval cannot silently spend against a changed allowance.

Repeat `train-submit` / `train-status` for the remaining models, then run:

```text
validate -> seal -> test -> report
```

Each arrow means submit the next CPU stage only after the previous one succeeds.
The seal requires all eight entries and freezes model/job IDs, thresholds, prediction
hashes, data, and study provenance. Training/validation cannot change afterward.
Test requires full-study authorization and uses the identical held-out rows.

Thresholds use the existing validation-F1 rule; they do not optimize AUC-PRC.
The primary research objective is AUC-PRC. AP above prevalence and the matched
classical comparator, ROC > 0.5, and AUC-PRC > 0.5 remain minimum reporting gates.
Final-test results must not select configurations or a winning variant. Missing
HF/Jev results are not invented.

Output scores are the normalized probabilities of the `0`/`1` label tokens from
the same output position. They are **conditional scores, not calibrated event
probabilities**. Both class log probabilities are required. Missing tokens,
refusals, invalid output, or missing usage fail the operation; there is no generated
confidence fallback or row dropping. With a one-token output cap, a `length`
finish is accepted only when exactly one complete, correctly scored class token
was returned.

## Recovery and cleanup

One cloud training job and one transient fine-tuned deployment may be active at a
time. The persistent ledger enforces training concurrency even after SLURM exits.
File and job intent are recorded before submission. An ambiguous submission is
reconciled by the unique training upload, not retried blindly.

Completed inference operations resume from their durable ledger results.
An interrupted request without a saved response remains **unconfirmed** and blocks
that row: no second paid request is silently made. Review provider request/billing
evidence before deciding on a separately budgeted recovery/new run. This deliberate
stop cannot be bypassed with a retry flag or by deleting ledger entries.

Only an explicit HTTP 429 rejection is eligible for a new durable inference
attempt, at most three total. Connection errors, timeouts, 5xx responses, missing
usage or invalid scoring output remain unknown and are not automatically retried.
SDK auto-retries are disabled. A stale worker may save an immutable completion
receipt but cannot finalize the ledger or dispatch another request. Lease expiry
or an absent job listing is not evidence that a request was never accepted.
Reservations remain conservative; an actual overrun permanently latches a stop.
There is no exactly-once guarantee across Azure Storage and Azure OpenAI.

Failed stages write an owner-only diagnostic record under `failures/`. The
stage's status JSON links to that record and its SHA-256; later failures use
different files rather than overwriting earlier evidence. Records include the
study identity, allowlisted provider error codes/parameters, validated request
IDs, and the dispatched operation/attempt/request hash when available. Unknown
error fields are fingerprinted; response bodies, messages, arbitrary headers and
request payloads are not saved. If cleanup also fails, the original dispatch
error is retained separately. A diagnostic-write failure is reported explicitly.
These records are excluded from artifact bundles.

Failure diagnostics are **not** completion receipts or permission to retry.
They do not change cloud reservations, clear pending intent, or prove that an
absent provider job was never accepted. A historical HTTP 400 recorded without
provider details cannot be reconstructed by installing this change. Obtain
provider rejection/billing evidence before reviewing any explicit recovery;
do not replay a create request merely to recover its error message. Changing
the diagnostics source changes the study signature, just like other source
changes: do not resume paid stages of an existing study under a new signature.

`cancel` requests Azure job cancellation. A killed SLURM job is not a cancelled
Azure job. Confirm terminal provider status using `train-status`, then run
`cleanup`. These recovery stages remain usable after approval expiry or code/
environment changes within the cloud-control contract; they read the original
study identity and configuration. They still need valid storage access/cost
approval. Legacy SQLite studies require their original recovery code, not an
implicit migration. Deletion/cancellation timeouts also require reconciliation.

Cleanup deletes only manifest-owned deployments and uploaded training files.
Models are retained by default for reproducibility. Explicitly add
`--delete-models` to `cleanup` if permanent model removal is approved. Inspect
`cleanup.json` and provider state; failed/ambiguous deletion is not reported as
successful. No resource group or subscription is deleted.

## Artifacts and reporting

| Artifact | Location |
| --- | --- |
| Data, transformer, tokenizer coverage | `<storage>/openai-runs/<run-id>/prepared/` and `prepared.json` |
| Private authorization and cost estimate | Same run's `authorization.json`, `cost_estimate.json` |
| File/training/model references | Same run's `remote/` |
| Validation scores and selection | Same run's `validation/<project>-<level>-<variant>/` |
| Sealed protocol | Same run's `sealed.json` |
| Test scores/metrics | Same run's `final/<project>-<level>-<variant>/` |
| Authoritative reservations, remote intents, receipts, selections and results | Fixed Azure Table partition |
| Private storage approval | `$HOME/.local/state/master-openai/cloud-approval.json` |
| SLURM logs and job mapping | `Tasks/<task>/cluster_runs/<submission>/logs/` and `llm_job_plan.json` |
| Private failure evidence | Same run's `failures/`, referenced by `status/<stage>.json` |
| Summary | Report submission's `results/llm_report.json` |

`llm_report.json` uses a distinct `openai-instability-report-v2` schema with eight
entries, real hosted model references, coverage, cost bounds, and per-cell gates.
The existing summary helper handles it without fake HF checkpoint files.
Its scope checks still accept archived v1 reports only with their original
48 entries. Regenerating a report for an older study requires that study's
original protocol version; the reduced runner will not relabel old results.
Only code and final summaries are allowlisted for bundling; raw stories,
JSONL, row scores, authorization, ledger, remote payloads, and logs are excluded.
Run-local authorization, remote references and seals are caches; they never
override cloud evidence. Reports label storage actuals as unreconciled instead
of pretending the storage reserve is an actual bill.
PR creation and presentation edits are separate actions, not part of this task.

The study remains retrospective, with possible public-text pretraining exposure.
Paired issue-bootstrap intervals do not model temporal dependence. Model hosting
and fine-tuning differ from classical/HF optimization, and higher AUC-PRC is not
guaranteed.

## Offline validation

```bash
python -m unittest discover -s Tasks/train-openai-instability-within-project/tests -v
python -m unittest discover -s Tasks/create-task-summary-pr/tests -v
```

Tests cover the real historical split/label contract, synthetic export and
train-only transforms, budget bounds, unknown remote outcomes, scoring errors,
retry limits, all eight mocked model/variant entries, final sealing, CPU launchers,
and artifact exclusions. They never make paid API calls.

Development validation used an existing scientific Python environment because
the private package feed required authentication and the public wheel host timed
out. The pinned Python 3.11/OpenAI/Azure environment and live Azure transport
remain cluster acceptance gates; mocked results do not validate account quota,
Developer availability, or live fine-tuned logprob support.

## Provider documentation

- https://learn.microsoft.com/en-us/azure/foundry/fine-tuning/overview
- https://learn.microsoft.com/en-us/azure/foundry-classic/openai/how-to/create-resource
- https://learn.microsoft.com/en-us/azure/foundry-classic/openai/how-to/role-based-access-control
- https://learn.microsoft.com/en-us/cli/azure/authenticate-azure-cli-interactively
- https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/fine-tuning
- https://learn.microsoft.com/en-us/azure/foundry/fine-tuning/cost-management
- https://learn.microsoft.com/en-us/azure/cost-management-billing/manage/spending-limit
- https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-acm-create-budgets

OpenAI's direct fine-tuning platform is currently unavailable to new users
according to its supervised fine-tuning guide. This task targets the separately
documented Azure offering and never falls back to a direct paid OpenAI account.
