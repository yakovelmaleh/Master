# Train code-smell models

Final task, after complete frozen labels. It uses only sprint-entry story
text statistics and pre-sprint metadata, with train-fitted preprocessing.
Code, native reports and post-sprint text are not prediction features.

Each eligible source/target receives matched baseline and training-balanced
variants of `RandomForestClassifier`, `MLPClassifier` and
`GradientBoostingClassifier`. `XGboost` is the historical identifier for the
last estimator, **not XGBClassifier**. `refactored` is the historical identifier
for the balanced variant. Independent binary targets permit multiple smells
per story. This is separate from the HF/OpenAI experiments.

## Stages

Run from the repository root using the dedicated `master-smells` environment
created by the preparation task. Wait for each stage to succeed:

```bash
STORAGE="$HOME/master-code-smells"
RUN="code-smells-001"

bash Tasks/run_cluster_task.sh train-code-smell-models \
  --stage validate --storage "$STORAGE" --run-id "$RUN" \
  --config Tasks/train-code-smell-models/experiment.json
bash Tasks/run_cluster_task.sh train-code-smell-models \
  --stage train --storage "$STORAGE" --run-id "$RUN"
bash Tasks/run_cluster_task.sh train-code-smell-models \
  --stage seal --storage "$STORAGE" --run-id "$RUN"
bash Tasks/run_cluster_task.sh train-code-smell-models \
  --stage test --storage "$STORAGE" --run-id "$RUN"
bash Tasks/run_cluster_task.sh train-code-smell-models \
  --stage report --storage "$STORAGE" --run-id "$RUN"
```

`validate` freezes the config and expected source/target/family/variant matrix.
Always pass the task's `experiment.json` explicitly to use its compact grids;
omitting `--config` selects the reused historical comparison config.
Sources below 100 fully labeled rows, empty applicable partitions and
single-class train/validation targets are marked `insufficient_data`.
They are reported, not replaced with fabricated scores or silently dropped.

`train` fits on train only, chooses parameters by validation trapezoidal AUC-PRC,
and selects a validation F1 threshold. Both variants use identical applicable
rows. `seal` requires all expected eligible models and freezes their artifacts;
subsequent training is forbidden. `test` then performs held-out evaluation.
Single-class test partitions retain defined metrics and explicit undefined
metrics. No hyperparameter or threshold selection uses test outcomes.

Add `--dry-run` for submission preview. Training/testing default to source
arrays capped at two simultaneous workers; `--source Apache` limits a stage.
Other SLURM options and logs follow the preparation task. Local `run_task.py`
uses the same arguments and requires a source for source-level stages.

## Results and inference

Study `models/` holds the expected matrix, selected model/transformer bundles,
candidate results, validation predictions, seal and test results. `report`
creates a metadata-only `code_smell_report.json` in the task submission's
`results/` directory; use `--report-output` to choose an explicit destination.
The report includes retention, applicability, model completeness, per-target
metrics, bootstrap intervals, paired average-precision comparisons and
per-language common-mask multilabel metrics. Dependence/overlap audits limit
interpretation: correlated stories are not independent causal evidence.

Reload saved models on a new CSV with the same feature-column contract:

```bash
python Tasks/train-code-smell-models/run_task.py \
  --stage predict --storage "$STORAGE" --run-id "$RUN" --source Apache \
  --family RF --variant refactored \
  --input /external/new-story-features.csv --output /external/predictions.csv
```

The input requires exactly the shared `FEATURE_COLUMNS` declared in
`Code_Smells_Detection/runtime/prepare.py`, including `issue_key`, `created`
and `time_add_to_sprint`; do not add `row_id`, `source` or label columns.
Do not supply new raw Jira JSON or code as inference features. Output includes
all trained targets for the selected source/model; language-specific scores
are conditional on that language being applicable, not predictions that a
story contains that language. Smell predictions are probabilities and
thresholded labels, not a substitute for running a code detector.

The existing `create-task-summary-pr` helper recognizes this task's report and
copies only allowlisted result metadata and task/runtime definitions into its
review bundle. It must not include raw stories, fetched code, detector tools,
licenses, models or predictions. PR creation and publication remain separate
user-authorized operations. Reports describe implementation/design smells
present in linked changed files, not necessarily smells introduced by a story.

## Verification boundary

Offline regressions exercise preparation, parser failures, Windows exchange
integrity, launchers, frozen splits and synthetic end-to-end model evaluation.
They do not establish real detector licensing/output compatibility, Jira
availability, Windows-host readiness or SLURM success. Those gates must pass
before claiming real dataset counts or empirical model quality.
