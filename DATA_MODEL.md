# DATA MODEL

Version: 1.1

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
- partial_payment_raw
- partial_payment
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
- partial_payment_raw
- partial_payment
- ocr_confidence
- created_at

### document_control_evidence

Hasil deteksi kelengkapan bukti pengendalian SPJ. Sistem hanya mendeteksi keterteraaan bukti, tidak menilai keaslian tanda tangan/stempel.

- id
- document_id
- receiver_signature_status
- receiver_signature_confidence
- receiver_signature_remarks
- driver_signature_status
- driver_signature_confidence
- driver_signature_remarks
- security_signature_status
- security_signature_confidence
- security_signature_remarks
- bm_signature_status
- bm_signature_confidence
- bm_signature_remarks
- checker_signature_status
- checker_signature_confidence
- checker_signature_remarks
- receiver_stamp_status
- receiver_stamp_confidence
- receiver_stamp_remarks
- stamp_text_raw
- stamp_text_normalized
- stamp_customer_match_status
- stamp_customer_match_confidence
- stamp_customer_match_remarks
- review_required
- review_reasons
- created_at
- updated_at

Status evidence: `PRESENT`, `MISSING`, `UNKNOWN`, `REVIEW`, `MATCH`, atau `NOT_EVALUATED` sesuai jenis field. Jika OCR/scan tidak cukup meyakinkan, sistem menyimpan alasan manual review.

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

Untuk field hasil OCR, simpan raw value, normalized value, confidence, page number, dan bounding box jika tersedia. Untuk evidence SPJ, simpan status, confidence, raw stamp text, normalized stamp text, dan alasan manual review.

## Integrity

Gunakan primary key, foreign key, index, unique constraint yang relevan, transaction, dan database-level validation. Uniqueness Physical Billing harus mempertimbangkan population/import batch agar nomor yang valid pada population berbeda tidak keliru dianggap duplicate.
