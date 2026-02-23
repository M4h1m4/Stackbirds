"""Pipeline runner: Extraction → Matching ↔ Clarification → Completion. Orchestrates phases and audit trail."""

import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.models import (
    AuditTrail,
    ExtractionObject,
    LLMThoughtEntry,
    MatchingObject,
    StateObject,
    UserVisiblePhase,
)
from backend.pipeline.extractor import extract_from_document
from backend.pipeline.excel_loader import load_excel_context
from backend.pipeline.llm_decision import get_decision_and_report
from backend.pipeline.llm_matching import get_matching
from backend.pipeline.llm_questions import get_clarification_questions
from backend.storage import (
    clarification_repo,
    extraction_repo,
    get_document_store,
    matching_repo,
    processing_repo,
    state_repo,
)
from backend.storage.repositories import get_invoice_by_invoice_id
from backend.storage.models import ClarificationRow


def _state_to_state_object(state_row: Any) -> StateObject:
    return StateObject(state_name=state_row.state_name, state_id=state_row.state_id)


def _build_states_for_storage(state_rows: List[Any], processing_states_json: Optional[List[Any]] = None) -> List[Any]:
    """Build states list as JSON-serializable (list of dicts or str) for DB storage."""
    out: List[Any] = []
    for s in state_rows:
        out.append({"state_name": s.state_name, "state_id": s.state_id})
    if processing_states_json:
        for x in processing_states_json:
            if isinstance(x, dict) and x.get("type") == "llm_thought":
                out.append(x.get("content") or "")
            elif isinstance(x, str):
                out.append(x)
    return out


def _initial_audit_trail(extraction: ExtractionObject) -> Dict[str, Any]:
    return AuditTrail(
        extracted={
            "vendor_name": extraction.vendor_name,
            "line_count": len(extraction.items),
            "total_invoice_price": extraction.total_invoice_price,
        },
        assumptions=[],
        uncertainties=[],
        decision_reasoning="",
        llm_thoughts=[],
    ).model_dump()


def _append_thought(audit_dict: Dict[str, Any], thought: Optional[LLMThoughtEntry]) -> None:
    if thought is None:
        return
    thoughts = audit_dict.get("llm_thoughts") or []
    thoughts.append(thought.model_dump())
    audit_dict["llm_thoughts"] = thoughts


