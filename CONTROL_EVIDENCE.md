# SPJ CONTROL EVIDENCE

Version: 1.0  
Status: Proposed for V2 pilot

## Objective

Menambahkan pemeriksaan kelengkapan bukti pengendalian pada dokumen SPJ tanpa menilai keaslian tanda tangan/stempel.

Modul ini hanya menjawab:

- apakah evidence terindikasi tertera;
- apakah evidence tidak terindikasi;
- apakah evidence tidak dapat dipastikan dan harus dicek manual.

Modul ini tidak boleh menyatakan tanda tangan atau stempel asli/palsu.

## Evidence Fields

SPJ control evidence yang diperiksa:

1. tanda tangan penerima;
2. stempel penerima;
3. tanda tangan driver;
4. tanda tangan satpam/security;
5. tanda tangan BM;
6. tanda tangan checker.

## Status

Setiap field menghasilkan status:

- `PRESENT` — evidence terindikasi tertera;
- `MISSING` — evidence terindikasi tidak ada;
- `UNKNOWN` — OCR/scan tidak cukup untuk memastikan;
- `REVIEW` — hasil perlu pemeriksaan manual.

`UNKNOWN` bukan berarti tidak ada. `UNKNOWN` berarti sistem tidak boleh menebak dan auditor harus melihat gambar asli.

## Stamp Name Check

Untuk stempel penerima, sistem juga mencoba membaca tulisan stempel dan membandingkan dengan nama pelanggan SAP bila tersedia.

Hasil perbandingan:

- `MATCH` — nama stempel cukup cocok dengan pelanggan SAP;
- `REVIEW` — nama berbeda, hanya terbaca sebagian, atau confidence rendah;
- `NOT_EVALUATED` — nama pelanggan SAP belum tersedia pada tahap ekstraksi dokumen.

Jika tulisan stempel tidak terbaca, hasil harus masuk manual review dengan catatan yang jelas.

## Current Capability

Current production OCR berbasis teks. OCR dapat membaca nomor, tanggal, nominal, dan sebagian tulisan pada dokumen. OCR tidak cukup andal untuk membuktikan keberadaan tanda tangan yang berupa goresan tangan atau stempel yang kualitasnya rendah.

Karena itu, modul `app.services.control_evidence` menggunakan prinsip konservatif:

- `PRESENT` hanya diberikan bila OCR secara eksplisit mengindikasikan evidence tertera;
- label form seperti `Checker`, `Driver`, atau `Penerima` saja tidak dianggap bukti tanda tangan;
- bila label terbaca tetapi tanda tangan tidak dapat dipastikan, status menjadi `UNKNOWN` dengan alasan manual review;
- stempel dibandingkan dengan nama pelanggan SAP hanya bila tulisan stempel terbaca.

## Future Vision Provider

Untuk deteksi visual penuh dari gambar/PDF scan, aplikasi perlu vision provider yang mampu menganalisis area tanda tangan dan stempel. Output vision tetap harus mengikuti status di atas dan tidak boleh menilai keaslian.

Deterministic rule engine tetap menjadi penentu hasil akhir audit. AI/vision hanya menyediakan evidence dan alasan review.
