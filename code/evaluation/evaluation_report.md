# Evaluation report

All numbers come from `python code/tools/evaluate.py` (public samples) and
`python code/tools/evaluate.py --custom` (hand-built cases). The scorer reads expected answers
only for scoring; prediction code never touches `sample_output.csv`.

> **In-sample caveat.** The 32 public samples were used while building the system (linking rules,
> citation rules, attribution windows). Treat the sample scores as a development score, not a
> held-out estimate. The 518 evaluation cases have no answers available to us.

## 1. Public samples (32 cases, in-sample)

| Metric | Value |
|---|---|
| Case-level deletion-status accuracy | 32 / 32 = 1.000 |
| Rows exactly equal to the expected row | 21 / 32 = 0.656 |
| Step precision | 1.000 |
| Step recall | 0.938 |
| Step F1 | 0.968 |
| Sequence accuracy (whole ordered step list equal) | 21 / 32 = 0.656 |
| Sequence accuracy (LCS ratio over ordered steps) | 0.938 |

Field-level accuracy over expected steps (a step counts when the same phase/system/resource/operation
exists in the prediction; an unmatched expected step counts as wrong for every field):

| Field | Accuracy |
|---|---|
| phase, system_id, resource_id, operation, state, evidence_id | 0.938 each |
| step_no | 0.829 (a missing step shifts the numbering of the steps after it) |
| mean over the 7 fields | 0.922 |

Every predicted step is correct (precision 1.0). The 11 non-exact rows are all missing steps, never wrong ones:

* analytics profiles that are already anonymized and carry no identifier in any file (6 steps);
* accounts whose only trace is a deletion-worker row shared by two or more requests with identical timing and status, so the owner cannot be told apart (3 steps);
* three `audit_record_*`/`account_*` ids that appear nowhere in participant data (3 steps).

## 2. Custom cases (4, `code/evaluation/custom_cases/`)

Expected answers were not produced by running the pipeline. Each case restates a public request with
one controlled change, so the correct answer is the published answer for the original case (or `[]`
for the non-deletion text). `evaluate.py --custom` drops the original request from the shared pool so
the two do not compete for the same worker row.

| Case | Change | Expected | Result |
|---|---|---|---|
| custom_01 | request sent from the *oldest* historical e-mail of case_10's subject | same as case_10 | pass |
| custom_02 | request text in Spanish | same as case_01 | pass |
| custom_03 | "send me a copy of my data, do not delete anything" on case_07's account | `NOT_APPLICABLE`, `[]` | pass |
| custom_04 | request sent from the *current* e-mail instead of the historical one (case_30) | same as case_30 | pass |

Result: status 4/4, exact rows 4/4, step F1 1.000.

## 2b. Independent end-to-end scenarios (5, `code/evaluation/scenarios/run_scenarios.py`)

A private mini dataset (fictional users, hand-written evidence, copy of `deletion_rules.csv`) is built in a
temp directory and the real CLI is run on it (`GHOST_DATASET` points the loaders at it). Expected rows were
derived by hand from the rules and the evidence, before running anything.

| Scenario | Covers | Result |
|---|---|---|
| scn_1 | request from a *historical* e-mail; account still present; retained audit record | pass |
| scn_2 | conflicting timestamps: present, then gone before `audit_at`, present again in a file captured after it | pass (later file neither used nor cited) |
| scn_3 | ambiguous evidence: archive listed with no restore information | pass (restore risk) |
| scn_4 | retention: one audit record within retention, one lapsed | **failed first run**, pass after fix |
| scn_5 | non-deletion request with an explicit refusal | pass |

Genuine defect found and fixed: a retained record whose retention period had already ended at `audit_at`
was still verified as "must remain present" (rule_12 protects only records within retention). It is now
skipped. This does not change the 518-row output (no in-scope record has lapsed retention).

## 3. Evaluation set (518 cases, no answers available)

Self-consistency checks run on every `main.py` run (`audit/validate.py`):
518 unique case ids, valid JSON, consecutive `step_no`, phase order, allowed operation/state pairs,
every cited id exists with a timestamp at or before the case's `audit_at`, COMPLETE rows are
verification-only and fully cited, INCOMPLETE findings are cited and remediation/verification carry no
citation. Output: 355 INCOMPLETE, 153 COMPLETE, 10 NOT_APPLICABLE; runtime about 2 s; output is byte-identical
across `PYTHONHASHSEED` values.

## 4. Failures found and improvements made

| Failure found | Improvement |
|---|---|
| Pipe-delimited log layout parsed with shifted columns, so evidence_48 produced no observations (10 cases had no steps) | Fixed column mapping; 93 of 94 files now yield observations or coverage (evidence_90 is an empty inventory by design) |
| Resources from an earlier episode of the same user (e.g. an old object-storage record) leaked into a later case | A resource whose last observation predates `requested_at` is dropped |
| A contact-lookup record on an analytics id was treated as an analytics profile | Records carrying `email_opt_in` are marketing contacts (delete policy) |
| Accounts with no identifier anywhere (404 lookups, worker rows only) were missing: 262 eval cases had no account | Cross-request attribution (`audit/roster.py`): a worker row is a candidate for a request only if it sits shortly before `reported_at` and its result matches `reported_status`; only unambiguous matches are kept. Eval cases without an account fell to 107 |
| Attribution iterated sets in hash order, so the output could differ between runs | Sorted iteration; rows owned by two requests, or requests with two exclusive rows, stay unassigned. Output verified identical for several hash seeds |
| Analytics-profile attribution by the same method gave wrong matches (precision 1.00 → 0.98) | Reverted; those profiles are left out instead of guessed |
| A COMPLETE case ended with a verification step that cited nothing (a backup shown in a screenshot without any restore information) | Unproven restore state is treated as a restore risk, so the case becomes INCOMPLETE rather than claiming a proof we do not have |
| Policy mapping lacked `SECONDARY_IDENTIFIER` (rule_02, delete) found when re-checking the code against `deletion_rules.csv` | Added to the delete categories; no change to any prediction (the category never occurs in the data) |
| Isolated single-target worker rows ("Target resource: x") near one request were ignored for non-account types | Any such row within 10 min of exactly one request is attributed (adds one analytics profile; no wrong matches) |
| Gating identity links by capture time dropped sample recall from 0.933 to 0.896 | Kept time gating for *state* and *citations*; identity links are time-invariant (a later file may still name the resource) |

## 5. Known limitations

* The policy mapping (category → required action) is coded in `audit/state.py` / `planner.py` to mirror
  `deletion_rules.csv`; the CSV is loaded but not consulted at run time.
* **107 of 508 deletion cases have no account step.** Their account appears only in shared worker rows
  that several requests could own. We leave these out rather than guess; each costs about one
  verification step.
* Already-anonymized analytics profiles with no identifier are not attributed (same reason).
* Three expected ids in the samples appear nowhere in participant data and cannot be derived.
* The unproven-restore rule (backup shown but restore state not visible) is a judgement call that
  favours never reporting COMPLETE without proof.
* Intent classification is rule-based (multilingual keywords and explicit refusals). All 518 texts
  resolved without the optional LLM hook; ambiguous texts would default to "not a deletion request".
