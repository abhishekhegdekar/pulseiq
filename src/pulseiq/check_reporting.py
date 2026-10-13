"""Check the dashboard views (schema 'reporting') against numbers computed independently in pandas
from the clean Parquet files, and against the workbook's own hires/exits table.

Run:  docker compose run --rm load python -m pulseiq.check_reporting
Exit 0 = everything agrees, 1 = a difference, 2 = config problem, 3 = unexpected error.
"""
import logging
import os
import sys
from pathlib import Path

import pandas as pd
import psycopg

from pulseiq.config import _require
from pulseiq.errors import ConfigError, PulseIQError
from pulseiq.load import _db_settings

log = logging.getLogger("pulseiq.reporting")

BANDS = ["Under 1 year", "1 to under 3 years", "3 to under 5 years", "5 to under 10 years", "10+ years"]


def persons(employee: pd.DataFrame) -> pd.DataFrame:
    return employee.groupby("employee_id").agg(hire=("hire_date", "min"), exit=("exit_date", "max"))


def employed_on(employee: pd.DataFrame, day: pd.Timestamp) -> pd.DataFrame:
    """People employed on `day` with their effective version (latest valid_from <= day)."""
    p = persons(employee)
    ids = p[(p.hire <= day) & (p["exit"].isna() | (p["exit"] > day))].index
    v = employee[(employee.valid_from <= day) & employee.employee_id.isin(ids)].sort_values("valid_from")
    return v.groupby("employee_id").tail(1).set_index("employee_id").join(p[["hire"]])


def expected_headcount(employee: pd.DataFrame, month_ends: list) -> pd.DataFrame:
    rows = [(m.date(), dept, n) for m in month_ends
            for dept, n in employed_on(employee, m).department_id.value_counts().items()]
    return pd.DataFrame(rows, columns=["month_end_date", "department_id", "headcount"])


