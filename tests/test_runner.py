"""Tests for pipeline runner."""

import pytest
from sqlalchemy.orm import sessionmaker

from backend.storage import get_engine, get_session_factory, init_db
from backend.storage.repositories import (
    create_invoice,
    create_processing,
    create_state,
)


def test_run_pipeline_requires_processing_and_document():
    """run_pipeline returns error when processing or document is missing."""
    from backend.pipeline.runner import run_pipeline

    init_db()
    session = get_session_factory()()
    err = run_pipeline(session, "nonexistent_id")
    assert err == "Processing not found"
    session.close()


def test_run_pipeline_requires_document_on_invoice():
    """run_pipeline returns error when invoice has no document_id."""
    from backend.pipeline.runner import run_pipeline

    init_db()
    session = get_session_factory()()
    inv = create_invoice(
        session,
        invoice_id="inv_no_doc",
        customer_id="c1",
        document_id=None,
    )
    proc = create_processing(
        session,
        processing_id="proc_no_doc",
        invoice_id=inv.invoice_id,
        customer_id="c1",
        user_visible_phase="Extraction",
        states=[],
    )
    create_state(
        session,
        state_id="state_ext",
        processing_id=proc.processing_id,
        state_name="Extraction",
    )
    session.commit()
    err = run_pipeline(session, proc.processing_id)
    assert err == "No document for invoice"
    session.close()
