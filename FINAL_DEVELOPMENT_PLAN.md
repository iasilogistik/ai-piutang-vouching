# FINAL DEVELOPMENT & RELEASE 1.0 PLAN

Status: locked completion plan after DEV-31 production release.

## Current baseline

- DEV-31 dynamic branch is merged through PR #147.
- Production schema includes `0032_dynamic_branch_scope`.
- Dynamic branch navigation/docs are aligned through PR #148.
- Legacy DEV-31 lane PRs #133-#137 are closed/superseded.
- PERF-02 remains blocked until live UAT #89 passes.
- No new product feature work is allowed before Release 1.0 acceptance.

## DEVELOPMENT — execution lanes

### DEV-40 — UAT readiness gate
Owner: Development

Do exactly:
1. Maintain `scripts/uat_preflight.py` as a read-only prerequisite check.
2. Require two real uploaded branches.
3. Require ADMIN plus global AUDITOR/REVIEWER/VIEWER.
4. Require one scoped VIEWER mapped to a real UAT branch.
5. Require branch-owned business roots to have non-null branch.
6. Treat branchless `USER_ROLE` audit events for global users as administrative/global, not branch-owned business data.
7. Do not create fake branch records merely to satisfy UAT.
8. Do not silently repurpose existing production users.

Exit: preflight READY.

### DEV-41 — Live multi-role UAT
Owner: Development + authorized UAT operator

Prerequisite: DEV-40 READY.

Do exactly:
1. Use official Supabase Auth users.
2. Use two real uploaded branches.
3. Keep tokens local-only.
4. Run `scripts/live_rbac_uat.py`.
5. Attach non-secret evidence to #89.

Exit: all live authorization checks PASS.

### DEV-42 — PERF-02 RLS consolidation
Owner: Development

Prerequisite: DEV-41 PASS.

Do exactly:
1. Port PR #106 onto latest main.
2. Use migration `0033_rls_policy_consolidation` with down revision `0032_dynamic_branch_scope`.
3. Preserve exact role and dynamic branch semantics.
4. Capture PRE-UAT authorization outcomes.
5. Apply 0033 schema-first.
6. Repeat identical POST-UAT.
7. Require PRE == POST.
8. Re-run Supabase advisors and confirm multiple-permissive warnings are reduced.

Exit: CI PASS, PRE/POST UAT identical, advisor reviewed.

### DEV-43 — Final production acceptance
Owner: Development + Internal Audit owner

Do exactly:
1. Confirm latest approved main is production READY.
2. Confirm `/health`, `/version`, `/readiness`.
3. Confirm protected APIs reject unauthenticated access.
4. Confirm no release-caused runtime errors.
5. Record SEC-01 disposition: upgrade to Pro and enable leaked-password protection, or formal risk acceptance while on Free.
6. Attach final evidence to #103.

Exit: Release 1.0 sign-off.

## Parallelization rules

- DEV-40 documentation/test work may run in parallel with preparation of authorized UAT accounts/data.
- DEV-41 cannot execute until DEV-40 is READY.
- DEV-42 cannot modify production RLS until DEV-41 PASS.
- DEV-43 evidence preparation may run in parallel, but final sign-off waits for DEV-42.
- No feature expansion, unrelated refactor, or cosmetic redesign before these gates close.

## Commit and push discipline

- One workstream = one logical branch/PR.
- Bundle related files into one reviewed commit where practical.
- No `tmp`, placeholder, retrigger, or per-file push sequence.
- Do not push merely to retrigger Vercel.
- Production changes require CI plus explicit release gate evidence.

## Release 1.0 completion criteria

- UAT preflight READY.
- Live dynamic multi-role UAT PASS.
- PERF-02 PRE/POST authorization outcomes identical.
- Supabase advisors reviewed.
- Security plan gap explicitly accepted or remediated.
- Latest main deployed and runtime verified.
- GO-LIVE #103 signed off.
