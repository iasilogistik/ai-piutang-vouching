from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO

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
SAP_LEDGER_CUSTOMER_ALIASES = (
    "Customer",
    "Customer Account",
    "Customer Number",
    "Customer Account Number",
)
BRANCH_COLUMN_ALIASES = ("branch", "cabang", "branch code", "kode cabang")


def _clean_text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    text = str(value).strip()
    return text or None


def _clean_identifier(value: object) -> str | None:
    text = _clean_text(value)
    if not text:
        return None
    if text.endswith(".0") and text.replace(".", "", 1).isdigit():
        return text[:-2]
    return text


def _parse_date(value: object, row_number: int) -> date:
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError(f"Row {row_number}: Doc. Date is required")
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)):
        try:
            from openpyxl.utils.datetime import from_excel

            parsed = from_excel(value)
            return parsed.date() if isinstance(parsed, datetime) else parsed
        except Exception:
            pass

    raw = str(value).strip()
    if not raw:
        raise ValueError(f"Row {row_number}: Doc. Date is required")

    try:
        return datetime.fromisoformat(raw).date()
    except ValueError:
        pass

    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y/%m/%d", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Row {row_number}: invalid Doc. Date")


def _parse_nominal(value: object, row_number: int) -> Decimal:
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError(f"Row {row_number}: Nominal is required")
    try:
        if isinstance(value, Decimal):
            result = value
        elif isinstance(value, (int, float)):
            result = Decimal(str(value))
        else:
            raw = str(value).strip().replace(" ", "")
            raw = raw.replace("Rp", "").replace("IDR", "")
            negative = raw.startswith("-")
            if negative:
                raw = raw[1:]
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
            if negative:
                raw = "-" + raw
            result = Decimal(raw)
    except (InvalidOperation, ValueError):
        raise ValueError(f"Row {row_number}: invalid Nominal") from None
    return result.quantize(Decimal("0.01"))


def _read_excel_records(content: bytes) -> tuple[list[str], list[dict[str, object]]]:
    """Read the active sheet with openpyxl instead of pandas.

    The serverless UI should not pay the cold-start cost of pandas/numpy merely
    because SAP upload support exists in the same FastAPI service. openpyxl is
    already required for report export and is sufficient for the SAP layouts.
    """
    try:
        from openpyxl import load_workbook

        workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
        worksheet = workbook.active
        iterator = worksheet.iter_rows(values_only=True)
        first = next(iterator, None)
        if first is None:
            raise ValueError("SAP Excel file is empty")
        columns = [str(value).strip() if value is not None else "" for value in first]
        if not any(columns):
            raise ValueError("SAP Excel header is empty")

        records: list[dict[str, object]] = []
        for values in iterator:
            if not any(value not in (None, "") for value in values):
                continue
            record = {
                column: (values[index] if index < len(values) else None)
                for index, column in enumerate(columns)
                if column
            }
            records.append(record)
        workbook.close()
        return columns, records
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("Unable to read SAP Excel file") from exc


def _coerce_table(
    columns_or_frame,
    records: list[dict[str, object]] | None = None,
) -> tuple[list[str], list[dict[str, object]]]:
    if records is not None:
        return list(columns_or_frame), records
    # Backward-compatible test/helper path: accept a pandas-like DataFrame
    # without importing pandas in production.
    frame = columns_or_frame
    columns = [str(column).strip() for column in frame.columns]
    return columns, list(frame.to_dict(orient="records"))


