# Deployment Checklist

## Delivery model
- `main` is the production branch.
- Routine development branches (`feature/*`, `fix/*`, `chore/*`, `codex/*`, `dev/*`) are disabled from automatic Vercel deployment through `vercel.json`.
- GitHub CI remains the required validation gate for feature branches and pull requests.
- Preview deployment should be an explicit exception, not a deployment for every intermediate commit.

This policy exists to prevent Vercel deployment quota exhaustion while preserving CI coverage.

## Before deployment
- [ ] CI migration and test checks are green.
- [ ] Production Supabase migration history contains every migration required by the target `main` commit.
- [ ] Database backup/restore procedure is current for any migration that changes production data.
- [ ] Required Vercel production environment variables are present.
- [ ] The target `main` SHA is recorded before release.

## Schema-first production sequence
For additive migrations used by this project:

1. Merge only after CI validates a clean `alembic upgrade head`.
2. Apply the required migration to production Supabase.
3. Verify tables, RLS policies, and Supabase security advisors.
4. Merge/deploy the application commit.
5. Run the production smoke workflow.
6. Confirm the Vercel production deployment SHA matches latest approved `main`.

This order prevents new application code from reaching production before the database objects it requires exist.

## Vercel quota recovery
If Vercel reports:

```
Resource is limited - try again in 24 hours
(more than 100, code: "api-deployments-free-per-day")
```

do not create repeated retrigger commits. Wait for quota recovery, then create or retry one production deployment for the latest approved `main` SHA. Intermediate feature commits should remain CI-only.

## Production smoke
The smoke script requires no application credentials. It validates:

- `/health` returns HTTP 200 with `{"status":"healthy"}`.
- Latest UI shells are reachable.
- Protected API routes return HTTP 401 without a bearer token.

Run locally:

```bash
python scripts/production_smoke.py
```

Or trigger GitHub Actions workflow **Production Smoke**. An alternate deployment URL can be supplied through the workflow input or:

```bash
PRODUCTION_BASE_URL=https://example.vercel.app python scripts/production_smoke.py
```

## Docker deployment
For non-Vercel deployments:

```bash
docker compose build
docker compose up -d
```

The application container runs `alembic upgrade head` before starting Uvicorn.

## Rollback
1. Identify the previous known-good application commit/deployment.
2. If the release included a destructive/data migration, restore the approved pre-deployment database backup rather than blindly downgrading schema.
3. Restore/promote the previous application deployment.
4. Run `/health` and the production smoke workflow.
5. Record rollback reason and affected release SHA.

## Data protection
Physical documents and generated reports must use persistent storage. Back up PostgreSQL/Supabase data and audit evidence according to the organization's retention policy.
