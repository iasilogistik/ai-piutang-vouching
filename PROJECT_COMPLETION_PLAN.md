# PROJECT COMPLETION PLAN

Version: 3.0 — 2026-09-24

## Objective

Complete the project from the current healthy production baseline through live four-role UAT, RLS consolidation, security disposition, documentation closeout, and final go-live sign-off.

This plan is split into two surfaces:

1. **Development / Release** — infrastructure, Auth mapping, UAT, database migration, release, security, handover.
2. **Codex** — execute-only verification tasks. Codex must not re-analyze architecture or redesign modules.

No task is DONE without objective evidence.

## Current baseline

- Repository: `iasilogistik/ai-piutang-vouching`
- Latest `main`: `368e52c9068069c58d9074e372239c6178338708`
- Vercel production: READY on the exact same SHA
- Production deployment: `dpl_DnRywkE2ge7mB5qGS3gMtj9879Sh`
- `/version`: exact main, branch `main`, environment `production`
- `/health`: HTTP 200 healthy
- `/readiness`: HTTP 200 ready, `schema_current=true`
- Production Supabase revision: `0031_revision_helper_acl`
- Runtime error/warning check after latest deployment: clean
- OPS-03 #114: COMPLETE
- Codex C01: PASS FINAL
- Codex C02: PASS FINAL
- PERF-02 draft PR #106: verified, draft only, migration target `0032_rls_policy_consolidation`
- UAT-01 #89: BLOCKED on authoritative role mapping/sessions
- SEC-01 #79: BLOCKED on Pro upgrade or explicit risk acceptance

## Definition of project DONE

The project is complete only when:

1. Final approved `main` equals Vercel production SHA.
2. `/version.environment=production`.
3. `/health=200 healthy`.
4. `/readiness=200 ready` and `schema_current=true`.
5. ADMIN/AUDITOR/REVIEWER/VIEWER live UAT passes.
6. Cross-branch negative authorization tests pass.
7. Migration `0032_rls_policy_consolidation` is applied schema-first after pre-migration UAT PASS.
8. The identical post-0032 UAT matrix passes with PRE == POST authorization outcomes.
9. Supabase security/performance advisors are reviewed after 0032.
10. SEC-01 is enabled or explicitly risk-accepted.
11. Final documentation matches final production state.
12. Codex C01–C05 are PASS.
13. GO-LIVE #103 contains final evidence and is closed.

# DEVELOPMENT / RELEASE PLAN

## Lane A — Production Infrastructure Alignment

**Status: DONE**

Evidence:
- latest main == production SHA
- health green
- readiness green
- intended Supabase schema visible
- schema revision helper returns `0031_revision_helper_acl`
- no recent production errors after final DATABASE_URL/driver correction

OPS-03 #114 is complete.

No further work unless production/database alignment regresses.

---

## Lane B — Live Four-Role UAT

**Issue:** #89  
**Status:** BLOCKED on authoritative role mapping and sessions.  
**Can run in parallel now with Lane D and Lane E.**

### B1 — Authoritative Auth inventory

Current production state:
- Supabase Auth users exist, but the current production `public.user_roles` mapping is not complete.
- Do not infer roles from email, account order, UUID, or creation time.

Required authoritative application roles:
- ADMIN
- AUDITOR
- REVIEWER
- VIEWER

Required branch for non-ADMIN UAT users:
- PASURUAN

If fewer than four official Auth identities exist, create the missing identity using the supported Supabase Auth administration flow. Never write directly to `auth.users`.

### B2 — Map application access

Using ADMIN user management or another authorized application-management path:
- ADMIN -> active
- AUDITOR -> PASURUAN -> active
- REVIEWER -> PASURUAN -> active
- VIEWER -> PASURUAN -> active

Do not guess which identity belongs to which role.

### B3 — Obtain local-only sessions

Login once as each role.

Tokens must stay local-only and must never be copied into:
- GitHub
- chat
- screenshots
- documentation
- commits
- issue comments

### B4 — Execute live matrix

```bash
export ADMIN_TOKEN='local-only'
export AUDITOR_TOKEN='local-only'
export REVIEWER_TOKEN='local-only'
export VIEWER_TOKEN='local-only'
export UAT_BRANCH='PASURUAN'
python scripts/live_rbac_uat.py
```

Required checks:
- identity/role
- navigation visibility
- authorized reads
- ADMIN-only denial
- AUDITOR write gate
- REVIEWER approval/verification gate
- VIEWER read-only behavior
- cross-branch denial
- search/export isolation
- evidence isolation
- follow-up/closing role gates
- audit-trail actor/branch/status evidence

### B5 — Evidence

Record only:
- production SHA
- readiness state
- role
- branch
- route/action
- PASS/FAIL

Never record credentials/tokens.

**Lane B DONE:** complete four-role matrix PASS and no cross-branch leakage.

---

## Lane C — PERF-02 RLS Consolidation

**Issue / PR:** #93 / #106  
**Status:** IMPLEMENTATION READY, DO NOT MERGE/APPLY  
**Hard dependency:** Lane B pre-migration PASS.

