# TASK-002 — Database Schema

## Objective
Implement the core relational schema required by DATA_MODEL.md.

## Scope
- documents
- import_batches
- sap_billing
- physical_billing
- billing_reconciliation
- spj
- vouching_result
- SQLAlchemy models
- Alembic migration
- schema integration tests

## Acceptance criteria
1. Migration upgrades from foundation successfully.
2. All seven core tables exist with required foreign keys and indexes.
3. SQLAlchemy models reflect the schema.
4. Schema tests verify the critical one-to-one cardinality constraints.
5. Schema tests pass in CI with PostgreSQL.
6. Existing health test remains green.
7. No business rule is changed.
