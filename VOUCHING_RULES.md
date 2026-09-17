# VOUCHING RULES

Version: 1.1  
Status: LOCKED

## Stage 1 — SAP vs Physical Billing

### R-SAP-001 — Cardinality

Setiap SAP Billing harus memiliki tepat satu Physical Billing.

- 0 → `EXCEPTION / BILLING_DOCUMENT_NOT_FOUND`
- 1 → lanjut pemeriksaan
- >1 → `EXCEPTION / DUPLICATE_PHYSICAL_BILLING`

### R-SAP-002 — Billing Number

`SAP.BillingDocument = PhysicalBilling.BillingDocument`

Tidak sama → `EXCEPTION / BILLING_NUMBER_MISMATCH`

### R-SAP-003 — Date

`SAP.DocDate = PhysicalBilling.DocDate`

Tidak sama → `EXCEPTION / DOC_DATE_MISMATCH`

### R-SAP-004 — Nominal setelah Partial Payment

Jika foto Physical Billing dan/atau Physical SPJ memuat pembayaran partial yang teridentifikasi secara eksplisit, seluruh nilai pembayaran partial dijumlahkan sebagai pengurang.

`NetPhysicalNominal = PhysicalBilling.Nominal - BillingPartialPayment - SPJPartialPayment`

`difference = SAP.Nominal - NetPhysicalNominal`

`difference = 0` → match.  
`difference != 0` → `EXCEPTION / NOMINAL_MISMATCH`.

Tidak ada tolerance nominal.

Pembayaran partial yang ambigu/tidak dapat diekstrak dengan yakin → `REVIEW`, bukan ditebak.

### R-SAP-005 — Partial Payment Extraction

Hanya pembayaran yang ditandai secara eksplisit sebagai partial/parsial yang diperlakukan sebagai pengurang. Nilai dan teks mentahnya disimpan terpisah untuk audit trail. Jika terdapat lebih dari satu partial payment, semuanya dijumlahkan.

## Stage 2 — Physical Billing vs Physical SPJ

### R-VCH-001 — Billing Must Have SPJ

No SPJ kosong → `EXCEPTION / BILLING_WITHOUT_SPJ`.

### R-VCH-002 — SPJ Exists

`Billing.NoSPJ` harus ditemukan pada `SPJ.NoSPJ`. Tidak ditemukan → `EXCEPTION / SPJ_NOT_FOUND`.

### R-VCH-003 — Exact SPJ Match

No SPJ Billing sama dengan No SPJ SPJ → `PASS`. Berbeda → `EXCEPTION / SPJ_MISMATCH`.

### R-VCH-004 — Duplicate SPJ Number

Lebih dari satu SPJ dengan No SPJ yang sama → `REVIEW / DUPLICATE_SPJ_NUMBER`.

## Overall Result

- SAP reconciliation `MATCH` + SPJ vouching `PASS` → `PASS`
- Material exception pada salah satu tahap → `EXCEPTION`
- Tidak ada exception tetapi ada kondisi yang memerlukan judgement → `REVIEW`

## OCR Rule

OCR hanya untuk ekstraksi dan confidence. OCR/LLM tidak boleh menentukan final audit result. Final result ditentukan deterministic rule engine.

## Normalization

Boleh melakukan trimming whitespace, standardisasi separator/case, format tanggal, dan format angka. Jangan melakukan koreksi spekulatif. Nilai yang ambigu harus masuk `REVIEW`.
