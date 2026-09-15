# TASK-017 — End-to-End Testing

## Tujuan
Memastikan alur utama berjalan dari SAP population sampai overall result dan reporting.

## Coverage
- SAP billing population.
- Physical Billing and SPJ records.
- SAP vs Billing reconciliation.
- Billing vs SPJ vouching.
- Overall result.
- Audit trail.
- Excel/PDF reporting.
- Exception paths: not found, duplicate physical Billing, missing SPJ, duplicate SPJ, and field mismatch.

## Acceptance criteria
1. E2E PASS flow returns overall `PASS`.
2. Material mismatch returns `EXCEPTION`.
3. Ambiguous/incomplete evidence returns `REVIEW` where defined by rules.
4. Migration from head succeeds.
5. Full pytest suite passes.
6. No business rule regression.
