"""Reconstruct the state of each in-scope resource at a case's audit_at."""
from __future__ import annotations

from dataclasses import dataclass, field

from .common import default_category, system_of
from .evidence.index import EvidenceIndex
from .evidence.obs import Obs

DELETE_CATS = {"USER_PROFILE", "SECONDARY_IDENTIFIER", "SEARCH_INDEX_ENTRY", "USER_EXPORT", "SUPPORT_ATTACHMENT",
               "MARKETING_PROFILE", "CACHE_ENTRY"}
REDACT_CATS = {"SUPPORT_MESSAGE", "EMAIL_DELIVERY_LOG", "ACCOUNT_TOMBSTONE"}
ANON_CATS = {"ANALYTICS_PROFILE", "PRODUCT_TELEMETRY"}
RETAIN_CATS = {"SECURITY_AUDIT_LOG", "LEGAL_HOLD_RECORD"}


@dataclass
class ResState:
    resource_id: str
    system_id: str
    category: str
    violation: str | None = None          # REMAINING | EXPOSED | FLOW | RESTORE | None
    finding_src: str | None = None        # evidence id proving the violation
    proof_src: str | None = None          # evidence id proving the compliant state
    lapsed: bool = False                  # retained category whose retention period had ended at audit_at
    seen: bool = False                    # any observation at or before audit_at
    notes: list = field(default_factory=list)


def usable(o: Obs, audit_at: str) -> bool:
    return o.t <= audit_at and o.file_time <= audit_at


def _latest(obs: list[Obs], pred) -> Obs | None:
    best = None
    for o in obs:
        if pred(o) and (best is None or (o.t, o.file_time) >= (best.t, best.file_time)):
            best = o
    return best


def category_of(rid: str, obs: list[Obs]) -> str:
    labelled = [o for o in obs if o.category]
    # prefer an explicit label that differs from the prefix default
    for o in sorted(labelled, key=lambda o: o.t, reverse=True):
        if o.category != default_category(rid):
            return o.category
    return default_category(rid) or "USER_PROFILE"


def resolve_state(ix: EvidenceIndex, rid: str, audit_at: str) -> ResState:
    allobs = ix.by_resource.get(rid, [])
    obs = [o for o in allobs if usable(o, audit_at)]
    cat = category_of(rid, obs or allobs)
    st = ResState(rid, system_of(rid) or "unknown", cat)
    if not obs:
        st.proof_src = coverage_proof(ix, st, audit_at)
        return st
    st.seen = True

    if cat in DELETE_CATS:
        pres = _latest(obs, lambda o: o.present is not None)
        if pres is not None and pres.present:
            st.violation, st.finding_src = "REMAINING", pres.src
        elif pres is not None:
            st.proof_src = pres.src
    elif cat in REDACT_CATS or cat in ANON_CATS:
        ex = _latest(obs, lambda o: o.exposed is not None and o.present is not False)
        if ex is not None and ex.exposed:
            st.violation, st.finding_src = "EXPOSED", ex.src
        elif ex is not None:
            st.proof_src = ex.src
    elif cat == "DATA_FLOW":
        fl = _latest(obs, lambda o: o.enabled is not None)
        if fl is not None and fl.enabled:
            st.violation, st.finding_src = "FLOW", fl.src
        elif fl is not None:
            st.proof_src = fl.src
    elif cat == "BACKUP_ARCHIVE":
        rs = _latest(obs, lambda o: o.restore_allowed is not None)
        if rs is not None and rs.restore_allowed:
            st.violation, st.finding_src = "RESTORE", rs.src
        elif rs is not None:
            st.proof_src = rs.src
        else:
            # the archive is shown but nothing proves restore is blocked: it cannot count as safe
            # rule_14 retains an archive only while restore can be blocked; an archive whose
            # retention already ended at audit_at is gone, so only live ones are flagged
            seen = _latest(obs, lambda o: o.present and not (o.retention_until and o.retention_until < audit_at))
            if seen is not None:
                st.violation, st.finding_src = "RESTORE", seen.src
                st.notes.append("restore state not shown; treated as unproven")
    elif cat in RETAIN_CATS:
        pr = _latest(obs, lambda o: o.present is not False)
        if pr is not None:
            st.proof_src = pr.src
            st.lapsed = bool(pr.retention_until and pr.retention_until < audit_at)   # rule_12: only within retention
    return st


def coverage_proof(ix: EvidenceIndex, st: ResState, audit_at: str) -> str | None:
    """Latest listing snapshot of the resource's system that does not contain it."""
    best = None
    for c in ix.coverage:
        if c.system_id != st.system_id or c.t > audit_at or c.file_time > audit_at:
            continue
        if c.category and c.category != st.category:
            continue
        if best is None or (c.t, c.file_time) > (best.t, best.file_time):
            best = c
    return best.src if best else None
