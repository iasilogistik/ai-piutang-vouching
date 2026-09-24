# MANUAL ACTIONS REQUIRED

Only actions that cannot be executed through the currently connected tools are listed here.

## 1. OPS-03 — Vercel Production DATABASE_URL — CRITICAL

Project:
```text
prj_uTNHTXIvJNDp1OluI9SDiQhKrEx8
```

Required:
1. Open Vercel → project → Settings → Environment Variables.
2. Inspect **Production** `DATABASE_URL` privately.
3. Open Supabase project `snmbkpjfmxrmautidlcf` → Connect.
4. Compare the intended current production connection string.
5. If different, update Production `DATABASE_URL`.
6. Do not paste the value into chat, GitHub, screenshots, or documents.
7. Current production alias is now 500 because the active DB context lacks `public.user_roles`. Do not run migrations against that unknown/stale database.
8. Optional immediate rollback: promote the same-main healthy deployment snapshot `ai-piutang-vouching-8286kcdj4-ia-logistik.vercel.app` while the env value is corrected.
9. Redeploy latest main exactly once after the correct Production `DATABASE_URL` is saved.
10. After redeploy, C02 verifies version/health/readiness/runtime.

Expected result:
```text
/version.commit == main
/health == 200 healthy
/readiness == 200 ready
schema_current == true
```

## 2. UAT-01 — Create three official Auth users

Supabase → Authentication → Users.

Current aggregate state: 3 Auth users, 0 active application-role mappings.

Ensure four effective accounts/sessions exist:
- ADMIN
- AUDITOR
- REVIEWER
- VIEWER

Create/invite whichever role account is still missing. Do not infer roles from account order.

Do not insert into `auth.users` through SQL.

Then, via production ADMIN user management, map:
- AUDITOR → PASURUAN → active
- REVIEWER → PASURUAN → active
- VIEWER → PASURUAN → active

Keep tokens local-only.

## 3. SEC-01 — Choose security disposition

Current Supabase plan is Free.

Choose:
- upgrade to Pro+ and enable leaked-password protection; or
- approve the documented risk acceptance.

Do not implement a SQL workaround.

## 4. Final owner sign-off

After C02/C03/C04/C05 PASS:
- review GO-LIVE #103 evidence
- record final owner/date
- close project
