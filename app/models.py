from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(20), nullable=False)
    document_type: Mapped[str] = mapped_column(String(20), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    uploaded_by: Mapped[str | None] = mapped_column(String(100))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    physical_billing: Mapped["PhysicalBilling | None"] = relationship(back_populates="document", uselist=False)
    spj: Mapped["SPJ | None"] = relationship(back_populates="document", uselist=False)


class ImportBatch(Base):
    __tablename__ = "import_batches"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    period: Mapped[date | None] = mapped_column(Date)
    uploaded_by: Mapped[str | None] = mapped_column(String(100))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    total_records: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default="UPLOADED")
    sap_billings: Mapped[list["SAPBilling"]] = relationship(back_populates="import_batch")


class SAPBilling(Base):
    __tablename__ = "sap_billing"
    __table_args__ = (UniqueConstraint("import_batch_id", "billing_document", name="uq_sap_billing_batch_document"), Index("ix_sap_billing_billing_document", "billing_document"))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    import_batch_id: Mapped[int] = mapped_column(ForeignKey("import_batches.id", ondelete="RESTRICT"), nullable=False)
    customer: Mapped[str | None] = mapped_column(String(255))
    customer_account_name: Mapped[str | None] = mapped_column(String(255))
    billing_document: Mapped[str] = mapped_column(String(100), nullable=False)
    doc_date: Mapped[date] = mapped_column(Date, nullable=False)
    nominal: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    import_batch: Mapped["ImportBatch"] = relationship(back_populates="sap_billings")
    reconciliations: Mapped[list["BillingReconciliation"]] = relationship(back_populates="sap_billing")


class PhysicalBilling(Base):
    __tablename__ = "physical_billing"
    __table_args__ = (Index("ix_physical_billing_billing_document", "billing_document"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, unique=True)
    billing_document_raw: Mapped[str | None] = mapped_column(Text)
    billing_document: Mapped[str | None] = mapped_column(String(100))
    no_spj_raw: Mapped[str | None] = mapped_column(Text)
    no_spj: Mapped[str | None] = mapped_column(String(100))
    doc_date: Mapped[date | None] = mapped_column(Date)
    nominal: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    partial_payment_raw: Mapped[str | None] = mapped_column(Text)
    partial_payment: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    ocr_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    document: Mapped["Document"] = relationship(back_populates="physical_billing")
    reconciliations: Mapped[list["BillingReconciliation"]] = relationship(back_populates="physical_billing")
    vouching_results: Mapped[list["VouchingResult"]] = relationship(back_populates="billing")


class BillingReconciliation(Base):
    __tablename__ = "billing_reconciliation"
    __table_args__ = (UniqueConstraint("sap_billing_id", name="uq_billing_reconciliation_sap"), UniqueConstraint("physical_billing_id", name="uq_billing_reconciliation_physical"), Index("ix_billing_reconciliation_status", "status"))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sap_billing_id: Mapped[int] = mapped_column(ForeignKey("sap_billing.id", ondelete="CASCADE"), nullable=False)
    physical_billing_id: Mapped[int | None] = mapped_column(ForeignKey("physical_billing.id", ondelete="SET NULL"))
    billing_match: Mapped[bool] = mapped_column(nullable=False)
    date_match: Mapped[bool] = mapped_column(nullable=False)
    nominal_match: Mapped[bool] = mapped_column(nullable=False)
    nominal_difference: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    exception_code: Mapped[str | None] = mapped_column(String(50))
    remarks: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    sap_billing: Mapped["SAPBilling"] = relationship(back_populates="reconciliations")
    physical_billing: Mapped["PhysicalBilling | None"] = relationship(back_populates="reconciliations")


class SPJ(Base):
    __tablename__ = "spj"
    __table_args__ = (Index("ix_spj_no_spj", "no_spj"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, unique=True)
    no_spj_raw: Mapped[str | None] = mapped_column(Text)
    no_spj: Mapped[str | None] = mapped_column(String(100))
    partial_payment_raw: Mapped[str | None] = mapped_column(Text)
    partial_payment: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    ocr_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    document: Mapped["Document"] = relationship(back_populates="spj")
    vouching_results: Mapped[list["VouchingResult"]] = relationship(back_populates="spj")


class VouchingResult(Base):
    __tablename__ = "vouching_result"
    __table_args__ = (UniqueConstraint("billing_id", name="uq_vouching_result_billing"), Index("ix_vouching_result_status", "status"), Index("ix_vouching_result_spj_id", "spj_id"))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    billing_id: Mapped[int] = mapped_column(ForeignKey("physical_billing.id", ondelete="CASCADE"), nullable=False)
    spj_id: Mapped[int | None] = mapped_column(ForeignKey("spj.id", ondelete="SET NULL"))
    no_spj_billing: Mapped[str | None] = mapped_column(String(100))
    no_spj_document: Mapped[str | None] = mapped_column(String(100))
    spj_match: Mapped[bool] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    rule_code: Mapped[str | None] = mapped_column(String(50))
    remarks: Mapped[str | None] = mapped_column(Text)
    reviewer_id: Mapped[str | None] = mapped_column(String(100))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    billing: Mapped["PhysicalBilling"] = relationship(back_populates="vouching_results")
    spj: Mapped["SPJ | None"] = relationship(back_populates="vouching_results")
