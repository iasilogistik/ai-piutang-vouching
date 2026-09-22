from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, Text, UniqueConstraint, func
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
    branch: Mapped[str | None] = mapped_column(String(255), index=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    physical_billing: Mapped["PhysicalBilling | None"] = relationship(back_populates="document", uselist=False)
    spj: Mapped["SPJ | None"] = relationship(back_populates="document", uselist=False)
    control_evidence: Mapped["DocumentControlEvidence | None"] = relationship(back_populates="document", uselist=False)
    control_evidence_detections: Mapped[list["ControlEvidenceDetection"]] = relationship(back_populates="document")


class ImportBatch(Base):
    __tablename__ = "import_batches"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    period: Mapped[date | None] = mapped_column(Date)
    uploaded_by: Mapped[str | None] = mapped_column(String(100))
    branch: Mapped[str | None] = mapped_column(String(255), index=True)
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


class DocumentControlEvidence(Base):
    __tablename__ = "document_control_evidence"
    __table_args__ = (
        Index("ix_document_control_evidence_review_required", "review_required"),
        Index("ix_document_control_evidence_review_status", "review_status"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, unique=True)

    receiver_signature_status: Mapped[str | None] = mapped_column(String(20))
    receiver_signature_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    receiver_signature_remarks: Mapped[str | None] = mapped_column(Text)
    driver_signature_status: Mapped[str | None] = mapped_column(String(20))
    driver_signature_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    driver_signature_remarks: Mapped[str | None] = mapped_column(Text)
    security_signature_status: Mapped[str | None] = mapped_column(String(20))
    security_signature_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    security_signature_remarks: Mapped[str | None] = mapped_column(Text)
    bm_signature_status: Mapped[str | None] = mapped_column(String(20))
    bm_signature_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    bm_signature_remarks: Mapped[str | None] = mapped_column(Text)
    checker_signature_status: Mapped[str | None] = mapped_column(String(20))
    checker_signature_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    checker_signature_remarks: Mapped[str | None] = mapped_column(Text)

    receiver_stamp_status: Mapped[str | None] = mapped_column(String(20))
    receiver_stamp_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    receiver_stamp_remarks: Mapped[str | None] = mapped_column(Text)
    stamp_text_raw: Mapped[str | None] = mapped_column(Text)
    stamp_text_normalized: Mapped[str | None] = mapped_column(String(255))
    stamp_customer_match_status: Mapped[str | None] = mapped_column(String(20))
    stamp_customer_match_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    stamp_customer_match_remarks: Mapped[str | None] = mapped_column(Text)

    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    review_reasons: Mapped[str | None] = mapped_column(Text)
    review_status: Mapped[str | None] = mapped_column(String(20))
    reviewer_id: Mapped[str | None] = mapped_column(String(100))
    reviewer_remarks: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    document: Mapped["Document"] = relationship(back_populates="control_evidence")


class ControlEvidenceDetection(Base):
    __tablename__ = "control_evidence_detections"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "detection_type",
            "source_file_hash",
            "detector_name",
            "detector_version",
            name="uq_control_evidence_detection_idempotency",
        ),
        Index("ix_control_evidence_detections_branch", "branch"),
        Index("ix_control_evidence_detections_type", "detection_type"),
        Index("ix_control_evidence_detections_processed_at", "processed_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    branch: Mapped[str | None] = mapped_column(String(255))
    detection_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    remarks: Mapped[str | None] = mapped_column(Text)
    page_number: Mapped[int | None] = mapped_column(Integer)
    reference_json: Mapped[dict | None] = mapped_column(JSON)
    source_file_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    detector_name: Mapped[str] = mapped_column(String(100), nullable=False)
    detector_version: Mapped[str] = mapped_column(String(50), nullable=False)
    extraction_engine: Mapped[str | None] = mapped_column(String(100))
    processing_status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="SUCCESS")
    error_message: Mapped[str | None] = mapped_column(Text)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    document: Mapped["Document"] = relationship(back_populates="control_evidence_detections")


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
    automated_status: Mapped[str | None] = mapped_column(String(20))
    automated_rule_code: Mapped[str | None] = mapped_column(String(50))
    automated_remarks: Mapped[str | None] = mapped_column(Text)
    manual_review_status: Mapped[str | None] = mapped_column(String(20))
    review_reason_code: Mapped[str | None] = mapped_column(String(50))
    reviewer_remarks: Mapped[str | None] = mapped_column(Text)
    expected_customer_name: Mapped[str | None] = mapped_column(String(255))
    control_evidence_id: Mapped[int | None] = mapped_column(
        ForeignKey("document_control_evidence.id", ondelete="SET NULL")
    )
    reviewer_id: Mapped[str | None] = mapped_column(String(100))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    billing: Mapped["PhysicalBilling"] = relationship(back_populates="vouching_results")
    spj: Mapped["SPJ | None"] = relationship(back_populates="vouching_results")
    control_evidence: Mapped["DocumentControlEvidence | None"] = relationship()


class AuditException(Base):
    __tablename__ = "audit_exceptions"
    __table_args__ = (
        Index("ix_audit_exceptions_branch", "branch"),
        Index("ix_audit_exceptions_status", "status"),
        Index("ix_audit_exceptions_type", "type"),
        Index("ix_audit_exceptions_due_date", "due_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    branch: Mapped[str] = mapped_column(String(255), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, server_default="MEDIUM")
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="OPEN")
    owner: Mapped[str | None] = mapped_column(String(100))
    due_date: Mapped[date | None] = mapped_column(Date)
    auditor_note: Mapped[str | None] = mapped_column(Text)
    reviewer_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReviewWorkflow(Base):
    __tablename__ = "review_workflows"
    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id", name="uq_review_workflows_entity"),
        Index("ix_review_workflows_branch", "branch"),
        Index("ix_review_workflows_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    branch: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default="NEW")
    auditor_id: Mapped[str | None] = mapped_column(String(100))
    reviewer_id: Mapped[str | None] = mapped_column(String(100))
    auditor_remarks: Mapped[str | None] = mapped_column(Text)
    reviewer_remarks: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditReport(Base):
    __tablename__ = "audit_reports"
    __table_args__ = (
        Index("ix_audit_reports_branch", "branch"),
        Index("ix_audit_reports_status", "status"),
        Index("ix_audit_reports_period", "period_start", "period_end"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    branch: Mapped[str] = mapped_column(String(255), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="DRAFT")
    population_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    sampled_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    matched_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    exception_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    unresolved_exception_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    resolved_exception_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    finding_summary: Mapped[str | None] = mapped_column(Text)
    conclusion: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(String(100))
    approved_by: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditClosing(Base):
    __tablename__ = "audit_closings"
    __table_args__ = (
        UniqueConstraint("audit_report_id", name="uq_audit_closings_report"),
        Index("ix_audit_closings_branch", "branch"),
        Index("ix_audit_closings_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    audit_report_id: Mapped[int] = mapped_column(ForeignKey("audit_reports.id", ondelete="RESTRICT"), nullable=False)
    branch: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default="OPEN")
    closing_note: Mapped[str | None] = mapped_column(Text)
    auditor_signoff_by: Mapped[str | None] = mapped_column(String(100))
    auditor_signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewer_signoff_by: Mapped[str | None] = mapped_column(String(100))
    reviewer_signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_by: Mapped[str | None] = mapped_column(String(100))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
