# Detect code smells

Second task, after `prepare-code-smell-dataset --stage fetch-code`. Analyze
complete pinned snapshots and attribute implementation/design findings only
to the story-associated changed files. Findings supply labels, never model
features. Each language has its own native smell catalog.

## Required native-tool qualification

The `profiles/*.example.json` files are **templates, not qualified releases**.
Before real analysis, obtain a lawful complete-export edition of DesigniteJava,
DPy and Designite C# as applicable. Review the actual native command, report
names/columns, full smell catalog, analyzed-file coverage output and runtime
requirements. Replace every placeholder, record the release and origin, and
SHA256-pin every executable and dependency. C# distribution files such as DLLs
and runtime configuration belong in the artifact inventory, not just the EXE.
Keep the completed profile and tool files in external storage.

No license is purchased or accepted automatically. Trial/restricted outputs
are rejected. Automatic downloads accept only an explicit official-publisher
HTTPS artifact URL without redirects; a reviewed local distribution can be
supplied instead. A successful process exit alone does not prove completeness.

"Licensed" does not mean "paid": Java Community can be downloaded and qualified
without a commercial license. DPy's free macOS 1.7.8 download was observed to
export detailed CSVs for a small fixture while reporting `Trial`; that is not
proof of unrestricted full-repository export. Its observed native `File`
column, metric report and case-sensitive smell names are now represented in
`python.example.json`. Requalify the selected platform/release and license.
The C# 5.3.0.0 download failed during registry access on macOS; use Windows.

Provide a small, manually reviewed fixture repository for each pinned release:
at least one known implementation smell, one known design smell and one clean
source-file control. C# fixtures must have the project context required by the
tool. Expected names and paths must match the native release, for example:

```json
{
  "positive": [
    {"path": "src/Bad.java", "category": "implementation", "smell": "Long Method"},
    {"path": "src/Bad.java", "category": "design", "smell": "Insufficient Modularization"}
  ],
  "clean_files": ["src/Clean.java"]
}
```

This illustrates the expectation schema, not a guarantee that arbitrary code
produces those findings. The qualification stage runs the real tool, requires
both categories, verifies positives and clean-file coverage, and preserves
hashed reports. Unit-test fake reports do not qualify a native release.

## Java and Python stages

Run from the repository root on a matching, isolated worker. Use a separate
qualified profile/fixture for each language.

```bash
STORAGE="$HOME/master-code-smells"
RUN="code-smells-001"
PROFILE="$STORAGE/profiles/java.json"
FIXTURE="$STORAGE/fixtures/java"
EXPECTED="$STORAGE/fixtures/java.expected.json"

bash Tasks/run_cluster_task.sh detect-code-smells \
  --stage setup --storage "$STORAGE" --run-id "$RUN" --profile "$PROFILE"
bash Tasks/run_cluster_task.sh detect-code-smells \
  --stage qualify --storage "$STORAGE" --run-id "$RUN" --profile "$PROFILE" \
  --fixture "$FIXTURE" --expected "$EXPECTED"
bash Tasks/run_cluster_task.sh detect-code-smells \
  --stage detect --storage "$STORAGE" --run-id "$RUN" --profile "$PROFILE"
```

Wait for each stage before the next; repeat for Python. `--dry-run` prints the
submission script, `--source Apache` limits detection, and cluster overrides
match the preparation task. Local execution uses `run_task.py` with the same
arguments and an explicit `--source` for detection.

Native logs and reports remain under the installed tool's `qualification/`
and the study's `detection/results/<key>/attempts/`, including failed attempts.
Missing reports, unknown catalog entries, unresolved entities, modified input
files and native execution/license errors still stop the stage immediately.
The bounded Apache policy below permits only specifically recognized native
analysis gaps, never arbitrary exceptions.

Qualified-name-only reports can contain the same Java type name in multiple
modules. A known ambiguity is recorded in `attribution.json` and the normalized
result's `ambiguous_entities`. All candidate files are removed from usable
coverage and findings, including otherwise uniquely named types in those
files. The full snapshot is still analyzed: files are not removed, renamed,
assigned by CSV order, or analyzed as separate module-only snapshots.

