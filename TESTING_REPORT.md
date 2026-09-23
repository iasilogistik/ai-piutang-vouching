# TESTING REPORT

Date: 2026-09-22

## Automated validation

GitHub CI requires:

- clean migration execution from head,
- full pytest suite,
- release-acceptance checks,
- RBAC/branch regression coverage.

Automated regression coverage includes:

- user roles and navigation,
- branch isolation and cross-branch denial,
- SAP/Billing/SPJ workflows,
- control evidence and manual review,
- engagement and assignment,
- sampling,
- working papers,
- findings,
- management responses/action plans,
- follow-up,
- management dashboard,
- notifications,
- evidence repository,
- global search/export,
- reports,
- closing/sign-off,
- audit trail,
- release identity/readiness behavior.

## Migration validation

Current production Supabase migration level:

```text
0028_performance_hardening
```

Recent hardening:
- `0027_release_schema_revision`
- `0028_performance_hardening`

The 0028 migration added 18 foreign-key indexes and optimized notification RLS evaluation.

## Current production smoke baseline

Current live production SHA:

```text
306e159529991cbed0b32ecc098df759743f2e3d
```

Latest approved main:

```text
35ba8cc32735e4963ba2e8ff7ed7822ca25179b1
```

Latest main is not live because Vercel Free currently reports:

```text
Deployment rate limited — retry in 24 hours.
```

Smoke checks completed against the live baseline:

- `/health` -> HTTP 200 healthy.
- `/version` -> HTTP 200, branch main, environment production.
- Audit UI routes checked -> HTTP 200.
- Protected API routes checked without bearer token -> HTTP 401.
- Production runtime errors in the latest two-hour validation window -> none.

Current older-live `/readiness` remains HTTP 503. Non-sensitive readiness diagnostics are merged on latest main and will be evaluated only after OPS-02 is resolved.

## Data integrity checks

Latest production checks:

- `documents.branch IS NULL` -> 0
- `import_batches.branch IS NULL` -> 0
- `audit_trail.branch IS NULL` -> 0
- `audit_findings.branch IS NULL` -> 0
- `corrective_action_plans.branch IS NULL` -> 0

## Supabase security advisor

Open control:

- `auth_leaked_password_protection`

Current organization plan: Free.

Supabase leaked-password protection requires Pro or above. This is tracked as SEC-01 #79 and cannot be safely replaced with a SQL workaround.

## Supabase performance advisor

PERF-01 completed:
- missing FK indexes addressed,
- notification auth init-plan warning addressed.

PERF-02 #93 remains:
- 21 tables have overlapping permissive authenticated SELECT + ALL/manage policies.
- Safe consolidation has been designed but is deliberately deferred until live multi-role UAT succeeds.

## Live RBAC UAT status

Harness:

```text
scripts/live_rbac_uat.py
UAT_MULTI_ROLE.md
```

Current production prerequisites:
- ADMIN: available
- AUDITOR: not provisioned
- REVIEWER: not provisioned
- VIEWER: not provisioned

UAT-01 #89 is blocked until official Supabase Auth users are created and mapped to PASURUAN. Accounts must be created through the supported Auth administration path; direct SQL writes to `auth.users` are prohibited.

Required live UAT matrix:
- authorized read paths,
- admin-only gate,
- auditor write paths,
- reviewer approval/verification paths,
- viewer read-only restrictions,
- cross-branch negative tests.

## Go-live acceptance

GO-LIVE #103 requires:
1. latest main deployed and READY,
2. `/version.commit` equals main,
3. `/version.environment=production`,
4. `/health=200 healthy`,
5. `/readiness=200 ready` and `schema_current=true`,
6. latest UI shells = 200,
7. protected APIs = 401 without token,
8. production migrations/advisors verified,
9. live four-role UAT PASS,
10. PERF-02 completed after UAT,
11. SEC-01 enabled or risk-accepted,
12. final handover evidence attached.

## Operational documentation

DEV-30 #104 / draft PR #105 contains:
- `USER_GUIDE.md`
- `GO_LIVE_RUNBOOK.md`
- `HANDOVER_CHECKLIST.md`

CI is required before handover documentation is merged.
