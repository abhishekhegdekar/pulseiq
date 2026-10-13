"""Pipeline entry point.

Exit codes:
  0  success
  1  row validation failure (added in a later step)
  2  configuration or structural failure (missing file, sheet or column)
"""
import logging
import sys

from pulseiq.config import load_config
from pulseiq.errors import PulseIQError
from pulseiq.extract import extract
from pulseiq.transform import transform


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
    except PulseIQError as exc:
        log.error("%s: %s", type(exc).__name__, exc)
        return 2

    rows_in = sum(stats["rows_in"] for _, stats in cleaned.values())
    rows_after = sum(len(df) for df, _ in cleaned.values())
    dupes = sum(stats["duplicates_removed"] for _, stats in cleaned.values())
    log.info("Transform complete: rows_in=%d duplicates_removed=%d rows_after_dedupe=%d",
             rows_in, dupes, rows_after)
    return 0


if __name__ == "__main__":
    sys.exit(main())