Unrelated ambiguous files no longer block an otherwise completely covered
story. If any associated changed file is a candidate, the required-file
coverage gate still fails; that story cannot receive any label. An entity
with no source match remains a hard error because its scope is unknown.
Unknown smells and uniquely resolved findings outside reported coverage also
remain errors. The qualification fixture's positives and clean controls must
still be unambiguously covered.

### Incomplete coverage accounting

Valid native reports are saved once per pinned snapshot/profile with
`result.json` status `analyzed`. This means the reports were parsed and checked,
**not** that every changed file was covered. Existing successful Windows results
remain supported. Each story is checked independently against the result's usable
coverage, even when other stories share the same snapshot.

Coverage gaps do not stop the remaining native snapshot analyses.
`detection/coverage/<source>-<language>.json` records each story/snapshot's
required and missing files, its complete/incomplete status, and the affected
story IDs. `scan_complete: true` means every applicable item was checked, not
that coverage is complete. A hard error leaves `scan_complete: false`.
After the scan, any incomplete story still makes the detection stage **fail**,
unless the explicit bounded policy below accounts for it, with an error
pointing to that report otherwise. A retry verifies and reuses the saved
native reports, including coverage-limited results; it does not blindly rerun
unchanged snapshots or turn a cached coverage gap into success.

Header-valid empty reports also provide no coverage, not negative labels.
Qualification still requires both known positives and covered clean controls.
A controlled macOS probe of the pinned Java Community JAR
(`92b17ae9d286a6d932d3bc67a5b1763e876ea4776275619a18fb3ede48765dc4`)
reported an ordinary class but omitted two standalone enums, one with methods.
This is a demonstrated coverage limitation of that artifact on that fixture,
not evidence that enum files are clean or a claim about all Java detector editions.
Required enum files are not dropped or automatically excluded.

Review the coverage report and native attempts before proposing any exclusions.
Final labels still require complete coverage of every supported language for
each retained story. A source scan may finish with recorded gaps, but neither
it nor an `analyzed` result authorizes automatic whole-story exclusions.

### Approved bounded Apache exclusions

For a new study, the operator can explicitly authorize up to ten unique Apache
stories to be excluded without investigating each one:

```bash
"$HOME/Master/Tasks/run_cluster_task.sh" detect-code-smells \
  --stage detect --source Apache \
  --storage "$HOME/master-code-smells" --run-id code-smells-008 \
  --profile "$HOME/master-code-smells/profiles/java-community-linux.json" \
  --max-incomplete-stories 10
```

Default `0` retains strict behavior. Values `1` through `10` are supported only
for Apache detection. The first detection saves an immutable, source-wide policy
in `detection/policies/Apache.json`, bound to the study and frozen split. Use the
same cap on retries and subsequent language scans; changing it requires a new
study. The count combines languages, revisions and failure types by story ID,
not by snapshot, attempt or missing file. A shared failed snapshot can therefore
exceed the cap immediately. Existing upstream evidence exclusions are not
reclassified as detector failures.

Eligible causes are required-file coverage gaps and these recognized diagnostic
messages from the SHA256-pinned Java Community JAR documented above:
Magic Number literal-parsing exceptions, ancestor-analysis memory-overflow
skips, and cyclic-dependency-analysis memory-overflow skips. The entire native
attempt is treated as incomplete; its CSVs provide **no findings or coverage**.
`failure.json` preserves the reason codes, snapshot/profile identity and hashed
attempt logs/reports. Resume verifies these bytes and diagnostic reasons rather
than rerunning unchanged failed snapshots.

Trial/license failures, unknown exceptions, configuration problems, nonzero
native exits/timeouts, missing or malformed reports, unknown smells, unresolved
entities and source/report integrity errors still stop immediately. Qualification
is always strict, even for an otherwise eligible diagnostic. The policy never
changes the tool profile, deletes input files, or suppresses an error to claim
successful analysis.

`detection/exclusions/Apache.json` records every eligible story and its reasons.
An eleventh unique story stops the scan with `cap_exceeded`; it does not select
an arbitrary first ten. Within the approved cap, detection can succeed with
explicitly accounted gaps. Final labeling recomputes exclusions from verified
results, requires completed scans for configured applicable languages, and
excludes each affected **whole story across all languages**. It freezes the
combined ledger in `labels/exclusions.json`; manual exclusions cannot bypass
the total cap. Policy hashes are bound into the label manifest and verified
before modeling.

