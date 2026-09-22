# Live Multi-Role RBAC UAT

This runbook executes the authenticated production acceptance matrix for issue #89 without storing credentials in Git.

## Prerequisites

Production must have four active Supabase Auth users mapped in `public.user_roles`:

| Role | Branch |
|---|---|
| ADMIN | no branch / all branches |
| AUDITOR | PASURUAN |
| REVIEWER | PASURUAN |
| VIEWER | PASURUAN |

The canonical branch master already contains active branch `PASURUAN`.

Auth users must be created through an authorized Supabase Auth management path. Do not insert users directly into `auth.users`.

After the Auth users exist, assign the application role/branch from:

```text
/ui/users
```

using an ADMIN bearer token.

## Obtain tokens

Log in once for each UAT account via `/auth/login` or the application login page. Keep tokens only in the local shell/session. Never commit them.

Example shell setup:

```bash
export ADMIN_TOKEN='...'
export AUDITOR_TOKEN='...'
export REVIEWER_TOKEN='...'
export VIEWER_TOKEN='...'
export UAT_BRANCH='PASURUAN'
```

Optional:

```bash
export UAT_BASE_URL='https://ai-piutang-vouching.vercel.app'
export UAT_OTHER_BRANCH='__UAT_OUTSIDE_SCOPE__'
```

## Run

```bash
python scripts/live_rbac_uat.py
```

The script never prints bearer tokens.

## What it validates

The harness checks:

1. `/auth/me` identifies the expected role and branch.
2. All four roles can read authorized findings, follow-up and search endpoints.
3. Only ADMIN can list `/admin/users`.
4. AUDITOR/REVIEWER/VIEWER cannot request another branch through findings/search/follow-up filters.
5. Finding creation allows ADMIN/AUDITOR and blocks REVIEWER/VIEWER.
6. Finding reopen allows ADMIN/REVIEWER and blocks AUDITOR/VIEWER.
7. Follow-up verification allows ADMIN/REVIEWER and blocks AUDITOR/VIEWER.

The mutation-role checks use resource ID `2147483647`, which is intentionally nonexistent. Authorized roles should therefore receive HTTP 404 before any mutation can occur; unauthorized roles should receive HTTP 403. No audit business data should be changed by these probes.

## Exit codes

- `0`: all checks passed.
- `1`: one or more authorization expectations failed.
- `2`: setup/precondition failure, such as a missing token.

## Completion evidence

Attach to UAT-01 (#89):

- script summary showing all checks passed,
- production `/version` response,
- production `/readiness` response,
- Supabase role count by role/branch,
- any negative-test observations.

Do not attach bearer tokens, passwords, refresh tokens, service keys, or database credentials.
