"""Independent end-to-end scenarios.

Builds a tiny private dataset (fictional users, hand-written evidence) in a temp directory, points the
pipeline at it with GHOST_DATASET and runs the real CLI.  Expected rows below were derived by hand from
deletion_rules.csv and the evidence written here; they are not copied from any sample answer.

    python code/evaluation/scenarios/run_scenarios.py
"""
import csv
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEL = "Please permanently delete my account and personal data."


def w(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def csv_text(header, rows):
    return ",".join(header) + "\n" + "".join(",".join(f'"{c}"' for c in r) + "\n" for r in rows)


def lookup(rid, system, rtype, result, subject, at):
    return {"recorded_at": at, "system": system, "resource_id": rid, "record_type": rtype,
            "result": result, "subject_reference": subject}


def build(d: Path):
    users = [("user_901", "Ana Costa", "ana.costa@mail.test"), ("user_902", "Ben Okoye", "ben.okoye@mail.test"),
             ("user_903", "Chi Wu", "chi.wu@mail.test"), ("user_904", "Dana Ruiz", "dana.ruiz@mail.test"),
             ("user_905", "Eli Marsh", "eli.marsh@mail.test")]
    w(d / "user_identities.csv", csv_text(["user_id", "name", "email", "phone", "email_hash", "updated_at"],
      [(u, n, e, f"+1 555 000 {i:04d}", chr(97 + i) * 64, "2026-03-01T00:00:00Z") for i, (u, n, e) in enumerate(users)]))
    w(d / "user_audit_log.csv", csv_text(["audit_id", "user_id", "event_time", "field_name", "old_value", "new_value"],
      [("audit_s1", "user_901", "2026-03-01T00:00:00Z", "email", "ana.old@mail.test", "ana.costa@mail.test")]))
    w(d / "system_activity.csv", "activity_id,event_time,event_type,source_system,target_system,resource_id,reported_result,details\n")
    shutil.copy(ROOT / "dataset" / "deletion_rules.csv", d / "deletion_rules.csv")
    # s1: historical e-mail, account still present, audit record retained
    j1 = {"exported_at": "2026-06-05T09:00:00Z", "records": [
        lookup("account_9001", "account_service", "USER_PROFILE", "FOUND", "ana.old@mail.test", "2026-06-05T09:00:00Z"),
        lookup("audit_record_9001", "security_service", "SECURITY_AUDIT_LOG", "FOUND", "user_901", "2026-06-05T09:00:00Z")]}
    # s2: present early, gone before audit_at, present again only after audit_at
    j2a = {"exported_at": "2026-06-02T09:00:00Z", "records": [
        lookup("account_9002", "account_service", "USER_PROFILE", "FOUND", "ben.okoye@mail.test", "2026-06-02T09:00:00Z")]}
    j2b = {"exported_at": "2026-06-08T09:00:00Z", "records": [
        lookup("account_9002", "account_service", "USER_PROFILE", "NOT_FOUND", "ben.okoye@mail.test", "2026-06-08T09:00:00Z")]}
    j2c = {"exported_at": "2026-06-20T09:00:00Z", "records": [
        lookup("account_9002", "account_service", "USER_PROFILE", "FOUND", "ben.okoye@mail.test", "2026-06-20T09:00:00Z")]}
    # s3: account gone, archive listed with no restore information
    j3 = {"exported_at": "2026-06-05T09:00:00Z", "records": [
        lookup("account_9003", "account_service", "USER_PROFILE", "NOT_FOUND", "chi.wu@mail.test", "2026-06-05T09:00:00Z"),
        lookup("backup_9003", "backup_service", "BACKUP_ARCHIVE", "FOUND", "chi.wu@mail.test", "2026-06-05T09:00:00Z")]}
    # s4: one audit record within retention, one whose retention has lapsed
    j4 = {"exported_at": "2026-06-05T09:00:00Z", "records": [
        lookup("account_9004", "account_service", "USER_PROFILE", "NOT_FOUND", "dana.ruiz@mail.test", "2026-06-05T09:00:00Z")]}
    log4 = "\n".join([
        "2026-06-05T10:00:00Z level=INFO service=security_service event=audit_record_query_started trace_id=tr-4001 subject_ref=user_904",
        "2026-06-05T10:00:02Z level=INFO service=security_service event=audit_record_read_completed trace_id=tr-4001 resource_id=audit_record_9004 retention_until=2027-06-05T10:00:00Z",
        "2026-06-05T10:01:00Z level=INFO service=security_service event=audit_record_query_started trace_id=tr-4002 subject_ref=user_904",
        "2026-06-05T10:01:02Z level=INFO service=security_service event=audit_record_read_completed trace_id=tr-4002 resource_id=audit_record_9005 retention_until=2026-01-01T00:00:00Z"]) + "\n"
    files = [("scn_e1", "evidence/records/s1.json", json.dumps(j1), "2026-06-05T09:00:00Z"),
             ("scn_e2", "evidence/records/s2a.json", json.dumps(j2a), "2026-06-02T09:00:00Z"),
             ("scn_e3", "evidence/records/s2b.json", json.dumps(j2b), "2026-06-08T09:00:00Z"),
             ("scn_e4", "evidence/records/s2c.json", json.dumps(j2c), "2026-06-20T09:00:00Z"),
             ("scn_e5", "evidence/records/s3.json", json.dumps(j3), "2026-06-05T09:00:00Z"),
             ("scn_e6", "evidence/records/s4.json", json.dumps(j4), "2026-06-05T09:00:00Z"),
             ("scn_e7", "evidence/logs/s4.log", log4, "2026-06-05T10:02:00Z")]
    for _, rel, text, _t in files:
        w(d / rel, text)
    w(d / "evidence_files.csv", csv_text(["file_id", "file_path", "origin", "captured_at"],
      [(f, r, "scenario", t) for f, r, _, t in files]))
    hdr = ["case_id", "email", "requested_at", "reported_status", "reported_at", "audit_at", "request_text"]
    base = ("2026-06-01T00:00:00Z", "COMPLETE", "2026-06-03T00:00:00Z", "2026-06-10T00:00:00Z")
    reqs = [("scn_1", "ana.old@mail.test", *base, DEL), ("scn_2", "ben.okoye@mail.test", *base, DEL),
            ("scn_3", "chi.wu@mail.test", *base, DEL), ("scn_4", "dana.ruiz@mail.test", *base, DEL),
            ("scn_5", "eli.marsh@mail.test", *base,
             "Please update my phone number. I am not asking for deletion and want to keep the account.")]
    w(d / "deletion_requests.csv", csv_text(hdr, reqs))
    w(d / "sample_deletion_requests.csv", csv_text(hdr, []))


def S(n, ph, sy, rid, op, st, ev=""):
    return {"step_no": n, "phase": ph, "system_id": sy, "resource_id": rid, "operation": op, "state": st, "evidence_id": ev}


EXPECTED = {
    # historical e-mail resolves; account present -> delete; audit record kept
    "scn_1": ("INCOMPLETE", [
        S(1, "FINDING", "account_service", "account_9001", "REPORT_REMAINING_RECORD", "PRESENT", "scn_e1"),
        S(2, "REMEDIATION", "account_service", "account_9001", "DELETE_RECORD", "ABSENT"),
        S(3, "VERIFICATION", "account_service", "account_9001", "VERIFY_RECORD_ABSENT", "ABSENT"),
        S(4, "VERIFICATION", "security_service", "audit_record_9001", "VERIFY_RECORD_PRESENT", "PRESENT")]),
    # state at audit_at is the 06-08 NOT_FOUND; the 06-20 file is later and must not be cited
    "scn_2": ("COMPLETE", [
        S(1, "VERIFICATION", "account_service", "account_9002", "VERIFY_RECORD_ABSENT", "ABSENT", "scn_e3")]),
    # archive with no restore information cannot be shown safe
    "scn_3": ("INCOMPLETE", [
        S(1, "FINDING", "backup_service", "backup_9003", "REPORT_RESTORE_RISK", "ACTIVE", "scn_e5"),
        S(2, "REMEDIATION", "backup_service", "backup_9003", "BLOCK_RESTORE", "BLOCKED"),
        S(3, "VERIFICATION", "account_service", "account_9003", "VERIFY_RECORD_ABSENT", "ABSENT"),
        S(4, "VERIFICATION", "backup_service", "backup_9003", "VERIFY_RESTORE_BLOCKED", "BLOCKED")]),
    # rule_12 protects only records within retention: 9004 verified, lapsed 9005 not required
    "scn_4": ("COMPLETE", [
        S(1, "VERIFICATION", "account_service", "account_9004", "VERIFY_RECORD_ABSENT", "ABSENT", "scn_e6"),
        S(2, "VERIFICATION", "security_service", "audit_record_9004", "VERIFY_RECORD_PRESENT", "PRESENT", "scn_e7")]),
    "scn_5": ("NOT_APPLICABLE", []),
}


def main():
    tmp = Path(tempfile.mkdtemp(prefix="ghost_scn_"))
    try:
        build(tmp / "dataset")
        env = {**os.environ, "GHOST_DATASET": str(tmp / "dataset")}
        out = tmp / "out.csv"
        r = subprocess.run([sys.executable, "-X", "utf8", "-I", str(ROOT / "code" / "main.py"), "--output", str(out)],
                           env=env, capture_output=True, text=True)
        print(r.stdout.strip(), r.stderr.strip()[-500:])
        got = {x["case_id"]: x for x in csv.DictReader(open(out, encoding="utf-8"))}
        bad = 0
        for cid, (st, steps) in EXPECTED.items():
            g = got.get(cid)
            ok = g and g["deletion_status"] == st and json.loads(g["steps_json"]) == steps
            bad += not ok
            print(("PASS " if ok else "FAIL ") + cid)
            if not ok and g:
                print("   got ", g["deletion_status"], g["steps_json"][:700])
                print("   want", st, json.dumps(steps)[:700])
        sys.exit(1 if bad else 0)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
