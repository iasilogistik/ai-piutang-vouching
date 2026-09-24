# PROJECT COMPLETION PLAN

Version: 3.1 — 2026-09-24

## Objective

Finish the project from the current production baseline to formal go-live sign-off.

This plan is split into:
1. **Development / Release execution**
2. **Codex execute-only verification**

No task is DONE without objective evidence.

## Current baseline

- Repository: `iasilogistik/ai-piutang-vouching`
- Latest main: `6153542f09cd6ef978e2f739d0b4d28c63f494c7`
- Latest main: `6153542f09cd6ef978e2f739d0b4d28c63f494c7`
- Current production alias: **UNHEALTHY** after the latest environment action
- Current alias `/version`, `/health`, `/readiness`: HTTP 500 / FUNCTION_INVOCATION_FAILED
- Runtime evidence: current Vercel DB context does not contain `public.user_roles`
- Same-main deployment snapshot `ai-piutang-vouching-8286kcdj4-ia-logistik.vercel.app`: `/health` 200 and `/version.commit` = latest main
- That healthy snapshot still has readiness 503 because it uses the previous/stale DB context
- expected revision: `0031_revision_helper_acl`
- runtime reports these schema objects as missing:
  - `public.audit_notifications`
  - `public.audit_workflow_cases`
  - `public.document_control_evidence`
  - `public.user_roles`
- Supabase project `snmbkpjfmxrmautidlcf` confirms those objects exist.
- Current root blocker: **OPS-03 #114** — Vercel Production `DATABASE_URL` must be aligned to the intended Supabase production database. The application code itself is proven viable by a same-SHA healthy deployment snapshot.
- PERF-02 draft PR #106 is based on current main, mergeable, and CI green.
- Codex C01 latest-baseline recheck: PASS FINAL.

## Definition of DONE

The project is complete only when:
1. Vercel production connects to the intended Supabase production DB.
2. `/version.commit == final main`.
3. `/version.environment == production`.
4. `/health == 200 healthy`.
5. `/readiness == 200 ready` and `schema_current=true`.
6. ADMIN/AUDITOR/REVIEWER/VIEWER live UAT passes.
7. Cross-branch negative tests pass.
8. PERF-02 migration `0032_rls_policy_consolidation` is applied only after pre-UAT PASS.
9. The identical post-0032 UAT matrix passes.
10. Supabase security/performance advisors are reviewed.
11. SEC-01 is enabled or explicitly risk-accepted.
12. Final handover docs match final production.
13. GO-LIVE #103 contains evidence and sign-off.
14. CODEX-01 #116 C01–C05 are PASS.

# DEVELOPMENT / RELEASE EXECUTION

## Lane A — OPS-03 Production DB Alignment
**P0 / critical path**
**Owner:** authorized Vercel/Supabase operator
**Issue:** #114
**Parallel with:** Lane B provisioning, Lane D security disposition, Lane E documentation

Actions:
1. Open Vercel project `prj_uTNHTXIvJNDp1OluI9SDiQhKrEx8`.
2. Inspect Production `DATABASE_URL` without sharing its value.
3. Compare it with the current Supabase Connect string for `snmbkpjfmxrmautidlcf`.
4. If mismatched, replace only Production `DATABASE_URL`.
5. If an immediate service-restoration action is needed before the env fix, an authorized Vercel operator may promote the same-main healthy deployment snapshot `ai-piutang-vouching-8286kcdj4-ia-logistik.vercel.app`; this is only a temporary rollback and does not close OPS-03.
6. Redeploy latest main exactly once after correcting Production `DATABASE_URL`.
7. Verify:
   - version SHA == main
   - environment == production
   - health 200
   - readiness 200
   - schema_current true
   - no release-caused runtime errors

**DONE:** #114 contains non-secret evidence and readiness is green.

## Lane B — Live Four-Role UAT
**Owner:** release/UAT operator
**Issue:** #89
**Provisioning can run in parallel with Lane A.**
**Execution dependency:** Lane A PASS.

Current aggregate state:
- Auth users total: 3
- active `public.user_roles`: 0
- Auth role metadata tags: none

For true four-role UAT, ensure **four effective role sessions** exist:
- ADMIN
- AUDITOR
- REVIEWER
- VIEWER

If only three Auth users exist, provision the missing account through official Supabase Auth administration. Do not infer identities or roles from creation order.

Map each to:
- branch: PASURUAN
- active: true

Do not write directly to `auth.users`.

