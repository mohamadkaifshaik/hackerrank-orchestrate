"""Decide whether a request authorizes deletion.

Deterministic multilingual rules first.  A text that mixes deletion words with an
explicit refusal is ambiguous; those go to an optional LLM hook (audit.llm) and,
when no model is configured, are treated as NOT authorizing deletion (the
conservative reading: never delete on an unclear request).
"""
from __future__ import annotations

import re

DELETE = re.compile(
    r"delet|eras(e|ure)|remov|wipe|purg|forget|close (my|this|the) account|closed (my|this) account|"
    r"exclus[aã]o|exclu[ií]r|eliminaci[oó]n|eliminar|borrar|suppression|supprim|"
    r"l[öo]schung|l[öo]schen|cancellazione|eliminazione|cancella|削除|消去|삭제|删除|刪除|"
    r"удал|verwijder|usuni|is gone|was gone|cannot identify me|no longer (identify|point)", re.I)
REFUSAL = re.compile(
    r"not asking for (a )?(deletion|erasure)|not a request to (erase|delete)|"
    r"(do not|don't|dont|do n't|please don't) (close|delete|erase|remove|change)|"
    r"(leave|keep) (the |my )?(account|profile)|without (removing|deleting)|"
    r"lists only|only from marketing|continue using|still (need|want|use|have)|"
    r"leave .* in place", re.I)


def classify(text: str) -> str:
    """Return 'DELETE', 'NOT_DELETE' or 'AMBIGUOUS'."""
    t = text or ""
    has_del, has_ref = bool(DELETE.search(t)), bool(REFUSAL.search(t))
    if not has_del:
        return "NOT_DELETE"
    if has_ref:
        return "NOT_DELETE" if _only_refusal(t) else "AMBIGUOUS"
    return "DELETE"


def _only_refusal(t: str) -> bool:
    """Refusal wording that explicitly negates the deletion verb (e.g. 'not asking for deletion')."""
    return bool(re.search(
        r"not asking for (a )?(deletion|erasure)|not a request to (erase|delete)|"
        r"(do not|don't|dont) (close|delete|erase|remove)|without (removing|deleting)|"
        r"lists only|leave .* in place", t, re.I))


def authorizes_deletion(text: str, llm=None) -> bool:
    c = classify(text)
    if c == "AMBIGUOUS" and llm is not None:
        return llm.is_deletion_request(text)
    return c == "DELETE"
