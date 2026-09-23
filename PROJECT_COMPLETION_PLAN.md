# PROJECT COMPLETION PLAN

Version: 2.0 — 2026-09-23

## Objective

Complete the project from the current production baseline through environment correction, live four-role UAT, RLS consolidation, security disposition, and final go-live sign-off.

This plan is intentionally split into two execution surfaces:

1. **Development / Release lanes** — production, database, UAT, security, release and handover work.
2. **Codex execution lanes** — narrow verify/implement tasks only. Codex must not re-analyze architecture or redesign modules.

No task is DONE without objective evidence.

## Current baseline

- Repository: `iasilogistik/ai-piutang-vouching`.
- Latest `main`: `bee659293f855353b130b19e8ea5e812022d8ca7`.
- Vercel production: READY on the same SHA.
- `/version`: correct commit, branch `main`, environment `production`.
- `/health`: HTTP 200 healthy.
- `/readiness`: HTTP 503, `migration_metadata_unavailable`.
- Runtime reports these required objects as missing:
  - `public.audit_notifications`
  - `public.audit_workflow_cases`
  - `public.document_control_evidence`
  - `public.user_roles`
- Supabase project `snmbkpjfmxrmautidlcf` independently confirms those objects exist.
- Strongest remaining blocker: OPS-03 #114 — Vercel production `DATABASE_URL` points to a stale/different DB or unsupported connection context.
- PERF-02 draft PR #106 is mergeable and verified; current migration target is `0032_rls_policy_consolidation`.
- SEC-02 #118 is complete: migration `0031_revision_helper_acl` is applied and the SECURITY DEFINER executable warnings are cleared.
- Codex C01 final verification was rerun after SEC-02 and is PASS FINAL in CODEX-01 #116 (239 passed, 51 warnings).

## Definition of project DONE

The project is complete only when all of the following are true:

1. Vercel production uses the intended Supabase production database.
2. `/version.commit` equals final approved `main`.
3. `/version.environment=production`.
4. `/health=200 healthy`.
5. `/readiness=200 ready` and `schema_current=true`.
6. ADMIN/AUDITOR/REVIEWER/VIEWER live UAT passes.
7. Cross-branch negative authorization tests pass.
8. Migration `0032_rls_policy_consolidation` is applied schema-first after pre-UAT PASS.
9. The identical post-0032 UAT matrix passes with no authorization change.
10. Supabase security/performance advisors are reviewed.
11. SEC-01 is enabled or explicitly risk-accepted.
12. Final documentation is present and current.
13. GO-LIVE #103 contains evidence and sign-off.
14. CODEX-01 #116 C01–C05 are PASS or an explicitly external blocker is resolved outside Codex before final PASS.

# DEVELOPMENT / RELEASE PLAN

## Lane A — OPS-03 Production Database Alignment

**Owner:** Vercel/Supabase operator  
**Issue:** #114  
**Runs in parallel with:** Lane B provisioning, Lane D security disposition, Lane E documentation.

### A1 — Inspect production DATABASE_URL
In Vercel project `prj_uTNHTXIvJNDp1OluI9SDiQhKrEx8`:
- open Production Environment Variables;
- inspect `DATABASE_URL` without copying it into GitHub/chat/screenshots;
- compare internally with Supabase project `snmbkpjfmxrmautidlcf` Connect string.

Safe fingerprint rule:
- direct connection should target the intended project endpoint; or
- pooler credentials should identify project ref `snmbkpjfmxrmautidlcf`.

### A2 — Correct the environment if mismatched
- update only Production `DATABASE_URL`;
- do not change application code to compensate for wrong infrastructure config;
- redeploy latest approved `main` once.

### A3 — Verify release
Required:
- `/version.commit == main`
- `/version.environment == production`
- `/health == 200 healthy`
- `/readiness == 200 ready`
- `schema_current == true`
- current audit tables query successfully
- no new runtime errors

### A4 — Evidence
Attach non-secret evidence to #114 and GO-LIVE #103.

**Lane A DONE:** readiness green on intended Supabase production DB.

---

## Lane B — Live Four-Role UAT

**Owner:** Release/UAT operator  
**Issue:** #89  
**Can start provisioning in parallel with Lane A.**  
**Full execution dependency:** Lane A PASS.

### B1 — Provision official Auth users
Create through supported Supabase Authentication administration:
- AUDITOR
- REVIEWER
- VIEWER

Existing ADMIN remains.

Do not insert directly into `auth.users`.

### B2 — Map application access
Through ADMIN user management:
- AUDITOR → PASURUAN → active
- REVIEWER → PASURUAN → active
- VIEWER → PASURUAN → active

### B3 — Run live harness
Tokens remain local-only:

```bash
export ADMIN_TOKEN='local-only'
export AUDITOR_TOKEN='local-only'
export REVIEWER_TOKEN='local-only'
export VIEWER_TOKEN='local-only'
export UAT_BRANCH='PASURUAN'
python scripts/live_rbac_uat.py
```

