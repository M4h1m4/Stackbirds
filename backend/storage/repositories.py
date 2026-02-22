"""CRUD repositories for invoices, processings, states, extraction, matching, clarification."""

from datetime import datetime
from typing import Any, List, Optional

from sqlalchemy.orm import Session

from backend.storage.models import (
    ClarificationRow,
    ExtractionRow,
    InvoiceRow,
    MatchingRow,
    ProcessingRow,
    StateRow,
)


# --- Invoices ---


def create_invoice(
    session: Session,
    *,
    invoice_id: str,
    customer_id: str,
    document_id: Optional[str] = None,
) -> InvoiceRow:
    row = InvoiceRow(
        invoice_id=invoice_id,
        customer_id=customer_id,
        document_id=document_id,
    )
    session.add(row)
    session.flush()
    return row


def get_invoice_by_invoice_id(session: Session, invoice_id: str) -> Optional[InvoiceRow]:
    return session.query(InvoiceRow).filter(InvoiceRow.invoice_id == invoice_id).first()


# --- Processings ---


def create_processing(
    session: Session,
    *,
    processing_id: str,
    invoice_id: str,
    customer_id: str,
    user_visible_phase: str,
    states: Optional[List[Any]] = None,
    inbox_email: Optional[str] = None,
) -> ProcessingRow:
    row = ProcessingRow(
        processing_id=processing_id,
        invoice_id=invoice_id,
        customer_id=customer_id,
        user_visible_phase=user_visible_phase,
        states=states or [],
        inbox_email=inbox_email,
    )
    session.add(row)
    session.flush()
    return row


def get_processing_by_processing_id(session: Session, processing_id: str) -> Optional[ProcessingRow]:
    return session.query(ProcessingRow).filter(ProcessingRow.processing_id == processing_id).first()


def list_processings_by_customer_id(session: Session, customer_id: str) -> List[ProcessingRow]:
    return session.query(ProcessingRow).filter(ProcessingRow.customer_id == customer_id).order_by(ProcessingRow.created_at.desc()).all()


def list_processings_by_inbox_email(session: Session, inbox_email: str) -> List[ProcessingRow]:
    return session.query(ProcessingRow).filter(ProcessingRow.inbox_email == inbox_email).order_by(ProcessingRow.created_at.desc()).all()


def update_processing(
    session: Session,
    processing_id: str,
    *,
    user_visible_phase: Optional[str] = None,
    states: Optional[List[Any]] = None,
    decision_result: Optional[Any] = None,
    reconciliation_report: Optional[Any] = None,
    audit_trail: Optional[Any] = None,
) -> Optional[ProcessingRow]:
    row = get_processing_by_processing_id(session, processing_id)
    if row is None:
        return None
    if user_visible_phase is not None:
        row.user_visible_phase = user_visible_phase
    if states is not None:
        row.states = states
    if decision_result is not None:
        row.decision_result = decision_result
    if reconciliation_report is not None:
        row.reconciliation_report = reconciliation_report
    if audit_trail is not None:
        row.audit_trail = audit_trail
    row.updated_at = datetime.utcnow()
    session.flush()
    return row


# --- States ---


def create_state(
    session: Session,
    *,
    state_id: str,
    processing_id: str,
    state_name: str,
    extraction_id: Optional[str] = None,
    matching_id: Optional[str] = None,
    clarification_id: Optional[str] = None,
) -> StateRow:
    row = StateRow(
        state_id=state_id,
        processing_id=processing_id,
        state_name=state_name,
        extraction_id=extraction_id,
        matching_id=matching_id,
        clarification_id=clarification_id,
    )
    session.add(row)
    session.flush()
    return row


def get_state_by_state_id(session: Session, state_id: str) -> Optional[StateRow]:
    return session.query(StateRow).filter(StateRow.state_id == state_id).first()


def list_states_by_processing_id(session: Session, processing_id: str) -> List[StateRow]:
    return session.query(StateRow).filter(StateRow.processing_id == processing_id).order_by(StateRow.created_at).all()


# --- Extraction ---


def upsert_extraction(session: Session, state_id: str, extraction_object: Any) -> ExtractionRow:
    row = session.query(ExtractionRow).filter(ExtractionRow.state_id == state_id).first()
    if row:
        row.extraction_object = extraction_object
        session.flush()
        return row
    row = ExtractionRow(state_id=state_id, extraction_object=extraction_object)
    session.add(row)
    session.flush()
    return row


def get_extraction_by_state_id(session: Session, state_id: str) -> Optional[ExtractionRow]:
    return session.query(ExtractionRow).filter(ExtractionRow.state_id == state_id).first()


# --- Matching ---


def upsert_matching(session: Session, state_id: str, matching_object: Any) -> MatchingRow:
    row = session.query(MatchingRow).filter(MatchingRow.state_id == state_id).first()
    if row:
        row.matching_object = matching_object
        session.flush()
        return row
    row = MatchingRow(state_id=state_id, matching_object=matching_object)
    session.add(row)
    session.flush()
    return row


def get_matching_by_state_id(session: Session, state_id: str) -> Optional[MatchingRow]:
    return session.query(MatchingRow).filter(MatchingRow.state_id == state_id).first()


# --- Clarification ---


def create_clarification(
    session: Session,
    *,
    clarification_id: str,
    processing_id: str,
    questions: Any,
    state_id: Optional[str] = None,
) -> ClarificationRow:
    row = ClarificationRow(
        clarification_id=clarification_id,
        processing_id=processing_id,
        state_id=state_id,
        questions=questions,
        answers=None,
        completed=False,
    )
    session.add(row)
    session.flush()
    return row


def get_clarification_by_id(session: Session, clarification_id: str) -> Optional[ClarificationRow]:
    return session.query(ClarificationRow).filter(ClarificationRow.clarification_id == clarification_id).first()


def update_clarification(
    session: Session,
    clarification_id: str,
    *,
    answers: Optional[Any] = None,
    completed: Optional[bool] = None,
) -> Optional[ClarificationRow]:
    row = get_clarification_by_id(session, clarification_id)
    if row is None:
        return None
    if answers is not None:
        row.answers = answers
    if completed is not None:
        row.completed = completed
    row.updated_at = datetime.utcnow()
    session.flush()
    return row


# Repository objects (namespace for dependency injection)


class InvoiceRepository:
    create = staticmethod(create_invoice)
    get_by_invoice_id = staticmethod(get_invoice_by_invoice_id)


class ProcessingRepository:
    create = staticmethod(create_processing)
    get_by_processing_id = staticmethod(get_processing_by_processing_id)
    list_by_customer_id = staticmethod(list_processings_by_customer_id)
    list_by_inbox_email = staticmethod(list_processings_by_inbox_email)
    update = staticmethod(update_processing)


class StateRepository:
    create = staticmethod(create_state)
    get_by_state_id = staticmethod(get_state_by_state_id)
    list_by_processing_id = staticmethod(list_states_by_processing_id)


class ExtractionRepository:
    upsert = staticmethod(upsert_extraction)
    get_by_state_id = staticmethod(get_extraction_by_state_id)


class MatchingRepository:
    upsert = staticmethod(upsert_matching)
    get_by_state_id = staticmethod(get_matching_by_state_id)


class ClarificationRepository:
    create = staticmethod(create_clarification)
    get_by_id = staticmethod(get_clarification_by_id)
    update = staticmethod(update_clarification)


invoice_repo = InvoiceRepository()
processing_repo = ProcessingRepository()
state_repo = StateRepository()
extraction_repo = ExtractionRepository()
matching_repo = MatchingRepository()
clarification_repo = ClarificationRepository()
