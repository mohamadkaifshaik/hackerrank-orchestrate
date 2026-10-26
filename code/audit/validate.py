"""Output-contract checks."""
from __future__ import annotations

import json

PHASES = ["FINDING", "REMEDIATION", "VERIFICATION"]
FIELDS = {"step_no", "phase", "system_id", "resource_id", "operation", "state", "evidence_id"}
ALLOWED = {
    "REPORT_REMAINING_RECORD": "PRESENT", "REPORT_EXPOSED_PII": "PRESENT",
    "REPORT_ACTIVE_DATA_FLOW": "ACTIVE", "REPORT_RESTORE_RISK": "ACTIVE",
    "DISABLE_DATA_FLOW": "DISABLED", "BLOCK_RESTORE": "BLOCKED", "DELETE_RECORD": "ABSENT",
    "REDACT_RECORD": "REDACTED", "ANONYMIZE_RECORD": "ANONYMIZED",
    "VERIFY_RECORD_ABSENT": "ABSENT", "VERIFY_RECORD_PRESENT": "PRESENT",
    "VERIFY_RECORD_REDACTED": "REDACTED", "VERIFY_RECORD_ANONYMIZED": "ANONYMIZED",
    "VERIFY_DATA_FLOW_DISABLED": "DISABLED", "VERIFY_RESTORE_BLOCKED": "BLOCKED",
}


def check_row(case_id: str, status: str, steps_json: str) -> list[str]:
    errs = []
    if status not in ("COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"):
        errs.append(f"{case_id}: bad status {status}")
    try:
        steps = json.loads(steps_json)
    except ValueError:
        return errs + [f"{case_id}: steps_json is not JSON"]
    if status == "NOT_APPLICABLE" and steps:
        errs.append(f"{case_id}: NOT_APPLICABLE must have empty steps")
    last = -1
    for i, s in enumerate(steps, 1):
        if set(s) != FIELDS:
            errs.append(f"{case_id}: step {i} fields")
        if s.get("step_no") != i:
            errs.append(f"{case_id}: step_no {i}")
        if ALLOWED.get(s.get("operation")) != s.get("state"):
            errs.append(f"{case_id}: step {i} operation/state")
        ph = PHASES.index(s["phase"]) if s.get("phase") in PHASES else -1
        if ph < last or ph < 0:
            errs.append(f"{case_id}: step {i} phase order")
        last = max(last, ph)
    return errs


def evidence_times(manifest, activity, audit_log) -> dict[str, str]:
    """citable id -> the time it came into existence."""
    times = {fid: r["captured_at"] for fid, r in manifest.items()}
    times.update({a["activity_id"]: a["event_time"] for a in activity})
    times.update({a["audit_id"]: a["event_time"] for a in audit_log})
    return times


def check_all(rows, requests, times) -> list[str]:
    """Cross-row checks: coverage of case ids, citations, status/step consistency."""
    errs = []
    by_case = {r["case_id"]: r for r in requests}
    ids = [r[0] for r in rows]
    if set(ids) != set(by_case) or len(ids) != len(set(ids)):
        errs.append("case_id set differs from the input requests")
    for case_id, status, sj in rows:
        steps = json.loads(sj)
        audit_at = by_case[case_id]["audit_at"]
        phases = {s["phase"] for s in steps}
        if status != "NOT_APPLICABLE" and not steps:
            errs.append(f"{case_id}: deletion case without steps")
        if status == "INCOMPLETE" and "FINDING" not in phases:
            errs.append(f"{case_id}: INCOMPLETE without findings")
        if status == "COMPLETE" and phases != {"VERIFICATION"}:
            errs.append(f"{case_id}: COMPLETE must contain only verification steps")
        for s in steps:
            ev = s["evidence_id"]
            cited = s["phase"] == "FINDING" or status == "COMPLETE"
            if cited and not ev:
                errs.append(f"{case_id}: step {s['step_no']} lacks evidence_id")
            if not cited and ev:
                errs.append(f"{case_id}: step {s['step_no']} must not cite evidence")
            if ev and (ev not in times or times[ev] > audit_at):
                errs.append(f"{case_id}: step {s['step_no']} cites {ev} unknown or after audit_at")
    return errs
