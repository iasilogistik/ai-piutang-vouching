from __future__ import annotations

from datetime import date
from io import BytesIO
from decimal import Decimal, InvalidOperation

import pandas as pd
from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.branch_access import branch_for_actor, normalize_branch
from app.models import ImportBatch, SAPBilling
from app.services.branch_master import ensure_branch_catalog


STANDARD_REQUIRED_COLUMNS = {
    "Customer": "customer",
    "Customer Account: Name": "customer_account_name",
    "Billing Document": "billing_document",
    "Doc. Date": "doc_date",
    "Nominal": "nominal",
}

SAP_LEDGER_COLUMNS = {
    "Billing Document": "billing_document",
    "Document Date": "doc_date",
    "Company Code Currency Value": "nominal",
    "Customer Account: Name 1": "customer_account_name",
}
SAP_LEDGER_TEXT_COLUMN = "Text"
SAP_LEDGER_CUSTOMER_ALIASES = ("Customer", "Customer Account", "Customer Number", "Customer Account Number")


def _clean_text(value: object) -> str | None:
    if pd.isna(value):
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    text = str(value).strip()
    return text or None


def _clean_identifier(value: object) -> str | None:
    text = _clean_text(value)
    if not text:
        return None
    return text.split(".")[0] if text.replace(".", "", 1).isdigit() and text.endswith(".0") else text


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