def _import_standard(
    columns_or_frame,
    records: list[dict[str, object]] | None = None,
) -> list[dict[str, object]]:
    columns, records = _coerce_table(columns_or_frame, records)
    missing = [column for column in STANDARD_REQUIRED_COLUMNS if column not in columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    rows: list[dict[str, object]] = []
    seen: set[str] = set()
    for offset, row in enumerate(records, start=2):
        billing_document = _clean_identifier(row.get("Billing Document"))
        if not billing_document:
            raise ValueError(f"Row {offset}: Billing Document is required")
        if billing_document in seen:
            raise ValueError(f"Row {offset}: duplicate Billing Document {billing_document}")
        seen.add(billing_document)
        rows.append(
            {
                "customer": _clean_identifier(row.get("Customer")),
                "customer_account_name": _clean_text(row.get("Customer Account: Name")),
                "billing_document": billing_document,
                "doc_date": _parse_date(row.get("Doc. Date"), offset),
                "nominal": _parse_nominal(row.get("Nominal"), offset),
            }
        )
    return rows


def _import_sap_ledger(
    columns_or_frame,
    records: list[dict[str, object]] | None = None,
) -> list[dict[str, object]]:
    columns, records = _coerce_table(columns_or_frame, records)
    missing = [column for column in SAP_LEDGER_COLUMNS if column not in columns]
    if missing:
        raise ValueError(f"Missing SAP export columns: {', '.join(missing)}")

    customer_code_column = next(
        (column for column in SAP_LEDGER_CUSTOMER_ALIASES if column in columns),
        None,
    )
    has_text = SAP_LEDGER_TEXT_COLUMN in columns
    grouped: dict[str, dict[str, object]] = {}

    for offset, source in enumerate(records, start=2):
        billing_document = _clean_identifier(source.get("Billing Document"))
        text_fallback = _clean_identifier(source.get(SAP_LEDGER_TEXT_COLUMN)) if has_text else None
        key = billing_document or text_fallback
        if not key:
            # Approved UAT rule: rows with neither Billing Document nor Text
            # are outside the vouching population.
            continue

        nominal = _parse_nominal(source.get("Company Code Currency Value"), offset)
        try:
            doc_date = _parse_date(source.get("Document Date"), offset)
        except ValueError:
            doc_date = None

        group = grouped.setdefault(
            key,
            {
                "customer": None,
                "customer_account_name": None,
                "billing_document": key,
                "doc_date": None,
                "nominal": Decimal("0.00"),
            },
        )
        group["nominal"] = Decimal(str(group["nominal"])) + nominal
        if doc_date is not None and (group["doc_date"] is None or doc_date > group["doc_date"]):
            group["doc_date"] = doc_date
        if group["customer_account_name"] is None:
            group["customer_account_name"] = _clean_text(source.get("Customer Account: Name 1"))
        if group["customer"] is None and customer_code_column:
            group["customer"] = _clean_identifier(source.get(customer_code_column))

    if not grouped:
        raise ValueError("SAP export contains no Billing Document or Text rows")

    rows: list[dict[str, object]] = []
    for key, group in grouped.items():
        if group["doc_date"] is None:
            raise ValueError(f"Billing/Text {key}: Document Date is required")
        group["nominal"] = Decimal(str(group["nominal"])).quantize(Decimal("0.01"))
        rows.append(group)
    return rows


def _infer_branch_from_records(columns: list[str], records: list[dict[str, object]]) -> str | None:
    by_casefold = {column.casefold(): column for column in columns}
    source_column = next(
        (by_casefold[name] for name in BRANCH_COLUMN_ALIASES if name in by_casefold),
        None,
    )
    if source_column is None:
        return None

    branches = {
        normalized
        for row in records
        if (normalized := normalize_branch(_clean_text(row.get(source_column)))) is not None
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
    columns: list[str],
    records: list[dict[str, object]],
    *,
    uploaded_by: str | None,
    branch: str | None,
) -> str:
    explicit = normalize_branch(branch)
    inferred = _infer_branch_from_records(columns, records)

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


def _refresh_same_sap_batch_from_source(
    db: Session,
    *,
    filename: str,
    branch: str,
    period: date | None,
    rows: list[dict[str, object]],
) -> ImportBatch | None:
    query = (
        db.query(ImportBatch)
        .filter(
            ImportBatch.file_name == filename,
            ImportBatch.branch == branch,
        )
        .order_by(ImportBatch.id.desc())
    )
    query = query.filter(ImportBatch.period.is_(None)) if period is None else query.filter(ImportBatch.period == period)
    batch = query.first()
    if batch is None:
        return None

    existing = db.query(SAPBilling).filter(SAPBilling.import_batch_id == batch.id).all()
    if len(existing) != len(rows):
        return None

    source_by_billing = {str(row["billing_document"]): row for row in rows}
    existing_by_billing = {str(row.billing_document): row for row in existing}
    if set(source_by_billing) != set(existing_by_billing):
        return None

    for billing_document, target in existing_by_billing.items():
        source = source_by_billing[billing_document]
        customer = _clean_identifier(source.get("customer"))
        customer_name = _clean_text(source.get("customer_account_name"))
        if customer:
            target.customer = customer
        if customer_name:
            target.customer_account_name = customer_name

    batch.total_records = len(existing)
    batch.status = "IMPORTED"
    db.commit()
    db.refresh(batch)
    return batch


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

    columns, records = _read_excel_records(content)
    if all(column in columns for column in SAP_LEDGER_COLUMNS):
        rows = _import_sap_ledger(columns, records)
    else:
        rows = _import_standard(columns, records)

    resolved_branch = _resolve_import_branch(
        db,
        columns,
        records,
        uploaded_by=uploaded_by,
        branch=branch,
    )

    refreshed = _refresh_same_sap_batch_from_source(
        db,
        filename=filename,
        branch=resolved_branch,
        period=period,
        rows=rows,
    )
    if refreshed is not None:
        return refreshed

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
