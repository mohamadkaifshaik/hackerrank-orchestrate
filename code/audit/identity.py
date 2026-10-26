"""Identity resolution: current + historical identifiers per user_id."""
from __future__ import annotations

from dataclasses import dataclass, field

from .common import norm_email, norm_phone


@dataclass
class Subject:
    user_id: str
    names: set[str] = field(default_factory=set)
    emails: set[str] = field(default_factory=set)
    phones: set[str] = field(default_factory=set)
    hashes: set[str] = field(default_factory=set)
    current_email: str = ""

    def has_identifier(self, *, email=None, phone=None, hash_=None, user=None) -> bool:
        return bool(
            (email and norm_email(email) in self.emails)
            or (phone and norm_phone(phone) in self.phones)
            or (hash_ and hash_.lower() in self.hashes)
            or (user and user == self.user_id)
        )


class IdentityBook:
    def __init__(self, identities: list[dict], audit_log: list[dict]):
        self.subjects: dict[str, Subject] = {}
        self.by_email: dict[str, set[str]] = {}
        for row in identities:
            s = Subject(user_id=row["user_id"])
            s.names.add(row["name"].strip().lower())
            s.emails.add(norm_email(row["email"]))
            s.current_email = norm_email(row["email"])
            s.phones.add(norm_phone(row["phone"]))
            s.hashes.add(row["email_hash"].lower())
            self.subjects[s.user_id] = s
        for a in audit_log:
            s = self.subjects.get(a["user_id"])
            if not s:
                continue
            for v in (a["old_value"], a["new_value"]):
                if not v:
                    continue
                if a["field_name"] == "email":
                    s.emails.add(norm_email(v))
                elif a["field_name"] == "email_hash":
                    s.hashes.add(v.lower())
                elif a["field_name"] == "phone":
                    s.phones.add(norm_phone(v))
        for s in self.subjects.values():
            for e in s.emails:
                self.by_email.setdefault(e, set()).add(s.user_id)

    def resolve_email(self, email: str) -> str | None:
        """Return the user_id owning this (current or historical) email, if unique."""
        hits = self.by_email.get(norm_email(email), set())
        if len(hits) == 1:
            return next(iter(hits))
        return None
