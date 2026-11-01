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
files and uncovered changed files fail the stage.

Qualified-name-only reports can contain the same Java type name in multiple
modules. A known ambiguity is recorded in `attribution.json` and the normalized
result's `ambiguous_entities`. All candidate files are removed from usable
coverage and findings, including otherwise uniquely named types in those
files. The full snapshot is still analyzed: files are not removed, renamed,
assigned by CSV order, or analyzed as separate module-only snapshots.

Unrelated ambiguous files no longer block an otherwise completely covered
story. If any associated changed file is a candidate, the existing required-file
coverage gate still fails; that story cannot receive a clean label. An entity
with no source match remains a hard error because its scope is unknown.
Unknown smells and uniquely resolved findings outside reported coverage also
remain errors. The qualification fixture's positives and clean controls must
still be unambiguously covered.

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

After every required language/source has completed:

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
labels. Restore tool/access prerequisites and rerun first. If some stories
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
