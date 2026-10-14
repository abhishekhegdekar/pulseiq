# Attendance analysis: one-page note (Phase I, Task 4)

Data: monthly attendance, April 2025 to September 2026, 7,339 employee-months after excluding 4 rows dated after the employee left. Definitions are in `docs/attendance_definitions.md`. All rates are pooled (sum over sum). Groups under 5 employees are blank.

## Headline
- Company attendance rate over the whole period is **94.2%**; the last 12 months are **93.9%**. Paid leave takes about 5.0% of scheduled days and unpaid absence about 1.1%.
- Monthly attendance moves in a narrow band, **92.9% (May 2026) to 95.5% (July 2025)**. September 2026 is 95.2%.
- Late arrivals are about **6.8% of days present** (monthly range 6.3% to 7.5%). WFH is about 41% of days present.

## Departments (last 12 months)
- Highest: Sales 95.2%, Data & AI 94.8%, Engineering 94.5%.
- Lowest: **Finance & Accounts 88.7%**, then Human Resources 92.0% and Product & Design 92.6%.
- Finance & Accounts is a small department (about 16 people). **Two long maternity leaves (about 130 working days each)** account for roughly 209 of its 278 paid leave days from March to August 2026. This is approved leave, not an attendance problem. Its rolling 3-month rate to September 2026 (84.1%) is low for the same reason.
- Without maternity leave, Finance & Accounts has the lowest approved leave rate of all departments (0.75 days per employee-month). Small departments can be dominated by a few long leaves, so read their rates with that in mind.
- Operations & IT has the highest late rate (8.7%); Legal & Compliance is next (7.6%). The other departments sit between 6.3% and 6.9%. The gaps are modest and none is tested statistically.
- The Executive Office has one employee and is not reported.

## Leave
- Only Approved requests count: 3,087 requests, about 7,274 days. Rejected 209, Cancelled 109, Pending 34 are reported separately.
- By days: Earned leave 2,336, Casual 1,995, Sick 1,767, Maternity 834 (7 requests), Bereavement 137, Loss of pay 129 (the only unpaid type).
- Leave starts are spread evenly over Monday to Friday (18.7% to 21.1%). This is when leave starts, not absence by weekday, because there is no daily data.

## December check
Company attendance was 94.05% in November 2025, 93.73% in December and 93.29% in January 2026. December is not an outlier. Paid leave share rose each month over the period (4.9%, 5.2%, 5.7%).

## Anomaly flags (AI/ML file)
- 221 attendance flags join to our data on employee and month; the flag's record id never matches ours.
- All 35 months with zero days present are flagged NO_ATTENDANCE, but 15 more NO_ATTENDANCE flags point to months with most days present.
- Of 43 LONG_UNPAID_ABSENCE flags, our monthly data supports 3. The largest unpaid absence in any month is 10 days, below the 11 to 14 days the flags claim.
- 128 flags (pattern shift, frequent late) cannot be checked with monthly data.
- The flags are a review list only and feed no metric.

## Limits
- No daily data: no weekday absence, no consecutive-day checks, no day-level lateness.
- One employee-month (EMP-0566, January 2026) has no attendance row and is not filled in.
- "Late" is the source system's count; no late-arrival rule is documented.
