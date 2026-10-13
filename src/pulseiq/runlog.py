"""Run log: one JSON line per run, appended to logs/runs.jsonl."""
import json
from pathlib import Path


def append_run_record(log_dir: Path, record: dict) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / "runs.jsonl"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True, default=str) + "\n")
    return path
