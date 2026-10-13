# Story-to-code-smell runtime

Shared implementation for `Tasks/prepare-code-smell-dataset`,
`Tasks/detect-code-smells` and `Tasks/train-code-smell-models`. Read their
READMEs for the study contract, ordered commands and operational gates.
Legacy `Code_Smells_Detection` modules are retained but are not entry points
for this experiment.

| Module | Responsibility |
| --- | --- |
| `common.py` | External storage, hashes, immutable artifacts, locks and stage state |
| `prepare.py` | Fixed cohort, complete Jira history, sprint-entry features and frozen splits |
| `evidence.py` | Verified GitHub links, pinned snapshots, changed-file lineage and overlap |
| `detectors.py` | Pinned profiles, qualification, native reports, attribution and labels |
| `windows.py` | Checksummed C# export, worker execution and result import |
| `models.py` | Matched binary models, validation selection, sealed tests and reporting |
| `cli.py`, `cluster.py` | Stage dispatch and task-owned nonblocking SLURM submission |
| `bundle.py` | Allowlisted review metadata and definitions |

Runtime data must live outside the repository. Source manifests cover this
runtime and reused Jira/model code: change code only between studies, not
mid-run. Preserve frozen row membership when applying evidence and language
masks. Never convert inaccessible or incompletely analyzed code to a negative.

Native adapters accept a configured CSV schema, not arbitrary vendor output.
Actual profiles must be qualified against a licensed pinned release and
reviewed positive/clean fixtures. Platform/build isolation is an operational
requirement, not a sandbox provided by these Python modules.

Run the independent discovery roots in a configured Python environment:

```bash
python -m unittest discover -s Tasks/prepare-code-smell-dataset/tests
python -m unittest discover -s Tasks/detect-code-smells/tests
python -m unittest discover -s Tasks/train-code-smell-models/tests
```

Tests use temporary external storage and fake native reports; none launches
Jira collection, a commercial detector, a PR or a cluster job.
