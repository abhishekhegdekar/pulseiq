# PulseIQ – Phase I

Workforce analytics pipeline, warehouse and dashboards for the fictional company Zenith Nova Technologies
(all data is fictional and synthetic).

## Status
- [x] Task 1: ETL pipeline (extract, transform, validate, publish, run log, tests, metric dictionary)
- [x] Task 2: Analytics warehouse
- [ ] Task 3: Headcount & Departments dashboard
- [ ] Task 4: Attendance analysis

## Quick start
Requirements: Docker Desktop (tested with Docker 29.8 and Compose v5).

1. Put `03_PulseIQ_Analytics_Star_Schema_Dataset.xlsx` in `data/raw/`. Data is **not** committed to Git.
2. `cp .env.example .env`
3. Run the pipeline (the required command):
   ```
   docker compose run etl
   ```
   (add `--rm` to remove the finished container, and `--build` after changing code).

With the supplied workbook the default strict policy **fails with exit code 1**, because 4 rows are invalid
(2 payroll rows for unknown employees, 2 leave requests ending before they start). To publish the valid rows
and still save the rejects, run:
```
docker compose run --rm -e ALLOW_REJECTS=true etl
```

Run the tests: `docker compose run --rm --build tests`

## What the pipeline does
1. **Extract** the four source sheets (`dim_employee`, `fact_payroll`, `fact_attendance_monthly`, `fact_leave`) and log rows in. Missing file/sheet/column stops the run.
2. **Transform**: trim text, convert dates and numbers, remove exact duplicates. No business value is changed or filled in.
3. **Validate** with pandera: valid dates, non-negative pay, correct keys per dataset, employee references. Bad rows are rejected with a reason.
4. **Enrich** valid rows with year, month and tenure columns (tenure measured to the fixed reporting date).
5. **Publish** clean Parquet files, rejected-row CSVs and a run-log line, using a safe staging-then-swap.

There is no separate "salary" file in the workbook: salary figures are columns of `fact_payroll`.

## Outputs
| Path | Content |
|---|---|
| `data/clean/*.parquet` | `employee`, `payroll`, `attendance`, `leave` (valid rows, sorted, no timestamps) |
| `data/rejected/*_rejected.csv` | Rejected rows with `dataset`, `source_row`, `reject_reason` (header only when none) |
| `logs/runs.jsonl` | One JSON line per run: start/end time, status, exit code, rows in/out/rejected/duplicates per dataset, input hash, output fingerprint |

`data/` and `logs/` are git-ignored because they hold employee and pay data.

## Exit codes and publication policy
| Code | Status | Meaning | `data/clean/` |
|---|---|---|---|
| 0 | `SUCCESS` | no rejected rows | replaced |
| 0 | `SUCCESS_WITH_REJECTS_OVERRIDE` | rejects exist and `ALLOW_REJECTS=true` | replaced |
| 1 | `FAILED_VALIDATION` | rejects exist, strict default | untouched |
| 2 | `FAILED_STRUCTURAL_OR_CONFIG` | missing file/sheet/column or bad setting | untouched |
| 3 | `FAILED_UNEXPECTED` | bug in the pipeline | untouched |

A failed run can never replace good output. Full rules and reasoning: [docs/cleaning_rules.md](docs/cleaning_rules.md).

## Configuration (`.env`, see `.env.example`)
| Variable | Meaning |
|---|---|
| `INPUT_WORKBOOK` | Path to the workbook (inside the container: `data/raw/...`) |
| `REPORTING_DATE` | Fixed date used for tenure and date checks (`2026-09-30`). Never "today" |
| `ALLOW_REJECTS` | `false` (default): any rejected row fails the run. `true`: publish valid rows, still save rejects |

## Repeatability
Clean files contain no timestamps and are sorted by key, so the same input gives byte-identical files (verified by comparing SHA-256 hashes across runs, and between Docker on an Apple-silicon Mac and a separate x86 Linux machine). Run timestamps in the log change on every run; the `output_fingerprint` does not.

## Folder structure (provisional: the assignment's Part 4 structure was not provided)
```
src/pulseiq/   config, errors, extract, transform, validate, enrich, publish, runlog, __main__
tests/         pytest suite (valid, invalid and repeated runs)
data/          raw/ (input, read-only in Docker), clean/, rejected/   (git-ignored)
logs/          runs.jsonl                                              (git-ignored)
docs/          metric_dictionary.md, cleaning_rules.md
sql/           warehouse SQL (Task 2)
dashboards/    exported dashboards (Task 3)
```

## Documentation
- [Metric dictionary](docs/metric_dictionary.md): Headcount, Payroll cost, Attendance rate, Leave without pay days, Average tenure
- [Cleaning, validation and publication rules](docs/cleaning_rules.md), including the joining-after-leaving decision

## Known limitations and open items
- Only the workbook was supplied; no separate Python-team export files exist.
- `fact_attendance_monthly` is monthly. The Task 2 brief describes attendance per day. Decision: the warehouse keeps the monthly grain (one row per employee version per month), as in the source.
- 82 payroll rows (85 attendance rows) fall after the valid_to of their employee version. Resolved in Task 2: they are the final months of leavers, and the as-of rule links them to the right version (check Q4 in sql/q4_facts_link_to_effective_version.sql).
- Reject files contain full row data (including pay). Keep them local.
- Dependencies are pinned in `requirements.txt` (pandas 3.0.6, pandera 0.34.1, pyarrow 26.0.0, openpyxl 3.1.5) on Python 3.13.
- Warehouse schema diagram: docs/schema_diagram.png (SQL in sql/01_schema.sql)

## How to run (Docker only; needs `.env`, copy from `.env.example`)

```
docker compose run --rm --build tests                              # 48 tests
docker compose run --rm --build -e ALLOW_REJECTS=true etl          # clean data -> data/clean (a strict run exits 1 if rows are rejected)
docker compose run --rm --build load                               # schema + upserts into PostgreSQL, builds the headcount fact
docker compose run --rm load python -m pulseiq.check_headcount     # vs workbook: 891 department-months match
docker compose run --rm load python -m pulseiq.check_answers       # 3 SQL answers + integrity check vs clean files
```

Loading twice changes nothing (0 inserted, 0 updated).

## Warehouse

- Schema: `sql/01_schema.sql`; diagram: `docs/schema_diagram.png`
- Design and grains: `docs/warehouse_design.md`
- Keys, SCD2 and the department-transfer rule: `docs/scd2_keys_and_transfers.md`
- Headcount rules and validation: `docs/headcount_validation.md`
- Answers: `sql/q1..q4_*.sql`
- Dashboard style guide: docs/style_guide.md
- Dashboard design review and definitions: docs/dashboard_design_review.md
