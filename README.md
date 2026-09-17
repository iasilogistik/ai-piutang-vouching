# AI Piutang Vouching

Foundation for SAP-to-physical Billing reconciliation and SPJ vouching.

## Current flow
1. Upload Program SAP Excel (`POST /sap/import`).
2. Validate SAP population (`GET /sap/validate/{batch_id}`).
3. Upload physical Billing/SPJ (`POST /documents/BILLING`, `POST /documents/SPJ`).
4. Run OCR/extraction for all physical documents (`POST /documents/{document_id}/ocr`).
5. Run SAP ↔ Billing reconciliation (`POST /reconciliation/{batch_id}/run`).
6. Review reconciliation summary (`GET /reconciliation/{batch_id}`).
7. Run Billing ↔ SPJ vouching (`POST /spj/vouch`).
8. Read overall result (`GET /results/{billing_id}`).
9. Review exceptions (`GET /exceptions`) and record reviewer decisions (`POST /reviews/vouching/{result_id}`).
10. View evidence metadata/source file (`GET /documents/{document_id}`, `GET /documents/{document_id}/content`).
11. Review audit trail (`GET /audit-trail`).
12. Generate Excel/PDF report (`GET /reports/{batch_id}?format=xlsx|pdf`).

## Business guardrails
- SAP is the expected population.
- One SAP Billing = exactly one physical Billing document.
- Nominal comparison is exact after documented partial-payment deductions.
- Explicit partial-payment amounts found by OCR on Billing and/or SPJ are summed and deducted from the document nominal.
- Partial-payment text is retained separately from the normalized amount; ambiguous extraction is for human review.
- OCR is evidence extraction only; deterministic rules make vouching decisions.
- Raw OCR and normalized values are retained separately.
- Ambiguous/incomplete extraction is surfaced for human review.

## Development
Python 3.11+, PostgreSQL 16+.

```bash
python -m venv .venv
# Windows
.venv\\Scripts\\activate
# Linux/macOS
source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env  # Windows
# cp .env.example .env  # Linux/macOS
alembic upgrade head
uvicorn app.main:app --reload
pytest -q
```

## Docker
Set `POSTGRES_PASSWORD` in the environment, then:

```bash
docker compose build
docker compose up -d
```

The application image installs Tesseract OCR and runs database migrations before starting the API. See `DEPLOYMENT.md` for the release and rollback checklist.

## Testing gate
Every task must pass implementation tests, migration checks, and relevant end-to-end checks before release. The release gate is TASK-017/018 with green CI and a completed smoke test.

See `PROJECT_CHARTER.md`, `REQUIREMENTS.md`, `VOUCHING_RULES.md`, `DATA_MODEL.md`, `CODEX_INSTRUCTIONS.md`, and `DEVELOPMENT_PLAN.md` for locked scope and task rules.