def _import_standard(dataframe: pd.DataFrame) -> list[dict[str, object]]:
    missing = [column for column in STANDARD_REQUIRED_COLUMNS if column not in dataframe.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    rows: list[dict[str, object]] = []
    seen: set[str] = set()
    for index, row in dataframe.iterrows():
        row_number = index + 2
        billing_document = _clean_identifier(row["Billing Document"])
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
    return rows


def _import_sap_ledger(dataframe: pd.DataFrame) -> list[dict[str, object]]:
    missing = [column for column in SAP_LEDGER_COLUMNS if column not in dataframe.columns]
    if missing:
        raise ValueError(f"Missing SAP export columns: {', '.join(missing)}")

    frame = dataframe.copy()
    has_text = SAP_LEDGER_TEXT_COLUMN in frame.columns
    frame["_billing_document"] = frame["Billing Document"].map(_clean_identifier)
    frame["_text_fallback"] = (
        frame[SAP_LEDGER_TEXT_COLUMN].map(_clean_identifier) if has_text else None
    )
    frame["_vouching_key"] = frame["_billing_document"].fillna(frame["_text_fallback"])
    # Approved UAT rule: rows with neither Billing Document nor Text are outside
    # the vouching population and are removed.
    frame = frame[frame["_vouching_key"].notna()].copy()
    if frame.empty:
        raise ValueError("SAP export contains no Billing Document or Text rows")

    frame["_value"] = pd.to_numeric(frame["Company Code Currency Value"], errors="coerce")
    invalid = frame[frame["_value"].isna()]
    if not invalid.empty:
        row_number = int(invalid.index[0]) + 2
        raise ValueError(f"Row {row_number}: invalid Company Code Currency Value")

    # Duplicate effective keys are aggregated to the net SAP balance.
    grouped = frame.groupby("_vouching_key", sort=False)
    rows: list[dict[str, object]] = []
    customer_code_column = next(
        (column for column in SAP_LEDGER_CUSTOMER_ALIASES if column in frame.columns),
        None,
    )
    for vouching_key, group in grouped:
        dates = pd.to_datetime(group["Document Date"], errors="coerce").dropna()
        if dates.empty:
            raise ValueError(f"Billing/Text {vouching_key}: Document Date is required")
        customer_name = next(
            (_clean_text(value) for value in group["Customer Account: Name 1"] if _clean_text(value)),
            None,
        )
        customer_code = (
            next(
                (_clean_identifier(value) for value in group[customer_code_column] if _clean_identifier(value)),
                None,
            )
            if customer_code_column
            else None
        )
        nominal = Decimal(str(group["_value"].sum())).quantize(Decimal("0.01"))
        rows.append(
            {
                "customer": customer_code,
                "customer_account_name": customer_name,
                "billing_document": str(vouching_key),
                "doc_date": dates.max().date(),
                "nominal": nominal,
            }
        )
    return rows



BRANCH_COLUMN_ALIASES = ("branch", "cabang", "branch code", "kode cabang")


def _infer_branch_from_dataframe(dataframe: pd.DataFrame) -> str | None:
    columns = {str(column).strip().casefold(): column for column in dataframe.columns}
    source_column = next((columns[name] for name in BRANCH_COLUMN_ALIASES if name in columns), None)
    if source_column is None:
        return None

    branches = {
        normalized
        for value in dataframe[source_column].tolist()
        if (normalized := normalize_branch(_clean_text(value))) is not None
    }
    if not branches:
        return None
    if len(branches) > 1:
        values = ", ".join(sorted(branches))
        raise ValueError(
            f"SAP import contains multiple branches ({values}); split the file per branch before upload"
        )
    return next(iter(branches))


def _resolve_import_branch(
    db: Session,
    dataframe: pd.DataFrame,
    *,
    uploaded_by: str | None,
    branch: str | None,
) -> str:
    explicit = normalize_branch(branch)
    inferred = _infer_branch_from_dataframe(dataframe)

    if explicit and inferred and explicit != inferred:
        raise ValueError(
            f"Uploaded branch {explicit} conflicts with branch {inferred} detected in SAP file"
        )

    resolved = inferred or explicit or branch_for_actor(db, uploaded_by)
    resolved = normalize_branch(resolved)
    if resolved is None:
        raise ValueError(
            "Branch is required: include Branch/Cabang/Branch Code/Kode Cabang in the SAP file "
            "or supply branch during upload"
        )

    return ensure_branch_catalog(db, resolved)


def import_sap_excel(
    db: Session,
    *,
    filename: str,
    content: bytes,
    uploaded_by: str | None = None,
    period: date | None = None,
    branch: str | None = None,
) -> ImportBatch:
    if not filename.lower().endswith((".xlsx", ".xls")):
        raise ValueError("SAP import file must be Excel (.xlsx or .xls)")

    try:
        dataframe = pd.read_excel(BytesIO(content), dtype=object)
    except Exception as exc:
        raise ValueError("Unable to read SAP Excel file") from exc

    dataframe.columns = [str(column).strip() for column in dataframe.columns]

    if all(column in dataframe.columns for column in SAP_LEDGER_COLUMNS):
        rows = _import_sap_ledger(dataframe)
    else:
        rows = _import_standard(dataframe)

    resolved_branch = _resolve_import_branch(
        db,
        dataframe,
        uploaded_by=uploaded_by,
        branch=branch,
    )

    batch = ImportBatch(
        file_name=filename,
        period=period,
        uploaded_by=uploaded_by,
        branch=resolved_branch,
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


def backfill_customer_codes_from_excel(
    db: Session,
    *,
    batch_id: int,
    filename: str,
    content: bytes,
) -> dict[str, object]:
    """Backfill Customer code on an existing SAP batch without replacing reconciliation.

    This is intentionally limited to the Customer field. Billing, date, nominal,
    reconciliation and evidence links are left untouched.
    """
    if not filename.lower().endswith((".xlsx", ".xls")):
        raise ValueError("SAP source file must be Excel (.xlsx or .xls)")

    batch = db.get(ImportBatch, batch_id)
    if batch is None:
        raise ValueError("SAP import batch not found")

    try:
        dataframe = pd.read_excel(BytesIO(content), dtype=object)
    except Exception as exc:
        raise ValueError("Unable to read SAP Excel file") from exc
    dataframe.columns = [str(column).strip() for column in dataframe.columns]

    if all(column in dataframe.columns for column in SAP_LEDGER_COLUMNS):
        source_rows = _import_sap_ledger(dataframe)
    else:
        source_rows = _import_standard(dataframe)

    by_billing = {
        str(row["billing_document"]): _clean_identifier(row.get("customer"))
        for row in source_rows
        if row.get("billing_document") and _clean_identifier(row.get("customer"))
    }
    by_name: dict[str, set[str]] = {}
    for row in source_rows:
        code = _clean_identifier(row.get("customer"))
        name = _clean_text(row.get("customer_account_name"))
        if code and name:
            by_name.setdefault(name.casefold(), set()).add(code)

    targets = db.query(SAPBilling).filter(SAPBilling.import_batch_id == batch_id).all()
    updated = 0
    unchanged = 0
    unresolved = 0
    for target in targets:
        code = by_billing.get(str(target.billing_document))
        if not code and target.customer_account_name:
            candidates = by_name.get(target.customer_account_name.casefold()) or set()
            if len(candidates) == 1:
                code = next(iter(candidates))
        if not code:
            unresolved += 1
            continue
        if target.customer == code:
            unchanged += 1
            continue
        target.customer = code
        updated += 1

    db.flush()
    return {
        "batch_id": batch_id,
        "source_file": filename,
        "updated": updated,
        "unchanged": unchanged,
        "unresolved": unresolved,
        "total": len(targets),
    }


def import_sap_upload(
    db: Session,
    upload: UploadFile,
    *,
    uploaded_by: str | None = None,
    period: date | None = None,
    branch: str | None = None,
) -> ImportBatch:
    content = upload.file.read()
    return import_sap_excel(
        db,
        filename=upload.filename or "sap_import.xlsx",
        content=content,
        uploaded_by=uploaded_by,
        period=period,
        branch=branch,
    )
