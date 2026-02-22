"""Decision result, reconciliation report, and audit trail models."""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel


class DecisionResult(BaseModel):
    status: Literal["APPROVED", "FLAGGED"]
    vendor_match_confidence: float
    variance_detected: bool
    clarification_questions: Optional[List[Dict[str, str]]] = None  # [{"id": "...", "text": "..."}]


class ReportLine(BaseModel):
    line_item_description: str
    invoice_unit_price: float
    contracted_unit_price: float
    variance_percent: float
    within_threshold: bool
    decision_note: str


class ReconciliationReport(BaseModel):
    """
    Human-readable reconciliation report. Generated entirely by the LLM at completion
    (not rule-based). The LLM produces vendor_name, per-line comparison (lines), and summary.
    """

    vendor_name: str
    invoice_total: Optional[float] = None
    lines: List[ReportLine]
    summary: str  # Short explanation of overall decision (LLM-generated)


class LLMThoughtEntry(BaseModel):
    """Single LLM interaction to be appended to the audit trail."""

    phase: str  # e.g. "Extraction", "Matching", "Completion", "Clarification"
    step: Optional[str] = None  # e.g. "clarification_questions", "matching", "decision"
    thoughts: str  # Full LLM reasoning / chain-of-thought for this step
    input_summary: Optional[str] = None  # Optional short summary of inputs (e.g. "ExtractionObject + Excel")
    output_summary: Optional[str] = None  # Optional short summary of output (e.g. "3 clarification questions")


class AuditTrail(BaseModel):
    """
    Full audit trail containing everything: extraction summary, every LLM thought step,
    assumptions, uncertainties, and final decision reasoning. Pipeline must append
    each LLM call's reasoning to llm_thoughts so the trail is complete.
    """

    extracted: Dict[str, Any]  # What was extracted (e.g. vendor, line count, item count)
    assumptions: List[str]
    uncertainties: List[str]
    decision_reasoning: str
    # Chronological list of all LLM thoughts/reasoning from every phase (Extraction, Matching, Completion, etc.)
    llm_thoughts: List[LLMThoughtEntry] = []