def expected_current(employee: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    cur = employed_on(employee, as_of)
    years = (as_of - cur["hire"]).dt.days / 365.25
    band = pd.cut(years, [-1, 1, 3, 5, 10, 1000], right=False, labels=BANDS)
    return pd.DataFrame({"job_level": cur.job_level, "tenure_years": years, "tenure_band": band.astype(str),
                         "department_id": cur.department_id})


def expected_flow(employee: pd.DataFrame, first_month_end: pd.Timestamp, as_of: pd.Timestamp) -> pd.DataFrame:
    p = persons(employee).reset_index()
    ev = pd.concat([p.rename(columns={"hire": "event_date"}).assign(kind="joiners")[["employee_id", "event_date", "kind"]],
                    p.dropna(subset=["exit"]).rename(columns={"exit": "event_date"})
                     .assign(kind="leavers")[["employee_id", "event_date", "kind"]]])
    ev = ev[(ev.event_date >= first_month_end.replace(day=1)) & (ev.event_date <= as_of)]
    versions = employee[["employee_id", "valid_from", "department_id"]].sort_values("valid_from")
    ev = pd.merge_asof(ev.sort_values("event_date"), versions, left_on="event_date", right_on="valid_from",
                       by="employee_id")
    ev["month_end_date"] = (ev.event_date + pd.offsets.MonthEnd(0)).dt.date
    out = ev.groupby(["month_end_date", "department_id", "kind"]).size().unstack("kind", fill_value=0)
    for col in ("joiners", "leavers"):
        if col not in out:
            out[col] = 0
    return out[["joiners", "leavers"]].reset_index()


def diff(got: pd.DataFrame, want: pd.DataFrame, keys: list, cols: list) -> list:
    m = got.merge(want, on=keys, how="outer", suffixes=("_view", "_expected")).fillna(0)
    problems = []
    for c in cols:
        bad = m[m[f"{c}_view"].astype(float) != m[f"{c}_expected"].astype(float)]
        problems += [f"{c} {dict(r[keys])}: view={r[f'{c}_view']:g} expected={r[f'{c}_expected']:g}"
                     for _, r in bad.head(10).iterrows()]
    return problems


def _q(cur, sql):
    cur.execute(sql)
    return pd.DataFrame(cur.fetchall(), columns=[c.name for c in cur.description])


def main() -> int:
    logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    try:
        settings = _db_settings()
        workbook = Path(_require("INPUT_WORKBOOK"))
        clean = Path(os.environ.get("DATA_DIR", "data")) / "clean" / "employee.parquet"
        for needed in (workbook, clean):
            if not needed.exists():
                raise ConfigError(f"Not found: {needed}")
        employee = pd.read_parquet(clean)
        sheet = pd.read_excel(workbook, sheet_name="fact_headcount_monthly")
        sheet["month_end_date"] = pd.to_datetime(sheet["date_key"].astype(str), format="%Y%m%d").dt.date
        with psycopg.connect(**settings) as conn, conn.cursor() as cur:
            hc = _q(cur, "SELECT month_end_date, department_id, count(*)::int AS headcount "
                         "FROM reporting.headcount_monthly GROUP BY 1, 2")
            lvl = _q(cur, "SELECT job_level, count(*)::int AS n FROM reporting.headcount_monthly "
                          "WHERE month_end_date = (SELECT max(month_end_date) FROM reporting.headcount_monthly) GROUP BY 1")
            cu = _q(cur, "SELECT as_of_date, job_level, tenure_years, tenure_band, department_id FROM reporting.current_employees")
            fl = _q(cur, "SELECT month_end_date, department_id, joiners, leavers FROM reporting.joiners_leavers_monthly")
    except PulseIQError as exc:
        log.error("STATUS=FAILED_CONFIG: %s", exc)
        return 2
    except Exception:
        log.exception("STATUS=FAILED_UNEXPECTED")
        return 3

    month_ends = sorted(pd.Timestamp(d) for d in hc.month_end_date.unique())
    as_of = month_ends[-1]
    checks = {}
    checks["R1 monthly headcount by department, all months"] = diff(
        hc, expected_headcount(employee, month_ends), ["month_end_date", "department_id"], ["headcount"])

    exp = expected_current(employee, as_of)
    p1 = []
    if len(cu) != len(exp):
        p1.append(f"current employees: view={len(cu)} expected={len(exp)}")
    p1 += diff(cu.groupby("tenure_band").size().rename("n").reset_index(),
               exp.groupby("tenure_band").size().rename("n").reset_index(), ["tenure_band"], ["n"])
    if abs(float(cu.tenure_years.astype(float).mean()) - float(exp.tenure_years.mean())) > 0.005:
        p1.append("average tenure differs")
    checks["R2 current employees: tenure bands and average tenure"] = p1

    checks["R3 job level mix at the latest month-end"] = diff(
        lvl, exp.groupby("job_level").size().rename("n").reset_index(), ["job_level"], ["n"])

    flow = expected_flow(employee, month_ends[0], as_of)
    checks["R4 joiners and leavers by department and month"] = diff(
        fl, flow, ["month_end_date", "department_id"], ["joiners", "leavers"])

    wb = sheet[["month_end_date", "department_id", "hires", "exits"]].rename(columns={"hires": "joiners", "exits": "leavers"})
    checks["R5 joiners and leavers vs the workbook's hires and exits"] = diff(
        fl, wb, ["month_end_date", "department_id"], ["joiners", "leavers"])

    co = fl.groupby("month_end_date")[["joiners", "leavers"]].sum()
    co["net"] = co.joiners - co.leavers
    total = hc.groupby("month_end_date").headcount.sum()
    co["delta"] = total.diff()
    co = co.reindex(total.index).fillna(0)
    co["delta"] = total.diff()
    bad = co.iloc[1:][co.iloc[1:].net != co.iloc[1:].delta]
    checks["R6 company net change equals the change in headcount"] = [
        f"{i}: net={r.net:g} headcount change={r.delta:g}" for i, r in bad.head(10).iterrows()]

    failed = 0
    for label, problems in checks.items():
        if problems:
            failed += 1
            log.error("MISMATCH  %s\n  %s", label, "\n  ".join(problems[:10]))
        else:
            log.info("MATCH     %s", label)
    log.info("As of %s: headcount=%d, average tenure=%.2f years", as_of.date(), len(exp), float(exp.tenure_years.mean()))
    log.info("STATUS=%s", "ALL_MATCH" if not failed else f"{failed}_MISMATCH")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
