# Deployment Checklist

## Before deployment
- [ ] PostgreSQL 16 is available.
- [ ] `POSTGRES_PASSWORD` is supplied through the deployment environment; never commit it.
- [ ] `.env.example` is used as the configuration template.
- [ ] Database backup is completed.
- [ ] CI migration and test checks are green.

## Deploy
```bash
docker compose build
docker compose up -d
```

The application container runs `alembic upgrade head` before starting Uvicorn.

## Verify
```bash
curl http://localhost:8000/health
```

Expected response:
```json
{"status":"healthy"}
```

Then perform a controlled smoke test: import a small SAP population, upload one Billing and one SPJ, run OCR where applicable, run reconciliation, run SPJ vouching, inspect overall result, and generate XLSX/PDF reports.

## Rollback
1. Stop the application container.
2. Restore the database from the pre-deployment backup if a data migration rollback is required.
3. Deploy the previous known-good image/commit.
4. Verify `/health` and rerun the smoke test.

## Data protection
Physical documents and generated reports are stored under the persistent `/app/storage` volume. Back up both PostgreSQL and application storage according to the organization's retention policy.
