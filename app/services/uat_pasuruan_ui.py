from __future__ import annotations


PASURUAN_DOCUMENTS = [
    ("SANTOSO", "8501735930"),
    ("Gemilang 86", ""),
    ("Berkah Al Aqso", "8501681202"),
    ("Wonokoyo", "8501681154"),
    ("Sumber Pasir", "8501755230"),
    ("Rajawali", "8540132459"),
    ("Firza Jaya", "8540130655"),
    ("Lancar Keramik", "8540131695"),
    ("Icha Jaya Kencana Sakti", "8501709449"),
    ("TB Joyo Arjuno Prigen", "8540088421"),
]


def uat_pasuruan_html() -> str:
    """Return a static UAT runner page for the Pasuruan pilot batch.

    This page is intentionally local-browser only. It helps auditors run and
    evidence the UAT sequence without storing UAT checklist state in the
    production database.
    """

    rows = "\n".join(
        f"""
        <tr>
          <td><input type=\"checkbox\" data-check=\"doc-{index}\" /></td>
          <td>{index}</td>
          <td>{customer}</td>
          <td>{billing or '-'}</td>
          <td><input type=\"text\" placeholder=\"PASS / REVIEW / EXCEPTION\" /></td>
          <td><input type=\"text\" placeholder=\"Catatan hasil cek manual\" /></td>
        </tr>
        """
        for index, (customer, billing) in enumerate(PASURUAN_DOCUMENTS, start=1)
    )

    return f"""
<!doctype html>
<html lang=\"id\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>UAT Pasuruan Final</title>
  <style>
    :root {{ --bg:#f6f8fb; --card:#fff; --line:#d9e0ea; --text:#182433; --muted:#64748b; --blue:#1f6feb; --green:#188038; --red:#b3261e; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: Arial, Helvetica, sans-serif; background: var(--bg); color: var(--text); }}
    header {{ background: #0f172a; color: white; padding: 18px 24px; }}
    header h1 {{ margin: 0; font-size: 22px; }}
    header p {{ margin: 6px 0 0; color: #cbd5e1; }}
    main {{ padding: 20px 24px 40px; }}
    .grid {{ display: grid; grid-template-columns: repeat(3, minmax(160px, 1fr)); gap: 12px; margin-bottom: 16px; }}
    .card, .panel {{ background: var(--card); border: 1px solid var(--line); border-radius: 12px; box-shadow: 0 1px 3px rgba(15,23,42,.06); }}
    .card {{ padding: 16px; }}
    .card .label {{ color: var(--muted); font-size: 13px; }}
    .card .value {{ font-size: 26px; font-weight: 800; margin-top: 5px; }}
    .panel {{ padding: 16px; margin: 14px 0; overflow: auto; }}
    h2 {{ margin: 0 0 10px; font-size: 18px; }}
    ol {{ margin-top: 8px; }}
    li {{ margin: 7px 0; }}
    table {{ width: 100%; border-collapse: collapse; min-width: 900px; }}
    th, td {{ border-bottom: 1px solid var(--line); text-align: left; padding: 9px 10px; font-size: 13px; vertical-align: top; }}
    th {{ background: #f8fafc; color: #334155; }}
    input[type='text'], textarea {{ width: 100%; border: 1px solid var(--line); border-radius: 8px; padding: 8px; font: inherit; }}
    button {{ border: 0; border-radius: 8px; padding: 10px 13px; background: var(--blue); color: white; font-weight: 700; cursor: pointer; }}
    button.secondary {{ background: #475569; }}
    .status {{ font-weight: 700; }}
    .ready {{ color: var(--green); }}
    .not-ready {{ color: var(--red); }}
    .actions {{ display: flex; gap: 8px; flex-wrap: wrap; }}
    @media (max-width: 900px) {{ .grid {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
<header>
  <h1>UAT Pasuruan Final</h1>
  <p>Checklist pilot end-to-end untuk SAP, Billing, SPJ, control evidence, manual review, export Excel, dan audit trail.</p>
</header>
<main>
  <section class=\"grid\" aria-label=\"Ringkasan UAT\">
    <div class=\"card\"><div class=\"label\">Dokumen UAT</div><div class=\"value\">10</div></div>
    <div class=\"card\"><div class=\"label\">Tahap Wajib</div><div class=\"value\">8</div></div>
    <div class=\"card\"><div class=\"label\">Status Checklist</div><div class=\"value status not-ready\" id=\"status\">BELUM SELESAI</div></div>
  </section>

  <section class=\"panel\">
    <h2>Urutan UAT End-to-End</h2>
    <ol>
      <li><label><input type=\"checkbox\" data-check=\"step\" /> Import SAP Pasuruan dan validasi effective billing key.</label></li>
      <li><label><input type=\"checkbox\" data-check=\"step\" /> Upload 10 dokumen Billing/SPJ Pasuruan.</label></li>
      <li><label><input type=\"checkbox\" data-check=\"step\" /> Pastikan OCR/extraction otomatis berjalan saat upload.</label></li>
      <li><label><input type=\"checkbox\" data-check=\"step\" /> Jalankan SAP vs Billing dan Billing vs SPJ vouching.</label></li>
      <li><label><input type=\"checkbox\" data-check=\"step\" /> Buka dashboard <code>/ui/control-evidence</code> dan cek TTD penerima, TTD driver, TTD satpam, TTD BM, TTD checker, dan stempel.</label></li>
      <li><label><input type=\"checkbox\" data-check=\"step\" /> Lakukan manual review untuk data REVIEW/UNKNOWN/MISSING.</label></li>
      <li><label><input type=\"checkbox\" data-check=\"step\" /> Export Excel control evidence dan simpan sebagai evidence UAT.</label></li>
      <li><label><input type=\"checkbox\" data-check=\"step\" /> Cek audit trail untuk upload, OCR, reconciliation, dan review evidence.</label></li>
    </ol>
    <div class=\"actions\"><button type=\"button\" id=\"printBtn\">Print / Save PDF</button><button type=\"button\" class=\"secondary\" id=\"resetBtn\">Reset Checklist</button></div>
  </section>

  <section class=\"panel\">
    <h2>Daftar Evidence Pasuruan</h2>
    <table>
      <thead><tr><th>Selesai</th><th>No</th><th>Customer / File</th><th>Billing Ref</th><th>Status Auditor</th><th>Catatan</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </section>

  <section class=\"panel\">
    <h2>Kriteria Sign-off Pilot</h2>
    <ol>
      <li>Seluruh dokumen berhasil di-upload dan dapat dibuka kembali dari link dokumen.</li>
      <li>Hasil OCR menampilkan Billing/SPJ/nominal/partial payment bila tertulis jelas di dokumen.</li>
      <li>Dashboard menampilkan TTD penerima, driver, satpam, BM, checker, stempel, dan match stempel.</li>
      <li>Data yang tidak jelas masuk REVIEW, bukan dipaksakan PASS.</li>
      <li>Auditor dapat menetapkan PASS/REVIEW/EXCEPTION dengan catatan manual.</li>
      <li>Export Excel dan audit trail tersedia sebagai evidence UAT.</li>
    </ol>
  </section>
</main>
<script>
const KEY = 'uatPasuruanChecklist';
function controls() {{ return Array.from(document.querySelectorAll('input, textarea')); }}
function save() {{
  const values = controls().map(el => el.type === 'checkbox' ? el.checked : el.value);
  localStorage.setItem(KEY, JSON.stringify(values));
  updateStatus();
}}
function load() {{
  const raw = localStorage.getItem(KEY);
  if (!raw) return;
  const values = JSON.parse(raw);
  controls().forEach((el, index) => {{ if (values[index] === undefined) return; if (el.type === 'checkbox') el.checked = values[index]; else el.value = values[index]; }});
  updateStatus();
}}
function updateStatus() {{
  const boxes = Array.from(document.querySelectorAll('input[type="checkbox"]'));
  const done = boxes.filter(el => el.checked).length;
  const status = document.getElementById('status');
  if (done === boxes.length) {{ status.textContent = 'SIAP SIGN-OFF'; status.className = 'value status ready'; }}
  else {{ status.textContent = `${{done}}/${{boxes.length}} SELESAI`; status.className = 'value status not-ready'; }}
}}
document.addEventListener('input', save);
document.getElementById('printBtn').addEventListener('click', () => window.print());
document.getElementById('resetBtn').addEventListener('click', () => {{ localStorage.removeItem(KEY); location.reload(); }});
load(); updateStatus();
</script>
</body>
</html>
"""
