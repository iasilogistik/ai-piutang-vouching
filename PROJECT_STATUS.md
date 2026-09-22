# PROJECT STATUS

Version: 3.0 — 2026-09-22

## Product baseline

The application has moved beyond the original vouching MVP into an integrated, branch-aware audit workflow covering:

- SAP population import/validation.
- Billing/SPJ upload, OCR/extraction, reconciliation and vouching.
- Signature/stamp/control-evidence detection with manual-review support.
- Application RBAC and canonical branch master.
- User management and branch isolation.
- Audit engagement and assignment.
- Population/sampling.
- Electronic working papers.
- Structured audit findings and version history.
- Management responses and corrective action plans.
- Follow-up monitoring, evidence, verification, overdue and reopening.
- Management portfolio dashboard.
- In-app notifications/reminders.
- Versioned evidence repository and integrity metadata.
- Global authorized search/filter/export.
- Audit reports, closing/sign-off and audit trail.
- Release identity, health, readiness and production smoke controls.

## Source-control state

- Latest approved `main`: `35ba8cc32735e4963ba2e8ff7ed7822ca25179b1`.
- Latest live production SHA: `306e159529991cbed0b32ecc098df759743f2e3d`.
- The latest main deployment is currently blocked by the Vercel Free build-rate limit and is tracked in OPS-02 #102.
- Feature/fix/perf/chore development branches are CI-only by default to avoid consuming Vercel preview deployment quota.
- Repeated retrigger commits are prohibited by the release runbook.

## Production infrastructure

- Runtime: Vercel FastAPI deployment.
- Production database: Supabase PostgreSQL.
- Production migration level: `0028_performance_hardening`.
- Release identity endpoint: `/version`.
- Liveness endpoint: `/health`.
- Readiness endpoint: `/readiness`.
- Final acceptance requires production SHA parity, health, readiness, public UI checks, unauthenticated protection checks, migration integrity and runtime-error review.

## Current live production verification

Latest checked live production baseline:

- `/health` -> HTTP 200, `healthy`.
- `/version` -> live SHA `306e159529991cbed0b32ecc098df759743f2e3d`, branch `main`, environment `production`.
- `/readiness` -> HTTP 503 on the older live SHA; non-sensitive diagnostics are already merged on latest main but are not live because of OPS-02.
- Current audit UI shells checked -> HTTP 200.
- Protected audit API endpoints checked without bearer token -> HTTP 401.
- No production runtime errors found in the latest two-hour validation window.
- Branch-null invariants remain zero for `documents`, `import_batches`, `audit_trail`, `audit_findings`, and `corrective_action_plans`.

## Database hardening completed

- Migration `0027_release_schema_revision`: protected release schema-revision helper.
- Migration `0028_performance_hardening`:
  - 18 missing foreign-key indexes added.
  - notification RLS auth init-plan pattern optimized.
- Supabase RLS remains enabled on audit/business tables.
- PERF-02 #93 tracks remaining overlapping permissive policies; changes are intentionally deferred until live four-role UAT is green.

## Locked audit rules

- SAP remains the expected/source population.
- Ambiguous extraction becomes REVIEW rather than automatic PASS.
- AI detects evidence but does not prove signature/stamp authenticity.
- Auditor/reviewer decisions remain authoritative.
- Branch isolation must be preserved at application and database-control layers.
- Issued findings, reviewed working papers and verified follow-up records require explicit controlled transitions to reopen/change.
- Evidence/source records must not be silently mutated to force a desired audit conclusion.

## Active go-live dependencies

### OPS-02 #102 — latest production deployment
Vercel currently rejects the latest main deployment with:

```text
Deployment rate limited — retry in 24 hours.
```

Completion requires production READY on latest main and full release acceptance.

### UAT-01 #89 — live multi-role RBAC UAT
Current production user counts:
- ADMIN: 1
- AUDITOR: 0
- REVIEWER: 0
- VIEWER: 0

Three official Supabase Auth users must be provisioned and mapped to PASURUAN before `scripts/live_rbac_uat.py` can run.

### SEC-01 #79 — leaked-password protection
The Supabase organization is currently on the Free plan. Leaked-password protection requires Pro or above. Go-live requires either:
- upgrade + enable the control, or
- explicit documented risk acceptance.

### PERF-02 #93 — RLS consolidation
21 tables currently have overlapping authenticated SELECT and ALL/manage policies. The safe consolidation design is prepared but must wait until UAT-01 is green.

### GO-LIVE #103
Issue #103 is the single final acceptance/sign-off gate.

## Operational documentation

DEV-30 #104 is prepared in draft PR #105:

- `USER_GUIDE.md`
- `GO_LIVE_RUNBOOK.md`
- `HANDOVER_CHECKLIST.md`

The documentation branch is CI-only and intentionally not merged while OPS-02 remains blocked.
