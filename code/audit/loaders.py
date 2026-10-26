"""Load the participant-facing CSV files."""
from __future__ import annotations

import csv
from pathlib import Path

from .common import DATASET, norm_time


def read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def load_requests(name: str = "deletion_requests.csv") -> list[dict]:
    rows = read_csv(DATASET / name)
    for r in rows:
        for k in ("requested_at", "reported_at", "audit_at"):
            r[k] = norm_time(r[k]) or r[k]
    return rows


def load_identities() -> list[dict]:
    return read_csv(DATASET / "user_identities.csv")


def load_audit_log() -> list[dict]:
    rows = read_csv(DATASET / "user_audit_log.csv")
    for r in rows:
        r["event_time"] = norm_time(r["event_time"]) or r["event_time"]
    return rows


def load_activity() -> list[dict]:
    rows = read_csv(DATASET / "system_activity.csv")
    for r in rows:
        r["event_time"] = norm_time(r["event_time"]) or r["event_time"]
    return rows


def load_rules() -> list[dict]:
    return read_csv(DATASET / "deletion_rules.csv")


def load_manifest() -> list[dict]:
    rows = read_csv(DATASET / "evidence_files.csv")
    for r in rows:
        r["captured_at"] = norm_time(r["captured_at"]) or r["captured_at"]
    return rows
