# Prepare code-smell dataset

For the sequential replacement that avoids accumulating repository snapshots,
see [`process-code-smell-stories`](../process-code-smell-stories/README.md).
Its initialization reuses frozen preparation; do not run bulk `fetch-code`
for a sequential study.

First of three tasks: prepare stories and pinned code evidence, then run
`detect-code-smells`, then `train-code-smell-models`. The shared implementation is
in `Code_Smells_Detection/runtime/`; the old detector entry points are not used.

## Study contract

Use the saved September 10 candidate CSV and adjacent `source_status.csv`.
The candidate SHA256 is
`a96d260478dfe2c6eb78ce8c47bac74707039c05853e90e0c8e2775d103d0aab`.
Its 68,358 IDs are preliminary candidates, not labeled or split model rows.
The four sources with at least 100 candidates are Apache, IntelDAOS, MongoDB
and RedHat (68,244 candidates total). No new JQL population is collected.

Enrichment reconstructs sprint-entry text and metadata, applying the existing
story/comment validity rules. Splits are frozen **before** code or detector
exclusions. Verified matching prior features and membership are reused;
otherwise the task freezes chronological 60/20/20 train/validation/test
partitions per source, with source-qualified row IDs breaking timestamp ties.
Later stages only mask these partitions; they never re-split surviving rows.

## Submit stages

Run from the repository root on the cluster. Paths must be visible to workers.
Keep storage outside Git and separate from active HF environments and runs.
Copy the two original CSVs to `$INPUTS`; do not regenerate them.

```bash
STORAGE="$HOME/master-code-smells"
RUN="code-smells-001"
INPUTS="$HOME/code-smell-inputs"

# Bootstrap from an existing environment with Python and conda.
# Creates master-smells; does not install into master or HF environments.
bash Tasks/run_cluster_task.sh prepare-code-smell-dataset \
  --stage environment --storage "$STORAGE" --run-id "$RUN" --conda-env master

# Wait for each stage to succeed before submitting the next one.
bash Tasks/run_cluster_task.sh prepare-code-smell-dataset \
  --stage audit --storage "$STORAGE" --run-id "$RUN" \
  --candidates "$INPUTS/live_model_candidates.csv" \
  --sources "$INPUTS/source_status.csv"

bash Tasks/run_cluster_task.sh prepare-code-smell-dataset \
  --stage enrich --storage "$STORAGE" --run-id "$RUN"
bash Tasks/run_cluster_task.sh prepare-code-smell-dataset \
  --stage freeze --storage "$STORAGE" --run-id "$RUN"
bash Tasks/run_cluster_task.sh prepare-code-smell-dataset \
  --stage fetch-code --storage "$STORAGE" --run-id "$RUN"
```

Add `--dry-run` to print the sbatch script without submission. Source stages
default to all retained sources; `--source Apache` selects one. Arrays run at
most two workers concurrently, and another code-smell array must finish before
the next is submitted. Override `--partition`, `--time`, `--mem`, `--cpus`,
`--module`, `--conda-env` and `--mail-user` for the target cluster.

For local or dedicated-worker execution use
`python Tasks/prepare-code-smell-dataset/run_task.py` with the same stage
arguments; source stages then require `--source`.

Optional `--prior-manifest /external/prior.json` on `audit` accepts a JSON
object keyed by source, with absolute file paths:

```json
{
  "Apache": {
    "raw_jsonl": "/external/prior/raw_issues.jsonl",
    "field_map": "/external/prior/field_map.json",
    "features": "/external/prior/features.csv",
    "split": "/external/prior/split.json"
  }
}
```

`raw_jsonl`/`field_map` and `features`/`split` are paired, optional imports.
Use the existing Jira pipeline raw-record/field-map schema and this runtime's
split schema. Imports are hashed and rechecked; incompatible features or
membership cause an error, not a silently substituted split.

## Evidence and failures

Concrete GitHub merged PRs and commits reachable from default-branch history
are supported. PRs use their pinned merged head and changed-file inventory;
commits use the first-parent diff. A closed PR with `merged=false` is **not**
assumed merged. The collector also recognizes explicit squash delivery: the
current closure event must name a commit in the canonical repository, that
commit must explicitly say `Closes #N from ... and squashes the following commits:`,
and the commit must be the merge base of its comparison with pinned
default-branch history. Missing or ambiguous proof is excluded. For this
fallback, the snapshot and complete changed-file inventory come from the
**landed commit**, never the unmerged PR head or its test-merge SHA.

