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
    env: str = "local"
    source_mode: str = "file"


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigError(f"Environment variable {name} is not set")
    return value


def load_config() -> Config:
    raw_date = _require("DEMO_TODAY")
    try:
        reporting_date = date.fromisoformat(raw_date)
    except ValueError:
        raise ConfigError(f"DEMO_TODAY must be YYYY-MM-DD, got {raw_date!r}") from None

    raw_flag = os.environ.get("ALLOW_REJECTS", "false").strip().lower()
    if raw_flag not in {"true", "false"}:
        raise ConfigError(f"ALLOW_REJECTS must be 'true' or 'false', got {raw_flag!r}")

    source_mode = os.environ.get("SOURCE_MODE", "file").strip().lower()
    if source_mode != "file":
        raise ConfigError(f"SOURCE_MODE must be 'file' in Phase I (workbook input), got {source_mode!r}")

    return Config(
        input_workbook=Path(_require("INPUT_WORKBOOK")),
        reporting_date=reporting_date,
        allow_rejects=raw_flag == "true",
        data_dir=Path(os.environ.get("DATA_DIR", "data")),
        log_dir=Path(os.environ.get("LOG_DIR", "logs")),
        env=os.environ.get("ENV", "local").strip() or "local",
        source_mode=source_mode,
    )
