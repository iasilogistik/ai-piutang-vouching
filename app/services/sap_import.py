from __future__ import annotations

from datetime import date
from io import BytesIO
from decimal import Decimal, InvalidOperation

import pandas as pd
from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.models import ImportBatch, SAPBilling

REQUIRED_COLUMNS = {
    "Customer": "customer",
    "Customer Account: Name": "customer_account_name",
    "Billing Document": "billing_document",
    "Doc. Date": "doc_date",
    "Nominal": "nominal",
}


def _clean_text(value: object) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def _parse_date(value: object, row_number: int) -> date:
    if pd.isna(value):
        raise ValueError(f"Row {row_number}: Doc. Date is required")
    parsed = pd.to_datetime(value, errors="coerce", dayfirst=False)
    if pd.isna(parsed):
        raise ValueError(f"Row {row_number}: invalid Doc. Date")
    return parsed.date()


def _parse_nominal(value: object, row_number: int) -> Decimal:
    if pd.isna(value):
        raise ValueError(f"Row {row_number}: Nominal is required")
    try:
        if isinstance(value, str):
            cleaned = value.strip().replace(",", "")
            decimal_value = Decimal(cleaned)
        else:
            decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"Row {row_number}: invalid Nominal") from None
    return decimal_value.quantize(Decimal("0.01"))


def import_sap_excel(
    db: Session,
    *,
    filename: str,
    content: bytes,
    uploaded_by: str | None = None,
    period: date | None = None,
) -> ImportBatch:
    if not filename.lower().endswith((".xlsx", ".xls")):
        raise ValueError("SAP import file must be Excel (.xlsx or .xls)")

    try:
        dataframe = pd.read_excel(BytesIO(content), dtype=object)
    except Exception as exc:
        raise ValueError("Unable to read SAP Excel file") from exc

    dataframe.columns = [str(column).strip() for column in dataframe.columns]
    missing = [column for column in REQUIRED_COLUMNS if column not in dataframe.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    rows: list[dict[str, object]] = []
    seen: set[str] = set()
    for index, row in dataframe.iterrows():
        row_number = index + 2
        billing_document = _clean_text(row["Billing Document"])
        if not billing_document:
            raise ValueError(f"Row {row_number}: Billing Document is required")
        if billing_document in seen:
            raise ValueError(f"Row {row_number}: duplicate Billing Document {billing_document}")
        seen.add(billing_document)
        rows.append(
            {
                "customer": _clean_text(row["Customer"]),
                "customer_account_name": _clean_text(row["Customer Account: Name"]),
                "billing_document": billing_document,
                "doc_date": _parse_date(row["Doc. Date"], row_number),
                "nominal": _parse_nominal(row["Nominal"], row_number),
            }
        )

    batch = ImportBatch(
        file_name=filename,
        period=period,
        uploaded_by=uploaded_by,
        total_records=len(rows),
        status="IMPORTED",
    )
    db.add(batch)
    db.flush()

    for row in rows:
        db.add(SAPBilling(import_batch_id=batch.id, **row))

    db.commit()
    db.refresh(batch)
    return batch


def import_sap_upload(
    db: Session,
    upload: UploadFile,
    *,
    uploaded_by: str | None = None,
    period: date | None = None,
) -> ImportBatch:
    content = upload.file.read()
    return import_sap_excel(
        db,
        filename=upload.filename or "sap_import.xlsx",
        content=content,
        uploaded_by=uploaded_by,
        period=period,
    )
