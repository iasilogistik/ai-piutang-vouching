# FINAL DEVELOPMENT & GO-LIVE PLAN

Status: execution plan after dynamic-branch requirement lock.

## Goal

Finish the project as a production-ready Internal Audit platform with dynamic branch discovery, authenticated multi-role UAT, optimized RLS, operational documentation, and final go-live sign-off.

## Locked architecture decisions

1. Branch is a data dimension discovered from upload, not a prerequisite fixed master.
2. `user_roles.branch = NULL` means global branch scope for an active application user.
3. Non-null user branch remains an optional exact restriction.
4. ADMIN remains global regardless of legacy branch metadata.
5. Every audit/business root record must still have a non-null branch.
6. New uploaded branches are normalized and auto-registered in the branch catalog.
7. Role authorization remains ADMIN / AUDITOR / REVIEWER / VIEWER.
8. Dynamic branch is implemented before PERF-02 RLS consolidation.

## Parallel workstreams

### Lane A — Branch access/RLS (#129 / PR #133)
- Migration `0032_dynamic_branch_scope`.
- Global vs optionally restricted user branch semantics.
- Rewrite branch-sensitive RLS while preserving role gates.
- Status: implementation + lane CI complete.

### Lane B — Upload discovery (#130 / PR #134)
- Auto-register branch from upload context.
- SAP single-branch inference from Branch/Cabang/Branch Code/Kode Cabang.
- Conflict/multi-branch rejection.
- Document/ZIP/Drive branch registration.
- Status: implementation + lane CI complete.

### Lane C — UI/user scope (#131 / PR #135)
- Blank user branch = `Semua cabang (dinamis)`.
- Existing branch remains optional restriction.
- Unified/Combined/Bulk/Drive upload UIs support dynamic typed branch.
- Branch master presented as discovered catalog.
- Status: implementation + lane CI complete.

### Lane D — UAT/docs (#132 / PR #136)
- No PASURUAN default.
- Two real uploaded UAT branches.
- Global role matrix across both branches.
- Dedicated scoped VIEWER control.
- Status: implementation + lane CI complete.

## Integration gate

1. Build combined integration branch from A+B+C+D.
2. Run clean migration from 0001 through 0032.
3. Run complete pytest suite.
4. Review diff for unrelated changes and secrets.
5. Do not apply 0032 or merge to main until integration CI is green.

## Production release sequence

### Release 1 — Dynamic branch
1. Freeze approved integration SHA.
2. Apply `0032_dynamic_branch_scope` to Supabase production first.
3. Run Supabase security/performance advisors.
4. Merge approved dynamic-branch integration to main.
5. Deploy exactly latest main to Vercel.
6. Verify `/version`, `/health`, `/readiness`, UI 200, protected API 401, runtime errors.

### Release 2 — Live RBAC UAT
1. Provision official Supabase Auth UAT accounts:
   - ADMIN
   - global AUDITOR
   - global REVIEWER
   - global VIEWER
   - scoped VIEWER control.
2. Pick two real branches created/discovered by upload.
3. Run `scripts/live_rbac_uat.py`.
4. Require all dynamic/global/scoped/role-gate tests PASS.
5. Attach evidence to UAT-01 #89 without credentials.

### Release 3 — PERF-02
1. Rebase draft PERF-02 onto the dynamic-branch main.
2. Migration becomes `0033_rls_policy_consolidation`.
3. Capture pre-migration UAT baseline.
4. Apply 0033 schema-first.
5. Repeat identical UAT matrix.
6. Re-run Supabase performance/security advisors.
7. Merge only if authorization outcomes are unchanged and overlap warnings are reduced.

### Release 4 — Documentation/handover
1. Rebase DEV-30 docs PR #105 onto final main.
2. Update USER_GUIDE, GO_LIVE_RUNBOOK, HANDOVER_CHECKLIST, PROJECT_STATUS, TESTING_REPORT for dynamic branch.
3. CI must pass.
4. Merge documentation.

## External go-live dependencies

### Vercel
- Latest-main production deployment must be READY.
- Do not use repeated retrigger commits.

### Supabase Auth
- Auth Admin provisioning is not available through the current connector.
- UAT users must be created through the official Supabase Auth administration path.

### Supabase leaked-password protection
- Current organization plan is Free.
- Control requires Pro or formal documented risk acceptance.

## Final GO-LIVE gate (#103)

Project is complete only when:
- latest main == production `/version.commit`,
- `/health` = 200 healthy,
- `/readiness` = 200 ready,
- current audit UIs = 200,
- protected APIs = 401 without token,
- migration head matches release,
- dynamic-branch live UAT PASS,
- PERF-02 before/after UAT PASS,
- advisors reviewed,
- leaked-password control enabled or risk accepted,
- handover docs merged,
- final evidence/sign-off attached to #103.

## Merge discipline

- No feature is considered done from code alone.
- Required: CI, self-review, integration regression, schema-first migration where applicable, deployment verification, and live UAT for authorization changes.
- No branch-related code may create a branch=NULL audit/business root record.
