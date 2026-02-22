"""User-facing API routes: processing, extraction, matching, clarification, optional invoice, health."""

import base64
import uuid
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.api.dependencies import get_config_dep, get_db
from backend.models import (
    ClarificationObject,
    ExtractionObject,
    InvoiceCreate,
    InvoiceCreateResponse,
    MatchingObject,
    ProcessingObject,
    StateObject,
    UserVisiblePhase,
)
from backend.pipeline.runner import run_pipeline, run_pipeline_after_clarify
from backend.storage import (
    clarification_repo,
    extraction_repo,
    get_document_store,
    matching_repo,
    processing_repo,
    state_repo,
)
from backend.storage.repositories import create_invoice, create_processing, create_state

router = APIRouter()


def _processing_row_to_object(proc: Any) -> ProcessingObject:
    phase = getattr(proc, "user_visible_phase", "Extraction")
    try:
        uv = UserVisiblePhase(phase)
    except ValueError:
        uv = UserVisiblePhase.EXTRACTION
    states = getattr(proc, "states", None) or []
    return ProcessingObject(
        invoice_id=proc.invoice_id,
        user_visible_phase=uv,
        states=states,
        processing_id=proc.processing_id,
        customer_id=proc.customer_id,
    )


@router.get("/health")
def health():
    """Health check for deployment."""
    return {"status": "ok"}


@router.get("/processing", response_model=List[ProcessingObject])
def list_processing(
    customer_id: str = Query(None, description="Customer ID (e.g. sender of invoice)"),
    inbox_email: str = Query(None, description="Inbox email (e.g. your email that receives invoices)"),
    db: Session = Depends(get_db),
):
    """Return list of ProcessingObject. Provide customer_id and/or inbox_email (at least one)."""
    if inbox_email and inbox_email.strip():
        rows = processing_repo.list_by_inbox_email(db, inbox_email.strip())
    elif customer_id and customer_id.strip():
        rows = processing_repo.list_by_customer_id(db, customer_id.strip())
    else:
        raise HTTPException(
            status_code=400,
            detail="Provide at least one of customer_id or inbox_email",
        )
    return [_processing_row_to_object(r) for r in rows]


@router.get("/extraction", response_model=ExtractionObject)
def get_extraction(
    state_id: str = Query(..., description="State ID"),
    db: Session = Depends(get_db),
):
    """Return ExtractionObject for the given state_id. 404 if not found."""
    row = extraction_repo.get_by_state_id(db, state_id)
    if not row:
        raise HTTPException(status_code=404, detail="Extraction not found")
    return ExtractionObject(**row.extraction_object)


@router.get("/matching", response_model=MatchingObject)
def get_matching(
    state_id: str = Query(..., description="State ID"),
    db: Session = Depends(get_db),
):
    """Return MatchingObject for the given state_id. 404 if not found."""
    row = matching_repo.get_by_state_id(db, state_id)
    if not row:
        raise HTTPException(status_code=404, detail="Matching not found")
    return MatchingObject(**row.matching_object)


@router.get("/clarification", response_model=ClarificationObject)
def get_clarification(
    clarification_id: str = Query(..., description="Clarification ID"),
    db: Session = Depends(get_db),
):
    """Return ClarificationObject (questions, answers if any, completed). 404 if not found."""
    row = clarification_repo.get_by_id(db, clarification_id)
    if not row:
        raise HTTPException(status_code=404, detail="Clarification not found")
    return ClarificationObject(
        questions=row.questions or [],
        answers=row.answers,
        completed=row.completed,
    )


@router.post("/clarification")
def post_clarification(
    clarification_id: str = Query(..., description="Clarification ID"),
    body: ClarificationObject = ...,
    db: Session = Depends(get_db),
):
    """Update clarification with answers and completed. If completed=True, resume pipeline. Return 200."""
    row = clarification_repo.get_by_id(db, clarification_id)
    if not row:
        raise HTTPException(status_code=404, detail="Clarification not found")
    if row.completed:
        raise HTTPException(status_code=409, detail="Clarification already completed")
    clarification_repo.update(
        db,
        clarification_id,
        answers=body.answers,
        completed=body.completed,
    )
    db.commit()
    if body.completed:
        err = run_pipeline_after_clarify(db, row.processing_id, clarification_id)
        if err:
            raise HTTPException(status_code=500, detail=err)
    return {}


@router.get("/completion")
def get_completion(
    processing_id: str = Query(..., description="Processing ID"),
    db: Session = Depends(get_db),
):
    """Return decision result and reconciliation report when processing is completed. 404 if not found or not completed."""
    proc = processing_repo.get_by_processing_id(db, processing_id)
    if not proc:
        raise HTTPException(status_code=404, detail="Processing not found")
    if (getattr(proc, "user_visible_phase", None) or "") != "Completion":
        raise HTTPException(status_code=404, detail="Processing not completed")
    return {
        "decision_result": proc.decision_result,
        "reconciliation_report": proc.reconciliation_report,
        "audit_trail": proc.audit_trail,
    }


@router.post("/invoice", response_model=InvoiceCreateResponse)
def create_invoice_for_testing(
    body: InvoiceCreate,
    db: Session = Depends(get_db),
    config=Depends(get_config_dep),
):
    """
    Optional (testing only). Create invoice from JSON body: data (e.g. document_base64, customer_id).
    Primary input is email inbox (Phase 7). Returns invoice_id (and caller can then GET /processing by customer_id).
    """
    data = body.data or {}
    customer_id = body.customer_id or ""
    if not customer_id:
        raise HTTPException(status_code=400, detail="customer_id required")
    document_id = None
    content_bytes = None
    content_type = (data.get("content_type") or "application/pdf").strip().lower()
    if "document_base64" in data:
        try:
            content_bytes = base64.b64decode(data["document_base64"])
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid document_base64")
    elif "document_id" in data:
        document_id = str(data["document_id"])
    else:
        raise HTTPException(status_code=400, detail="data must contain document_base64 or document_id")
    invoice_id = f"inv_{uuid.uuid4().hex[:12]}"
    if content_bytes is not None:
        doc_id = get_document_store().save(
            content=content_bytes,
            invoice_id=invoice_id,
            content_type=content_type or "application/pdf",
        )
        document_id = doc_id
    create_invoice(
        db,
        invoice_id=invoice_id,
        customer_id=customer_id,
        document_id=document_id,
    )
    processing_id = f"proc_{uuid.uuid4().hex[:12]}"
    extraction_state_id = f"state_{uuid.uuid4().hex[:12]}"
    create_processing(
        db,
        processing_id=processing_id,
        invoice_id=invoice_id,
        customer_id=customer_id,
        user_visible_phase=UserVisiblePhase.EXTRACTION.value,
        states=[{"state_name": "Extraction", "state_id": extraction_state_id}],
    )
    create_state(
        db,
        state_id=extraction_state_id,
        processing_id=processing_id,
        state_name="Extraction",
    )
    err = run_pipeline(db, processing_id)
    if err:
        raise HTTPException(status_code=500, detail=err)
    return InvoiceCreateResponse(invoice_id=invoice_id)