Repository renames/transfers are resolved only through bounded, permanent
GitHub API metadata redirects. Redirect targets must stay on
`https://api.github.com` and identify a repository, not another API operation.
Numeric repository IDs and canonical metadata must agree. Evidence retains the
original link, requested repository, lookup paths, canonical name and ID;
snapshots and overlap audits use the canonical repository.

Links are extracted from actual Jira string values, including ADF link
attributes, rather than serialized JSON escapes. Jira markup, newlines and
concatenated URLs are separated before classifying evidence. Codecov report
hosts (`codecov.io` and `app.codecov.io`) are ancillary and do not count as code
delivery or unresolved code links. Genuine unsupported code hosts and
non-concrete commit-history links remain explicit exclusions.

Full snapshots preserve project context,
but labels apply only to associated changed `.java`, `.py` and `.cs` files.
Source paths use native filename rules: on POSIX workers, literal `:` and `?`
in repository filenames (such as Spark's timestamped test fixtures) are kept
unchanged through extraction, changed-file resolution, analysis and integrity
checks. They are not URLs and are never decoded, renamed or silently omitted.
Traversal, absolute/drive paths, backslashes, control characters, links and
special archive members remain rejected. Artifact/tool paths retain their
stricter validation. Windows export preflights every snapshot filename,
including non-C# context files, and fails on incompatible names rather than
producing a partial snapshot or a clean label.
Added and renamed files retain their post-change paths; deleted files cannot
produce post-change labels. Multiple revisions are not a consolidated latest
state or an introduced-smell experiment.

GitHub access uses `GITHUB_TOKEN`, or `GH_TOKEN` if the former is unset. Jira authentication follows
the reused `jira_pipeline.client` environment-variable contract. Do not place
tokens in task arguments, profiles or committed files.

GitHub API connection failures and timeouts have at most five attempts, with
bounded exponential delays and explicit retry messages. TLS verification and
authentication failures remain errors. Only a commit endpoint's HTTP 409 with
the exact GitHub response `Git Repository is empty.` is classified as
`repository_empty`; other conflicts still stop the stage. Empty repositories
are recorded as unavailable code evidence, never as negative smell labels.

A commit endpoint's HTTP 422 is also classified as `commit_not_found` **only**
when its requested reference is 7-40 hexadecimal characters and GitHub's JSON
message exactly says `No commit found for SHA: <requested reference>`, without
additional validation errors. The affected whole story is excluded even if
another linked revision was available; later stories continue. This does not
prove that a commit was deleted or never existed. Other 422 responses (including
PR endpoints, validation/spam errors and malformed bodies) remain failures.
Do not treat every HTTP 422 as transient or silently discard its story.

Unavailable Jira records stop enrichment after recording failures by default;
rerun after restoring access, or use the explicit reviewed policy below.
Evidence failures and unsupported links are explicitly
recorded, not labeled clean. Read the exclusion ledger before accepting cohort
retention. Detection incompleteness is a separate hard gate in the next task.

## Reviewed unavailable Jira records

Use this path only when authorized access or complete historical records are
unavailable and the study explicitly accepts collection attrition. It does not
weaken code-evidence or detector-completeness gates. All original selected
candidate IDs remain in the cohort; inaccessible issues are never negative
labels or imputed feature rows.

Code changes require a **new run ID**. Do not edit `study.json` hashes to resume
an old run. The `migrate` stage supports the pinned original preparation
implementation (source hash
`67c6b55de71534f36736c3756b8ab895eb83638b7ed4a7baf6ad2adaec5f2e07`),
with no prior imports and no downstream evidence/detection/model artifacts.
It checks input and artifact hashes, copies complete cached records and field
maps, and imports existing frozen features/splits byte-for-byte. The parent is
read-only and must have no running stages. Partial-cache hashes are recorded
at migration time, not misrepresented as harvest-time verification.

```bash
STORAGE="$HOME/master-code-smells"
RUN="code-smells-002"

# Submit once; wait for successful completion before subsequent stages.
bash Tasks/run_cluster_task.sh prepare-code-smell-dataset \
  --stage migrate --storage "$STORAGE" --run-id "$RUN" \
  --from-run "$STORAGE/runs/code-smells-001"

# Each command is a separate submission; wait between submissions.
bash Tasks/run_cluster_task.sh prepare-code-smell-dataset \
  --stage diagnose --storage "$STORAGE" --run-id "$RUN" --source MongoDB
bash Tasks/run_cluster_task.sh prepare-code-smell-dataset \
  --stage diagnose --storage "$STORAGE" --run-id "$RUN" --source RedHat
```

Migration is resumable with the same arguments and fails on conflicting
artifacts. It does not copy old successful stage statuses blindly: complete
collections are checked again; frozen sources must pass `freeze` under the new
code before they can be used. A recomputed feature/split difference is an error,
not permission to overwrite an existing split.

`diagnose` attempts only uncached records, keeps newly successful collections,
and probes known cached issues as source/project access controls. It does not
finalize enrichment. Inspect these files under `raw/<source>/`:

- `collection_diagnostics.json`: every remaining failed ID, operation, HTTP
  status, normalized reason, observation time, controls and inventory binding.
  Credentials, response bodies and raw exception text are not recorded.
- `missing_records.proposed.json`: **unapproved** review template. Only
  issue-level 401/403 (`authentication_or_permission_denied`) and 404
  (`not_found_or_not_visible`) observations are proposed. A 404 does not prove
  deletion. Legacy `RuntimeError` entries alone are insufficient evidence.

Review every missing ID and the controls. Copy the proposal to an external
approval file and set `approved` to `true`, `reviewed_at` to the UTC ISO timestamp
of your review (for example the format `YYYY-MM-DDTHH:MM:SS+00:00`), and
`review_note` to your actual reason for accepting the exclusions. Keep the
study/source/candidate/diagnostic hashes and exact issue-to-reason mapping
unchanged. For any project whose control status is `no_cached_control`,
explicitly list its project key in `reviewed_uncontrolled_projects` and
explain your decision in the note. The list must contain exactly those projects.
Do not put tokens or personal issue content in the ledger.

A failed source/project control blocks approval. Transient HTTP/network
failures, unexpected JSON, incomplete pagination and comments/changelog-only
failures remain unresolved; a proposal covering only some missing IDs cannot
finalize collection. Fix those failures and rerun diagnostics before reviewing
again. New diagnostics or changed cached bytes invalidate an earlier approval.
Required custom-field mappings must remain compatible with the cached field
map; the collector never silently replaces that map.

After review, finalize **one explicit source per approval**:

```bash
bash Tasks/run_cluster_task.sh prepare-code-smell-dataset \
  --stage enrich --storage "$STORAGE" --run-id "$RUN" --source MongoDB \
  --missing-records /external/reviewed-mongodb.json
# Repeat for RedHat with its own reviewed file after the first job completes.
# If diagnosis recovered every missing record, run enrich WITHOUT this flag.
```

Successful finalization pins `collection_exclusions.json` and the diagnostic
evidence in the raw manifest. The exact candidate set must equal the disjoint
union of complete records and approved unavailable records. There must be zero
unresolved records. A finalized approval cannot be changed or silently recovered
in place; use another study run for a later policy/cohort change. If interrupted
while finalizing approval, resume with the same approval file.

Once every source is finalized, submit `freeze` for the new run. Unavailable
records appear in `filter_decisions.json` as `jira_unavailable`, separately from
ordinary preprocessing failures. They have no reconstructed sprint-entry time,
feature row or partition; candidate creation dates are **not** substitutes.
New splits retain the existing post-preprocessing chronological 60/20/20 rule.
Existing frozen features/splits must remain byte-identical, including Apache's
454/151/153 membership in the current study. Later evidence/label masks never
re-split the remaining rows. The 100-fully-labeled-story training gate remains.

Reports distinguish complete collection from complete accounting with approved
missing records, with attrition by source, project and candidate creation year.
Model results are conditional on accessible, eligible stories; missingness may
be selective, and observed creator-history counts may be incomplete. This is a
disclosed change to study eligibility, not a claim of unbiased full-cohort
inference. Never exclude all failures merely because a few sampled issues were
inaccessible.

## Recovering the frozen run after code-evidence failures

### Reuse verified work from `010` instead of resubmitting successful stages

The pinned `010` runtime from PR #404
(`46cb99d9cbbe30ac78678ec8454744f3d4a0741e2203f3e51e303be51e53358b`)
supports migration to the missing-commit fix without repeating successful work.
The pinned `009` runtime from PR #402
(`33e847ba327d6a02329aaea78a12a471089aa189c20aa60d67329b8882effea8`)
also remains supported.

```bash
"$HOME/Master/Tasks/run_cluster_task.sh" prepare-code-smell-dataset \
  --stage migrate --storage "$HOME/master-code-smells" --run-id code-smells-011 \
  --from-run "$HOME/master-code-smells/runs/code-smells-010" \
  --reuse-verified
```

Update the checkout once before migration and do not pull between stages.
Wait for migration success. This migration revalidates the frozen preparation
**inside the migration job**, rather than requiring four more freeze submissions.
For each successful parent fetch it checks every evidence-record hash and
membership/partition, recomputes audit counts/overlaps, and verifies complete
snapshot manifests and source bytes. Those evidence artifacts are copied
unchanged and receive a newly validated fetch status: no GitHub/Jira requests.
Failed or absent fetches are not promoted to success.

Atomic link-resolution decisions from unfinished fetches are also imported.
Their URL-derived filenames must match links in frozen story records, and their
bytes are anchored in the migration inventory. These are **transfer-time hashes**,
not a claim that unfinished fetches had final record manifests. Partial story
records are archived, not activated; the resumed fetch rebuilds them using
cached link decisions and verified shared snapshots, requesting only unresolved
links. An unfinished parent reuse migration blocks this migration.

`reuse.json` lists `frozen_sources`, `evidence_sources`,
`missing_evidence_sources`, `resolved_links` (the imported link-decision count),
reused native result keys and skipped result reasons.
Proceed directly to detection for `evidence_sources`; fetch only missing
sources. Unfinished reuse blocks downstream evidence/feature consumption and
can be resumed with the identical migration command.

Compatible Java results are sought in the pinned `010`, `009` and archived `008`
ancestry only. Snapshot/profile keys, report hashes, matching native attempt
logs and current report attribution must agree. Known failure manifests are
hash-verified and their diagnostic reasons rechecked. Results without matching
logs, uncommitted failed attempts, and unverified other-language caches are not
silently reused. No old detection success status, exclusion policy or decision
ledger is activated. Select `--exclude-incomplete` on the next detection run
to apply the newly approved uncapped policy.

All raw records, original collection approvals, frozen features and partitions
remain byte-identical; parents are read-only. The ordinary migration path below
remains archival-only. Verified reuse is restricted to these explicitly supported
parent versions, not a general override for incompatible runtime hashes.

For the interrupted MongoDB fetch, after migration succeeds and the summary
confirms Apache/IntelDAOS evidence reuse, submit only:

```bash
"$HOME/Master/Tasks/run_cluster_task.sh" prepare-code-smell-dataset \
  --stage fetch-code --source MongoDB \
  --storage "$HOME/master-code-smells" --run-id code-smells-011
```

Use the shell with `GITHUB_TOKEN` exported. Do not pull again or repeat
Apache/IntelDAOS fetches or native analysis. Existing eligibility decisions
still apply; this fix does not lower the 100-story minimum or imply new labels.

### Older archival-only migrations

The `migrate` stage also supports the finalized, fully frozen implementation
from PR #377 (source hash
`c0005a0d6467c4e053ccceb7d8b27b910d2131eed863650d660a1fc6153c1fb7`).
This is the `code-smells-002` format, including a verified earlier migration
and approved unavailable Jira records. It also supports the `code-smells-003`
runtime from PR #384 (source hash
`a8776a676eea4425b8f8332e2cecca3def8bf38afd53b1fd0f0fa84e9594d335`),
including its verified frozen import from `002`, and the `code-smells-004`
runtime from PR #389 (source hash
`4bfc7081a576c69d7fec9d179a5a00add07f73f5b85df1bbd53a3bf2ee9d4acd`).
The `code-smells-005` runtime from PR #392 is also supported (source hash
`075a48ab04792e520d0efdac9229e50512b02d545ca0cc7d7a87c31d54ccb356`).
The `code-smells-006` runtime from PR #393 is supported as well (source hash
`09c3e46d55ae1fd9fc68d19f3a78dfc2dc45323e4a39b3c1bd3ae59ba5044400`).
The `code-smells-007` runtime from PR #394 is supported (source hash
`21e404a3f8ba14e8e1478216b391ac787c9bc1808f20fe926508041eebd7a776`).
The `code-smells-008` runtime from PR #397 is supported (source hash
`6f57fd48e84f7b775cb00100bad6c48f9797d4d9f021ccbd7a3f435abeb6352e`).
Use `008` to `009` for inheritance-depth warning accounting; do not modify the old
study's source hash or delete its failed reports. All sources must have successful
enrichment and freeze stages. Running stages and label, model, or report-stage
artifacts block migration. Only the pinned `005` through `008` formats additionally permit
pre-label detector artifacts: these are checksummed and archived in
`parent/detection/`, never reused as active results. Earlier parent formats
remain preparation-only.

