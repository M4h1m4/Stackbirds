"""Job record model for storage and API serialization."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class JobRecord(BaseModel):
    """Job metadata stored in SQLite; dict/list fields stored as JSON."""

    processing_id: str
    status: str  # processing | needs_clarification | completed
    created_at: datetime
    updated_at: datetime
    extracted_invoice: Optional[Dict[str, Any]] = None
    decision_result: Optional[Dict[str, Any]] = None
    reconciliation_report: Optional[Dict[str, Any]] = None
    audit_trail: Optional[Dict[str, Any]] = None
    clarification_questions: Optional[List[Dict[str, str]]] = None
    clarification_answers: Optional[List[Dict[str, str]]] = None
    resolved_vendor: Optional[str] = None
    document_id: Optional[str] = None

    model_config = {"extra": "forbid"}
