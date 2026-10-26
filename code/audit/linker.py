"""Link resources to a subject through shared identifiers."""
from __future__ import annotations

from .evidence.index import EvidenceIndex
from .evidence.obs import Obs
from .identity import Subject


def obs_matches(o: Obs, s: Subject) -> bool:
    ids = o.ids
    return bool(
        (ids.emails & s.emails)
        or (ids.hashes & s.hashes)
        or (ids.phones & s.phones)
        or (s.user_id in ids.users)
    )


def linked_resources(ix: EvidenceIndex, s: Subject, audit_at: str | None = None) -> dict[str, set[str]]:
    """resource_id -> set of reasons ('obs:<src>', 'link:<activity>')."""
    reasons: dict[str, set[str]] = {}
    known = [o for o in ix.obs if audit_at is None or o.file_time <= audit_at]
    for o in known:
        if o.resource_id and obs_matches(o, s):
            reasons.setdefault(o.resource_id, set()).add(f"obs:{o.src}")
    for act_id, t, rid, email, user in ix.links:
        if audit_at is not None and t > audit_at:
            continue
        if user == s.user_id or email in s.emails:
            reasons.setdefault(rid, set()).add(f"link:{act_id}")
    # follow explicit resource-to-resource links (e.g. search doc -> source account)
    changed = True
    while changed:
        changed = False
        for o in known:
            if not o.ids.resources or not o.resource_id:
                continue
            if o.resource_id in reasons:
                for r in o.ids.resources:
                    if r not in reasons:
                        reasons[r] = {f"via:{o.resource_id}"}
                        changed = True
            else:
                hit = o.ids.resources & set(reasons)
                if hit:
                    reasons[o.resource_id] = {f"via:{sorted(hit)[0]}"}
                    changed = True
    return reasons
