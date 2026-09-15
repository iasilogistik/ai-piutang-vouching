# TASK-018 — Deployment & Release

## Tujuan
Menyiapkan aplikasi untuk deployment yang reproducible dan aman.

## Deliverables
- Dockerfile dengan Python 3.11 dan Tesseract OCR runtime.
- docker-compose untuk aplikasi + PostgreSQL.
- Environment variables melalui `.env`; tidak ada secret di repository.
- Deployment checklist.
- Health check dan migration sebelum service digunakan.

## Release gate
1. CI migration hijau.
2. Full pytest hijau.
3. E2E test hijau.
4. `.env.example` tersedia dan secret-free.
5. Database backup/restore procedure tersedia.
6. Business rules tidak berubah saat deployment.
