from datetime import date

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import SessionLocal, engine
from app.services.sap_import import import_sap_upload

app = FastAPI(title="AI Piutang Vouching")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/health")
def health() -> dict[str, str]:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return {"status": "healthy"}


@app.post("/sap/import")
def sap_import(
    file: UploadFile = File(...),
    period: date | None = None,
    uploaded_by: str | None = None,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    try:
        batch = import_sap_upload(db, file, uploaded_by=uploaded_by, period=period)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "batch_id": batch.id,
        "file_name": batch.file_name,
        "period": batch.period.isoformat() if batch.period else None,
        "total_records": batch.total_records,
        "status": batch.status,
    }