Update the checkout to the recovery implementation once, before migration.
Use a new run ID; never replace the old run's source hash or edit its artifacts.
Submit the following stages separately, waiting for each to succeed:

```bash
"$HOME/Master/Tasks/run_cluster_task.sh" prepare-code-smell-dataset \
  --stage migrate --storage "$HOME/master-code-smells" --run-id code-smells-009 \
  --from-run "$HOME/master-code-smells/runs/code-smells-008"

# After migrate succeeds: revalidate all four sources without fetching Jira.
"$HOME/Master/Tasks/run_cluster_task.sh" prepare-code-smell-dataset \
  --stage freeze --storage "$HOME/master-code-smells" --run-id code-smells-009

# After every freeze succeeds, use the shell with GITHUB_TOKEN exported.
"$HOME/Master/Tasks/run_cluster_task.sh" prepare-code-smell-dataset \
  --stage fetch-code --source Apache \
  --storage "$HOME/master-code-smells" --run-id code-smells-009
```

Do not add `--pull` between stages. The migration preserves raw records, field
maps, original approvals and diagnostic evidence, preprocessing decisions,
feature CSVs, and split files byte-for-byte. Original approvals retain their
original study identity: the new run validates that identity through its
hashed migration inventories and preserved parent-study chain, rather than fabricating
new approvals or weakening collection checks. Any mismatch is a hard failure.
Neither Jira recollection nor repartitioning is performed.
Across frozen imports through `009`, approvals still belong to their
original `002` study, not to the immediate parent. Every intervening frozen import must bind the
same raw manifest, diagnostics and approval bytes. Earlier parent artifacts
are retained under nested `parent/` directories.

