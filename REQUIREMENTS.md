# REQUIREMENTS — AI PIUTANG VOUCHING

Version: 1.0  
Status: LOCKED

## Workflow

1. Auditor mengunggah population SAP terlebih dahulu.
2. Auditor mengunggah dokumen fisik Billing dan SPJ.
3. Sistem otomatis mengekstrak field dari dokumen fisik saat upload; auditor tidak perlu menjalankan OCR sebagai langkah terpisah.
4. Hasil ekstraksi dinormalisasi dan disimpan bersama raw value.
5. Deterministic rule engine menjalankan SAP ↔ Billing reconciliation dan Billing ↔ SPJ vouching.
6. Reviewer memeriksa REVIEW/EXCEPTION, evidence, audit trail, dan report.

## SAP Population

Field:
- Customer
- Customer Account: Name
- Billing Document
- Doc. Date
- Nominal

Effective key:
- gunakan Billing Document;
- jika kosong, gunakan Text;
- jika Billing Document dan Text kosong, keluarkan baris;
- duplicate effective key dijumlahkan pada nominal.

## Physical Billing

Ekstrak:
- No Billing
- No SPJ
- tanggal
- nominal
- partial payment bila ada

## Physical SPJ

Ekstrak:
- No SPJ
- partial payment bila ada

Partial payment bersifat opsional. Tidak ditemukan berarti Rp0 dan bukan error. Nilai ambigu masuk REVIEW dan tidak boleh ditebak.

## Audit Decision

OCR/document extraction hanya menghasilkan evidence. PASS/MATCH/REVIEW/EXCEPTION ditentukan oleh deterministic rules pada VOUCHING_RULES.md.

## Traceability

Simpan raw OCR/extraction dan normalized value secara terpisah. Simpan confidence, page, dan bounding box jika tersedia. Raw evidence tidak boleh ditimpa oleh hasil normalisasi.

## Security

Tidak boleh hardcode secret. Dokumen audit disimpan private. Akses aplikasi harus mengikuti RBAC.

## Out of Scope V1

ERP integration, GL, AR Aging, payment matching umum, faktur pajak, PO, DO, contract matching, fraud detection, mobile app, chatbot, dan automatic audit opinion.
