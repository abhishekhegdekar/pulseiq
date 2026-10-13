"""Writing outputs safely.

Everything is written to a staging folder first. A folder is swapped into place
only after it is complete, so a failed or interrupted run cannot leave a half-written
or mixed set of files in clean/ or rejected/.
"""
import hashlib
import json
import logging
import os
import shutil
from pathlib import Path

import pandas as pd

log = logging.getLogger("pulseiq.publish")

SORT_KEYS = {
    "department": ["department_id"],
    "role": ["role_id"],
    "leave_type": ["leave_type_code"],
    "date": ["date_key"],
    "employee": ["employee_key"],
    "payroll": ["date_key", "employee_key"],
    "attendance": ["date_key", "employee_key"],
    "leave": ["leave_request_id"],
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def write_clean(directory: Path, clean: dict[str, pd.DataFrame]) -> dict[str, str]:
    """Write one Parquet file per dataset, sorted by key. Returns {file: sha256}."""
    directory.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for name, df in clean.items():
        ordered = df.sort_values(SORT_KEYS[name], kind="mergesort").reset_index(drop=True)
        path = directory / f"{name}.parquet"
        ordered.to_parquet(path, index=False, engine="pyarrow", compression="snappy")
        hashes[path.name] = sha256_file(path)
    return hashes


def write_rejected(directory: Path, rejected: dict[str, pd.DataFrame]) -> None:
    """Write one CSV per dataset (header only when nothing was rejected)."""
    directory.mkdir(parents=True, exist_ok=True)
    for name, df in rejected.items():
        ordered = df.sort_values("source_row", kind="mergesort")
        ordered.to_csv(directory / f"{name}_rejected.csv", index=False,
                       date_format="%Y-%m-%d", lineterminator="\n", encoding="utf-8")


def swap_in(staged: Path, target: Path) -> None:
    """Replace `target` with `staged` using renames (same filesystem)."""
    previous = target.with_name(target.name + ".prev")
    if previous.exists():
        shutil.rmtree(previous)
    if target.exists():
        os.replace(target, previous)
    try:
        os.replace(staged, target)
    except OSError:
        if previous.exists() and not target.exists():
            os.replace(previous, target)  # put the old good folder back
        raise
    shutil.rmtree(previous, ignore_errors=True)


def recover_interrupted_swap(data_dir: Path) -> None:
    """If a previous run died between the two renames, restore the old folder."""
    for name in ("clean", "rejected"):
        target, previous = data_dir / name, data_dir / f"{name}.prev"
        if previous.exists() and not target.exists():
            log.warning("Recovering %s from an interrupted publish", name)
            os.replace(previous, target)
        elif previous.exists():
            shutil.rmtree(previous, ignore_errors=True)


def fingerprint(hashes: dict[str, str]) -> str:
    """One hash for the whole clean output: same data in -> same fingerprint out."""
    text = json.dumps(hashes, sort_keys=True)
    return hashlib.sha256(text.encode()).hexdigest()
