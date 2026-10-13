"""Settings read from environment variables (set via .env in Docker Compose)."""
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from pulseiq.errors import ConfigError


@dataclass(frozen=True)
class Config:
    input_workbook: Path
    reporting_date: date
    allow_rejects: bool
    data_dir: Path
    log_dir: Path


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigError(f"Environment variable {name} is not set")
    return value


def load_config() -> Config:
    raw_date = _require("REPORTING_DATE")
    try:
        reporting_date = date.fromisoformat(raw_date)
    except ValueError:
        raise ConfigError(f"REPORTING_DATE must be YYYY-MM-DD, got {raw_date!r}") from None

    raw_flag = os.environ.get("ALLOW_REJECTS", "false").strip().lower()
    if raw_flag not in {"true", "false"}:
        raise ConfigError(f"ALLOW_REJECTS must be 'true' or 'false', got {raw_flag!r}")

    return Config(
        input_workbook=Path(_require("INPUT_WORKBOOK")),
        reporting_date=reporting_date,
        allow_rejects=raw_flag == "true",
        data_dir=Path(os.environ.get("DATA_DIR", "data")),
        log_dir=Path(os.environ.get("LOG_DIR", "logs")),
    )