def run_pipeline(session: Session, processing_id: str) -> Optional[str]:
    """
    Run pipeline for the given processing_id. Returns None on success; returns error message string on failure.
    - Loads processing, invoice, document bytes.
    - Runs extraction, saves ExtractionObject.
    - Calls LLM for clarification questions; if any, creates Clarification state and returns (pipeline pauses).
    - Otherwise creates Matching state, runs LLM matching; if clarification needed, creates Clarification and returns.
    - Otherwise runs LLM decision, saves decision_result, reconciliation_report, audit_trail; sets Completion.
    """
    proc = processing_repo.get_by_processing_id(session, processing_id)
    if not proc:
        return "Processing not found"
    inv_row = get_invoice_by_invoice_id(session, proc.invoice_id)
    if not inv_row:
        return "Invoice not found"
    doc_id = inv_row.document_id
    if not doc_id:
        return "No document for invoice"
    store = get_document_store()
    content, content_type = store.get_with_type(doc_id)
    if not content:
        return "Document not found"

    state_rows = state_repo.list_by_processing_id(session, processing_id)
    extraction_state = next((s for s in state_rows if s.state_name == "Extraction"), None)
    if not extraction_state:
        return "No Extraction state found"

    # Extract (PDF or image)
    extraction = extract_from_document(content, extraction_state.state_id, content_type)
    extraction_repo.upsert(session, extraction_state.state_id, extraction.model_dump())

    audit = _initial_audit_trail(extraction)

    # LLM clarification questions (Extraction)
    questions, thought = get_clarification_questions(extraction, extraction.extracted_text)
    _append_thought(audit, thought)
    if questions:
        clarification_id = f"clr_{uuid.uuid4().hex[:12]}"
        clarification_repo.create(
            session,
            clarification_id=clarification_id,
            processing_id=processing_id,
            questions=questions,
            state_id=extraction_state.state_id,
        )
        state_repo.create(
            session,
            state_id=clarification_id,
            processing_id=processing_id,
            state_name="Clarification",
            clarification_id=clarification_id,
        )
        states_for_api = _build_states_for_storage(
            state_repo.list_by_processing_id(session, processing_id),
            proc.states,
        )
        processing_repo.update(
            session,
            processing_id,
            user_visible_phase=UserVisiblePhase.MATCHING.value,
            states=states_for_api,
            audit_trail=audit,
        )
        session.commit()
        return None  # paused for clarification

    # Matching: only create Matching state when we have a matching result (avoids 404 on GET /matching)
    matching_state_id = f"matching_{uuid.uuid4().hex[:12]}"
    context = load_excel_context()
    matching, match_questions, match_thought = get_matching(
        matching_state_id,
        extraction,
        context,
        clarification_qa=None,
        max_clarification_questions=3,
    )
    _append_thought(audit, match_thought)
    if match_questions:
        clarification_id = f"clr_{uuid.uuid4().hex[:12]}"
        clarification_repo.create(
            session,
            clarification_id=clarification_id,
            processing_id=processing_id,
            questions=match_questions,
            state_id=matching_state_id,
        )
        state_repo.create(
            session,
            state_id=clarification_id,
            processing_id=processing_id,
            state_name="Clarification",
            clarification_id=clarification_id,
        )
        states_for_api = _build_states_for_storage(
            state_repo.list_by_processing_id(session, processing_id),
            proc.states,
        )
        processing_repo.update(
            session,
            processing_id,
            user_visible_phase=UserVisiblePhase.MATCHING.value,
            states=states_for_api,
            audit_trail=audit,
        )
        session.commit()
        return None  # paused for clarification

    state_repo.create(
        session,
        state_id=matching_state_id,
        processing_id=processing_id,
        state_name="Matching",
    )
    session.flush()
    matching_repo.upsert(session, matching_state_id, matching.model_dump())
    session.flush()

    # Completion: LLM decision + report
    clarification_qa = _get_clarification_qa_for_processing(session, processing_id)
    decision, report, dec_thought = get_decision_and_report(
        extraction,
        matching,
        clarification_qa=clarification_qa,
    )
    _append_thought(audit, dec_thought)
    audit["decision_reasoning"] = getattr(decision, "status", "") + ": " + (report.summary or "")

    processing_repo.update(
        session,
        processing_id,
        user_visible_phase=UserVisiblePhase.COMPLETION.value,
        states=_build_states_for_storage(
            state_repo.list_by_processing_id(session, processing_id),
            proc.states,
        ),
        decision_result=decision.model_dump(),
        reconciliation_report=report.model_dump(),
        audit_trail=audit,
    )
    session.commit()
    return None


def _get_clarification_qa_for_processing(session: Session, processing_id: str) -> List[dict]:
    """Collect all clarification Q&A for this processing (for LLM context)."""
    from backend.storage.models import ClarificationRow
    rows = session.query(ClarificationRow).filter(
        ClarificationRow.processing_id == processing_id,
        ClarificationRow.completed == True,
    ).order_by(ClarificationRow.updated_at).all()
    out = []
    for r in rows:
        if r.answers:
            out.extend(r.answers if isinstance(r.answers, list) else [])
    return out


