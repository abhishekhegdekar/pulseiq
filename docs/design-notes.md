# Headcount & Departments: design review and definitions

Layout drafted with an AI design tool (Claude's Design canvas), then reviewed against `docs/style_guide.md`.
The canvas keeps both versions side by side: **v1 = AI draft**, **v2 = reviewed**, laptop (1280 px) and phone (390 px).
Figures in the mockups are real warehouse numbers for 30 Sep 2026 and are re-verified in Task 3 step "numbers match SQL".

## What the AI draft did well
- Header, 4 key numbers first, charts below, filters on the side, as asked.
- Style-guide palette (blue / vermillion / grey), metric-dictionary titles, a takeaway under every title.
- Department split as sorted bars in one colour with one highlighted bar (no 11-colour chart).
- Real `<label>`/`<select>` controls, 44 px targets, 12 px minimum text.

## Review findings and what changed

| # | Finding in v1 | Decision | Change in v2 |
|---|---|---|---|
| 1 | Takeaway sentences are text; in Superset they do not change when a filter is applied, so they could become wrong | Keep them static, but say so | Header says "takeaways describe all departments"; sidebar note: "After you filter, read the chart numbers." A check (later) compares every takeaway number with SQL |
| 2 | Trend line axis starts at 380, which can exaggerate growth | Keep (line chart, labelled) | Axis note kept ("Axis starts at 380"); the takeaway states the real change (+12%) |
| 3 | "Joiners" and "Leavers" tiles repeated the bottom chart | Replace | Tiles are now: Headcount 441, **Net change +14 (17 joined, 3 left)**, **Largest department 38%**, Average tenure 3.8 years |
| 4 | Phone: filters sat above the headline number | Move | Headline 441 first; filters come right after the key numbers, two side by side |
| 5 | Phone: month labels were single letters | Fix | Three-letter months (Oct, Nov ...) |
| 6 | "Role mix" as job title has 57 values: unreadable | Keep job level | Role mix = headcount by job level L1 to L7; job titles stay available in the data table |

Checked and unchanged: most important number first (441, largest, top-left, blue); contrast from the
style guide table (text 14.8:1, muted 6.5:1, blue 5.2:1, vermillion marks 3.9:1); nothing relies on
colour alone (series are labelled and values are printed); layout stacks to one column on a phone.

## Definitions (used identically in SQL, charts and takeaways)
- **Current headcount (M01):** people employed on the last day of the latest month (30 Sep 2026): hired on or before it and with no exit date or an exit date after it. Counted as distinct `employee_id`.
- **Monthly headcount:** the same rule at every month-end.
- **Joiners / leavers in a month:** people whose hire date / exit date falls inside that month.
- **Net change:** joiners minus leavers = change in headcount since the previous month-end (Sep 2026: 17 - 3 = +14, 427 to 441).
- **Tenure (L01):** years from hire date to 30 Sep 2026, current employees only. Bands: under 1, 1 to under 3, 3 to under 5, 5 to under 10, 10 or more.
- **Job level:** `job_level` of the employee version effective at 30 Sep 2026 (as-of rule).
- **Largest department share:** largest department headcount divided by total headcount.
