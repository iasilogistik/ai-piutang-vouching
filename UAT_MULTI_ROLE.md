# Live Multi-Role RBAC UAT — Dynamic Branch

This runbook validates authenticated production authorization for dynamic branch scope without storing credentials in Git.

## Branch model under test

Branch is a data dimension discovered from uploads, not a mandatory fixed user attribute.

Application-user semantics:

- `branch = NULL` -> global across all uploaded branches.
- non-null branch -> optional exact restriction.
- ADMIN remains global.
- Audit/business records must still carry a non-null branch.
- A new branch can be registered automatically from upload context.

The UAT therefore uses **two real branches that already exist from uploaded data**. Do not use placeholder branches for global-access checks.

## Required UAT accounts

| Account | Role | User branch |
|---|---|---|
| Admin | ADMIN | any / NULL |
| Global Auditor | AUDITOR | NULL |
| Global Reviewer | REVIEWER | NULL |
| Global Viewer | VIEWER | NULL |
| Scoped Control Viewer | VIEWER | one of the two UAT branches |

Auth users must be created through the supported Supabase Auth administration path. Do not insert directly into `auth.users`.

Map application roles/scopes through `/ui/users`. Blank branch means **Semua cabang (dinamis)**.

## Select two real uploaded branches

Choose two distinct branches already present in production upload/catalog data. Example only:

```bash
export UAT_BRANCH='GRESIK'
export UAT_SECOND_BRANCH='SIDOARJO'
export SCOPED_VIEWER_BRANCH='GRESIK'
```

Do not hard-code PASURUAN. Actual values depend on what branches have been uploaded.

`SCOPED_VIEWER_BRANCH` must equal either `UAT_BRANCH` or `UAT_SECOND_BRANCH`.

## Obtain tokens

Log in once for each UAT account. Keep access tokens only in the local shell/session.

```bash
export ADMIN_TOKEN='...'
export AUDITOR_TOKEN='...'
export REVIEWER_TOKEN='...'
export VIEWER_TOKEN='...'
export SCOPED_VIEWER_TOKEN='...'
```

Optional runtime target:

```bash
export UAT_BASE_URL='https://ai-piutang-vouching.vercel.app'
```

Never commit or attach bearer tokens, passwords, refresh tokens, service keys, or database credentials.

## Run

```bash
python scripts/live_rbac_uat.py
```

## What the harness validates

### Global users

ADMIN, global AUDITOR, global REVIEWER and global VIEWER:

1. `/auth/me` returns the expected role.
2. Non-ADMIN global accounts expose no fixed branch.
3. Each account can read findings, follow-up and global search for `UAT_BRANCH`.
4. Each account can read the same endpoints for `UAT_SECOND_BRANCH`.
5. Only ADMIN can access user administration.

### Scoped control user

The dedicated scoped VIEWER:

1. `/auth/me` returns VIEWER + its configured branch.
2. Reads to its assigned branch succeed.
3. Requests to the second real UAT branch are rejected with HTTP 403.

This proves optional branch restriction still works while the normal/global workflow is flexible.

### Role gates

The non-mutating probe matrix also confirms:

- Finding creation: ADMIN/AUDITOR allowed to reach resource lookup; REVIEWER/VIEWER denied.
- Finding reopen: ADMIN/REVIEWER allowed; AUDITOR/VIEWER denied.
- Follow-up verification: ADMIN/REVIEWER allowed; AUDITOR/VIEWER denied.

Mutation probes use intentionally nonexistent resource ID `2147483647`, so authorized roles should receive HTTP 404 and no audit business data is modified.

## Exit codes

- `0`: all checks passed.
- `1`: one or more authorization expectations failed.
- `2`: missing/invalid tokens or branch prerequisites.

## Required completion evidence for UAT-01

Attach to issue #89:

- script PASS/FAIL summary,
- production `/version`,
- production `/readiness`,
- two selected real UAT branch codes,
- user-role count showing global AUDITOR/REVIEWER/VIEWER and the scoped control VIEWER,
- any negative-test observations.

Do not attach secrets.

## Go-live relationship

Dynamic branch UAT must pass after DEV-31A/B/C are deployed and before PERF-02 policy consolidation is applied.

```text
DEV-31 dynamic branch
    -> production deploy
    -> live dynamic-branch UAT
    -> PERF-02 RLS consolidation
    -> repeat same UAT
    -> GO-LIVE sign-off
```
