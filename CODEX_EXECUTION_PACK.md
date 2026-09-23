# CODEX EXECUTION PACK

Version: 1.0 — 2026-09-23

## Purpose

These tasks are written so Codex does **not** need to re-analyze the architecture.

Codex must execute only the requested scope, run the specified checks, self-review the diff, and return evidence.

Do not redesign the application.
Do not rename unrelated modules.
Do not refactor unrelated code.
Do not create new migrations unless explicitly requested.
Do not change RBAC semantics.
Do not change branch-isolation semantics.
Do not modify source audit records to satisfy tests.

# CODEX TASK C01 — Final review of PERF-02 draft

**Status before Codex:** implementation already prepared in draft PR #106.

## Objective
Verify that migration `0029_rls_policy_consolidation` removes SELECT overlap from the 21 manage policies without changing authorization semantics.

## Files to inspect
```text
alembic/versions/0029_rls_policy_consolidation.py
tests/test_rls_policy_consolidation.py
tests/test_performance_hardening.py
tests/test_release_readiness.py
app/services/release_readiness.py
```

## Required checks
1. Confirm `down_revision == "0028_performance_hardening"`.
2. Confirm exactly 21 source FOR ALL policies are represented.
3. Confirm existing broad read SELECT policies are not dropped.
4. Confirm every source manage policy is replaced only by INSERT, UPDATE and DELETE policies.
5. Confirm no role set or branch predicate is broadened.
6. Confirm downgrade restores original FOR ALL policy.
7. Confirm `EXPECTED_SCHEMA_REVISION == "0029_rls_policy_consolidation"`.
8. Run:
   ```bash
   alembic upgrade head
   pytest -q
   ```
9. Self-review `git diff main...HEAD` for unrelated changes.

## Stop conditions
Stop and report BLOCKED if policy expressions cannot be proven equivalent, migration has more than one head, tests fail, or unrelated business logic is changed.

## Completion response
Return only PASS or BLOCKED, changed files, migration head, pytest summary, and authorization-semantic concerns. Do not propose architecture changes.

# CODEX TASK C02 — Production readiness diagnosis after latest-main deploy

**Run only after OPS-02 deploys latest main.**

## Objective
If production `/readiness` is still 503, implement the smallest safe fix using only the non-sensitive diagnostic payload.

## Inputs
Collect `/version`, `/health`, and `/readiness`.

Allowed readiness fields:
- reason
- expected_revision
- database_revision

## Rules
- Never request or print DB URL, password, service key or access token.
- Do not change audit business logic.
- Do not create a migration unless diagnosis proves a schema object is required.
- Prefer a test-first minimal patch.
- Preserve fail-closed readiness behavior.

## Files likely in scope
```text
app/services/release_readiness.py
tests/test_release_readiness.py
tests/test_release_acceptance.py
```

## Required checks
```bash
pytest -q tests/test_release_readiness.py tests/test_release_acceptance.py
pytest -q
```

Self-review diff and ensure no secret/error text is exposed.

## Completion response
Return diagnostic reason observed, minimal root cause, files changed, test summary, PASS/BLOCKED. Do not analyze unrelated modules.

# CODEX TASK C03 — Live UAT harness verification

**Run after official ADMIN/AUDITOR/REVIEWER/VIEWER tokens exist locally.**

## Objective
Verify the existing live UAT harness. Do not redesign it.

## Files
```text
scripts/live_rbac_uat.py
UAT_MULTI_ROLE.md
```

## Execute
```bash
export ADMIN_TOKEN='local-only'
export AUDITOR_TOKEN='local-only'
export REVIEWER_TOKEN='local-only'
export VIEWER_TOKEN='local-only'
export UAT_BRANCH='PASURUAN'
python scripts/live_rbac_uat.py
```

## Verify
- correct identity/role,
- authorized read paths,
- ADMIN-only denial for non-admin,
- AUDITOR write gate,
- REVIEWER approval/verification gate,
- VIEWER read-only behavior,
- cross-branch negative tests.

## Security
Never print or persist token values. Never commit .env files or credentials.

## Completion response
Return only role matrix PASS/FAIL, failed route names if any, branch used, production SHA from /version, readiness status.

# CODEX TASK C04 — Post-0029 authorization equivalence check

**Run only after C03 is PASS and 0029 is applied schema-first.**

## Objective
Prove authorization behavior is unchanged after RLS consolidation.

Run the exact same C03 live UAT command and compare outcomes.

## Acceptance
- Every authorization outcome matches pre-0029 UAT.
- Cross-branch denial remains intact.
- Target multiple-permissive-policy warnings are removed/reduced as expected.
- No new security advisor issue is introduced by 0029.

## Completion response
Return PRE/POST matrix comparison, PASS/BLOCKED, and any changed authorization outcome. Do not make extra code changes if matrix already passes.

# CODEX TASK C05 — Final repository release check

**Run after all implementation PRs are merged.**

## Objective
Verify repository is ready for final GO-LIVE sign-off.

## Required commands
```bash
alembic heads
alembic upgrade head
pytest -q
```

## Verify
- one Alembic head only,
- release readiness expected revision equals Alembic head,
- no open implementation PR required for go-live,
- documentation files exist,
- `vercel.json` deployment governance remains present.

## Files that must exist
```text
USER_GUIDE.md
GO_LIVE_RUNBOOK.md
HANDOVER_CHECKLIST.md
PROJECT_COMPLETION_PLAN.md
CODEX_EXECUTION_PACK.md
UAT_MULTI_ROLE.md
DEPLOYMENT.md
PROJECT_STATUS.md
TESTING_REPORT.md
```

## Completion response
Return PASS/BLOCKED, Alembic head, pytest count, missing file list, and remaining blocker issue numbers only. No new feature suggestions.

## Codex definition of DONE

Codex may report DONE only when:
1. requested implementation/check is complete,
2. specified tests pass,
3. diff is self-reviewed,
4. no unrelated change exists,
5. no unresolved authorization/security concern exists,
6. evidence is included in the completion response.

If any item fails, report BLOCKED instead of DONE.
