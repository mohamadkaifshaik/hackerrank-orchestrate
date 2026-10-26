"""Audit one deletion request end to end."""
from __future__ import annotations

from .evidence.index import EvidenceIndex
from .identity import IdentityBook
from .linker import linked_resources
from .planner import build_steps
from .roster import assign_accounts, assign_targeted
from .state import resolve_state


def _recent(ix, rid, req) -> bool:
    """False when the resource was last seen before the request was submitted."""
    ts = [o.t for o in ix.by_resource.get(rid, []) if o.t <= req["audit_at"]]
    return not ts or max(ts) >= req["requested_at"]


class Auditor:
    """Holds the shared evidence index and the cross-request account attribution."""

    def __init__(self, ix: EvidenceIndex, book: IdentityBook, all_requests: list[dict]):
        self.ix, self.book = ix, book
        self.scopes = {r["case_id"]: self._identity_scope(r) for r in all_requests}
        claimed = {rid for res in self.scopes.values() for rid in res if rid.startswith("account_")}
        needy = [r for r in all_requests
                 if not any(x.startswith("account_") for x in self.scopes[r["case_id"]])]
        for case_id, rid in assign_accounts(ix.activity, needy, claimed).items():
            self.scopes[case_id][rid] = {"activity"}
        owned = {rid for res in self.scopes.values() for rid in res}
        for case_id, rids in assign_targeted(ix.activity, all_requests, owned).items():
            for rid in rids:
                self.scopes[case_id][rid] = {"activity"}

    def _identity_scope(self, req: dict) -> dict[str, set]:
        uid = self.book.resolve_email(req["email"])
        if uid is None:
            return {}
        res = linked_resources(self.ix, self.book.subjects[uid])   # identity is time-invariant: later files may still name the resource
        return {rid: why for rid, why in res.items() if _recent(self.ix, rid, req)}

    def audit(self, req: dict):
        states = [resolve_state(self.ix, rid, req["audit_at"])
                  for rid in sorted(self.scopes.get(req["case_id"], {}))]
        return build_steps(states)
