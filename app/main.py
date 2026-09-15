from fastapi import FastAPI
from sqlalchemy import text

from app.database import engine

app = FastAPI(title="AI Piutang Vouching")


@app.get("/health")
def health() -> dict[str, str]:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return {"status": "healthy"}
