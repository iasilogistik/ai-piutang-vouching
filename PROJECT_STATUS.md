# PROJECT STATUS
Version: 1.1 — 2026-09-18
The repository MVP already contains SAP import, Billing/SPJ upload, OCR, reconciliation, vouching, partial-payment handling, audit trail, and reporting.
This batch adds the Supabase schema, private evidence bucket, and AI evidence-traceability tables.
Locked rules: SAP is source population; ambiguous extraction becomes REVIEW; Security TTD is not mandatory; AI detects evidence but does not prove signature/stamp authenticity; auditor makes final decisions.
Production validation still required: real document UAT, handwriting/signature/stamp accuracy, live backend connection, and final RLS/auth policies.
