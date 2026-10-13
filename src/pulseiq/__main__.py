"""Pipeline entry point.

Exit codes:
  0  success (or success with rejects when ALLOW_REJECTS=true)
  1  row validation failure: some rows were rejected and ALLOW_REJECTS is false
  2  configuration or structural failure (missing file, sheet or column)
"""
import logging
import sys

from pulseiq.config import load_config
from pulseiq.errors import PulseIQError
from pulseiq.extract import extract
from pulseiq.transform import transform
from pulseiq.validate import build_schemas, validate


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    log = logging.getLogger("pulseiq")
    try:
        cfg = load_config()
        log.info("Reporting date=%s allow_rejects=%s", cfg.reporting_date, cfg.allow_rejects)
        frames = extract(cfg.input_workbook)
        cleaned = {name: transform(name, df) for name, df in frames.items()}

        schemas = build_schemas(cfg.reporting_date)
        results = {"employee": validate("employee", *cleaned["employee"], schemas["employee"])}
        valid_keys = set(results["employee"][0]["employee_key"])  # facts must point at a valid employee
        for name in ("payroll", "attendance", "leave"):
            results[name] = validate(name, *cleaned[name], schemas[name], valid_keys)
    except PulseIQError as exc:
        log.error("%s: %s", type(exc).__name__, exc)
        return 2

    totals = {key: sum(stats[key] for _, _, stats in results.values())
              for key in ("rows_in", "duplicates_removed", "rows_rejected", "rows_out")}
    log.info("Totals: %s", totals)

    if totals["rows_rejected"] and not cfg.allow_rejects:
        log.error("STATUS=FAILED_VALIDATION: %d row(s) rejected; nothing published", totals["rows_rejected"])
        return 1
    status = "SUCCESS_WITH_REJECTS_OVERRIDE" if totals["rows_rejected"] else "SUCCESS"
    log.info("STATUS=%s", status)
    return 0


if __name__ == "__main__":
    sys.exit(main())
