"""Attribute activity-only account deletions to the requests they belong to.

Many accounts leave no identifier in any evidence file; the only trace is a
deletion_worker DELETE_RECORD row.  Those rows are shared between cases, so a
row is a candidate for a request only when

  * it falls shortly before the request's reported_at,
  * its result agrees with the request's reported_status (the worker result is
    what the workflow then reported), and
  * no other request already owns the account through identifiers.

Matches are then fixed by constraint propagation (a request with a single
candidate, or a row wanted by a single request) and anything still ambiguous
is left unassigned rather than guessed.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime

RESULT_FOR_STATUS = {"COMPLETE": "SUCCESS", "PARTIALLY_COMPLETE": "PARTIAL", "NOT_STARTED": "FAILED"}
MIN_BEFORE, MAX_BEFORE = 40, 80     # minutes before reported_at (roster rows)
NEAR = 10                           # minutes either side (single "Target resource" rows)


def _t(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ")


def _minutes(a, b):
    return (_t(a) - _t(b)).total_seconds() / 60


def assign_accounts(activity: list[dict], needy: list[dict], claimed: set[str]) -> dict[str, str]:
    """needy: requests with no identifier-linked account.  Returns case_id -> account_id."""
    rows = [a for a in activity
            if a["source_system"] == "deletion_worker" and a["event_type"] == "DELETE_RECORD"
            and a["target_system"] == "account_service" and a["resource_id"] not in claimed]
    return _match(rows, needy, status_linked=True)


def assign_targeted(activity: list[dict], cases: list[dict], owned: set[str]) -> dict[str, set]:
    """Single-resource worker rows ("Target resource: x") sitting at a request's reported_at.

    Returns case_id -> resources.  A row counts only when exactly one request is that close."""
    rows = [a for a in activity if a["source_system"] == "deletion_worker"
            and "Target resource:" in a["details"] and a["resource_id"] not in owned]
    out: dict[str, set] = defaultdict(set)
    for a in rows:
        near = [c["case_id"] for c in cases
                if abs(_minutes(a["event_time"], c["reported_at"])) <= NEAR and a["event_time"] <= c["audit_at"]]
        if len(near) == 1:
            out[near[0]].add(a["resource_id"])
    return out


def _match(rows, needy, status_linked, lo=MIN_BEFORE, hi=MAX_BEFORE) -> dict[str, str]:
    out: dict[str, str] = {}
    cand: dict[str, set] = {}
    for c in needy:
        mine = set()
        for a in rows:
            off = _minutes(a["event_time"], c["reported_at"])
            if a["event_time"] > c["audit_at"]:
                continue
            if "Target resource:" in a["details"]:
                if abs(off) <= NEAR:
                    mine.add(a["resource_id"])
            elif -hi <= off <= -lo and (not status_linked
                                        or RESULT_FOR_STATUS.get(c["reported_status"]) == a["reported_result"]):
                mine.add(a["resource_id"])
        cand[c["case_id"]] = mine
    while True:
        taken = set(out.values())
        for k in cand:
            cand[k] -= taken
        pending = {k: v for k, v in sorted(cand.items()) if k not in out and v}
        wanted = defaultdict(list)
        for k, v in pending.items():
            for e in sorted(v):
                wanted[e].append(k)
        picks: dict[str, set] = defaultdict(set)
        for k, v in pending.items():
            if len(v) == 1:                                   # only candidate for this request
                picks[k].add(next(iter(v)))
        for e, ks in wanted.items():
            if len(ks) == 1:                                  # only request that can own this row
                picks[ks[0]].add(e)
        fresh = {}
        for k, es in sorted(picks.items()):
            if len(es) == 1:                                  # two exclusive rows -> ambiguous, skip
                fresh[k] = next(iter(es))
        owners = defaultdict(list)
        for k, e in fresh.items():
            owners[e].append(k)
        fresh = {k: e for k, e in fresh.items() if len(owners[e]) == 1}
        if not fresh:
            return out
        out.update(fresh)
