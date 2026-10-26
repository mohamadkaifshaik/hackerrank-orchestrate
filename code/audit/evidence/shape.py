"""Turn generic record dicts / lookup tokens into Observations."""
from __future__ import annotations

from .obs import Obs, collect_ids, make_obs, valid_resource

TRUE = {"true", "1", "yes", "y"}
FALSE = {"false", "0", "no", "n"}


def to_bool(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    if isinstance(v, str):
        s = v.strip().lower()
        if s in TRUE:
            return True
        if s in FALSE:
            return False
    return None


def apply_token(o: Obs, token: str) -> None:
    """Map a lookup result label (FOUND, NOT_FOUND, IDENTIFIABLE, ...) onto the observation."""
    token = (token or "").strip().upper()
    o.token = token
    if token == "NOT_FOUND":
        o.present = False
    elif token == "FOUND":
        o.present = True
    elif token == "IDENTIFIABLE":
        o.present, o.exposed = True, True
    elif token in ("ANONYMIZED", "REDACTED"):
        o.present, o.exposed = True, False
    elif token == "ACTIVE":
        o.present = True
        if o.category == "BACKUP_ARCHIVE":
            o.restore_allowed = True
        else:
            o.enabled = True
    elif token == "DISABLED":
        o.present, o.enabled = True, False
    elif token == "BLOCKED":
        o.present, o.restore_allowed = True, False


def obs_from_record(rec: dict, *, src, file_time, t, kind, category=None, copy=None,
                    resource_id=None) -> Obs | None:
    rid = valid_resource(resource_id or rec.get("resource_id"))
    if not rid:
        return None
    o = make_obs(src, file_time, t, kind, rid, category, copy=copy)
    ids = collect_ids({k: v for k, v in rec.items() if k != "resource_id"})
    o.ids = ids
    o.present = True
    o.exposed = ids.direct()
    if "enabled" in rec:
        o.enabled = to_bool(rec["enabled"])
    if "restore_allowed" in rec:
        o.restore_allowed = to_bool(rec["restore_allowed"])
    for k in ("retention_until", "retained_until"):
        if rec.get(k):
            o.retention_until = str(rec[k])
    if rec.get("source_resource_id"):
        ids.resources.add(rec["source_resource_id"])
    return o
