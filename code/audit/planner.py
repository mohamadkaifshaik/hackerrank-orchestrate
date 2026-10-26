"""Turn resource states into the ordered finding/remediation/verification steps."""
from __future__ import annotations

import json

from .state import ANON_CATS, DELETE_CATS, REDACT_CATS, RETAIN_CATS, ResState

FINDING = {"REMAINING": ("REPORT_REMAINING_RECORD", "PRESENT"),
           "EXPOSED": ("REPORT_EXPOSED_PII", "PRESENT"),
           "FLOW": ("REPORT_ACTIVE_DATA_FLOW", "ACTIVE"),
           "RESTORE": ("REPORT_RESTORE_RISK", "ACTIVE")}
FIX = {"FLOW": ("DISABLE_DATA_FLOW", "DISABLED"),
       "RESTORE": ("BLOCK_RESTORE", "BLOCKED")}
ORDER = {"FINDING": ["REPORT_REMAINING_RECORD", "REPORT_EXPOSED_PII",
                     "REPORT_ACTIVE_DATA_FLOW", "REPORT_RESTORE_RISK"],
         "REMEDIATION": ["DISABLE_DATA_FLOW", "BLOCK_RESTORE", "DELETE_RECORD",
                         "REDACT_RECORD", "ANONYMIZE_RECORD"],
         "VERIFICATION": ["VERIFY_RECORD_ABSENT", "VERIFY_RECORD_PRESENT", "VERIFY_RECORD_REDACTED",
                          "VERIFY_RECORD_ANONYMIZED", "VERIFY_DATA_FLOW_DISABLED",
                          "VERIFY_RESTORE_BLOCKED"]}


def _fix(st: ResState):
    if st.violation in FIX:
        return FIX[st.violation]
    if st.category in DELETE_CATS:
        return "DELETE_RECORD", "ABSENT"
    if st.category in REDACT_CATS:
        return "REDACT_RECORD", "REDACTED"
    if st.category in ANON_CATS:
        return "ANONYMIZE_RECORD", "ANONYMIZED"
    return None


def _verify(st: ResState):
    c = st.category
    if c in DELETE_CATS:
        return "VERIFY_RECORD_ABSENT", "ABSENT"
    if c in REDACT_CATS:
        return "VERIFY_RECORD_REDACTED", "REDACTED"
    if c in ANON_CATS:
        return "VERIFY_RECORD_ANONYMIZED", "ANONYMIZED"
    if c in RETAIN_CATS:
        return "VERIFY_RECORD_PRESENT", "PRESENT"
    if c == "DATA_FLOW":
        return "VERIFY_DATA_FLOW_DISABLED", "DISABLED"
    if c == "BACKUP_ARCHIVE":
        return "VERIFY_RESTORE_BLOCKED", "BLOCKED"
    return None


def build_steps(states: list[ResState]) -> tuple[str, list[dict]]:
    bad = [s for s in states if s.violation]
    status = "INCOMPLETE" if bad else "COMPLETE"
    raw = []  # (phase, op, state, system, resource, evidence)
    if bad:
        for s in bad:
            op, state = FINDING[s.violation]
            raw.append(("FINDING", op, state, s.system_id, s.resource_id, s.finding_src or ""))
            fix = _fix(s)
            if fix:
                raw.append(("REMEDIATION", fix[0], fix[1], s.system_id, s.resource_id, ""))
    for s in states:
        v = None if s.lapsed else _verify(s)
        if v:
            ev = "" if bad else (s.proof_src or "")
            raw.append(("VERIFICATION", v[0], v[1], s.system_id, s.resource_id, ev))
    phases = list(ORDER)
    raw.sort(key=lambda r: (phases.index(r[0]), ORDER[r[0]].index(r[1]), r[3], r[4]))
    steps = [{"step_no": i + 1, "phase": p, "system_id": sy, "resource_id": rid,
              "operation": op, "state": stt, "evidence_id": ev}
             for i, (p, op, stt, sy, rid, ev) in enumerate(raw)]
    return status, steps


def dumps(steps: list[dict]) -> str:
    return json.dumps(steps, separators=(",", ":"), ensure_ascii=False)
