# AI Piutang Vouching

Sistem pemeriksaan dokumen piutang berbasis OCR dengan dua tahap pemeriksaan:

1. **Rekonsiliasi Program SAP ↔ Fisik Billing**
2. **Vouching Fisik Billing ↔ Fisik SPJ**

## Business Rule Utama

- 1 Billing pada Program SAP = tepat 1 dokumen Billing fisik.
- Jika 0 dokumen fisik: `EXCEPTION / BILLING_DOCUMENT_NOT_FOUND`.
- Jika >1 dokumen fisik: `EXCEPTION / DUPLICATE_PHYSICAL_BILLING`.
- SAP vs Billing dibandingkan berdasarkan Billing Document, Doc Date, dan Nominal.
- Billing vs SPJ dibandingkan berdasarkan No. SPJ.
- OCR membantu ekstraksi data, tetapi **tidak menentukan hasil audit**. Final result ditentukan deterministic rule engine.

## Status

`PASS` · `REVIEW` · `EXCEPTION` · `NOT_FOUND`

## Project Documents

- [PROJECT_CHARTER.md](PROJECT_CHARTER.md)
- [REQUIREMENTS.md](REQUIREMENTS.md)
- [DATA_MODEL.md](DATA_MODEL.md)
- [VOUCHING_RULES.md](VOUCHING_RULES.md)
- [CODEX_INSTRUCTIONS.md](CODEX_INSTRUCTIONS.md)
- [TASKS/TASK-001.md](TASKS/TASK-001.md)

## Development Principle

Project dikembangkan secara bertahap per task. Business rule yang sudah berstatus LOCKED tidak boleh diubah tanpa persetujuan project owner.
