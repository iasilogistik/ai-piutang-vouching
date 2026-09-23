# FINAL EXTERNAL OPERATOR ACTIONS

These are the remaining actions that cannot be completed by the current connected tooling. Execute them in parallel where possible.

## OP-1 — Vercel Production DATABASE_URL

Issue: OPS-03 #114

Current evidence:
- application main and Vercel production SHA are aligned;
- /health is healthy;
- /readiness reports migration metadata unavailable and four required public relations missing;
- intended Supabase production contains those relations and the current migration helper.

Action:
1. Vercel project `prj_uTNHTXIvJNDp1OluI9SDiQhKrEx8`.
2. Open Production Environment Variables.
3. Inspect `DATABASE_URL` privately.
4. Compare with the current Supabase Connect string for project `snmbkpjfmxrmautidlcf`.
5. Correct Production `DATABASE_URL` if it targets a different/stale database.
6. Redeploy latest main once.

Never paste the connection string into GitHub, chat, screenshots or logs.

Done when:
- /version == latest main
- /health == 200
- /readiness == 200 ready
- schema_current == true

The existing Production DB Alignment Watch will verify automatically.

## OP-2 — UAT Auth Users

Issue: UAT-01 #89

Action:
1. Supabase Dashboard → Authentication → Users.
2. Create/invite dedicated UAT users for AUDITOR, REVIEWER and VIEWER.
3. Do not write directly to `auth.users`.
4. Through the application ADMIN user-management flow, map:
   - AUDITOR → PASURUAN → active
   - REVIEWER → PASURUAN → active
   - VIEWER → PASURUAN → active
5. Keep credentials/tokens local only.

Done when aggregate production role coverage is:
- ADMIN >= 1
- AUDITOR >= 1
- REVIEWER >= 1
- VIEWER >= 1
- all three non-admin UAT roles mapped to PASURUAN

The existing UAT Role Readiness Watch will detect readiness.

## OP-3 — SEC-01 Decision

Issue: SEC-01 #79

Choose:
- upgrade Supabase and enable leaked-password protection; or
- complete `SECURITY_RISK_ACCEPTANCE_TEMPLATE.md` with explicit owner approval and expiry/review date.

Do not invent a SQL workaround.

## What happens after OP-1 / OP-2

1. Run live four-role UAT.
2. If PASS, apply draft migration `0032_rls_policy_consolidation` schema-first.
3. Run the identical UAT matrix again.
4. Review security/performance advisors.
5. Merge PR #106 only if PRE == POST.
6. Run final Codex C05 verifier.
7. Attach evidence to GO-LIVE #103 and sign off.
