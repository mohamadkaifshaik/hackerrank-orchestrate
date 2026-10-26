"""JSON and TXT record evidence -> observations + coverage."""
from __future__ import annotations

import json

from ..common import norm_time
from .obs import COLLECTION_CATEGORY, Coverage, Obs, collect_ids, make_obs, valid_resource
from .shape import apply_token, obs_from_record, to_bool


def _lookup_obs(rec: dict, src, file_time, t, kind) -> Obs | None:
    """record_lookup shape: system/resource_id/record_type/result/subject."""
    rid = valid_resource(rec.get("resource_id"))
    if not rid:
        return None
    o = make_obs(src, file_time, t, kind, rid, rec.get("record_type"))
    if rec.get("system"):
        o.system_id = rec["system"]
    subject = {k: v for k, v in rec.items()
               if k in ("subject_reference", "lookup_value", "lookup_key")}
    o.ids = collect_ids(subject)
    apply_token(o, rec.get("result", ""))
    return o


def parse_txt(path, src, file_time):
    obs = []
    for line in open(path, encoding="utf-8"):
        parts = [p.strip() for p in line.strip().lstrip("-").split("|")]
        if len(parts) != 6:
            continue
        t = norm_time(parts[0])
        rec = {"system": parts[1], "resource_id": parts[2], "record_type": parts[3],
               "result": parts[4], "subject_reference": parts[5]}
        o = _lookup_obs(rec, src, file_time, t or file_time, "txt_lookup")
        if o:
            obs.append(o)
    return obs, []


def _service_export(d, src, file_time):
    obs, cov = [], []
    for system, groups in d["service_exports"].items():
        for group, items in groups.items():
            for rec in items:
                t = norm_time(rec.get("observed_at")) or file_time
                rid = valid_resource(rec.get("resource_id"))
                if not rid:
                    continue
                if group == "profile_lookups":
                    o = make_obs(src, file_time, t, "export_profile", rid, "USER_PROFILE")
                    o.present = rec.get("profile") is not None and rec.get("status_code") != 404
                    if rec.get("profile"):
                        o.ids = collect_ids(rec["profile"])
                        o.exposed = o.ids.direct()
                    obs.append(o)
                elif group == "index_queries":
                    docs = (rec.get("hits") or {}).get("documents") or []
                    o = make_obs(src, file_time, t, "export_index", rid, "SEARCH_INDEX_ENTRY")
                    o.present = bool(docs)
                    o.ids = collect_ids(docs)
                    o.exposed = o.ids.direct()
                    # the query string is an identifier of whoever was searched for
                    o.ids.merge(collect_ids({"q": rec.get("query")}))
                    obs.append(o)
                else:
                    o = obs_from_record(rec, src=src, file_time=file_time, t=t, kind=f"export_{group}")
                    if o:
                        obs.append(o)
    return obs, cov


def _bundle(d, src, file_time):
    obs, cov = [], []
    for snap in d["snapshots"]:
        t = norm_time(snap.get("captured_at")) or file_time
        system, collection = snap["data_store"], snap["collection"]
        category = COLLECTION_CATEGORY.get(collection)
        for rec in snap["records"]:
            if collection == "operational_record_history":
                o = _lookup_obs(rec, src, file_time, norm_time(rec.get("recorded_at")) or t, "bundle_history")
            else:
                if collection == "customer_search_documents":
                    rec = {**rec, **(rec.get("document") or {})}
                    rec.pop("document", None)
                o = obs_from_record(rec, src=src, file_time=file_time, t=t, kind="bundle_record",
                                    category=category)
                if o and not o.system_id:
                    o.system_id = system
            if o:
                obs.append(o)
        if category:                          # an explicitly empty snapshot proves absence too
            cov.append(Coverage(src, file_time, t, system, category))
    return obs, cov


def parse_json(path, src, file_time):
    d = json.load(open(path, encoding="utf-8"))
    if "service_exports" in d:
        return _service_export(d, src, file_time)
    if "snapshots" in d:
        return _bundle(d, src, file_time)
    obs, cov = [], []
    t0 = norm_time(d.get("captured_at") or d.get("exported_at")) or file_time
    records = d.get("records", [])
    collection = d.get("collection")
    category = COLLECTION_CATEGORY.get(collection)
    for rec in records:
        if "record_type" in rec and "result" in rec:
            t = norm_time(rec.get("recorded_at")) or t0
            o = _lookup_obs(rec, src, file_time, t, "json_lookup")
        else:
            o = obs_from_record(rec, src=src, file_time=file_time, t=t0, kind="json_record", category=category)
        if o:
            obs.append(o)
    if records and category and (system := _system_for(collection)):
        cov.append(Coverage(src, file_time, t0, system, category))
    return obs, cov


def _system_for(collection):
    return {"customer_export_jobs": "export_service",
            "customer_analytics_reports": "analytics_platform"}.get(collection)
