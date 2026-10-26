"""Observation model shared by every evidence parser.

An Observation is one fact about one resource: "at time t, source `src` showed
resource R (category C) in state S, with these identifiers".  Parsers only
describe what the artifact shows; judging it against policy happens later.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..common import (EMAIL_RE, HASH_RE, RES_RE, USER_RE, default_category,
                      norm_email, norm_phone, system_of)

NAME_KEYS = {"full_name", "display_name", "requester_name", "name", "customer_name"}
PHONE_KEYS = {"phone", "requester_phone", "owner_phone", "customer_phone"}
# keys whose values are never an identifier of the data subject
IGNORE_KEYS = {"resource_id", "ticket_id", "trace_id", "order_reference", "archive_path",
               "archive_key", "object_key", "connector_name", "file_name", "file", "index_name",
               "index", "destination", "uploaded_by_system"}

COLLECTION_CATEGORY = {
    "customer_profiles": "USER_PROFILE",
    "customer_search_documents": "SEARCH_INDEX_ENTRY",
    "security_audit_events": "SECURITY_AUDIT_LOG",
    "customer_analytics_reports": "ANALYTICS_PROFILE",
    "connector_configurations": "DATA_FLOW",
    "support_conversations": "SUPPORT_MESSAGE",
    "backup_catalog": "BACKUP_ARCHIVE",
    "ticket_attachments": "SUPPORT_ATTACHMENT",
    "customer_export_jobs": "USER_EXPORT",
    "retained_order_records": "LEGAL_HOLD_RECORD",
    "deleted_customer_references": "ACCOUNT_TOMBSTONE",
}


@dataclass
class Ids:
    emails: set = field(default_factory=set)
    users: set = field(default_factory=set)
    hashes: set = field(default_factory=set)
    phones: set = field(default_factory=set)
    names: set = field(default_factory=set)
    resources: set = field(default_factory=set)  # linked resource ids (e.g. source_resource_id)

    def direct(self) -> bool:
        """True when a direct identifier (not just a stable user ref) is present."""
        return bool(self.emails or self.hashes or self.phones or self.names)

    def merge(self, other: "Ids") -> None:
        self.emails |= other.emails
        self.users |= other.users
        self.hashes |= other.hashes
        self.phones |= other.phones
        self.names |= other.names
        self.resources |= other.resources


def _is_null(v) -> bool:
    return v is None or (isinstance(v, str) and v.strip().lower() in ("", "null", "none", "-"))


def collect_ids(obj, key: str = "", ids: Ids | None = None) -> Ids:
    """Walk a dict/list/scalar and classify every identifier-looking value."""
    ids = ids if ids is not None else Ids()
    if isinstance(obj, dict):
        for k, v in obj.items():
            collect_ids(v, str(k), ids)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            collect_ids(v, key, ids)
    elif isinstance(obj, str) and not _is_null(obj):
        s = obj.strip()
        if key in IGNORE_KEYS:
            return ids
        if key == "source_resource_id" or key == "linked_resource":
            ids.resources.add(s)
            return ids
        if USER_RE.match(s):
            ids.users.add(s)
        elif HASH_RE.match(s):
            ids.hashes.add(s.lower())
        elif key in PHONE_KEYS:
            ids.phones.add(norm_phone(s))
        elif key in NAME_KEYS:
            ids.names.add(s.strip().lower())
        else:
            for m in EMAIL_RE.findall(s):
                ids.emails.add(norm_email(m))
    return ids


@dataclass
class Obs:
    src: str                      # citation id: evidence file_id (or activity_id)
    file_time: str                # manifest captured_at of the file (citation gate)
    t: str                        # time the shown state was observed
    kind: str                     # parser/shape tag, useful when debugging
    resource_id: str | None
    system_id: str | None
    category: str | None
    present: bool | None = None   # True = record exists, False = shown absent
    exposed: bool | None = None   # direct identifiers visible in the record
    enabled: bool | None = None   # data flow active?
    restore_allowed: bool | None = None
    retention_until: str | None = None
    token: str | None = None      # raw state label from the source, if any
    ids: Ids = field(default_factory=Ids)
    copy: str | None = None       # primary / replica table name
    note: str = ""

    def brief(self) -> str:
        flags = []
        for k in ("present", "exposed", "enabled", "restore_allowed"):
            v = getattr(self, k)
            if v is not None:
                flags.append(f"{k}={'Y' if v else 'N'}")
        return (f"{self.src}@{self.t} {self.kind} {self.resource_id} {self.category} "
                f"{' '.join(flags)} {self.copy or ''} ids={sorted(self.ids.emails | self.ids.users)[:2]}")


@dataclass
class Coverage:
    """A snapshot that fully lists records of (system, category) at time t.

    A resource of that category missing from the listing is shown absent."""
    src: str
    file_time: str
    t: str
    system_id: str
    category: str | None  # None = every category of the system
    copy: str | None = None


def make_obs(src, file_time, t, kind, resource_id, category=None, **kw) -> Obs:
    system = system_of(resource_id) if resource_id else None
    if category is None and resource_id:
        category = default_category(resource_id)
    return Obs(src=src, file_time=file_time, t=t, kind=kind, resource_id=resource_id,
               system_id=kw.pop("system_id", None) or system, category=category, **kw)


def valid_resource(value) -> str | None:
    if isinstance(value, str) and RES_RE.fullmatch(value.strip()):
        return value.strip()
    return None
