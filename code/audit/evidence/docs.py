"""PDF and screenshot evidence, read from the extraction caches.

Screenshots are read once (see cache/image_extractions.json, built by manual
AI vision and disclosed in evaluation/usage_report.md); PDFs come from
cache/document_extractions.json.  Parsers never call a model at run time.
"""
from __future__ import annotations

import json

from ..common import CACHE_DIR, norm_time
from .obs import Ids, Obs, collect_ids, make_obs, valid_resource


def _load(name):
    path = CACHE_DIR / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _record_obs(rec: dict, src: str, file_time: str, kind: str, aliases: dict) -> Obs | None:
    rid = valid_resource(rec.get("resource_id"))
    if not rid:
        for key in ("alias", "object_name", "user_ref"):
            val = rec.get(key)
            if val and val in aliases:
                rid = aliases[val]
                break
    if not rid:
        return None
    t = file_time
    o = make_obs(src, file_time, t, kind, rid, rec.get("category"))
    if rec.get("system_id"):
        o.system_id = rec["system_id"]
    fields = {"name": rec.get("name"), "email": rec.get("email"), "phone": rec.get("phone"),
              "user_ref": rec.get("user_ref"), "email_hash": rec.get("email_hash")}
    o.ids = collect_ids({k: v for k, v in fields.items() if v})
    if rec.get("selector"):
        collect_ids({"email": rec["selector"]}, ids=o.ids)
    state = rec.get("state")
    o.present = True if state in ("PRESENT", "ACTIVE") else None
    o.exposed = o.ids.direct()
    if state == "ACTIVE":
        o.enabled = True
    if rec.get("restore_allowed") is not None:
        o.restore_allowed = rec["restore_allowed"]
    if rec.get("retention_until"):
        o.retention_until = norm_time(rec["retention_until"])
    return o


def parse_cached(src: str, file_time: str, aliases: dict):
    obs: list[Obs] = []
    images = _load("image_extractions.json").get("images", {})
    docs = _load("document_extractions.json").get("documents", {})
    entry = images.get(src) or docs.get(src)
    if not entry:
        return obs, []
    kind = "image" if src in images else "pdf"
    for rec in entry["records"]:
        o = _record_obs(rec, src, file_time, kind, aliases)
        if o:
            obs.append(o)
    return obs, []