Run:
```bash
export ADMIN_TOKEN='local-only'
export AUDITOR_TOKEN='local-only'
export REVIEWER_TOKEN='local-only'
export VIEWER_TOKEN='local-only'
export UAT_BRANCH='PASURUAN'
python scripts/live_rbac_uat.py
```

Required matrix:
- identity/role
- authorized reads
- ADMIN-only denial
- AUDITOR write gate
- REVIEWER approval/verification gate
- VIEWER read-only
- cross-branch denial
- search/export isolation
- evidence isolation
- follow-up/closing gates
- audit-trail actor/branch/status

**DONE:** complete four-role matrix PASS with no cross-branch leakage.

## Lane C — PERF-02 RLS Consolidation
**Owner:** database/release
**Issue/PR:** #93 / #106
**Hard dependency:** Lane B pre-migration PASS.

Prepared state:
- migration `0032_rls_policy_consolidation`
- PR #106 draft
- based on latest main
- mergeable
- CI PASS
- 21 manage policies captured
- broad read SELECT policies unchanged
- existing USING/WITH CHECK preserved
- C01 PASS FINAL

Execution:
1. Freeze pre-0032 UAT evidence.
2. Rebase #106 only if main changed.
3. Rerun CI.
4. Apply 0032 schema-first to production.
5. Run identical post-0032 UAT.
6. PRE must equal POST.
7. Run security/performance advisors.
8. Merge #106 only after equivalence PASS.

**DONE:** no authorization change and target overlap warnings reduced/removed.

## Lane D — SEC-01 Disposition
**Owner:** project owner / Supabase operator
**Issue:** #79
**Runs in parallel.**

Choose exactly one:
1. Upgrade Supabase plan and enable leaked-password protection; or
2. Record explicit risk acceptance.

No SQL workaround.

**DONE:** advisor cleared or signed risk acceptance recorded.

## Lane E — Documentation/Handover
**Owner:** development/release
**Runs in parallel.**

Required:
- USER_GUIDE.md
- GO_LIVE_RUNBOOK.md
- HANDOVER_CHECKLIST.md
- PROJECT_COMPLETION_PLAN.md
- CODEX_EXECUTION_PACK.md
- UAT_MULTI_ROLE.md
- DEPLOYMENT.md
- PROJECT_STATUS.md
- TESTING_REPORT.md
- MANUAL_ACTIONS_REQUIRED.md
- SEC01_RISK_ACCEPTANCE.md

**DONE:** files reflect final SHA/UAT/advisor outcome.

## Lane F — Final Go-Live Sign-Off
**Owner:** project owner
**Issue:** #103
**Dependency:** A + B + C + D + E.

Attach:
- final main SHA
- production deployment ID/URL
- version/health/readiness
- migration head
- pre/post RLS UAT matrix
- advisor summary
- runtime-error review
- risk acceptance, if any
- handover evidence
- sign-off owner/date

**DONE:** #103 closed.

# PARALLEL BOARD

```text
NOW
├─ A: align Vercel Production DATABASE_URL ─────────────┐
├─ B1: provision AUDITOR/REVIEWER/VIEWER ────────────┐  │
├─ D: Pro upgrade OR SEC-01 risk acceptance ───────┐ │  │
└─ E: keep closeout docs current ─────────────────┐ │ │  │
                                                 │ │ │  │
AFTER A PASS                                     │ │ │  │
└─ B2: run live four-role UAT ───────────────────┘ │ │  │
                                                   │ │  │
AFTER B PASS                                       │ │  │
└─ C: apply 0032 -> repeat UAT -> advisors ─────────┘ │  │
                                                     │  │
FINAL                                                │  │
└─ F: GO-LIVE #103 sign-off <─────────────────────────┴──┘
```

## Current status

| Work | Status |
|---|---|
| Production SHA parity | PASS |
| Production alias health | **FAIL (500)** after env change |
| Same-main deployment snapshot health | PASS |
| Readiness | BLOCKED by OPS-03 |
| C01 PERF-02 verifier | PASS FINAL |
| UAT harness | READY |
| UAT users | BLOCKED by official Auth provisioning |
| PERF-02 implementation | READY in draft #106 |
| 0032 production apply | BLOCKED by pre-UAT |
| SEC-01 | BLOCKED by owner choice / plan |
| Documentation | READY for final refresh |
| GO-LIVE | BLOCKED by A/B/C/D |

## Non-negotiable controls

- No architecture redesign during closeout.
- No retrigger-only commits.
- No direct SQL writes to `auth.users`.
- No secret/token/password/DATABASE_URL in repo, issue, chat, or screenshot.
- No 0032 apply before pre-UAT PASS.
- No RLS weakening.
- No GO-LIVE closure without evidence.
