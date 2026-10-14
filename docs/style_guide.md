# PulseIQ dashboard style guide

Applies to every PulseIQ dashboard (Superset). Short on purpose: if a rule is not here, choose the
simplest option and add the rule.

## 1. The one rule
**Every chart has a title and a one-line takeaway.** The title says *what* is shown, the takeaway says
*what it means*, written from the real numbers (never invented, never "shows the trend of...").

- Title format: `<metric id> <metric dictionary name> - <slice>, <period>`
  e.g. `M01 Headcount - by department, 30 Sep 2026`. Use the exact name from `metric_dictionary`, so
  every number can be traced to its definition (`docs/metric-dictionary.md`).
- Takeaway: one sentence, at most about 120 characters, with at least one number and a verb.
  e.g. `Engineering holds 167 of 441 people (38%); Executive Office has 1.`
- If the takeaway is no longer true after a data refresh, it must be regenerated (see Task 3 checks).

## 2. Colour
Palette: the PulseIQ guide palette, registered in Superset as the colour scheme "PulseIQ"
(`superset/superset_config.py`). Contrast is measured against white (WCAG: 3:1 for chart marks,
4.5:1 for text). Dashboards are also viewed on Superset's dark theme, where navy is almost invisible
(1.6:1), so navy is kept for titles and print, not for chart marks.

| Role | Colour | Contrast on white | Use |
|---|---|---|---|
| Primary data | `#2E75B6` blue | 4.84 | every single-series chart, KPI numbers, "the" measure |
| Comparison B / "bad" | `#C55A11` orange | 4.33 | the second series (leavers vs joiners), contradicted AI flags |
| Category 3 / "good" | `#548235` green | 4.54 | confirmed AI flags; only when 3+ series are unavoidable |
| Context / others | `#7F7F7F` grey | 4.00 | not checkable AI flags, everything that is not the point |
| Dark | `#1F3864` navy | 11.62 | titles and print; not used for chart marks on the dark theme |
| Text | `#1F2933` | 14.76 | titles, labels |
| Muted text | `#52606D` | 6.46 | takeaway line, axis labels, footnotes |
| Text on blue marks | `#FFFFFF` | 4.84 | labels inside bars |
| Text version of orange | `#A84800` | 5.85 | text only (never the lighter orange) |
| Gridlines | `#CBD2D9` | 1.53 | decorative only, thin |

Series colours are fixed per dashboard in Properties, under `label_colors`, so a series never changes colour when
a filter is applied.

Rules:
- Never use yellow `#F0E442` (1.3:1) or sky blue `#56B4E9` (about 2.3:1) for marks on white.
- **Never rely on colour alone.** Direct labels, legend words, order or position must also carry the meaning.
- Blue and orange mean good and bad. No red/green pairs. Joiners vs leavers is blue vs orange, with direct labels.
- The AI flag chart uses grey, orange and green. Orange and green have similar lightness, so people with red-green
  colour blindness may confuse them. The legend words (Not checkable, Contradicted, Confirmed) and the fixed
  stacking order carry the meaning.
- Maximum 4 colours in one chart. With more than 4 groups (11 departments), use **one colour, sorted bars,
  labelled**.
- Ordered categories (tenure bands) use one colour and the axis order, not a colour ramp.
- Background white (`#FFFFFF`) on cards, page background `#F5F7FA` (text contrast 13.75).

## 3. Fonts and sizes
Font: **Inter** (Superset's default), fallback `system-ui, sans-serif`. Numbers use tabular figures where possible.

| Element | Size / weight |
|---|---|
| Dashboard title | 24 px / 600 |
| KPI number | 40 px / 700 (blue) |
| KPI label | 14 px / 500 (muted) |
| Chart title | 16 px / 600 |
| Takeaway line | 14 px / 400 (muted) |
| Axis labels, legends, footnotes | 12 px minimum / 400 |

Nothing below 12 px. No italics for meaning. No all-caps paragraphs.

## 4. Number formats
| Kind | Format | Example |
|---|---|---|
| Counts (headcount, joiners) | thousands separator, no decimals | `1,606` |
| Percentages | one decimal | `96.2%` |
| Ratios (attendance rate) | shown as a percentage, one decimal | `96.2%` |
| Money (INR) | millions, one decimal, unit in the title | `Employer cost, INR million: 46.5` |
| Tenure | years, one decimal | `4.3 years` |
| Months on axes | `Mon YYYY` | `Sep 2026` |
| Dates in tooltips | `YYYY-MM-DD` | `2026-09-30` |
| Negative values | true minus sign, never brackets | `-3` |

Always show the unit (people, %, INR million, days, years) in the title, axis or KPI label.

## 5. Chart choices
- Comparison across departments, roles: **horizontal bars, sorted high to low**, bars start at zero.
- Change over time: **line** (or columns for joiners/leavers per month); no more than 4 lines.
- Parts of a whole with 2-6 parts: stacked bar or single bar. **No pie or donut charts, no 3D, no dual axes.**
- Single important number: KPI tile with the label, the period and one comparison (e.g. vs previous month).
- Every chart offers its data as a table (Superset "View as table") for people who cannot read the chart.

## 6. Layout (laptop and phone)
1. Header: dashboard title, data date ("Data as of 30 Sep 2026"), link to the metric definitions.
2. Row of **4 KPI tiles, most important first** (left to right = top to bottom on a phone).
3. Charts below, one idea per chart, the biggest question first.
4. Filters in a left sidebar on laptop; on a phone the filters sit at the top and the charts stack in one column.
5. Minimum tap target 44 px; no hover-only information.

## 7. Wording
Plain words ("people", "left the company"), no abbreviations without a definition on the page, no
jargon like "SCD2". Say "headcount" for people employed at the last day of the month, and "joiners" /
"leavers" for people who started / left during the month.

## 8. Checklist before a dashboard is accepted
- [ ] Every chart has a metric-dictionary title and a takeaway with real numbers
- [ ] Colours come from section 2; nothing relies on colour alone
- [ ] Readable at laptop width and at phone width (one column)
- [ ] Filters work and the takeaways still agree with the filtered numbers, or say "(all departments)"
- [ ] Every number matches the SQL answer for the same period (Task 3 check)
