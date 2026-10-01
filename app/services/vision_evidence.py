from __future__ import annotations

import base64
import io
import json
import os
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import httpx


AI_GATEWAY_URL = "https://ai-gateway.vercel.sh/v1/chat/completions"
DEFAULT_VISION_MODEL = "openai/gpt-5.6-sol"
MAX_PAGES = 3


def _gateway_token() -> str | None:
    return (os.getenv("AI_GATEWAY_API_KEY") or os.getenv("VERCEL_OIDC_TOKEN") or "").strip() or None


def vision_available() -> bool:
    return _gateway_token() is not None


def _image_data_urls(path: str, *, max_pages: int = MAX_PAGES) -> list[str]:
    suffix = Path(path).suffix.lower()
    images: list[bytes] = []

    if suffix == ".pdf":
        import fitz
        from PIL import Image

        pdf = fitz.open(path)
        try:
            for page in list(pdf)[:max_pages]:
                pix = page.get_pixmap(matrix=fitz.Matrix(1.8, 1.8), alpha=False)
                image = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
                if image.width > 1800:
                    ratio = 1800 / image.width
                    image = image.resize((1800, max(1, int(image.height * ratio))))
                output = io.BytesIO()
                image.save(output, format="JPEG", quality=78, optimize=True)
                images.append(output.getvalue())
        finally:
            pdf.close()
    else:
        from PIL import Image

        image = Image.open(path).convert("RGB")
        if image.width > 1800:
            ratio = 1800 / image.width
            image = image.resize((1800, max(1, int(image.height * ratio))))
        output = io.BytesIO()
        image.save(output, format="JPEG", quality=82, optimize=True)
        images.append(output.getvalue())

    return ["data:image/jpeg;base64," + base64.b64encode(raw).decode("ascii") for raw in images]


def _extract_json(text: str) -> dict[str, Any]:
    value = (text or "").strip()
    fence = chr(96) * 3
    if value.startswith(fence):
        value = value[len(fence):].lstrip()
        if value.lower().startswith("json"):
            value = value[4:].lstrip()
        if value.endswith(fence):
            value = value[:-len(fence)].rstrip()
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", value, re.DOTALL)
        if not match:
            return {}
        try:
            parsed = json.loads(match.group(0))
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}


def _normalize_amount(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float, Decimal)):
        try:
            return Decimal(str(value)).quantize(Decimal("0.01"))
        except InvalidOperation:
            return None
    raw = re.sub(r"[^0-9,.-]", "", str(value))
    if not raw:
        return None
    if "," in raw and "." in raw:
        if raw.rfind(",") > raw.rfind("."):
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", "")
    elif "," in raw:
        parts = raw.split(",")
        raw = "".join(parts) if len(parts[-1]) == 3 else raw.replace(",", ".")
    elif "." in raw:
        parts = raw.split(".")
        if len(parts) > 1 and all(len(part) == 3 for part in parts[1:]):
            raw = "".join(parts)
    try:
        return Decimal(raw).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def _normalize_date(value: Any) -> date | None:
    if not value:
        return None
    raw = str(value).strip()
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def _status(value: Any) -> str:
    normalized = str(value or "UNCLEAR").upper().strip()
    return normalized if normalized in {"PRESENT", "MISSING", "UNCLEAR"} else "UNCLEAR"


