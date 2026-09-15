# Development Plan

## Prinsip
- Development berbasis TASK.
- Independent tasks dikerjakan paralel; dependent tasks menunggu dependency.
- Setiap batch perubahan direview dan diuji sebelum merge.
- Business Requirement > Application Logic > AI/OCR Suggestion.

## Workstreams
| Workstream | Tasks | Fokus |
|---|---|---|
| A Core/Data | 001-004 | Foundation, schema, SAP import & validation |
| B Document/OCR | 005-006, 009-010 | Storage/upload dan OCR Billing/SPJ |
| C Business Engine | 007, 011-012 | Reconciliation, vouching, overall result |
| D UI/Control | 008, 013-015 | Dashboard, exception/review, evidence, audit trail |
| E Release | 016-018 | Reporting, E2E test, deployment |

## Dependency Plan
1. TASK-001 Foundation
2. Setelah foundation stabil, TASK-002 Database Schema menjadi dependency utama data.
3. TASK-003 SAP Import dan TASK-005 Document Storage dapat dikembangkan paralel setelah kontrak schema/storage disepakati.
4. TASK-004 SAP validation bergantung TASK-003.
5. TASK-006 Billing OCR bergantung TASK-005.
6. TASK-007 SAP Reconciliation bergantung TASK-002, TASK-003, TASK-004, TASK-006.
7. TASK-008 Dashboard dapat dimulai paralel setelah output kontrak TASK-007 disepakati.
8. TASK-009 SPJ Upload dapat berjalan paralel dengan TASK-007 setelah storage siap.
9. TASK-010 SPJ OCR bergantung TASK-009.
10. TASK-011 SPJ Vouching bergantung TASK-010 dan output Billing yang dibutuhkan.
11. TASK-012 Overall Result bergantung TASK-007 dan TASK-011.
12. TASK-013/014/015 dapat berjalan paralel setelah result/evidence contracts stabil.
13. TASK-016 Reporting bergantung result, exception, evidence, dan audit contracts.
14. TASK-017 E2E Testing setelah seluruh alur bisnis utama selesai.
15. TASK-018 Deployment setelah E2E test dan release checklist lulus.

## Parallel Execution
```text
TASK-001
   |
   +--> TASK-002 --> TASK-003 --> TASK-004 --+
   |                                          |
   +--> TASK-005 --> TASK-006 ----------------+--> TASK-007 --> TASK-008
   |                         
   +------------------------> TASK-009 --> TASK-010 --> TASK-011
                                                     |
TASK-007 --------------------------------------------+--> TASK-012
                                                          |
                              +---------------------------+----------------+
                              |                           |                |
                           TASK-013                    TASK-014         TASK-015
                              +---------------------------+----------------+
                                                          |
                                                       TASK-016
                                                          |
                                                       TASK-017
                                                          |
                                                       TASK-018
```

## Definition of Done per Task
- Implementasi sesuai task scope.
- Unit/integration tests yang relevan tersedia dan lulus.
- Error handling memadai.
- Dokumentasi task diperbarui.
- Tidak mengubah business rule tanpa approval.
- Tidak ada secret committed.
- Tidak ada regression pada test sebelumnya.

## Current Gate
TASK-001 harus lulus test lokal/CI dan migration check sebelum TASK-002 dimulai. PR TASK-001 tidak boleh di-merge sebelum CI hijau.
