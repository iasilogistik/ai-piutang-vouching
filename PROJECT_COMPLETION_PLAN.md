# PROJECT COMPLETION PLAN

Version: 1.0 — 2026-09-23

## Objective

Complete the AI Piutang Vouching / Internal Audit platform through final production acceptance, multi-role UAT, RLS performance hardening, security risk disposition, and handover.

This plan separates:
- **Development / Release work** — orchestration, deployment, database, UAT, sign-off.
- **Codex work** — narrowly scoped code verification or implementation tasks only.

No task may be marked DONE without evidence.

## Completion definition

The project is complete when all of the following are true:

1. Latest approved `main` is READY in Vercel production.
2. `/version.commit` equals latest approved `main`.
3. `/version.environment=production`.
4. `/health=200 healthy`.
5. `/readiness=200 ready` and `schema_current=true`.
6. Production Supabase has every migration required by the release.
7. ADMIN/AUDITOR/REVIEWER/VIEWER live UAT passes, including cross-branch negatives.
8. PERF-02 RLS consolidation is applied and the identical UAT matrix still passes.
9. Supabase security/performance advisors are reviewed.
10. SEC-01 is either enabled on Pro or explicitly risk-accepted by the project owner.
11. User guide, go-live SOP, handover checklist, status and testing report are merged.
12. GO-LIVE #103 contains final evidence and sign-off.

## Parallel execution lanes

### Lane A — Production Recovery & Release Acceptance

**Issues:** #102, #103

**Can run in parallel with:** Lane B, Lane C preparation, Lane D.

Tasks:
- A1. Compare latest `main` SHA to Vercel production SHA.
- A2. When Vercel quota permits, deploy exactly one latest-main release. Do not create retrigger commits.
- A3. Verify `/version`, `/health`, `/readiness`.
- A4. Smoke latest audit UI routes.
- A5. Verify protected API routes return 401 without token.
- A6. Verify production migrations and RLS/advisors.
- A7. Review production runtime errors.
- A8. Attach evidence to OPS-02 #102 and GO-LIVE #103.

**Done gate:** production SHA == approved main, health/readiness/release identity green, no release-caused runtime error.

### Lane B — Live Multi-Role UAT

**Issue:** #89

**External prerequisite:** three official Supabase Auth users.

Required users:
- AUDITOR / PASURUAN
- REVIEWER / PASURUAN
- VIEWER / PASURUAN
- existing ADMIN

Tasks:
- B1. Provision Auth users through official Supabase Authentication administration.
- B2. Map role + PASURUAN branch through `/ui/users`.
- B3. Sign in once as each role and keep tokens only in local shell.
- B4. Run `scripts/live_rbac_uat.py`.
- B5. Record PASS/FAIL only; never store tokens/passwords.
- B6. Verify cross-branch negative tests.
- B7. Attach evidence to #89 and #103.

**Done gate:** full four-role matrix PASS and no role bypasses branch/admin/reviewer gates.

### Lane C — PERF-02 RLS Consolidation

**Issue / PR:** #93 / draft PR #106

**Hard dependency:** Lane B must be green before production application.

Preparation already complete:
- Migration `0029_rls_policy_consolidation` drafted.
- Exact 21 production FOR ALL policies captured.
- Existing read SELECT policies left untouched.
- Existing USING / WITH CHECK expressions preserved.
- Migration and tests PASS in CI.

Execution after UAT:
- C1. Capture pre-migration UAT result.
- C2. Rebase PR #106 on final main.
- C3. Confirm CI migration + pytest green.
- C4. Apply 0029 schema-first to Supabase production.
- C5. Re-run same live UAT matrix.
- C6. Run Supabase security/performance advisors.
- C7. Verify overlapping permissive-policy warnings drop without authorization changes.
- C8. Merge PR #106 only after post-migration UAT is green.

**Done gate:** same RBAC outcomes before and after 0029 and target overlap warnings resolved.

### Lane D — Security Disposition

**Issue:** #79

Current condition:
- Supabase organization is Free.
- Leaked-password protection requires Pro or above.

Options:
1. Upgrade Supabase plan and enable leaked-password protection.
2. Project owner explicitly accepts the residual risk for current go-live.

**Done gate:** control enabled/advisor cleared, or documented risk acceptance attached to GO-LIVE #103.

### Lane E — Documentation & Handover

**Issue / PR:** #104 / #105

Deliverables:
- `USER_GUIDE.md`
- `GO_LIVE_RUNBOOK.md`
- `HANDOVER_CHECKLIST.md`
- `PROJECT_STATUS.md`
- `TESTING_REPORT.md`
- `PROJECT_COMPLETION_PLAN.md`
- `CODEX_EXECUTION_PACK.md`

**Done gate:** CI green, PR merged, final docs reference final release/UAT state.

## Dependency map

```text
                    ┌─────────────┐
                    │ Lane A      │
                    │ Production  │
                    └──────┬──────┘
                           │
                           v
┌─────────────┐      ┌─────────────┐      ┌─────────────┐
│ Lane B      │ ---> │ Lane C      │ ---> │ GO-LIVE     │
│ Live UAT    │      │ RLS PERF-02 │      │ #103        │
└─────────────┘      └─────────────┘      └──────┬──────┘
                                                 ^
┌─────────────┐                                  │
│ Lane D      │ ---------------------------------┤
│ Security    │                                  │
└─────────────┘                                  │
                                                 │
┌─────────────┐                                  │
│ Lane E      │ ---------------------------------┘
│ Handover    │
└─────────────┘
```

Lane A, B provisioning, D and E can progress independently.
Lane C production execution is blocked by Lane B success.

## Release sequencing

### Release R1 — latest main recovery
Contains current release/readiness diagnostics and production hardening.

Gate:
- main == production
- readiness green

### Release R2 — PERF-02
Only after live UAT is green.

Gate:
- 0029 production migration
- same UAT matrix passes after migration

### Release R3 — documentation/final handover
Documentation may be merged with R1 if it is the next legitimate approved main release.
No retrigger-only commit.

## Task status

| Task | Status |
|---|---|
| OPS-02 latest-main deploy | BLOCKED — Vercel Free build-rate limit |
| UAT-01 harness | READY |
| UAT Auth users | BLOCKED — external provisioning required |
| PERF-02 implementation | READY — draft PR #106, CI green |
| PERF-02 production apply | BLOCKED — requires live UAT PASS |
| SEC-01 | BLOCKED — Pro plan or risk acceptance |
| DEV-30 docs | READY — PR #105 |
| GO-LIVE sign-off | BLOCKED by gates above |

## Non-negotiable controls

- Do not create retrigger-only commits.
- Do not write directly to `auth.users`.
- Do not expose access tokens, passwords, service keys, database URLs or secrets.
- Do not apply 0029 before four-role live UAT.
- Do not consolidate RLS by weakening read/write predicates.
- Do not close GO-LIVE #103 without evidence.
