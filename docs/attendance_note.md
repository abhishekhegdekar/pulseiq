# Attendance analysis: insight note (Phase I, Task 4)

Data: monthly attendance, April 2025 to September 2026 (18 months), 7,339 employee-months after excluding 4 rows dated after the employee left. **The data is synthetic (fake).** Figures are the ones on the Attendance & Leave dashboard (Executive Office, one person, excluded; groups under 5 people hidden). Rates are pooled (sum over sum). Definitions: `docs/attendance_definitions.md`. Every number is reproduced by `sql/q6_attendance_dashboard_numbers.sql`.

## Headline
Company attendance is stable: **94.2%** over the whole period and **93.9%** over the last 12 months, in a narrow monthly band from 92.9% (May 2026) to 95.6% (July 2025). Paid leave takes about 5.0% of scheduled days, unpaid absence about 0.9%. Late arrivals are about 6.9% of days present (monthly range 6.3% to 7.5%).

## Three findings

**1. Finance & Accounts has the lowest attendance (88.7%), but this is long approved leave, not a problem.**
- *Meaning:* it is a team of about 17 people. Two long maternity leaves (about 130 working days each) account for roughly 209 of its 278 paid leave days from March to August 2026, which pulls its monthly rate from about 95% down to 81% in July 2026.
- *What HR could do:* check that the team had cover during those months, and keep reading small-department rates together with the leave behind them. Do not treat the number as a performance signal.

**2. Operations & IT (8.7%) and Legal & Compliance (7.6%) are late more often than every other department (6.3% to 6.9%).**
- *Meaning:* the gap is about 2 percentage points over the last 12 months. It could reflect shift or on-call start times, or simply the small size of Legal & Compliance (11 people). No statistical test was run.
- *What HR could do:* ask the two managers whether start times or on-call rules differ, and watch the rate for another quarter before acting.

**3. The AI/ML anomaly flags should be used as a review list, not as findings.**
- *Meaning:* 221 attendance flags join to our data on employee and month. Of the 93 we can check against monthly data, 38 are supported and 55 are contradicted. All 35 months with zero days present are flagged, but 15 further "no attendance" flags point to months with most days present. 43 "long unpaid absence" flags claim 11 to 14 days, while the largest unpaid absence in any month is 10 days; only 3 are supported. 128 flags (pattern shift, frequent late) cannot be checked with monthly data.
- *What HR could do:* ask the AI/ML team to review the long-unpaid-absence rule and share daily data so the other flags can be checked. Until then, look at flags one by one and let none of them feed a metric.

## Leave
Only Approved requests count: 3,087 requests, 7,274 days (about 7,200 inside the period; two leaves that run past September 2026 are pro-rated). By days: Earned 2,336, Casual 1,995, Sick 1,767, Maternity 834, Bereavement 137, Loss of Pay 129 (the only unpaid type). Rejected (209), Cancelled (109) and Pending (34) are reported separately. Leave starts are spread evenly over Monday to Friday (575 to 650), so there is no weekday pattern worth acting on. This is the day a leave starts, not absence by weekday.

## Question: does attendance drop every December, and is it real or an artefact?
- **What the data shows:** company attendance was 94.08% in November 2025, 93.73% in December and 93.35% in January 2026. December is not the lowest month (May 2026 is, at 92.87%), and the paid leave share simply kept rising: 4.9%, 5.3%, 5.6%. Finance & Accounts did dip to 89.4% in December, but it also fell to 90.4% in September 2025 and 90.9% in February 2026, which is normal noise for 17 people.
- **Artefact check:** scheduled days per employee in December (21.6) are not lower than in other months, so the month is not shrunk by holidays in the calendar.
- **Answer:** the data holds only one December, so "every December" cannot be tested. This December shows no company-wide drop.
- **How to check properly:** with at least three Decembers, compare December with the average of November and January of the same year. Split the gap into paid leave, unpaid absence and late arrivals. Confirm that scheduled days follow the real working-day calendar. Then check that the same pattern shows up in several departments, not in one small team.

## Limits
- **Synthetic data:** patterns here come from a data generator, not from real people. Do not read any finding as true of a real workforce.
- **Small samples:** departments have 11 to 17 people in several cases, and a few long leaves can move a department's rate by several points. 18 months, one December.
- **Monthly grain:** no daily data, so no weekday absence, no consecutive-day checks and no day-level lateness. Checks on the AI/ML flags are therefore partial.
- **Definition choices:** paid leave counts as not present, so "attendance rate" is presence at work, not good conduct. "Late" is the source system's count and no late-arrival rule is documented.
- **No statistical tests** were run; gaps of one or two points are described, not proven.
- One employee-month (EMP-0566, January 2026) has no attendance row and is not filled in.
