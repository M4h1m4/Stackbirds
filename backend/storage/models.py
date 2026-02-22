"""SQLAlchemy ORM models for metadata (SQLite)."""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.storage.database import Base


class InvoiceRow(Base):
    """Invoice record: id, invoice_id (unique), customer_id, document_id, created_at."""

    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    invoice_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    customer_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    document_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    processings: Mapped[list["ProcessingRow"]] = relationship(
        "ProcessingRow", back_populates="invoice", cascade="all, delete-orphan"
    )


class ProcessingRow(Base):
    """Processing record: processing_id, invoice_id (FK), customer_id, user_visible_phase, states (JSON), completion fields, timestamps."""

    __tablename__ = "processings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    processing_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    invoice_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("invoices.invoice_id", ondelete="CASCADE"), nullable=False
    )
    customer_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    inbox_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    user_visible_phase: Mapped[str] = mapped_column(String(64), nullable=False)
    states: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    decision_result: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    reconciliation_report: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    audit_trail: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    invoice: Mapped["InvoiceRow"] = relationship("InvoiceRow", back_populates="processings")
    states_rows: Mapped[list["StateRow"]] = relationship(
        "StateRow", back_populates="processing", cascade="all, delete-orphan", order_by="StateRow.created_at"
    )
    clarifications: Mapped[list["ClarificationRow"]] = relationship(
        "ClarificationRow", back_populates="processing", cascade="all, delete-orphan"
    )


class StateRow(Base):
    """State record: state_id (unique), processing_id (FK), state_name, optional extraction/matching/clarification refs."""

    __tablename__ = "states"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    state_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    processing_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("processings.processing_id", ondelete="CASCADE"), nullable=False
    )
    state_name: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    extraction_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    matching_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    clarification_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    processing: Mapped["ProcessingRow"] = relationship("ProcessingRow", back_populates="states_rows")
    extraction: Mapped[Optional["ExtractionRow"]] = relationship(
        "ExtractionRow",
        back_populates="state",
        uselist=False,
        primaryjoin="StateRow.state_id == ExtractionRow.state_id",
        foreign_keys="ExtractionRow.state_id",
    )
    matching: Mapped[Optional["MatchingRow"]] = relationship(
        "MatchingRow",
        back_populates="state",
        uselist=False,
        primaryjoin="StateRow.state_id == MatchingRow.state_id",
        foreign_keys="MatchingRow.state_id",
    )


class ExtractionRow(Base):
    """Extraction record: state_id (PK/FK), extraction_object (JSON)."""

    __tablename__ = "extraction"

    state_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("states.state_id", ondelete="CASCADE"), primary_key=True
    )
    extraction_object: Mapped[Any] = mapped_column(JSON, nullable=False)

    state: Mapped["StateRow"] = relationship("StateRow", back_populates="extraction")


class MatchingRow(Base):
    """Matching record: state_id (PK/FK), matching_object (JSON)."""

    __tablename__ = "matching"

    state_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("states.state_id", ondelete="CASCADE"), primary_key=True
    )
    matching_object: Mapped[Any] = mapped_column(JSON, nullable=False)

    state: Mapped["StateRow"] = relationship("StateRow", back_populates="matching")


class ClarificationRow(Base):
    """Clarification record: clarification_id (PK), processing_id (FK), state_id (optional), questions/answers (JSON), completed."""

    __tablename__ = "clarification"

    clarification_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    processing_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("processings.processing_id", ondelete="CASCADE"), nullable=False, index=True
    )
    state_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    questions: Mapped[Any] = mapped_column(JSON, nullable=False)
    answers: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    processing: Mapped["ProcessingRow"] = relationship("ProcessingRow", back_populates="clarifications")
