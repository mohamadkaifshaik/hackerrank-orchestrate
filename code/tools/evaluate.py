"""Score predictions against known answers (development / reporting only).

    python code/tools/evaluate.py                 # the 32 public samples (in-sample)
    python code/tools/evaluate.py --custom        # hand-built cases in code/evaluation/custom_cases
    python code/tools/evaluate.py -v              # per-case differences

Expected answers are never read by the prediction code.
"""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from audit.case import Auditor
from audit.common import DATASET
from audit.evidence.index import EvidenceIndex
from audit.identity import IdentityBook
from audit.intent import authorizes_deletion
from audit.loaders import load_audit_log, load_identities, load_requests, read_csv

FIELDS = ["step_no", "phase", "system_id", "resource_id", "operation", "state", "evidence_id"]


def key(s):
    return tuple(s[f] for f in FIELDS if f != "step_no")


def lcs(a, b):
    dp = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i, x in enumerate(a):
        for j, y in enumerate(b):
            dp[i + 1][j + 1] = dp[i][j] + 1 if x == y else max(dp[i][j + 1], dp[i + 1][j])
    return dp[-1][-1]


def align(pred, want):
    """Pair steps by (phase, system, resource, operation); returns [(pred_step, want_step)]."""
    ident = lambda s: (s["phase"], s["system_id"], s["resource_id"], s["operation"])
    pool = {}
    for p in pred:
        pool.setdefault(ident(p), []).append(p)
    return [(pool[ident(w)].pop(0) if pool.get(ident(w)) else None, w) for w in want]


def score(preds, wants, verbose=False):
    n = len(wants)
    status_ok = exact = 0
    tp = fp = fn = 0
    field_hit = {f: 0 for f in FIELDS}
    field_tot = 0
    seq_ok = 0
    lcs_sum = lcs_den = 0
    for cid, (st, steps) in preds.items():
        want_st, want = wants[cid]
        status_ok += st == want_st
        a, b = {key(s) for s in steps}, {key(s) for s in want}
        tp += len(a & b); fp += len(a - b); fn += len(b - a)
        exact += steps == want
        ok_order = [key(s) for s in steps] == [key(s) for s in want]
        seq_ok += ok_order
        lcs_sum += lcs([key(s) for s in steps], [key(s) for s in want])
        lcs_den += max(len(steps), len(want))
        for p, w in align(steps, want):
            field_tot += 1
            for f in FIELDS:
                field_hit[f] += p is not None and p[f] == w[f]
        if verbose and (a != b or st != want_st):
            print(f"{cid} {st}/{want_st} extra={sorted(a - b)[:5]} miss={sorted(b - a)[:5]}")
    p_ = tp / max(1, tp + fp); r_ = tp / max(1, tp + fn)
    out = {
        "cases": n,
        "status_accuracy": status_ok / n,
        "exact_case_rows": exact / n,
        "step_precision": p_, "step_recall": r_, "step_f1": 2 * p_ * r_ / max(1e-9, p_ + r_),
        "field_accuracy": {f: field_hit[f] / max(1, field_tot) for f in FIELDS},
        "field_accuracy_mean": sum(field_hit.values()) / max(1, field_tot * len(FIELDS)),
        "sequence_exact": seq_ok / n,
        "sequence_lcs": lcs_sum / max(1, lcs_den),
    }
    return out


def main():
    verbose = "-v" in sys.argv
    custom = "--custom" in sys.argv
    ix = EvidenceIndex()
    book = IdentityBook(load_identities(), load_audit_log())
    pool = load_requests("sample_deletion_requests.csv") + load_requests("deletion_requests.csv")
    if custom:
        base = ROOT / "evaluation" / "custom_cases"
        reqs = [dict(r) for r in read_csv(base / "requests.csv")]
        from audit.common import norm_time
        for r in reqs:
            for k in ("requested_at", "reported_at", "audit_at"):
                r[k] = norm_time(r[k])
        exp_rows = read_csv(base / "expected.csv")
    else:
        reqs = load_requests("sample_deletion_requests.csv")
        exp_rows = read_csv(DATASET / "sample_output.csv")
    if custom:   # a custom case restates a public request: drop the original so they don't compete
        dup = {(book.resolve_email(r["email"]), r["reported_at"]) for r in reqs}
        pool = [r for r in pool if (book.resolve_email(r["email"]), r["reported_at"]) not in dup] + reqs
    aud = Auditor(ix, book, pool)
    wants = {r["case_id"]: (r["deletion_status"], json.loads(r["steps_json"])) for r in exp_rows}
    preds = {}
    for r in reqs:
        preds[r["case_id"]] = aud.audit(r) if authorizes_deletion(r["request_text"]) else ("NOT_APPLICABLE", [])
    print(json.dumps(score(preds, wants, verbose), indent=1))


if __name__ == "__main__":
    main()
