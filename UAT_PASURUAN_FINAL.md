# UAT Pasuruan Final

Dokumen ini digunakan sebagai checklist resmi pilot terbatas Pasuruan untuk aplikasi AI Piutang Vouching.

## Tujuan

Memastikan alur audit end-to-end berjalan dari upload data sampai evidence review:

1. Import SAP.
2. Upload Billing dan SPJ.
3. Auto OCR/extraction.
4. SAP vs Billing reconciliation.
5. Billing vs SPJ vouching.
6. SPJ control evidence: TTD penerima, driver, satpam, BM, checker, stempel.
7. Manual review PASS / REVIEW / EXCEPTION.
8. Export Excel dan audit trail.

## Dataset Pasuruan

| No | Customer / File | Billing Ref |
|---:|---|---|
| 1 | SANTOSO | 8501735930 |
| 2 | Gemilang 86 | - |
| 3 | Berkah Al Aqso | 8501681202 |
| 4 | Wonokoyo | 8501681154 |
| 5 | Sumber Pasir | 8501755230 |
| 6 | Rajawali | 8540132459 |
| 7 | Firza Jaya | 8540130655 |
| 8 | Lancar Keramik | 8540131695 |
| 9 | Icha Jaya Kencana Sakti | 8501709449 |
| 10 | TB Joyo Arjuno Prigen | 8540088421 |

## Halaman UAT

Buka:

```text
/ui/uat-pasuruan
```

Halaman ini berisi checklist browser-side untuk auditor. Status checklist disimpan di localStorage browser dan tidak masuk database produksi.

## Halaman Dashboard Evidence

Buka:

```text
/ui/control-evidence
```

Masukkan Bearer token, lalu cek:

- Overall control status.
- TTD penerima.
- TTD driver.
- TTD satpam/security.
- TTD BM.
- TTD checker.
- Stempel.
- Nama stempel.
- Match stempel vs customer.
- Alasan review.
- Tombol PASS / REVIEW / EXCEPTION.
- Export Excel.

## Kriteria PASS

Satu dokumen dinyatakan PASS apabila:

1. Dokumen berhasil di-upload dan dapat dibuka kembali.
2. Nomor billing / SPJ / nominal terbaca jika tersedia di dokumen.
3. SAP vs Billing tidak memiliki selisih material.
4. Billing vs SPJ match.
5. Evidence TTD/stempel yang wajib terdeteksi atau sudah divalidasi manual.
6. Review status akhir ditetapkan PASS oleh auditor bila sebelumnya masuk REVIEW.

## Kriteria REVIEW

Dokumen tetap REVIEW apabila:

1. TTD/stempel tidak jelas.
2. Nama stempel tidak terbaca penuh.
3. Nama stempel berbeda sebagian dengan nama customer SAP.
4. Nominal/partial payment kurang jelas.
5. Ada data yang perlu dikonfirmasi ke cabang.

## Kriteria EXCEPTION

Dokumen menjadi EXCEPTION apabila auditor menyimpulkan ada ketidaksesuaian setelah review manual, misalnya:

1. Billing tidak sesuai SAP.
2. SPJ tidak sesuai billing.
3. Nominal tidak sesuai dan tidak dapat dijelaskan.
4. Stempel jelas berbeda dengan customer SAP.
5. Dokumen evidence wajib tidak tersedia setelah konfirmasi.

## Evidence Sign-off

Minimal evidence yang harus disimpan:

1. Export Excel control evidence.
2. Screenshot dashboard control evidence.
3. Audit trail review evidence.
4. Catatan gap / issue UAT.
5. Daftar perbaikan yang diperlukan sebelum pilot cabang berikutnya.

## Batasan

Aplikasi tidak menilai keaslian tanda tangan atau stempel. Sistem hanya mendeteksi keberadaan evidence, membaca teks stempel bila memungkinkan, membandingkan nama stempel dengan customer SAP, dan mengarahkan item tidak jelas ke manual review.
