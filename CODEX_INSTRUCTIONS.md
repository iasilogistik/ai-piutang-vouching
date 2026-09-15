# CODEX INSTRUCTIONS

Version: 1.0  
Status: LOCKED FOR MVP

## Operating Principle

Baca `README.md`, `PROJECT_CHARTER.md`, `VOUCHING_RULES.md`, dan `DATA_MODEL.md` sebelum coding. Jangan mengubah business rule locked tanpa persetujuan project owner.

## Architecture Principle

Sistem memiliki dua tahap:

1. Program SAP ↔ Fisik Billing
2. Fisik Billing ↔ Fisik SPJ

Billing menjadi titik penghubung.

## Deterministic Audit Logic

OCR/LLM hanya membantu ekstraksi, normalization, dan confidence. Final PASS/REVIEW/EXCEPTION harus berasal dari deterministic rule engine.

## Traceability

Raw OCR tidak boleh dihapus. Simpan raw value, normalized value, confidence, page, dan bounding box jika tersedia.

## Security

Tidak boleh hardcode secret/API key/password. Gunakan environment variables. `.env` harus masuk `.gitignore`; sediakan `.env.example`.

## Scope Control

Jangan menambahkan ERP integration, GL, AR Aging, payment matching, tax invoice, PO/DO/contract matching, fraud detection, mobile app, chatbot, atau automatic audit opinion ke V1 tanpa persetujuan.

## Development Method

TASK → IMPLEMENT → TEST → REVIEW → COMMIT → NEXT TASK.

Task berikutnya tidak dikerjakan sebelum task sebelumnya memenuhi Definition of Done.

## Git

Gunakan commit kecil dan jelas, misalnya:

- `feat: create initial database schema`
- `feat: add SAP billing import`
- `feat: add physical billing upload`
- `feat: implement billing reconciliation`
- `feat: implement SPJ vouching`
- `test: add reconciliation test cases`

## Testing

Setiap business rule wajib memiliki automated test yang relevan. Jangan menyatakan task selesai jika test gagal.

## Definition of Done

Implementation selesai, tests pass, error handling tersedia, dokumentasi diperbarui, dan tidak merusak feature sebelumnya.

## Golden Rule

**DO NOT CHANGE BUSINESS LOGIC WITHOUT PROJECT OWNER APPROVAL.**
