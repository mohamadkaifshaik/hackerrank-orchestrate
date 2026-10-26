"""Shared constants, regexes and small helpers."""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATASET = Path(os.environ.get("GHOST_DATASET") or REPO_ROOT / "dataset")   # override only for test fixtures
CACHE_DIR = REPO_ROOT / "code" / "cache"

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
USER_RE = re.compile(r"^user_\d+$")
HASH_RE = re.compile(r"^[0-9a-fA-F]{64}$")
RES_RE = re.compile(
    r"\b(account|search|support|analytics|audit_record|data_flow|backup|export|"
    r"tombstone|marketing|object|cache|email_delivery|legal_hold)_\d+\b"
)

# resource-id prefix -> (system_id, default data category)
PREFIX_INFO = {
    "account": ("account_service", "USER_PROFILE"),
    "search": ("search_service", "SEARCH_INDEX_ENTRY"),
    "support": ("support_platform", "SUPPORT_MESSAGE"),
    "analytics": ("analytics_platform", "ANALYTICS_PROFILE"),
    "audit_record": ("security_service", "SECURITY_AUDIT_LOG"),
    "data_flow": ("integration_service", "DATA_FLOW"),
    "backup": ("backup_service", "BACKUP_ARCHIVE"),
    "export": ("export_service", "USER_EXPORT"),
    "tombstone": ("identity_service", "ACCOUNT_TOMBSTONE"),
    "marketing": ("marketing_platform", "MARKETING_PROFILE"),
    "object": ("object_storage", "SUPPORT_ATTACHMENT"),
    "cache": ("cache_service", "CACHE_ENTRY"),
    "email_delivery": ("email_delivery_service", "EMAIL_DELIVERY_LOG"),
    "legal_hold": ("legal_service", "LEGAL_HOLD_RECORD"),
}


def prefix_of(resource_id: str) -> str:
    return resource_id.rsplit("_", 1)[0]


def system_of(resource_id: str) -> str | None:
    info = PREFIX_INFO.get(prefix_of(resource_id))
    return info[0] if info else None


def default_category(resource_id: str) -> str | None:
    info = PREFIX_INFO.get(prefix_of(resource_id))
    return info[1] if info else None


def norm_time(value: str | None) -> str | None:
    """Normalize an ISO-8601 timestamp to 'YYYY-MM-DDTHH:MM:SSZ' (UTC)."""
    if not value:
        return None
    s = str(value).strip().replace(" ", "T")
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def norm_email(value: str) -> str:
    return value.strip().lower()


def norm_phone(value: str) -> str:
    return re.sub(r"\D", "", value)
