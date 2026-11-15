---
name: sprint-presentation
description: Create or extend sprint PowerPoint presentations using Yakov Elmaleh's thesis presentation template. Use when asked to create a PowerPoint, start a sprint presentation, append an experiment, add Data Analysis, results, charts, tables, or conclusions to a presentation.
---

# Sprint presentation

Use the bundled PowerPoint template and generator. Do not recreate the visual
style from scratch.

## Mandatory repository gate

Before creating or appending a presentation:

1. Run `git rev-parse --show-toplevel`.
2. Require the resolved repository basename to be exactly `Master`.
3. Run `git remote get-url origin` and require `yakovelmaleh/Master`.
4. Require `Tasks/run_cluster_task.sh` and this skill directory to exist.
5. If any check fails, stop and say this repository skill works only in
   `yakovelmaleh/Master`.

## Required workflow

1. Read `README.md` beside this file.
2. Run commands from the repository root.
3. For a new sprint, run
   `skills/sprint-presentation/scripts/sprint_presentation.py create`.
4. For an experiment, prepare a JSON specification and run
   `skills/sprint-presentation/scripts/sprint_presentation.py append`.
5. Keep one presentation per sprint. Append each experiment to that deck rather
   than creating an unrelated presentation.
6. Validate the generated PowerPoint by reopening it with `python-pptx` and
   checking its ZIP structure.

## Experiment slide block

Append three or four slides:

1. **Introduction** — what the new task or experiment is and why it is needed.
2. **Data Analysis** — a clear old-data versus new-data comparison, including
   row counts, splits, class balance, coverage, exclusions, and comparability.
3. **Results** — a table or bar chart. Prefer AUC-PRC as the primary metric for
   instability experiments, with accuracy and ROC AUC as supporting metrics.
4. **Conclusions** — findings, limitations, and next steps.

The introduction or conclusions slide may be disabled in the JSON specification
when a three-slide block is more appropriate.

## Presentation rules

- Preserve the bundled template's 16:9 layout, theme, logo, title styling,
  orange accent, gray geometry, and slide numbering.
- A new sprint presentation starts with a clean title slide, not the original
  38 thesis slides.
- Never overwrite an existing presentation unless `--in-place` is explicit.
- Keep Data Analysis factual and visually comparative. Use the same units and
  definitions in the old and new columns.
- Identify split or population differences that make metrics non-comparable.
- Never apply training sample weights to test metrics. Evaluation must represent
  the original test distribution unless the slide explicitly documents another
  methodology.
- Do not claim improvement from accuracy alone on imbalanced data.
- Results tables must name the model, unstable level, AUC-PRC, accuracy, and
  ROC AUC when those values exist.

## Files

- Template: `assets/Yakov Elmaleh Presentation Template.pptx`
- Generator: `scripts/sprint_presentation.py`
- Example specification: `assets/example-experiment.json`
