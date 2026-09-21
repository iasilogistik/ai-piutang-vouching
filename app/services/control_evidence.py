from __future__ import annotations

import re
from typing import Any

STATUS_PRESENT = "PRESENT"
STATUS_MISSING = "MISSING"
STATUS_UNKNOWN = "UNKNOWN"
STATUS_REVIEW = "REVIEW"
STATUS_MATCH = "MATCH"
STATUS_NOT_EVALUATED = "NOT_EVALUATED"

_STAMP_PRESENCE_WORDS = {"ADA", "YES", "TERTERA", "LENGKAP", "V", "✓"}


def _norm(value: str | None) -> str | None:
    if value is None:
        return None
    value = re.sub(r"\s+", " ", value).strip()
    return value or None


def _norm_name(value: str | None) -> str | None:
    value = _norm(value)
    if not value:
        return None
    value = value.upper()
    value = re.sub(r"\b(TOKO|TK|TB|CV|PT|UD)\b", " ", value)
    value = re.sub(r"[^A-Z0-9 ]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value or None


def _is_presence_word(value: str | None) -> bool:
    value = _norm(value)
    return bool(value and value.upper() in _STAMP_PRESENCE_WORDS)


def _contains_any(text: str, aliases: list[str]) -> bool:
    return any(re.search(alias, text, re.IGNORECASE) for alias in aliases)


def _field(status: str, confidence: float, remarks: str | None = None) -> dict[str, Any]:
    return {"status": status, "confidence": round(confidence, 4), "remarks": remarks}


def detect_signature_presence(text: str, aliases: list[str], role_label: str) -> dict[str, Any]:
    """Conservative OCR-based signature presence detection.

    This function does not authenticate signatures and does not guess from a
    printed form label. It marks PRESENT only when OCR text explicitly indicates
    the role signature/paraf is present. When OCR only sees the role label, the
    result remains UNKNOWN and should be manually reviewed against the image.
    """

    if not _norm(text):
        return _field(STATUS_UNKNOWN, 0.0, f"OCR kosong; {role_label} harus dicek manual pada gambar SPJ.")

    missing_pattern = rf"(?:tidak\s+ada|tanpa|belum\s+ada)\s+(?:ttd|tanda\s*tangan|paraf|signature)?\s*(?:{'|'.join(aliases)})"
    if re.search(missing_pattern, text, re.IGNORECASE):
        return _field(STATUS_MISSING, 0.85, f"OCR menyatakan {role_label} tidak ada.")

    present_patterns = [
        rf"(?:ttd|tanda\s*tangan|paraf|signature)\s*(?:{'|'.join(aliases)})?\s*[:=\-]?\s*(?:ada|yes|tertera|signed|lengkap|v|✓)",
        rf"(?:{'|'.join(aliases)})\s*(?:ttd|tanda\s*tangan|paraf|signature)\s*[:=\-]?\s*(?:ada|yes|tertera|signed|lengkap|v|✓)",
    ]
    if any(re.search(pattern, text, re.IGNORECASE) for pattern in present_patterns):
        return _field(STATUS_PRESENT, 0.8, f"OCR mengindikasikan {role_label} tertera.")

    if _contains_any(text, aliases):
        return _field(
            STATUS_UNKNOWN,
            0.4,
            f"Label {role_label} terbaca, tetapi keberadaan tanda tangan tidak dapat dipastikan dari OCR; cek visual/manual.",
        )

    return _field(STATUS_UNKNOWN, 0.2, f"Label {role_label} tidak terbaca oleh OCR; cek visual/manual.")


def _extract_stamp_text(text: str) -> str | None:
    lines = [_norm(line) or "" for line in text.splitlines()]
    for index, line in enumerate(lines):
        if re.search(r"\b(stempel|cap|stamp)\b", line, re.IGNORECASE):
            after_label = re.sub(r".*?\b(?:stempel|cap|stamp)\b\s*[:=\-]?", "", line, flags=re.IGNORECASE).strip()
            if len(after_label) >= 3 and not _is_presence_word(after_label):
                return after_label
            for next_line in lines[index + 1 : index + 4]:
                if re.search(r"\b(TOKO|TK|TB|CV|PT|UD)\b", next_line, re.IGNORECASE):
                    return next_line
    for line in lines:
        if re.search(r"\b(TOKO|TK|TB|CV|PT|UD)\b", line, re.IGNORECASE):
            return line
    return None


def compare_stamp_to_customer(stamp_text: str | None, expected_customer: str | None) -> dict[str, Any]:
    if not expected_customer:
        return {"status": STATUS_NOT_EVALUATED, "confidence": 0.0, "remarks": "Nama pelanggan SAP tidak tersedia untuk pembanding stempel."}
    if not stamp_text:
        return {"status": STATUS_REVIEW, "confidence": 0.0, "remarks": "Tulisan stempel tidak terbaca; perlu pengecekan manual."}

    stamp_norm = _norm_name(stamp_text)
    customer_norm = _norm_name(expected_customer)
    if not stamp_norm or not customer_norm:
        return {"status": STATUS_REVIEW, "confidence": 0.0, "remarks": "Nama stempel/pelanggan tidak cukup untuk dibandingkan."}

    stamp_tokens = set(stamp_norm.split())
    customer_tokens = set(customer_norm.split())
    overlap = len(stamp_tokens & customer_tokens) / max(len(stamp_tokens | customer_tokens), 1)
    if overlap >= 0.6 or stamp_norm in customer_norm or customer_norm in stamp_norm:
        return {"status": STATUS_MATCH, "confidence": round(max(overlap, 0.8), 4), "remarks": None}
    return {
        "status": STATUS_REVIEW,
        "confidence": round(overlap, 4),
        "remarks": f"Nama stempel '{stamp_text}' tidak cukup cocok dengan pelanggan SAP '{expected_customer}'; cek manual.",
    }


def detect_stamp(text: str, expected_customer: str | None = None) -> dict[str, Any]:
    if not _norm(text):
        return {
            "status": STATUS_UNKNOWN,
            "confidence": 0.0,
            "stamp_text_raw": None,
            "stamp_text_normalized": None,
            "customer_match": compare_stamp_to_customer(None, expected_customer),
            "remarks": "OCR kosong; stempel harus dicek manual pada gambar SPJ.",
        }

    stamp_text = _extract_stamp_text(text)
    explicit_missing = re.search(r"(?:tidak\s+ada|tanpa|belum\s+ada)\s+(?:stempel|cap|stamp)", text, re.IGNORECASE)
    explicit_present = re.search(r"(?:stempel|cap|stamp)\s*[:=\-]?\s*(?:ada|yes|tertera|lengkap|v|✓)", text, re.IGNORECASE)

    if explicit_missing:
        status = STATUS_MISSING
        confidence = 0.85
        remarks = "OCR menyatakan stempel tidak ada."
    elif stamp_text or explicit_present:
        status = STATUS_PRESENT
        confidence = 0.7 if stamp_text else 0.55
        remarks = None if stamp_text else "Stempel terindikasi ada, tetapi tulisan stempel tidak terbaca jelas; cek manual."
    else:
        status = STATUS_UNKNOWN
        confidence = 0.2
        remarks = "Stempel tidak dapat dipastikan dari OCR; cek visual/manual."

    return {
        "status": status,
        "confidence": round(confidence, 4),
        "stamp_text_raw": stamp_text,
        "stamp_text_normalized": _norm_name(stamp_text),
        "customer_match": compare_stamp_to_customer(stamp_text, expected_customer),
        "remarks": remarks,
    }


def analyze_spj_control_evidence(text: str, expected_customer: str | None = None) -> dict[str, Any]:
    """Analyze SPJ control evidence without judging authenticity.

    The output covers all required evidence fields automatically. UNKNOWN is a
    valid automatic result when the scan/OCR is insufficient, and should create a
    manual-review note rather than a guessed PASS/FAIL.
    """

    result = {
        "receiver_signature": detect_signature_presence(text, [r"penerima", r"diterima\s+oleh", r"customer"], "tanda tangan penerima"),
        "driver_signature": detect_signature_presence(text, [r"driver", r"sopir", r"pengemudi"], "tanda tangan driver"),
        "security_signature": detect_signature_presence(text, [r"satpam", r"security"], "tanda tangan satpam/security"),
        "bm_signature": detect_signature_presence(text, [r"\bbm\b", r"branch\s+manager"], "tanda tangan BM"),
        "checker_signature": detect_signature_presence(text, [r"checker", r"pemeriksa", r"gudang"], "tanda tangan checker"),
        "receiver_stamp": detect_stamp(text, expected_customer),
    }

    review_reasons: list[str] = []
    for key, value in result.items():
        if key == "receiver_stamp":
            if value["status"] != STATUS_PRESENT:
                review_reasons.append(value.get("remarks") or "Stempel penerima belum dapat dipastikan.")
            match = value.get("customer_match", {})
            if match.get("status") not in {STATUS_MATCH, STATUS_NOT_EVALUATED}:
                review_reasons.append(match.get("remarks") or "Nama stempel perlu dicek manual.")
        elif value["status"] != STATUS_PRESENT:
            review_reasons.append(value.get("remarks") or f"{key} perlu dicek manual.")

    result["review_required"] = bool(review_reasons)
    result["review_reasons"] = review_reasons
    return result
