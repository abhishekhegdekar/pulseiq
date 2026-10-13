# PulseIQ dashboard style guide

Applies to every PulseIQ dashboard (Superset). Short on purpose: if a rule is not here, choose the
simplest option and add the rule.

## 1. The one rule
**Every chart has a title and a one-line takeaway.** The title says *what* is shown, the takeaway says
*what it means*, written from the real numbers (never invented, never "shows the trend of...").

- Title format: `<metric id> <metric dictionary name> - <slice>, <period>`
  e.g. `M01 Headcount - by department, 30 Sep 2026`. Use the exact name from `metric_dictionary`, so
  every number can be traced to its definition (`docs/metric_dictionary.md`).
- Takeaway: one sentence, at most about 120 characters, with at least one number and a verb.
  e.g. `Engineering holds 167 of 441 people (38%); Executive Office has 1.`
- If the takeaway is no longer true after a data refresh, it must be regenerated (see Task 3 checks).

## 2. Colour (colour-blind safe)
Palette: Okabe-Ito (designed to be distinguishable with the common types of colour blindness).
Contrast measured against white (WCAG: 3:1 for chart marks, 4.5:1 for text).

| Role | Colour | Contrast on white | Use |
|---|---|---|---|
| Primary data | `#0072B2` blue | 5.19 | single-series charts, KPI numbers, "the" measure |
| Comparison B | `#D55E00` vermillion | 3.87 | the second series (e.g. leavers vs joiners) |
| Category 3 | `#009E73` green | 3.42 | only when 3+ series are unavoidable |
| Category 4 | `#CC79A7` purple | 3.06 | only when 4 series are unavoidable |
| Context / others | `#7B8794` grey | 3.66 | everything that is not the point of the chart |
| Text | `#1F2933` | 14.76 | titles, labels |
| Muted text | `#52606D` | 6.46 | takeaway line, axis labels, footnotes |
| Text on blue marks | `#FFFFFF` | 5.19 | labels inside bars |
| Text version of vermillion | `#A84800` | 5.85 | text only (never the light vermillion) |
| Gridlines | `#CBD2D9` | 1.53 | decorative only, thin |

Rules:
- Never use yellow `#F0E442` (1.3:1), orange `#E69F00` or sky blue `#56B4E9` (about 2.3:1) for marks on white.
- **Never rely on colour alone.** Direct labels, legend order, line styles or position must also carry the meaning.
- No red/green pairs. Joiners vs leavers is blue vs vermillion, with direct labels.
- Maximum 4 colours in one chart. With more than 4 groups (11 departments), use **one colour, sorted bars,
  labelled**, and highlight at most one bar in blue while the rest are grey.
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
