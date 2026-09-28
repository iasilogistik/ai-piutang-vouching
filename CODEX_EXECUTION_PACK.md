# CODEX EXECUTION PACK

Version: 5.0 — 2026-09-28

## Operating mode

This is an execute-only verification pack. Architecture and work order are locked by `FINAL_DEVELOPMENT_PLAN.md`.

Codex MUST NOT:
- re-analyze or redesign architecture;
- reopen superseded DEV-31 PRs #133-#137;
- restore PASURUAN or another branch as a global default;
- create fake upload/branch data just to satisfy UAT;
- silently change a real production user's role or branch scope;
- create Supabase Auth users by direct SQL;
- weaken RLS to make tests pass;
- run PERF-02 before live UAT PASS;
- expose credentials, tokens, keys, database URLs, or secrets;
- refactor unrelated code.

Codex MUST:
1. execute only the named task;
2. inspect named files plus direct failing-test dependencies;
3. run targeted tests and full pytest for code changes;
4. run `git diff --check`;
5. self-review for unrelated changes and secrets;
6. report PASS or BLOCKED with exact non-secret evidence;
7. stop at a gate rather than inventing prerequisites.

## Locked baseline

- DEV-31 merged via PR #147.
- Dynamic branch docs aligned via PR #148.
- Schema head is `0032_dynamic_branch_scope`.
- Active user `branch = NULL` means global scope.
- Non-null user branch is an optional exact restriction.
- Branch-owned business roots must have a non-null branch.
- Branchless `USER_ROLE` audit events for global users are administrative/global and are not a business-root invariant failure.
- PERF-02 target revision is `0033_rls_policy_consolidation`.

# CODEX-UAT-PREFLIGHT

Run exactly:
```bash
pytest -q tests/test_uat_preflight.py tests/test_live_rbac_uat_harness.py
python scripts/uat_preflight.py
git diff --check
```

PASS only when `scripts/uat_preflight.py` returns READY.

If BLOCKED, report the exact prerequisite codes. Do not mutate production users/data to clear them.

# CODEX-LIVE-UAT

Prerequisite: CODEX-UAT-PREFLIGHT PASS and authorized UAT tokens are available locally.

Run:
```bash
python scripts/live_rbac_uat.py
```

Verify:
- ADMIN identity and admin-only gate;
- global AUDITOR/REVIEWER/VIEWER across both real branches;
- scoped VIEWER own-branch allow and other-branch deny;
- auditor write role gate;
- reviewer reopen/verification role gate;
- probes remain non-mutating;
- no token appears in output committed to Git.

Return BLOCKED when tokens or authorized UAT identities are not available. Never fabricate them.

# CODEX-PERF — #93 / PR #106

BLOCKED until #89 live UAT is PASS.

When unblocked:
1. port/rebase on latest main;
2. migration = `0033_rls_policy_consolidation`;
3. down revision = `0032_dynamic_branch_scope`;
4. preserve current role + branch predicates;
5. capture PRE live UAT;
6. apply schema-first;
7. run identical POST live UAT;
8. require PRE == POST for every authorization outcome;
9. rerun security/performance advisors;
10. merge only if no authorization regression.

# CODEX-FINAL

Prerequisites:
- live UAT PASS;
- PERF-02 PRE/POST PASS;
- SEC-01 disposition recorded;
- latest approved main deployed.

Run:
```bash
alembic heads
alembic upgrade head
pytest -q
git status --short
git diff --check
```

Verify production release evidence:
- latest main == production `/version.commit`;
- `/health` healthy;
- `/readiness` ready;
- UI smoke succeeds;
- protected APIs reject unauthenticated requests;
- no new runtime errors;
- Supabase advisor results recorded;
- GO-LIVE #103 updated.

## Completion format

```text
STATUS: PASS | BLOCKED
TASK: CODEX-...
EVIDENCE:
- commands/tests/result
CHANGED FILES:
- ...
MIGRATION IMPACT:
- none | exact revision
BLOCKER:
- none | exact blocker
SECURITY/AUTHORIZATION:
- unchanged | exact concern
```

Do not output a new architecture plan.