def run_pipeline_after_clarify(session: Session, processing_id: str, clarification_id: str) -> Optional[str]:
    """
    Resume pipeline after user submitted clarification answers. Returns None on success.
    If previous phase was Extraction → go to Matching. If previous phase was Matching → re-run matching then completion.
    """
    proc = processing_repo.get_by_processing_id(session, processing_id)
    if not proc:
        return "Processing not found"
    clar = clarification_repo.get_by_id(session, clarification_id)
    if not clar or not clar.completed:
        return "Clarification not found or not completed"
    state_rows = state_repo.list_by_processing_id(session, processing_id)
    idx = next((i for i, s in enumerate(state_rows) if s.state_id == clarification_id), None)
    if idx is None or idx == 0:
        return "Clarification state not found"
    source_state = state_rows[idx - 1]
    source_phase = source_state.state_name

    if source_phase == "Extraction":
        # Go to Matching: create Matching state, run matching (and possibly completion)
        inv_row = get_invoice_by_invoice_id(session, proc.invoice_id)
        if not inv_row or not inv_row.document_id:
            return "Invoice or document not found"
        store = get_document_store()
        pdf_bytes = store.get_by_id(inv_row.document_id)
        if not pdf_bytes:
            return "Document not found"
        extraction_state = next((s for s in state_rows if s.state_name == "Extraction"), None)
        if not extraction_state:
            return "No Extraction state"
        ext_row = extraction_repo.get_by_state_id(session, extraction_state.state_id)
        if not ext_row:
            return "No extraction data"
        extraction = ExtractionObject(**ext_row.extraction_object)

        matching_state_id = f"matching_{uuid.uuid4().hex[:12]}"
        context = load_excel_context()
        clarification_qa = clar.answers if isinstance(clar.answers, list) else []
        total_asked = len(clarification_qa)
        max_questions = max(0, 3 - total_asked)
        matching, match_questions, match_thought = get_matching(
            matching_state_id,
            extraction,
            context,
            clarification_qa=clarification_qa,
            max_clarification_questions=max_questions,
        )
        audit = proc.audit_trail or _initial_audit_trail(extraction)
        if isinstance(audit, dict):
            _append_thought(audit, match_thought)
        if match_questions:
            new_clar_id = f"clr_{uuid.uuid4().hex[:12]}"
            clarification_repo.create(
                session,
                clarification_id=new_clar_id,
                processing_id=processing_id,
                questions=match_questions,
                state_id=matching_state_id,
            )
            state_repo.create(
                session,
                state_id=new_clar_id,
                processing_id=processing_id,
                state_name="Clarification",
                clarification_id=new_clar_id,
            )
            processing_repo.update(
                session,
                processing_id,
                user_visible_phase=UserVisiblePhase.MATCHING.value,
                states=_build_states_for_storage(
                    state_repo.list_by_processing_id(session, processing_id),
                    proc.states,
                ),
            )
            session.commit()
            return None
        state_repo.create(
            session,
            state_id=matching_state_id,
            processing_id=processing_id,
            state_name="Matching",
        )
        session.flush()
        matching_repo.upsert(session, matching_state_id, matching.model_dump())
        session.flush()
        all_qa = _get_clarification_qa_for_processing(session, processing_id)
        decision, report, dec_thought = get_decision_and_report(
            extraction,
            matching,
            clarification_qa=all_qa,
        )
        if isinstance(audit, dict):
            _append_thought(audit, dec_thought)
            audit["decision_reasoning"] = (report.summary or "")
        processing_repo.update(
            session,
            processing_id,
            user_visible_phase=UserVisiblePhase.COMPLETION.value,
            states=_build_states_for_storage(
                state_repo.list_by_processing_id(session, processing_id),
                proc.states,
            ),
            decision_result=decision.model_dump(),
            reconciliation_report=report.model_dump(),
            audit_trail=audit,
        )
        session.commit()
        return None

    if source_phase == "Matching":
        # Re-run matching then completion
        extraction_state = next((s for s in state_rows if s.state_name == "Extraction"), None)
        if not extraction_state:
            return "No Extraction state"
        ext_row = extraction_repo.get_by_state_id(session, extraction_state.state_id)
        if not ext_row:
            return "No extraction data"
        extraction = ExtractionObject(**ext_row.extraction_object)
        matching_state = next((s for s in state_rows if s.state_name == "Matching"), None)
        if not matching_state:
            return "No Matching state"
        match_row = matching_repo.get_by_state_id(session, matching_state.state_id)
        if not match_row:
            return "No matching data"
        matching = MatchingObject(**match_row.matching_object)
        context = load_excel_context()
        all_qa = _get_clarification_qa_for_processing(session, processing_id)
        decision, report, dec_thought = get_decision_and_report(
            extraction,
            matching,
            clarification_qa=all_qa,
        )
        audit = proc.audit_trail or _initial_audit_trail(extraction)
        if isinstance(audit, dict):
            _append_thought(audit, dec_thought)
            audit["decision_reasoning"] = (report.summary or "")
        processing_repo.update(
            session,
            processing_id,
            user_visible_phase=UserVisiblePhase.COMPLETION.value,
            states=_build_states_for_storage(
                state_repo.list_by_processing_id(session, processing_id),
                proc.states,
            ),
            decision_result=decision.model_dump(),
            reconciliation_report=report.model_dump(),
            audit_trail=audit,
        )
        session.commit()
        return None

    return "Unknown source phase"