def analyze_document_vision(
    path: str,
    *,
    file_name: str | None = None,
    expected_customer: str | None = None,
    expected_billing_document: str | None = None,
    expected_nominal: Decimal | None = None,
) -> dict[str, Any] | None:
    token = _gateway_token()
    if not token:
        return None

    image_urls = _image_data_urls(path)
    if not image_urls:
        return None

    prompt = f"""
Anda membaca dokumen evidence audit distribusi barang di Indonesia (Billing/Invoice, Delivery Order, SPJ).
Tujuan: ekstraksi fakta dari gambar, bukan menilai keaslian tanda tangan/stempel.

Nama file: {file_name or Path(path).name}
Customer SAP yang diharapkan: {expected_customer or "-"}
Billing Document SAP yang diharapkan: {expected_billing_document or "-"}
Nominal SAP/net outstanding yang diharapkan: {expected_nominal if expected_nominal is not None else "-"}

Baca SELURUH halaman yang diberikan. Return ONLY valid JSON tanpa markdown dengan struktur:
{{
  "billing_document": string|null,
  "invoice_date": "YYYY-MM-DD"|null,
  "grand_total": number|null,
  "spj_number": string|null,
  "delivery_order_number": string|null,
  "receiver_name": string|null,
  "partial_payments": [
    {{"amount": number, "date": "YYYY-MM-DD"|null, "reference": string|null}}
  ],
  "signatures": {{
    "receiver": {{"status":"PRESENT|MISSING|UNCLEAR","confidence":0.0,"page_number":1|null}},
    "driver": {{"status":"PRESENT|MISSING|UNCLEAR","confidence":0.0,"page_number":1|null}},
    "security": {{"status":"PRESENT|MISSING|UNCLEAR","confidence":0.0,"page_number":1|null}},
    "bm": {{"status":"PRESENT|MISSING|UNCLEAR","confidence":0.0,"page_number":1|null}},
    "checker": {{"status":"PRESENT|MISSING|UNCLEAR","confidence":0.0,"page_number":1|null}}
  }},
  "stamp": {{
    "status":"PRESENT|MISSING|UNCLEAR",
    "text": string|null,
    "confidence":0.0,
    "page_number":1|null
  }},
  "notes":[string]
}}

Aturan:
- PRESENT tanda tangan = ada coretan/tanda tangan visual pada kotak/area role tersebut. Jangan menilai siapa penandatangan atau autentik/tidak.
- PRESENT stempel = ada cap/stempel visual. Jika cap terlihat tetapi tulisannya tidak terbaca, status tetap PRESENT dan text=null.
- receiver_name hanya isi jika nama penerima tertulis/terbaca pada area penerima/diterima customer.
- partial_payments hanya untuk pembayaran sebagian/pelunasan sebagian/payment history yang eksplisit, termasuk istilah DP, payment received, telah dibayar, pembayaran terdahulu, atau nilai yang jelas mengurangi grand total menjadi outstanding/net amount. Jangan masukkan grand_total sebagai partial payment.
- Nilai SAP di atas hanya referensi rekonsiliasi. Jangan mengubah hasil pembacaan gambar agar cocok dengan SAP. Jika ada partial payment yang eksplisit dan grand_total - partial payment = nominal SAP, tetap laporkan nilai yang benar-benar terlihat pada dokumen.
- Jika nilai tidak yakin, gunakan null/UNCLEAR dan confidence rendah. Jangan mengarang.
- Gunakan angka IDR tanpa separator ribuan, contoh 5644800.
""".strip()

    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    content.extend(
        {"type": "image_url", "image_url": {"url": image_url, "detail": "high"}}
        for image_url in image_urls
    )

    payload = {
        "model": os.getenv("AI_VISION_MODEL", DEFAULT_VISION_MODEL),
        "messages": [{"role": "user", "content": content}],
        "stream": False,
    }

    try:
        with httpx.Client(timeout=90.0) as client:
            response = client.post(
                AI_GATEWAY_URL,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
    except Exception:
        return None

    try:
        text = data["choices"][0]["message"]["content"]
    except Exception:
        return None
    parsed = _extract_json(text)
    if not parsed:
        return None

    partials: list[dict[str, Any]] = []
    for item in parsed.get("partial_payments") or []:
        if not isinstance(item, dict):
            continue
        amount = _normalize_amount(item.get("amount"))
        if amount is None:
            continue
        partials.append(
            {
                "amount": amount,
                "date": _normalize_date(item.get("date")),
                "reference": str(item.get("reference") or "").strip() or None,
            }
        )

    signatures = parsed.get("signatures") if isinstance(parsed.get("signatures"), dict) else {}
    normalized_signatures: dict[str, dict[str, Any]] = {}
    for role in ("receiver", "driver", "security", "bm", "checker"):
        item = signatures.get(role) if isinstance(signatures.get(role), dict) else {}
        try:
            confidence = max(0.0, min(float(item.get("confidence") or 0.0), 1.0))
        except (TypeError, ValueError):
            confidence = 0.0
        normalized_signatures[role] = {
            "status": _status(item.get("status")),
            "confidence": confidence,
            "page_number": item.get("page_number") if isinstance(item.get("page_number"), int) else None,
        }

    stamp = parsed.get("stamp") if isinstance(parsed.get("stamp"), dict) else {}
    try:
        stamp_confidence = max(0.0, min(float(stamp.get("confidence") or 0.0), 1.0))
    except (TypeError, ValueError):
        stamp_confidence = 0.0

    return {
        "engine": "AI_VISION",
        "model": payload["model"],
        "billing_document": str(parsed.get("billing_document") or "").strip() or None,
        "invoice_date": _normalize_date(parsed.get("invoice_date")),
        "grand_total": _normalize_amount(parsed.get("grand_total")),
        "spj_number": str(parsed.get("spj_number") or "").strip() or None,
        "delivery_order_number": str(parsed.get("delivery_order_number") or "").strip() or None,
        "receiver_name": str(parsed.get("receiver_name") or "").strip() or None,
        "partial_payments": partials,
        "signatures": normalized_signatures,
        "stamp": {
            "status": _status(stamp.get("status")),
            "text": str(stamp.get("text") or "").strip() or None,
            "confidence": stamp_confidence,
            "page_number": stamp.get("page_number") if isinstance(stamp.get("page_number"), int) else None,
        },
        "notes": [str(item) for item in (parsed.get("notes") or []) if str(item).strip()],
    }


def partial_payment_summary(vision: dict[str, Any] | None) -> tuple[Decimal | None, str | None]:
    if not vision:
        return None, None
    rows = vision.get("partial_payments") or []
    amounts = [row.get("amount") for row in rows if isinstance(row, dict) and row.get("amount") is not None]
    if not amounts:
        return None, None
    total = sum((Decimal(str(value)) for value in amounts), Decimal("0.00")).quantize(Decimal("0.01"))
    raw = "; ".join(
        f"{row.get('date') or '-'} | {row.get('amount')} | {row.get('reference') or '-'}"
        for row in rows
        if isinstance(row, dict)
    )
    return total, raw or None
