"""Service log evidence (six different line layouts) -> observations."""
from __future__ import annotations

import json
import re

from ..common import RES_RE, norm_time
from .obs import Ids, Obs, collect_ids, make_obs, valid_resource
from .shape import apply_token, to_bool

KV = re.compile(r'([A-Za-z_]+)=("(?:[^"\\]|\\.)*"|\S+)')
TRACE_RE = re.compile(r"\b((?:tr|rb)-[A-Za-z0-9\-]+)\b")
NULLS = {"null", "none", ""}
# kv keys that never identify the data subject
SKIP_KEYS = {"resource_id", "trace_id", "requestId", "instance", "pod", "region", "level", "service",
             "event", "seq", "rows", "http_status", "duration_ms", "result", "index", "shard",
             "took_ms", "integrity_check", "attempt", "pool", "wait_ms", "latency_ms", "cursor"}


def _kv(text: str) -> dict:
    return {k: v.strip('"') for k, v in KV.findall(text)}


def parse_line(line: str):
    """Return (timestamp, event, kv, trace) or None."""
    line = line.rstrip("\n")
    parts = line.split(" ", 1)
    if len(parts) < 2:
        return None
    t = norm_time(parts[0])
    if not t:
        return None
    rest = parts[1]
    kv: dict = {}
    event = None
    m = re.search(r'message="(.*)"\s*$', rest)
    if m:                                    # cloud runtime export
        kv = _kv(m.group(1).replace('\\"', '"'))
        kv.update({k: v for k, v in _kv(rest[:m.start()]).items() if k not in kv})
    elif rest.startswith("{"):                # structured json lines
        try:
            kv = {k: ("" if v is None else str(v)) for k, v in json.loads(rest).items()}
        except ValueError:
            return None
    elif " | " in rest:                      # pipe layout
        cols = [c.strip() for c in rest.lstrip("| ").split(" | ")]
        kv = _kv(cols[-1])
        if len(cols) >= 5:                   # level | service | trace | event | key=value ...
            kv.setdefault("event", cols[3])
            kv.setdefault("trace_id", cols[2])
            kv.setdefault("service", cols[1])
    else:                                    # kv / syslog / bracket layouts
        kv = _kv(rest)
        b = re.match(r"\[(\w+)\] \[([\w\-]+)\] \[([\w\-]+)\] (\w+): ", rest)
        if b:
            kv.setdefault("event", b.group(4))
            kv.setdefault("trace_id", b.group(3))
            kv.setdefault("service", b.group(2))
    event = kv.get("event")
    trace = kv.get("trace_id") or kv.get("requestId") or ""
    if not trace:
        mt = TRACE_RE.search(rest)
        trace = mt.group(1) if mt else ""
    return t, event, kv, trace


def _ids_from(kv: dict) -> Ids:
    ids = Ids()
    for k, v in kv.items():
        if k in SKIP_KEYS or v.strip().lower() in NULLS:
            continue
        if k in ("lookup_key", "correlation_key", "subject_ref", "subject_reference") and RES_RE.fullmatch(v):
            ids.resources.add(v)
            continue
        collect_ids({k: v}, ids=ids)
    return ids


def _null(kv, key):
    return kv.get(key, "null").strip().lower() in NULLS


def parse_log(path, src, file_time):
    lines = [parse_line(l) for l in open(path, encoding="utf-8")]
    lines = [x for x in lines if x]
    trace_ids: dict[str, Ids] = {}
    for t, event, kv, trace in lines:           # pass 1: identities named at lookup start
        if event and event.endswith("_started") and trace:
            trace_ids.setdefault(trace, Ids()).merge(_ids_from(kv))
    obs: list[Obs] = []
    for t, event, kv, trace in lines:
        rid = valid_resource(kv.get("resource_id"))
        if not rid or not event or event.endswith("_started"):
            continue
        o = make_obs(src, file_time, t, f"log:{event}", rid)
        o.ids = _ids_from(kv)
        if trace in trace_ids:
            o.ids.merge(trace_ids[trace])
        if event == "record_lookup":
            if kv.get("system"):
                o.system_id = kv["system"]
            o.category = kv.get("record_type") or o.category
            apply_token(o, kv.get("result", ""))
        elif event == "profile_lookup_completed":
            o.category = "USER_PROFILE"
            o.present = not (kv.get("rows") == "0" or kv.get("http_status") == "404")
        elif event == "index_query_completed":
            o.category = "SEARCH_INDEX_ENTRY"
            o.present = kv.get("result", "hit") == "hit"
        elif event == "audit_record_read_completed":
            o.present = True
            o.retention_until = kv.get("retention_until")
        elif event in ("analytics_profile_read", "analytics_profile_read_completed"):
            o.present = True
            o.exposed = o.ids.direct() and kv.get("direct_identifiers", "1") != "0"
        elif event == "analytics_identity_scan":
            o.present, o.exposed = True, True
        elif event == "contact_lookup_completed":
            if "email_opt_in" in kv:
                o.category = "MARKETING_PROFILE"
            o.present = kv.get("rows") != "0"
            o.exposed = o.ids.direct()
        elif event in ("message_pii_scan", "attachment_pii_scan"):
            o.present, o.exposed = True, True
            if event == "attachment_pii_scan":
                o.category = "SUPPORT_ATTACHMENT"
        elif event == "message_read":
            o.present = True
            o.exposed = o.ids.direct()
        elif event == "support_ticket_read_completed":
            o.present = True
            o.exposed = o.ids.direct()
        elif event in ("contact_query_completed", "deletion_marker_check"):
            o.category = "SUPPORT_ATTACHMENT"
            o.present = kv.get("rows") != "0" if "rows" in kv else (kv.get("marker_found") == "false")
        elif event == "restore_candidate_evaluated":
            o.present = True
            o.restore_allowed = to_bool(kv.get("eligible")) and not to_bool(kv.get("deletion_block"))
        elif event == "restore_authorization_completed":
            o.present = True
            o.restore_allowed = kv.get("decision") == "allow"
        elif event == "restore_policy_read_completed":
            o.present = to_bool(kv.get("archive_present")) is not False
            o.restore_allowed = to_bool(kv.get("restore_allowed"))
        elif event in ("connector_heartbeat", "connector_config_loaded", "connector_config_read_completed"):
            o.present = True
            o.enabled = to_bool(kv.get("enabled"))
        elif event in ("export_download_check_completed", "export_metadata_read_completed"):
            o.present = to_bool(kv.get("available")) is not False
        elif event == "retained_order_loaded":
            o.present = True
            o.category = "LEGAL_HOLD_RECORD"
        else:
            continue
        obs.append(o)
    return obs, []
