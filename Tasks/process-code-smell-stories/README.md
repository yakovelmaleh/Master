# Process code-smell stories sequentially

Replaces **collect every repository snapshot, then analyze everything** with:

1. Resolve the current frozen story's code links.
2. Fetch one required revision into worker-local scratch.
3. Run the selected, qualified native detectors and verify original source bytes.
4. Durably save normalized results, native reports/logs, source-file hashes and
   an attribution index. These records can be verified without retaining source.
5. Remove that temporary revision before fetching another revision or story.
6. Commit the story checkpoint and atomically update the source CSV.

One story may contain several revisions or languages. Its binary labels are
complete only when all its applicable changed files have successful coverage.
This is not a detector restricted to isolated changed files: the native tool
still sees the full project snapshot, but only temporarily.

## Inputs, files and outputs

`run_task.py` is the local/worker entry point. `cluster/submit_jobs.sh` and
`cluster/submit_jobs.py` use the shared cluster launcher.
`Code_Smells_Detection/runtime/streaming.py` owns processing, durable checkpoints
and label finalization. `tests/test_streaming.py` covers the sequential contract.

Inputs are the existing frozen study, concrete GitHub links, qualified detector
profiles, persistent result storage and an isolated worker's local scratch.
No new database, Azure account or package dependency is introduced.

Within the new run:

| Output | Purpose |
| --- | --- |
| `streaming/<source>.csv` | Incremental story rows and binary targets, status and reason |
| `streaming/catalog.json` | Names corresponding to language/category/smell target columns |
| `streaming/stories/<source>/<issue>.json` | Atomic, checksummed story commit records |
| `streaming/revisions/<key>/` | Portable normalized result plus reports, logs, hashes and attribution |
| `streaming/<source>-progress.json` | Counts of complete/excluded/pending stories and cross-partition revision audit |
| `streaming/<source>-scan.json` | Completed traversal and checkpoint inventory |
| `streaming/errors/` | Native stdout/stderr captured for unclassified execution errors |
| `labels/` | Final model-compatible CSV, catalog, coverage, exclusions and manifest |

`1` means present. `0` means successfully checked and absent. Blank values mean
either an inapplicable language or a non-complete story; `status` and `reason`
distinguish these cases. Findings are smells present in associated changed
files, not necessarily newly introduced smells.

An unfinished CSV update can be reconstructed from committed JSON. A restart
validates existing story and revision checkpoints and does not download or
analyze completed results again. Shared repository/revision/profile results
are reused across stories. The in-memory report-validation cache is bounded.
The source CSV is regenerated atomically after each story, rather than relying
on a potentially truncated append.

## Start from the pinned `011` run

The supported `011` runtime is
`218f518f28efbe65bf767603d748ca75ef897269f857270fe7a38adad86d48c9`.
Update the checkout once after the PR merges; do not pull between stages.
Initialization imports and revalidates frozen preparation and compatible
evidence/results without network requests or native execution. It also converts
verified existing analyses/failures into portable records.

```sh
cd "$HOME/Master"
./Tasks/run_cluster_task.sh process-code-smell-stories \
  --stage initialize \
  --storage "$HOME/master-code-smells" --run-id code-smells-012 \
  --from-run "$HOME/master-code-smells/runs/code-smells-011"
```

Wait for `status/initialize-all.json` to say `succeeded`. Existing approvals,
features, partitions, cached links and compatible native outcomes are preserved.
No separate freeze, fetch-code or bulk detect submission is needed.
Initialization may take time to verify old source trees and reports. It does
not duplicate the old extracted snapshot cache or delete it. It retains the
existing archived provenance chain and copies verified metadata/reports.
Do not edit old run hashes or delete source caches before initialization.

The home-directory quota must still permit **durable metadata, reports, CSVs
and checkpoints**. This change prevents new source accumulation; it does not
free the already exhausted quota. Quota remediation or separately reviewed
cleanup of old snapshots remains a prerequisite for production rollout.
Azure result storage is deferred.

## Process stories

Use the existing qualified Java profile; replace/add profiles only when the
corresponding tool has lawful, successful qualification.

```sh
./Tasks/run_cluster_task.sh process-code-smell-stories \
  --stage process --source MongoDB \
  --storage "$HOME/master-code-smells" --run-id code-smells-012 \
  --profiles "$HOME/master-code-smells/profiles/java-community-linux.json"
```

`--profiles` accepts multiple profile files on the same worker. Later runs may
add a new language while reusing already-completed language results. Omitted
or unavailable languages produce `pending` stories, not negatives or silently
discarded data; other applicable stories continue. A successful process job
means traversal completed, **not** that every story has final labels.

The runner uses `SLURM_SCRATCH_DIR` on the worker, or an explicit `--scratch`.
Scratch must exist and be outside the repository, home directory and persistent
study storage. Do not expand `$SLURM_SCRATCH_DIR` on the login node.
Use only a user-confirmed isolated analysis worker without sensitive mounts.
The existing detector environment filtering remains in force.

Source acquisition and selected detectors run serially under a study-wide
lock. Only one runner-created revision directory is active, with no second full
source copy for analysis. The existing per-archive limits still apply: up to
4 GiB compressed and 20 GiB expanded, plus native tool working space and reports.
Worker scratch must accommodate an individual revision; storage/configuration
errors are blockers, not evidence exclusions.

On normal completion or exceptions, the temporary directory is removed. Only
directories created by this invocation are removed; no caller-owned cache,
scratch root, prior run or repository is deleted. An uncatchable process/node
termination may leave one unfinished workspace, so production should use
job-local scratch with scheduler cleanup. No application can guarantee cleanup
after `SIGKILL` or a lost node.

Use a shell with `GITHUB_TOKEN` exported for uncached metadata. Tokens are never
stored in result files or passed to detector subprocesses.

For local execution on a **dedicated isolated worker**:

```sh
python Tasks/process-code-smell-stories/run_task.py \
  --stage process --source MongoDB \
  --storage /persistent/study --run-id code-smells-012 \
  --scratch /worker-local/scratch \
  --profiles /profiles/java.json /profiles/python.json
```

## Failures, continuation and finalization

Known missing evidence, recognized native incompleteness, attribution gaps and
uncovered changed files exclude the entire story with an audit reason, without
a numerical cap. Missing language prerequisites leave it pending. Unknown
process failures, invalid schemas/catalogs, configuration/license failures,
source/report tampering and quota errors stop processing. Already committed
results remain reusable.

Progress messages identify each story and revision so long jobs are observable.
Resume the identical command after resolving an infrastructure failure. A crash
after the revision commit but before the story commit reuses the durable revision
and reconstructs the story, without requiring its deleted source.

After processing **every selected source** and resolving pending tool
prerequisites, finalize:

```sh
./Tasks/run_cluster_task.sh process-code-smell-stories \
  --stage labels \
  --storage "$HOME/master-code-smells" --run-id code-smells-012
```

Finalization verifies all checkpoints without retained source and refuses
unprocessed or pending stories. It exports the existing label schema for
`train-code-smell-models`. Sources below 100 fully labeled stories remain
ineligible; frozen partitions are never reshuffled. A wholly excluded study
gets a coverage report, not fabricated labels. Once final labels are sealed,
further processing requires a new study.

Legacy bulk tasks remain unchanged for reproducing old runs. Do not mix new
bulk fetch/detect submissions into a sequential run.