Old partial code-evidence JSON is copied only into `parent/evidence/` for
provenance, not reused as active decisions under changed code. The next fetch
re-resolves links; verified full snapshots in the shared storage cache are
reused. No old fetch/detector success status is imported. Migration validates
the copied collection before marking enrichment successful, and the separate
`freeze` stage must reproduce all feature and partition bytes before fetching.

For `code-smells-002`, the expected frozen feature counts remain Apache 758,
IntelDAOS 235, MongoDB 5,088, and RedHat 6,905 (12,986 total), with 325 approved
unavailable Jira candidates still excluded. Apache's 454/151/153 partition
membership is unchanged. These are preparation counts, not final labeled counts.
The same counts and membership must hold in `004` through `009`. The earlier Apache
`003` fetch found 68 complete-evidence stories, not 68 detector-labeled stories.
The corrected collector does not guarantee recovery to 100; a new fetch and
complete detector coverage are still required before the unchanged training
minimum can be evaluated.

## Outputs and restart

Study artifacts live in `$STORAGE/runs/$RUN`: cohort snapshots, per-source raw
records and features, immutable split manifests, evidence manifests and
exclusion/overlap audits. Shared snapshots and tool caches also stay outside
Git. Task-owned `cluster_runs/<submission>/` contains `job_plan.json`,
`submitted_jobs.tsv`, and separate `logs/job-<job>_<array>.out/.err`.

Inspect study `status/*.json` and stage artifacts, not just scheduler exit
status. Rerun the same stage to reuse verified artifacts; changed code, cohort,
features, partitions or profiles require a new study ID. Never edit hashes to
force a resume. Full collection and snapshot acquisition are user-operated
runtime work, not performed by the offline regression tests.
