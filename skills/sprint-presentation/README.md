# Sprint Presentation Skill

This skill creates one PowerPoint per sprint and appends a consistent experiment
section to it. The design is based on `Yakov Elmaleh Presentation (2).pptx`.
The bundled template is sanitized to one neutral title slide, retaining the
original layouts and visual theme but no original thesis-content slides.

## Requirements

- Python 3
- `python-pptx`

Install the skill dependency from the repository root:

```bash
python3 -m pip install -r skills/sprint-presentation/requirements.txt
```

## Create a clean sprint presentation

```bash
python3 skills/sprint-presentation/scripts/sprint_presentation.py \
  create \
  --sprint "Sprint 12" \
  --title "Master — Instability Model Experiments" \
  --subtitle "Yakov Elmaleh" \
  --output "./Sprint-12-Experiments.pptx"
```

The command copies the bundled template, removes the old content slides, keeps
the themed title slide, and replaces its text.

## Append an experiment

```bash
python3 skills/sprint-presentation/scripts/sprint_presentation.py \
  append \
  --presentation "./Sprint-12-Experiments.pptx" \
  --spec "./experiment.json" \
  --output "./Sprint-12-Experiments-v2.pptx"
```

Use `--in-place` only when the existing file should be replaced.

## Experiment JSON

```json
{
  "experiment": "Training-only sample weights",
  "task": "Improve instability prediction without changing the test distribution.",
  "why": [
    "The positive class is underrepresented.",
    "AUC-PRC is the primary evaluation metric."
  ],
  "data": {
    "old": {
      "name": "Historical data",
      "metrics": {
        "Rows": "23,901",
        "Train / validation / test": "60% / 20% / 20%",
        "Projects": "6",
        "Test positive rate": "15.3%"
      }
    },
    "new": {
      "name": "Refactored data",
      "metrics": {
        "Rows": "23,822",
        "Train / validation / test": "60% / 20% / 20%",
        "Projects": "6",
        "Test positive rate": "15.7%"
      }
    },
    "notes": [
      "Seventy-nine rows with invalid sprint dates were excluded.",
      "Evaluation remains unweighted."
    ]
  },
  "results": {
    "visual": "table",
    "columns": [
      "Model",
      "Unstable level",
      "AUC-PRC",
      "Accuracy",
      "ROC AUC"
    ],
    "rows": [
      ["Old RF", 5, 0.268, 0.860, 0.672],
      ["New logistic", 5, 0.300, 0.700, 0.688]
    ]
  },
  "conclusions": {
    "findings": [
      "Training-only balancing is methodologically valid.",
      "Test metrics must remain unweighted."
    ],
    "next_steps": [
      "Tune on unweighted validation AUC-PRC.",
      "Evaluate once on the untouched test set."
    ]
  }
}
```

### Optional fields

- `include_intro`: defaults to `true`
- `include_conclusions`: defaults to `true`
- `results.visual`: `table` or `bar`
- For a bar chart:
  - `category_column`: column name used for labels
  - `value_column`: numeric column name used for bar length

## Output behavior

- `create` refuses to overwrite an existing file.
- `append` writes `<presentation>-updated.pptx` when neither `--output` nor
  `--in-place` is specified.
- Parent directories are created automatically.
- The generator reopens the saved file and confirms its slide count.

## Run tests

```bash
python3 -m unittest \
  skills/sprint-presentation/tests/test_sprint_presentation.py
```
