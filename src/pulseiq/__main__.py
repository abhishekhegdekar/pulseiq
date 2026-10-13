"""Pipeline entry point.

Exit codes:
  0  success (or success with rejects when ALLOW_REJECTS=true)
  1  row validation failure: some rows were rejected and ALLOW_REJECTS is false
  2  configuration or structural failure (missing file, sheet or column)
  3  unexpected internal error (a bug)

Publication policy: clean/ is replaced only by a run that finishes with status
SUCCESS or SUCCESS_WITH_REJECTS_OVERRIDE. rejected/ always describes the latest run.
"""
import logging
import os
import shutil
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

from pulseiq.config import Config, load_config
from pulseiq.enrich import add_helper_columns
from pulseiq.errors import PulseIQError
from pulseiq.extract import extract
from pulseiq.publish import (fingerprint, recover_interrupted_swap, sha256_file, swap_in,
                             write_clean, write_rejected)
from pulseiq.runlog import append_run_record
from pulseiq.transform import transform
from pulseiq.validate import build_schemas, validate

log = logging.getLogger("pulseiq")


def run_pipeline(cfg: Config, record: dict) -> int:
    recover_interrupted_swap(cfg.data_dir)
    staging_root = cfg.data_dir / "_staging"
    shutil.rmtree(staging_root, ignore_errors=True)
    try:
        log.info("Reporting date=%s allow_rejects=%s", cfg.reporting_date, cfg.allow_rejects)
        record["input_sha256"] = sha256_file(cfg.input_workbook) if cfg.input_workbook.is_file() else None
        frames = extract(cfg.input_workbook)
        cleaned = {name: transform(name, df) for name, df in frames.items()}

        schemas = build_schemas(cfg.reporting_date)
        results = {}

        def check(name, **kwargs):
            results[name] = validate(name, *cleaned[name], schemas[name], **kwargs)

        def valid(name, column):  # values found in the VALID rows of an already-validated dataset
            return set(results[name][0][column])

        # Dimensions first, then whatever points at them (references use valid rows only).
        check("department")
        check("leave_type")
        check("date")
        departments = ("department_id", valid("department", "department_id"), "departments")
        dates = valid("date", "date_key")
        check("role", references=[departments])
        roles = ("role_id", valid("role", "role_id"), "roles")
        check("employee", references=[departments, roles])
        lookup = results["employee"][0].set_index("employee_key")[["department_id", "role_id"]]
        employee_ref = ("employee_key", set(lookup.index), "employees")
        check("payroll", employee_lookup=lookup,
              references=[employee_ref, departments, roles, ("date_key", dates, "dates")])
        check("attendance", employee_lookup=lookup,
              references=[employee_ref, departments, ("date_key", dates, "dates")])
        check("leave", references=[
            employee_ref, ("leave_type_code", valid("leave_type", "leave_type_code"), "leave types"),
            ("start_date_key", dates, "dates"), ("end_date_key", dates, "dates")])

        record["datasets"] = {name: stats for name, (_, _, stats) in results.items()}
        totals = {key: sum(stats[key] for _, _, stats in results.values())
                  for key in ("rows_in", "duplicates_removed", "rows_rejected", "rows_out")}
        record["totals"] = totals
        log.info("Totals: %s", totals)

        publish_clean = not (totals["rows_rejected"] and not cfg.allow_rejects)
        run_dir = staging_root / record["run_id"]
        write_rejected(run_dir / "rejected", {n: rej for n, (_, rej, _) in results.items()})
        if publish_clean:
            clean = {n: add_helper_columns(n, c, cfg.reporting_date) for n, (c, _, _) in results.items()}
            record["outputs"] = write_clean(run_dir / "clean", clean)
            record["output_fingerprint"] = fingerprint(record["outputs"])

        swap_in(run_dir / "rejected", cfg.data_dir / "rejected")  # evidence of this run, always
        if not publish_clean:
            record.update(status="FAILED_VALIDATION", exit_code=1, published=False)
            log.error("STATUS=FAILED_VALIDATION: %d row(s) rejected; clean/ left untouched. "
                      "See %s", totals["rows_rejected"], cfg.data_dir / "rejected")
            return 1
        swap_in(run_dir / "clean", cfg.data_dir / "clean")
        status = "SUCCESS_WITH_REJECTS_OVERRIDE" if totals["rows_rejected"] else "SUCCESS"
        record.update(status=status, exit_code=0, published=True)
        log.info("STATUS=%s published clean files to %s", status, cfg.data_dir / "clean")
        return 0
    finally:
        shutil.rmtree(staging_root, ignore_errors=True)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    started = datetime.now(timezone.utc)
    record = {"run_id": started.strftime("%Y%m%dT%H%M%SZ"), "started_at": started.isoformat(),
              "status": None, "exit_code": None, "published": False}
    log_dir = Path(os.environ.get("LOG_DIR", "logs"))
    try:
        cfg = load_config()
        log_dir = cfg.log_dir
        record.update(reporting_date=cfg.reporting_date.isoformat(), allow_rejects=cfg.allow_rejects,
                      input_workbook=str(cfg.input_workbook))
        code = run_pipeline(cfg, record)
    except PulseIQError as exc:
        log.error("%s: %s", type(exc).__name__, exc)
        record.update(status="FAILED_STRUCTURAL_OR_CONFIG", exit_code=2, error=f"{type(exc).__name__}: {exc}")
        code = 2
    except Exception as exc:  # a bug: keep it distinct from validation failures
        log.error("Unexpected error:\n%s", traceback.format_exc())
        record.update(status="FAILED_UNEXPECTED", exit_code=3, error=f"{type(exc).__name__}: {exc}")
        code = 3
    finished = datetime.now(timezone.utc)
    record.update(finished_at=finished.isoformat(),
                  duration_seconds=round((finished - started).total_seconds(), 3))
    try:
        append_run_record(log_dir, record)
    except OSError as exc:
        log.error("Could not write run log: %s", exc)
    return code


if __name__ == "__main__":
    sys.exit(main())
