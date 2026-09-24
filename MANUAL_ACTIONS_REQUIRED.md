# MANUAL ACTIONS REQUIRED

Only actions that cannot be executed through the currently connected tools are listed here.

## 1. OPS-03 — Vercel Production DATABASE_URL — CRITICAL

Project:
```text
prj_uTNHTXIvJNDp1OluI9SDiQhKrEx8
```

Required:
1. Open Supabase project `snmbkpjfmxrmautidlcf` → **Connect** → **Transaction pooler**.
2. Copy the exact generated transaction-pooler connection string privately.
3. Open Vercel → project `prj_uTNHTXIvJNDp1OluI9SDiQhKrEx8` → Settings → Environment Variables.
4. Update only **Production** `DATABASE_URL` with that exact string.
5. Do not manually reconstruct the pooler username, host, port, or password.
6. Do not paste the value into chat, GitHub, screenshots, or documents.
7. Current production already includes BUG-05 psycopg3 URL normalization; no driver suffix needs to be manually added to the secret.
8. Redeploy latest main exactly once after the corrected value is saved.
9. After redeploy, C02 verifies version/health/readiness/runtime.

Current non-secret evidence:
- `/version` 200 on latest main
- `/health` 500
- `/readiness` 503 database_unavailable
- Supabase shared pooler :6543 is reachable
- database authentication fails for user `postgres`

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