### B4 — Required matrix
- identity/role
- navigation visibility
- authorized reads
- admin-only denial
- auditor write gate
- reviewer approval/verification gate
- viewer read-only behavior
- cross-branch denial
- search/export isolation
- evidence isolation
- follow-up/closing role gates
- audit-trail actor/branch/status evidence

### B5 — Evidence
Record only PASS/FAIL, routes, role and branch. Never record tokens/passwords.

**Lane B DONE:** complete four-role matrix PASS with no cross-branch leakage.

---

## Lane C — PERF-02 RLS Consolidation

**Owner:** Database/Release operator  
**Issue / PR:** #93 / #106  
**Hard dependency:** Lane B pre-migration PASS.

Preparation already complete:
- draft PR #106
- migration `0032_rls_policy_consolidation`
- exactly 21 overlapping authenticated manage policies represented
- broad read SELECT policies preserved
- USING/WITH CHECK expressions preserved
- C01 Codex verification PASS FINAL
- CI green
- PR remains draft

### C1 — Freeze baseline
Capture pre-0032 UAT matrix from Lane B.

### C2 — Refresh draft
- rebase PR #106 on final main if main changed;
- rerun CI;
- rerun Codex C01 only if functional diff changed.

### C3 — Apply schema-first
Apply `0032_rls_policy_consolidation` to Supabase production before merging application release contract changes.

### C4 — Post-migration equivalence
Run identical live UAT matrix.

PRE must equal POST.

### C5 — Advisor review
Run:
- Supabase performance advisor
- Supabase security advisor

Expected:
- targeted multiple-permissive-policy warnings reduced/removed;
- no new authorization/security issue.

### C6 — Merge
Merge #106 only after post-migration UAT PASS.

**Lane C DONE:** authorization semantics unchanged and targeted planner warning resolved.

---

## Lane D — Security Disposition

**Owner:** Project owner / Supabase operator  
**Issue:** #79  
**Runs in parallel with A/B preparation.**

Current condition:
- Supabase organization plan is Free.
- leaked-password protection requires Pro or above.

Choose one:
1. upgrade Supabase plan and enable leaked-password protection; or
2. record explicit risk acceptance for go-live.

No SQL workaround.

**Lane D DONE:** advisor cleared or signed risk acceptance attached to GO-LIVE #103.

---

## Lane E — Documentation & Handover

**Owner:** Development/Release  
**Status:** core DEV-30 documentation already merged.

Required files:
- `USER_GUIDE.md`
- `GO_LIVE_RUNBOOK.md`
- `HANDOVER_CHECKLIST.md`
- `PROJECT_COMPLETION_PLAN.md`
- `CODEX_EXECUTION_PACK.md`
- `UAT_MULTI_ROLE.md`
- `DEPLOYMENT.md`
- `PROJECT_STATUS.md`
- `TESTING_REPORT.md`

Final step:
- update status/test evidence to final SHA/UAT/advisor outcome.

**Lane E DONE:** handover package matches final production state.

---

## Lane F — Final Go-Live Sign-Off

**Owner:** Project owner  
**Issue:** #103  
**Dependency:** A + B + C + D + E.

Final evidence:
- final main SHA
- final production deployment ID/URL
- `/version`
- `/health`
- `/readiness`
- migration head
- pre/post RLS UAT matrix
- advisor summary
- runtime-error review
- accepted risks
- handover docs
- sign-off date/owner

**Lane F DONE:** #103 closed with evidence.

# PARALLEL EXECUTION BOARD

```text
NOW
├─ Lane A: OPS-03 DATABASE_URL correction ─────────────┐
├─ Lane B: provision UAT Auth users ────────────────┐  │
├─ Lane D: Pro upgrade / risk acceptance ─────────┐ │  │
└─ Lane E: keep final docs current ──────────────┐ │ │  │
                                                │ │ │  │
AFTER A PASS                                    │ │ │  │
└─ Lane B: execute live four-role UAT ──────────┘ │ │  │
                                                  │ │  │
AFTER B PASS                                      │ │  │
└─ Lane C: apply 0032 -> repeat UAT -> advisors ───┘ │  │
                                                    │  │
FINAL                                               │  │
└─ Lane F: GO-LIVE #103 sign-off <───────────────────┴──┘
```

## Current task status

| Work | Status |
|---|---|
| Production SHA parity | PASS |
| Health | PASS |
| OPS-03 database alignment | BLOCKED — external Vercel env write |
| Readiness | BLOCKED by OPS-03 |
| UAT harness | READY |
| UAT users | BLOCKED — official Auth provisioning required |
| PERF-02 implementation | READY — draft #106 |
| Codex C01 | PASS FINAL |
| PERF-02 production apply | BLOCKED by UAT |
| SEC-01 | BLOCKED — plan upgrade or risk acceptance |
| Documentation | READY / update final evidence later |
| GO-LIVE | BLOCKED by A/B/C/D |

## Non-negotiable controls

- No architecture redesign during finalization.
- No retrigger-only commits.
- No direct SQL writes to `auth.users`.
- No secret/token/password/database URL in repository, issue, chat or screenshot.
- No 0032 production apply before pre-migration four-role UAT PASS.
- No RLS weakening.
- No GO-LIVE closure without evidence.
