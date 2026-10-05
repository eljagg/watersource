# Data quality: anomaly flags and source profiling

## Anomaly flags for reviewers (`apps/submissions/anomalies.py`)

Every submission (form, CSV or API) is checked against WRA's own approved
record immediately after validation. Findings never reject a row; they add a
plain-English message to the row and move it to *Flagged for review*, and the
submission page shows a count of rows with anomaly findings. The checks are
deterministic and explainable — each message says what was compared with what.

| Check | Meaning | Applies to |
|---|---|---|
| Out of character for this site | Value more than 3.5 robust standard deviations (median / MAD) from the site's approved median; needs ≥ 8 approved readings | well levels, station readings, water-quality parameters |
| Big jump | Change from the latest approved reading far larger than the site's usual step between readings | same |
| Already on record | An approved row for the same site within a minute of the same timestamp exists | all site-linked tables |
| In the future | Timestamp after now | all |
| Flat line | The same value six or more times in a row for one site within the batch | same as first row |
| Abstraction out of pattern | Daily-equivalent volume more than 3× or less than ⅓ of the licence's approved median | abstraction |

Thresholds are module constants (`Z_LIMIT`, `MIN_HISTORY`, `FLAT_RUN`); WRA
tunes them at the data workshop. Corrections are not checked (they are reviewed
against the original row instead).

## Model output (design doc 15 §3.1)

External model results load through the **Model output** category:

1. Admin console → Observations → **Model runs** → add the run (code, model and
   version, scenario, basin, calibration NSE/KGE, notes on karst treatment).
2. Upload results as the Model output category (CSV template on the Data
   submissions page), or convert a native file first:

   ```
   manage.py import_model_output --format swatplus --run riocobre-swatplus-2026a \
       --user hydrologist@wra.gov.jm --map "12=Rio Cobre at Bog Walk" channel_sd_day.txt
   manage.py import_model_output --format wflow --run riocobre-wflow-1 --user … --map "1=Rio Cobre at Bog Walk" output.csv
   ```

3. A reviewer approves it like any other submission; values are then
   `obs_modeloutput` rows (provisional until approved, carrying the chosen
   classification) and can be overlaid on the station's observed record.

## Source profiling for the migration (Milestone 3)

```
manage.py profile_source "extracts/*.csv" extracts/wells.xlsx --out reports/m3 --title "WRA legacy data — DQA"
```

Produces `m3.md` (the body of the Data Quality Assessment Report) and `m3.json`
(for the migration toolkit). Per column: inferred type, completeness,
placeholder blanks (N/A, -, ?), distinct values, min/max, date range and mixed
date formats, leading/trailing spaces, case variants, non-ASCII, numeric
outliers (robust z), and — for columns that look like well, station, parish,
basin or licence references — the match rate against WaterSource's reference
tables with the top unmatched values (the cleaning work queue). Per file:
encoding, duplicate rows, inconsistent column counts, duplicate headers and
candidate keys. Standard library + openpyxl only; `--no-reference` runs it
without a database.
