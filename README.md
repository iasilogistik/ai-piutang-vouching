# AI Piutang Vouching

Foundation project for SAP-to-physical billing reconciliation and SPJ vouching.

## Development

### Prerequisites
- Python 3.11+
- PostgreSQL 16+ (or Docker)
- Git

### Setup

```bash
python -m venv .venv
# Windows
.venv\\Scripts\\activate
# Linux/macOS
source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env  # Windows
# cp .env.example .env  # Linux/macOS
```

Set `DATABASE_URL` in `.env` for your local PostgreSQL database.

### Database and migration

```bash
alembic upgrade head
```

### Run

```bash
uvicorn app.main:app --reload
```

Health check: `GET /health` should return HTTP 200 and `{"status":"healthy"}`.

### Import Program SAP

The SAP population must be uploaded before physical-document vouching. The API accepts an Excel file with these columns:

- `Customer`
- `Customer Account: Name`
- `Billing Document`
- `Doc. Date`
- `Nominal`

```text
POST /sap/import
```

The importer validates required columns, dates, nominal values, missing Billing Document, and duplicate Billing Document within the same batch.

### Test

```bash
pytest
```

## Scope

See `PROJECT_CHARTER.md`, `REQUIREMENTS.md` (when added), and `VOUCHING_RULES.md` for locked business requirements. Task-specific instructions are in `TASKS/`.
