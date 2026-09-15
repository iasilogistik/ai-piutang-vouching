# TASK-016 — Excel/PDF Reporting

## Tujuan
Menyediakan laporan hasil rekonsiliasi dan vouching yang dapat diekspor untuk kebutuhan review dan dokumentasi audit.

## Acceptance criteria
1. Endpoint laporan tersedia untuk batch SAP.
2. Format Excel (`xlsx`) berisi summary dan detail rekonsiliasi/SPJ.
3. Format PDF berisi summary dan detail ringkas.
4. Report hanya membaca hasil yang sudah diproses; report tidak mengubah business result.
5. File report disimpan di storage laporan dengan nama unik.
6. Test XLSX dan PDF lulus.