Already verified:
- Codex C01 PASS FINAL
- PR #106 draft + mergeable at final verification
- migration target `0032_rls_policy_consolidation`
- exactly 21 manage policies represented
- broad read SELECT policies preserved
- existing `USING` / `WITH CHECK` predicates preserved
- no business-logic module changed
- CI / full pytest PASS at verification

### C1 — Freeze PRE baseline

Attach Lane B UAT matrix as PRE evidence.

### C2 — Rebase only if needed

If `main` changes before 0032:
- rebase #106;
- rerun CI;
- rerun Codex C01 only if functional diff changed.

### C3 — Schema-first apply

Apply `0032_rls_policy_consolidation` to production Supabase only after PRE UAT PASS.

### C4 — POST equivalence

Run the exact same UAT matrix.

Acceptance:
- PRE == POST for every authorization outcome
- cross-branch denial intact
- no role escalation
- no new write permission

### C5 — Advisor review

Run:
- Supabase performance advisor
- Supabase security advisor

Expected:
- target multiple-permissive-policy warnings reduced/removed
- no new security issue caused by 0032

### C6 — Merge

Merge #106 only after POST equivalence PASS.

**Lane C DONE:** planner warning reduced without authorization change.

---

## Lane D — Security Disposition

**Issue:** #79  
**Status:** BLOCKED on project-owner decision.  
**Runs in parallel with Lane B.**

Current condition:
- Supabase organization plan: Free
- leaked-password protection requires Pro or above

Choose one:

### Option D1 — Upgrade and enable
- upgrade Supabase plan
- enable leaked-password protection
- regression-test login/refresh
- rerun security advisor
- close #79 when warning is cleared

### Option D2 — Explicit risk acceptance
- use the repository security-risk acceptance template
- record owner/date/reason/compensating controls/review date
- attach to GO-LIVE #103
- keep technical warning documented as accepted residual risk

No SQL workaround.

**Lane D DONE:** control enabled or explicit project-owner risk acceptance recorded.

---

## Lane E — Documentation & Handover

**Status:** READY FOR FINAL REFRESH  
**Runs in parallel with Lane B and Lane D.**

Required final files:
- `USER_GUIDE.md`
- `GO_LIVE_RUNBOOK.md`
- `HANDOVER_CHECKLIST.md`
- `PROJECT_COMPLETION_PLAN.md`
- `CODEX_EXECUTION_PACK.md`
- `UAT_MULTI_ROLE.md`
- `DEPLOYMENT.md`
- `PROJECT_STATUS.md`
- `TESTING_REPORT.md`

Final refresh occurs after:
- C03 PASS
- 0032 POST-UAT PASS
- SEC-01 disposition

**Lane E DONE:** documents match final production SHA, migration head, UAT/advisor evidence and accepted risk.

---

## Lane F — Final Go-Live Sign-Off

**Issue:** #103  
**Dependency:** B + C + D + E.

Final evidence package:
- final main SHA
- final Vercel deployment ID/URL
- `/version`
- `/health`
- `/readiness`
- final migration head
- PRE/POST RLS UAT matrix
- security/performance advisor summary
- runtime-error review
- SEC-01 disposition
- handover docs
- sign-off owner/date

**Lane F DONE:** GO-LIVE #103 closed with evidence.

# PARALLEL EXECUTION BOARD

```text
NOW
├─ B1/B2: confirm/create/map 4 UAT identities ─────────────┐
├─ D: Pro upgrade OR explicit SEC-01 risk acceptance ───┐ │
└─ E: keep final docs current ─────────────────────────┐ │ │
                                                     │ │ │
AFTER B MAPPING                                      │ │ │
└─ C03 / Lane B: run live four-role PRE-UAT ─────────┘ │ │
                                                       │ │
AFTER PRE-UAT PASS                                     │ │
└─ Lane C: apply 0032 -> POST-UAT -> advisors ──────────┘ │
                                                         │
FINAL                                                    │
└─ C05 + Lane F GO-LIVE #103 <───────────────────────────┘
```

## Current status

| Work | Status |
|---|---|
| Production SHA parity | PASS |
| Health | PASS |
| Readiness | PASS |
| OPS-03 | DONE |
| Codex C01 | PASS FINAL |
| Codex C02 | PASS FINAL |
| UAT harness | READY |
| UAT effective role mapping/sessions | BLOCKED |
| Codex C03 | BLOCKED by UAT mapping/sessions |
| PERF-02 implementation | READY — draft #106 |
| Codex C04 | BLOCKED by C03 + 0032 apply |
| SEC-01 | BLOCKED — Pro upgrade or risk acceptance |
| Codex C05 | BLOCKED by C03/C04/SEC-01 |
| Documentation | READY / final refresh later |
| GO-LIVE | BLOCKED by B/C/D |

## Non-negotiable controls

- No architecture redesign during finalization.
- No direct SQL writes to `auth.users`.
- No role inference from email/account order/UUID.
- No secret/token/password/database URL in repository, issue, chat or screenshot.
- No 0032 production apply before PRE four-role UAT PASS.
- No RLS weakening.
- No GO-LIVE closure without evidence.
