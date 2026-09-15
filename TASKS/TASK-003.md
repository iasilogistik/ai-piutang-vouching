# TASK-003 — Import Program SAP Excel

## Objective
Import the Program SAP billing population into the database before any physical-document vouching.

## Scope
- Accept SAP Excel upload (`.xlsx`/`.xls` filename validation; parser currently requires a format readable by pandas/openpyxl).
- Validate required columns:
  - `Customer`
  - `Customer Account: Name`
  - `Billing Document`
  - `Doc. Date`
  - `Nominal`
- Normalize whitespace in text fields.
- Parse Doc. Date to database `date`.
- Parse Nominal to `Decimal` with 2 decimal places.
- Reject missing Billing Document.
- Reject duplicate Billing Document within the imported batch.
- Persist `import_batches` and `sap_billing` records atomically.
- Expose `POST /sap/import` for the import operation.

## Explicit non-scope
- No physical Billing upload.
- No OCR.
- No reconciliation/matching.
- No SAP/ERP integration.
- No speculative correction of source values.

## Acceptance criteria
1. Valid SAP Excel creates one import batch and one SAP billing row per source row.
2. Required-column validation returns a clear error.
3. Invalid date or nominal values are rejected.
4. Missing Billing Document is rejected.
5. Duplicate Billing Document in one batch is rejected.
6. Existing health/schema tests remain green.
7. CI runs migration and tests successfully on PostgreSQL.
8. No business rule is changed.
