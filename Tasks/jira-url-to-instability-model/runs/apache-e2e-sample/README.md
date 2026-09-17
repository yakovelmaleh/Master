# Apache bounded E2E validation

This run validates the complete live Jira URL to data to model workflow using
a bounded Apache cross-project sample.

## Command

```bash
python3 run_pipeline.py \
  --jira-url https://issues.apache.org/jira \
  --run-name apache-e2e-sample \
  --max-issues 100 \
  --refresh
```

## Filters

GitHub/PR evidence was enabled. The exact JQL was:

```text
(type != Bug)
AND (Sprint is not EMPTY)
AND (statusCategory = Done)
AND (comment ~ "https://github.com")
ORDER BY created ASC
```

## Results

- 100 issue records downloaded.
- 0 download errors.
- 68 issues accepted by preprocessing.
- 29 rejected because no comment existed at or before sprint entry.
- 3 rejected because sprint entry could not be reconstructed.
- The processed dataset was written successfully.
- The chronological model trained and wrote all expected artifacts.

This intentionally small sample validates pipeline behavior only. It is too
small for meaningful model-quality conclusions, and its validation partition
contains no positive instability labels. In that situation the trainer uses
the documented neutral threshold fallback of 0.50.

## Output

- `raw/` contains downloaded Jira data and field metadata.
- `processed/` contains the filter summary and model dataset.
- `model/apache_words_5/` contains the fitted model, predictions, metrics,
  feature coefficients, metadata, transformer, and HTML report.
