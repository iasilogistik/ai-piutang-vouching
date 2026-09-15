from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AuditTrail(Base):
    __tablename__ = "audit_trail"
    __table_args__ = (Index("ix_audit_trail_entity", "entity_type", "entity_id"), Index("ix_audit_trail_created_at", "created_at"))

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[int | None] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    status_from: Mapped[str | None] = mapped_column(String(30))
    status_to: Mapped[str | None] = mapped_column(String(30))
    actor: Mapped[str | None] = mapped_column(String(100))
    remarks: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
