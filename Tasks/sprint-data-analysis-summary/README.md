# Sprint summary: pre-cluster data analysis

This folder keeps the sprint PowerPoint in the repository. Maintain this copy
when adding more experiments; a copy in Downloads is only for convenience.

## Presentation

`results/Master-Sprint-Summary-2026-09-24.pptx`

The deck uses the existing presentation template and contains 13 slides:

| Slides | Content |
|---|---|
| 1 | Sprint summary title |
| 2-5 | `unstable-user-story-timechart-live` |
| 6-9 | `unstable-user-story-timechart-without-pr-evidence` |
| 10-13 | `research-new-public-jira-repositories` |

Each task has an introduction, Data Analysis, results, and conclusions.
The source results were measured on September 10, 2026; the presentation was
assembled on September 24, 2026. No Jira data was refreshed.

## Open and update

Open the `.pptx` in PowerPoint. On macOS, from the repository root:

```bash
open Tasks/sprint-data-analysis-summary/results/Master-Sprint-Summary-2026-09-24.pptx
```

Append future experiment sections to this deck and submit the updated file
through a pull request. This change versions the finished presentation and its
guide; local authoring tools and the unfinished presentation skill are separate.

## Data interpretation

Candidate counts are not unstable labels or final model-ready rows. Neither
time-chart cohort has passed the comment-before-sprint filter. All strict-cohort
issue keys are present in the wider cohort; duplicate keys and daily aggregate
totals were checked before generation. Public-Jira research counts are API
estimates, and compatibility checks cover only one sample issue per source.
The September 24 cluster selection changes are not retroactively applied to
these September 10 experiments.

Source filenames, cohort definitions, and measurement dates are included in
slide notes. No AUC-PRC or other model scores are invented for these data tasks.
