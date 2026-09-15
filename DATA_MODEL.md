# DATA MODEL

Version: 1.0

## Core Entities

### documents

- id
- file_name
- file_type
- document_type (`SPJ`, `BILLING`)
- file_hash
- storage_path
- uploaded_by
- uploaded_at

### import_batches

- id
- file_name
- period
- uploaded_by
- uploaded_at
- total_records
- status

### sap_billing

- id
- import_batch_id
- customer
- customer_account_name
- billing_document
- doc_date
- nominal
- created_at

### physical_billing

- id
- document_id
- billing_document_raw
- billing_document
- no_spj_raw
- no_spj
- doc_date
- nominal
- ocr_confidence
- created_at

### billing_reconciliation

- id
- sap_billing_id
- physical_billing_id
- billing_match
- date_match
- nominal_match
- nominal_difference
- status
- exception_code
- remarks
- created_at

### spj

- id
- document_id
- no_spj_raw
- no_spj
- ocr_confidence
- created_at

### vouching_result

- id
- billing_id
- spj_id
- no_spj_billing
- no_spj_document
- spj_match
- status
- rule_code
- remarks
- reviewer_id
- reviewed_at

## OCR Traceability

Untuk field hasil OCR, simpan raw value, normalized value, confidence, page number, dan bounding box jika tersedia.

## Integrity

Gunakan primary key, foreign key, index, unique constraint yang relevan, transaction, dan database-level validation. Uniqueness Physical Billing harus mempertimbangkan population/import batch agar nomor yang valid pada population berbeda tidak keliru dianggap duplicate.
