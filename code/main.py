"""Deletion-audit agent CLI.

    python code/main.py                       # all requests -> output.csv at the repo root
    python code/main.py --case case_07        # print one case's steps
    python code/main.py --input sample_deletion_requests.csv --output out_samples.csv
    python code/main.py --llm                 # ANTHROPIC_API_KEY set: ask a model only for ambiguous texts
    python code/tools/evaluate.py             # score the public samples
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from audit.case import Auditor
from audit.common import DATASET, REPO_ROOT
from audit.evidence.index import EvidenceIndex
from audit.identity import IdentityBook
from audit.intent import authorizes_deletion
from audit.loaders import load_audit_log, load_identities, load_requests
from audit.planner import dumps
from audit.validate import check_all, check_row, evidence_times


def run_case(aud, req, llm=None):
    if not authorizes_deletion(req["request_text"], llm):
        return "NOT_APPLICABLE", []
    return aud.audit(req)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="deletion_requests.csv")
    ap.add_argument("--output", default=str(REPO_ROOT / "output.csv"))
    ap.add_argument("--case")
    ap.add_argument("--llm", action="store_true", help="resolve ambiguous request texts with a model")
    args = ap.parse_args()

    llm = None
    if args.llm:
        from audit.llm import LLM
        llm = LLM()
        if not llm.available:
            print("--llm ignored: ANTHROPIC_API_KEY is not set")
            llm = None
    ix = EvidenceIndex()
    book = IdentityBook(load_identities(), load_audit_log())
    pool = load_requests("sample_deletion_requests.csv") + load_requests("deletion_requests.csv")
    aud = Auditor(ix, book, pool)   # account attribution looks at every request at once
    reqs = sorted(load_requests(args.input), key=lambda r: (len(r["case_id"]), r["case_id"]))
    if args.case:
        for r in reqs:
            if r["case_id"] == args.case:
                st, steps = run_case(aud, r, llm)
                print(st)
                for s in steps:
                    print(json.dumps(s))
        return
    rows, errs = [], []
    for r in reqs:
        st, steps = run_case(aud, r, llm)
        sj = dumps(steps)
        errs += check_row(r["case_id"], st, sj)
        rows.append((r["case_id"], st, sj))
    times = evidence_times(ix.manifest, ix.activity, load_audit_log())
    errs += check_all(rows, reqs, times)
    with open(args.output, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["case_id", "deletion_status", "steps_json"])
        w.writerows(rows)
    counts = {}
    for _, st, _ in rows:
        counts[st] = counts.get(st, 0) + 1
    print(f"wrote {len(rows)} rows to {args.output}: {counts}")
    if errs:
        print("VALIDATION ERRORS:", *errs[:20], sep="\n  ")
        sys.exit(1)


if __name__ == "__main__":
    main()
