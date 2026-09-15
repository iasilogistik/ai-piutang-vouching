# TASK-001 — PROJECT FOUNDATION

Status: TODO  
Priority: P0  
Phase: Foundation

## Objective

Membuat skeleton aplikasi AI Piutang Vouching yang siap dikembangkan.

## Scope

1. Repository structure
2. Application configuration
3. Database connection
4. Initial database migration
5. Environment configuration
6. Basic health check
7. Basic test framework
8. Docker configuration jika digunakan
9. README development setup

## DO NOT IMPLEMENT

- OCR
- SAP import
- Billing upload
- SPJ upload
- Matching
- Dashboard
- AI/LLM
- Reporting

## Acceptance Criteria

- Application dapat dijalankan secara lokal.
- `.env.example` tersedia dan tidak ada secret di repository.
- Database dapat connect dan migration berhasil.
- Health check mengembalikan healthy/HTTP 200.
- Test framework dapat dijalankan dan semua test pass.
- README menjelaskan prerequisites, installation, environment, database, migration, run, dan test.

## Definition of Done

- Application starts.
- Database connects.
- Migration succeeds.
- Test suite passes.
- README tersedia.
- No secret committed.
