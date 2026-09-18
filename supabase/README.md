# Supabase Setup
Run schema.sql in the connected Supabase project. The schema mirrors the current FastAPI/SQLAlchemy MVP and adds traceability for OCR extraction, signatures/stamps, and handwriting adjustments.
The evidence bucket is private. RLS is enabled on application tables. Browser-facing policies are intentionally deferred until Auditor/Reviewer/Admin authentication is implemented.
Never commit database passwords, service-role keys, or other secrets.
