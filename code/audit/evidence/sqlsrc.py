"""SQLite-compatible SQL snapshot exports -> observations + coverage."""
from __future__ import annotations

import json
import re
import sqlite3

from ..common import norm_time
from .obs import COLLECTION_CATEGORY, Coverage, Obs, collect_ids, make_obs, valid_resource
from .shape import obs_from_record

# inventory tables -> (system, category)
INVENTORY = {
    "customer_profiles": ("account_service", "USER_PROFILE"),
    "customer_search_documents": ("search_service", "SEARCH_INDEX_ENTRY"),
    "customer_analytics_profiles": ("analytics_platform", "ANALYTICS_PROFILE"),
    "support_records": ("support_platform", "SUPPORT_MESSAGE"),
    "customer_exports": ("export_service", "USER_EXPORT"),
    "connector_subscriptions": ("integration_service", "DATA_FLOW"),
    "backup_restore_entries": ("backup_service", "BACKUP_ARCHIVE"),
    "security_audit_records": ("security_service", "SECURITY_AUDIT_LOG"),
}
ACCOUNT_TABLES = ("customer_profiles_primary", "customer_profiles_failover_replica")


def _copy_name(table: str) -> str:
    return "primary" if "primary" in table else table


def parse_sql(path, src: str, file_time: str):
    text = open(path, encoding="utf-8").read()
    header = dict(re.findall(r"^--\s*([A-Za-z ]+?):\s*(.+)$", text, re.M))
    snap_t = norm_time(header.get("Captured at")) or file_time
    m = re.search(r"snapshot_completed_at=(\S+)", text)
    if m:
        snap_t = norm_time(m.group(1)) or snap_t
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.executescript(text)
    tables = [r[0] for r in con.execute("select name from sqlite_master where type='table'")]
    obs: list[Obs] = []
    cov: list[Coverage] = []
    scope = {}
    if "snapshot_scope" in tables:
        scope = {r["origin_system"]: norm_time(r["captured_at"]) for r in con.execute("select * from snapshot_scope")}

    for table in tables:
        rows = [dict(r) for r in con.execute(f"select * from {table}")]
        if table == "snapshot_scope":
            continue
        if table in INVENTORY:
            system, category = INVENTORY[table]
            t = scope.get(system, snap_t)
            for rec in rows:
                o = obs_from_record(rec, src=src, file_time=file_time, t=t, kind="sql_inventory",
                                    category=category)
                if o:
                    o.system_id = system
                    obs.append(o)
            if rows and system in scope:
                cov.append(Coverage(src, file_time, t, system, category))
        elif table in ACCOUNT_TABLES:
            for rec in rows:
                rec = dict(rec)
                o = obs_from_record(rec, src=src, file_time=file_time, t=snap_t, kind="sql_account",
                                    category="USER_PROFILE", copy=_copy_name(table))
                if o:
                    o.system_id = "account_service"
                    o.note = rec.get("account_status", "")
                    obs.append(o)
            if rows:
                cov.append(Coverage(src, file_time, snap_t, "account_service", "USER_PROFILE", _copy_name(table)))
        elif table == "search_documents_primary":
            for rec in rows:
                o = obs_from_record(rec, src=src, file_time=file_time, t=snap_t, kind="sql_search",
                                    category="SEARCH_INDEX_ENTRY", copy="primary")
                if o:
                    o.system_id = "search_service"
                    obs.append(o)
            if rows:
                cov.append(Coverage(src, file_time, snap_t, "search_service", "SEARCH_INDEX_ENTRY", "primary"))
        elif "record_json" in (rows[0] if rows else {}):
            seen_cov = set()
            for rec in rows:
                payload = json.loads(rec["record_json"])
                category = COLLECTION_CATEGORY.get(rec["collection_name"])
                payload.setdefault("resource_id", rec["resource_id"])
                o = obs_from_record(payload, src=src, file_time=file_time, t=snap_t, kind="sql_generic",
                                    category=category, copy=_copy_name(table))
                if o:
                    o.system_id = rec["origin_system"] or o.system_id
                    obs.append(o)
                    seen_cov.add((o.system_id, o.category))
            for system, category in seen_cov:
                cov.append(Coverage(src, file_time, snap_t, system, category, _copy_name(table)))
    return obs, cov