Unconfigured languages, missing jobs and unrelated hard failures do not qualify
for automatic exclusion. They still block labels for retained stories. Frozen
feature rows/splits remain untouched; only eligible label rows are omitted.
The 100-fully-labeled-story training minimum remains unchanged and is not
guaranteed by the exclusion cap. Results are conditional on analyzable stories;
the audited exclusions must be disclosed in subsequent reporting.

**Isolation is an operator prerequisite, not a sandbox implemented here.**
Detector subprocesses omit Jira/GitHub credential environment variables, but
inherit runtime paths and home directories. Use a dedicated least-privilege
worker without secrets, sensitive mounts or privileged access; do not run
untrusted project builds on a credential-bearing login machine. Do not disable
worker security controls to make a detector run.

## Windows C# exchange

Export one source at a time after reviewing a complete Windows profile:

```bash
python Tasks/detect-code-smells/run_task.py \
  --stage export-windows --storage "$STORAGE" --run-id "$RUN" \
  --source Apache --profile "$STORAGE/profiles/csharp.json" \
  --bundle "$STORAGE/exchanges/apache-csharp"
```

Copy the exchange directory, fixture, expected JSON, matching repository
checkout and licensed tool distribution to the isolated Windows worker.
Profile content must remain identical across export, qualification and
execution. Set artifact `local_path` values for their eventual Windows
locations **before exporting**; export does not install those files locally.
Provision the Windows Python environment from
`Tasks/detect-code-smells/requirements.txt` and the native tool prerequisites.

```powershell
python Tasks/detect-code-smells/run_task.py --stage setup `
  --storage C:\smells --run-id code-smells-001 --profile C:\smells\csharp.json
python Tasks/detect-code-smells/run_task.py --stage qualify `
  --storage C:\smells --run-id code-smells-001 --profile C:\smells\csharp.json `
  --fixture C:\smells\fixture --expected C:\smells\expected.json
& Tasks/detect-code-smells/windows/start_worker.ps1 `
  -Bundle C:\smells\apache-csharp -Storage C:\smells
```

The launcher returns a process ID and separate `worker.out`/`worker.err` paths.
Completion requires `completed.json`, not merely a started or exited process.
Copy the completed bundle back without changing its files, then import:

```bash
python Tasks/detect-code-smells/run_task.py \
  --stage import-windows --storage "$STORAGE" --run-id "$RUN" \
  --bundle "$STORAGE/exchanges/apache-csharp"
```

The importer checks exported work identity, job completeness, qualification,
result/report hashes, catalog membership and changed-file coverage. The
exchange is trusted-worker transport with integrity checks, not signed
attestation of an untrusted worker.

## Final labels

After every required language/source has been processed and any remaining
coverage gaps have been explicitly reviewed:

```bash
bash Tasks/run_cluster_task.sh detect-code-smells \
  --stage labels --storage "$STORAGE" --run-id "$RUN"
```

`labels/story_labels.csv` contains independent binary language/category/smell
targets plus `any_supported_smell`. A language absent from a story is
not applicable (`null`), not negative. Findings on unrelated snapshot files
do not label that story. Repeated findings are deduplicated across linked
evidence. `catalog.json` maps target IDs to native names.

`labels/coverage.json` distinguishes complete, excluded and incomplete stories.
By default any required missing/incomplete detector result blocks freezing final
labels. The explicit bounded Apache policy above is the only automatic exception.
Restore tool/access prerequisites and rerun first. If some stories
cannot be fully analyzed, review their failed attempts and explicitly exclude
the **whole story**, not just its failed language:

```json
{
  "Apache:EXAMPLE-123": "Unsupported syntax in pinned snapshot; detector attempt reviewed"
}
```

Pass this external JSON as `--exclusions /external/reviewed-exclusions.json`
to `--stage labels`. Unknown IDs, already complete stories and blank reasons
are rejected. The ledger, coverage and surviving labels are frozen and hashed;
changing the decision requires a new study. Missing results not listed in the
ledger still block labeling. This never relaxes detector qualification or
labels an incomplete story clean. Training separately excludes sources with
fewer than 100 fully labeled stories without moving rows between partitions.
