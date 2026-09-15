# TASK-015 — Audit Trail

## Tujuan
Menyediakan jejak aktivitas yang dapat ditelusuri untuk proses import SAP, upload dokumen, OCR, rekonsiliasi, vouching, dan review.

## Ruang lingkup
- Tabel `audit_trail` dengan entity, action, actor, status sebelum/sesudah, remarks, metadata, dan timestamp.
- Pencatatan aktivitas utama pada API.
- Endpoint `GET /audit-trail` untuk pencarian berdasarkan entity dan entity ID.
- Metadata tidak boleh menyimpan secret, password, token, atau isi dokumen mentah.

## Prinsip
- Audit entry bersifat append-only pada level aplikasi.
- Audit trail tidak mengubah business rule vouching.
- Status audit harus mencerminkan aktivitas yang benar-benar terjadi.
- Kegagalan transaksi harus rollback sehingga audit tidak mencatat keberhasilan palsu.

## Acceptance criteria
1. Migration `0003_audit_trail` berhasil dari `0002_schema`.
2. Aktivitas utama menghasilkan audit entry.
3. Review menyimpan actor dan perubahan status.
4. Audit dapat difilter berdasarkan entity/entity ID.
5. Metadata dapat disimpan tanpa secret.
6. Unit test audit trail lulus.
7. CI migration dan pytest hijau.
8. Tidak ada perubahan business rule.
