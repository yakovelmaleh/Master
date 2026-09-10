# 4. Dataset, features, and instability labels

After preprocessing, one model row is created for every accepted issue.

The dataset is saved to:

```text
processed/<repository-or-project>/features_labels_table_os.csv
```

## Instability calculation

For summary, description, and acceptance criteria, the pipeline compares the
reconstructed sprint-entry text with the current text.

It counts added and removed words using the same `difflib.ndiff` approach as
the legacy preprocessing.

The total is stored in:

```text
num_different_words_all_text_sprint
```

The number of summary, description, and acceptance-criteria changes after
sprint entry is stored in:

```text
num_changes_summary_description_acceptance_sprint
```

An issue is unstable at threshold `K` when:

```text
changed words >= K
AND
post-sprint text change count > 0
```

The dataset contains four labels:

- `is_change_text_num_words_5`
- `is_change_text_num_words_10`
- `is_change_text_num_words_15`
- `is_change_text_num_words_20`

## Model input features

Only information available at or before sprint entry is used.

Text-derived features include:

- Text length and word count.
- Unique-word count.
- Question and exclamation marks.
- Newline count.
- URL and code indicators.
- `TBD`/`TODO`, `please`, and acceptance indicators.

Categorical features:

- Issue type.
- Jira project key.
- Priority.

Numeric features:

- Original sprint-entry story points.
- Comments before sprint.
- Text changes before sprint.
- Story-point changes before sprint.
- Time from issue creation to sprint entry.
- Number of earlier downloaded issues by the same creator.

Post-sprint change counts and instability labels are not used as model
features, preventing direct target leakage.

## Cross-project behavior

For a repository-wide run, all projects are combined in chronological order.
`project_key` remains a categorical feature, allowing one model to learn
cross-project behavior.
