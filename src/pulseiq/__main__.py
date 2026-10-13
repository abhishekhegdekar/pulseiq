"""Placeholder entry point; replaced by the real pipeline in the next steps."""
import os
import sys
from pathlib import Path


def main() -> int:
    workbook = Path(os.environ.get("INPUT_WORKBOOK", ""))
    print(f"Reporting date : {os.environ.get('REPORTING_DATE')}")
    print(f"Allow rejects  : {os.environ.get('ALLOW_REJECTS')}")
    if not workbook.is_file():
        print(f"ERROR: input workbook not found: {workbook}", file=sys.stderr)
        return 1
    print(f"Found workbook : {workbook} ({workbook.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
