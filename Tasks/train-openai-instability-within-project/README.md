# Azure OpenAI within-project instability experiment

**Objective: maximize trapezoidal AUC-PRC on the unchanged historical test rows,
using validation for decisions, not test results.** This is supervised fine-tuning,
not a replacement of training with prompting. The cluster orchestrates Azure
training and inference using CPU jobs; no OpenAI weights run on cluster GPUs.

| Contract | Experiment |
| --- | --- |
| Data | Exact immutable #357 CSV, ordered-row, and label hashes from the shared HF contract |
| Partitions | Unchanged independent chronological 60/20/20 for Jira and Qt |
| Labels | 5 and 20; separate model for each repository and level |
| Variants | Original pre-sprint text; text plus serialized train-fitted `FeatureTransformer` values |
| Full scope | 4 repository/level cells x 2 variants = 8 fine-tunes; no pooled model or automatic sweep |
| Pilot | Both Jira/20 variants, all 944 training and 314 validation rows; no early test |
| Cost ceilings | $7 pilot, $80 entire experiment including pilot, $20 credit reserve |
| Default candidate | `gpt-4.1-mini-2025-04-14`, one explicit epoch; subject to actual Azure availability and approval |

**No real OpenAI scores or cloud-validation claims are included.** Offline tests
use synthetic provider responses; these are not research results.

## Reduced-scope protocol and migration

Protocol `openai-instability-v2` deliberately selects Jira and Qt at levels 5 and
20, retaining both variants and every historical row in those cells. The other
four projects and levels 10 and 15 are outside this approved study, not missing
results. The shared historical reference contract and the HF experiment are
unchanged. "Full" approval now means all eight selected models, not the former
48-model study.

After updating the checkout, use the current checked-in `experiment.json` and a
**new run ID**, for example `openai-qt-jira-01`. Do not reuse the old
`openai-mini-study-01` run or its external `openai-mini.json` configuration: the
old schema and study signature cannot authorize the revised scope. Keep their
files and the global ledger; a new run never resets reservations or costs.
The existing `master-openai` environment can be reused if dependencies are
unchanged. Run `prepare` again, then review the new approval template and cost
estimate. A scope change is not authorization for paid calls.

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

All nodes must share the same durable home directory and support SQLite file
locking. The global control directory is
`$HOME/.local/state/master-openai/`, shared across run IDs and storage roots.
SQLite uses rollback journaling and full synchronous writes, not WAL on network
storage. Confirm these filesystem semantics with the cluster administrators.
Never copy/delete the ledger to bypass a budget or a pending cloud job.

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

Run `prepare` with the same command shape:

```bash
./Tasks/run_cluster_task.sh train-openai-instability-within-project \
  --stage prepare --partition main --run-id openai-qt-jira-01 \
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
  --stage preflight --partition main --run-id openai-qt-jira-01 \
  --storage "$HOME/master-openai" --approval "$HOME/private/openai-approval.json"
```

The `pilot` approval must fit both Jira/20 fine-tunes, both complete validation
passes, retries, two synthetic scoring probes, and an unfine-tuned diagnostic on
the first 20 Jira/20 validation rows into $7. This is included within, not added
to, the $80 total ceiling. A cost worksheet is persisted before
any training request. Unknown/insufficient funding blocks execution, not just
prints a warning.

Submit these stages separately, waiting for each SLURM job to finish:

| Stage | Effect |
| --- | --- |
| `smoke` | Billable base-model logprob probes and the small validation-only control |
| `train-submit` | Submit the next not-yet-trained model in the approved scope, then exit |
| `train-status` | Retrieve/reconcile Azure jobs; it does not wait for a queued job or start another one |
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

Transient inference retries are bounded; SDK auto-retries are disabled. Reservations
include all attempts. Unknown earlier attempt costs remain reserved. Azure billing
can lag; the ledger is conservative and never treats delayed billing as free usage.
Actual usage above the bound sets a global breach flag and stops further spending.

`cancel` requests Azure job cancellation. A killed SLURM job is not a cancelled
Azure job. Confirm terminal provider status using `train-status`, then run
`cleanup`. These recovery stages remain usable after approval expiry or code/
environment changes; they read the original study identity and configuration.

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
| Global reservations and response cache | `$HOME/.local/state/master-openai/ledger.sqlite3` |
| SLURM logs and job mapping | `Tasks/<task>/cluster_runs/<submission>/logs/` and `llm_job_plan.json` |
| Summary | Report submission's `results/llm_report.json` |

`llm_report.json` uses a distinct `openai-instability-report-v2` schema with eight
entries, real hosted model references, coverage, cost bounds, and per-cell gates.
The existing summary helper handles it without fake HF checkpoint files.
Its scope checks still accept archived v1 reports only with their original
48 entries. Regenerating a report for an older study requires that study's
original protocol version; the reduced runner will not relabel old results.
Only code and final summaries are allowlisted for bundling; raw stories,
JSONL, row scores, authorization, ledger, remote payloads, and logs are excluded.
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
