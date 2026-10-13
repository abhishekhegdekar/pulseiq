# PulseIQ – Phase I

Workforce analytics pipeline, warehouse and dashboards for the fictional company Zenith Nova Technologies.

## Status
- [x] Project skeleton
- [ ] Task 1: ETL pipeline
- [ ] Task 2: Analytics warehouse
- [ ] Task 3: Headcount & Departments dashboard
- [ ] Task 4: Attendance analysis

## Data
Source data is **not stored in Git**. Place `03_PulseIQ_Analytics_Star_Schema_Dataset.xlsx` in `data/raw/`.
The workbook's fact and dimension sheets are treated as the raw exports.

## Folder structure (provisional)
- `src/pulseiq/` – pipeline code
- `tests/` – automated tests
- `data/raw|clean|rejected/` – inputs and outputs (git-ignored)
- `logs/` – run logs (git-ignored)
- `sql/` – warehouse SQL (Task 2)
- `docs/` – diagrams and metric dictionary
- `dashboards/` – exported dashboards (Task 3)
