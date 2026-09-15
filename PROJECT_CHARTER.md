# PROJECT CHARTER — AI PIUTANG VOUCHING

Version: 1.0  
Status: LOCKED

## Objective

Membangun sistem yang membantu pemeriksaan dokumen piutang dengan dua tahap:

1. Program SAP ↔ Fisik Billing
2. Fisik Billing ↔ Fisik SPJ

## In Scope

### Program SAP
- Customer
- Customer Account Name
- Billing Document
- Doc Date
- Nominal

### Fisik Billing
- Billing Document
- Doc Date
- Nominal
- No SPJ

### Fisik SPJ
- No SPJ

### Processing
- OCR
- Normalization
- Matching
- Deterministic rule engine
- Exception
- Review
- Reporting
- Audit trail

## Cardinality Rule

**1 SAP Billing = tepat 1 Physical Billing.**

- 0 physical billing → `EXCEPTION`
- >1 physical billing → `EXCEPTION`

## Vouching Relationship

Physical Billing → Physical SPJ berdasarkan **No. SPJ**.

## Overall Result

Setiap Billing memiliki:
- SAP vs Fisik Result
- SPJ vs Billing Result
- Overall Result

## Out of Scope V1

GL, AR Aging, Payment, Faktur Pajak, PO, DO, Contract, ERP integration, fraud detection, mobile app, chatbot, automatic audit opinion.

## Success Criteria

Reviewer dapat import population SAP, upload Billing fisik, menjalankan rekonsiliasi, melihat exception, upload SPJ, melakukan vouching, melihat evidence/audit trail, dan export hasil.
