"""LLM for completion: decision (APPROVE/FLAGGED) + Human Reconciliation Report. Appends to audit trail."""

import json
from typing import Any, Dict, List, Optional, Tuple

from backend.models import (
    DecisionResult,
    ExtractionObject,
    LLMThoughtEntry,
    MatchingObject,
    ReconciliationReport,
    ReportLine,
)
from backend.config import get_config
from backend.pipeline.llm_client import call_llm


def _system_completion(variance_threshold_pct: float = 10.0) -> str:
    return f"""You are an invoice approval assistant. Given:
1. Extracted invoice (vendor, line items with unit prices, totals)
2. Matching result (vendor, item -> contracted row mapping with contracted unit prices)
3. Any user clarification Q&A

You must check in this strict order:
1. **Vendor match first**: The invoice vendor must match the approved vendor from the matching result. If not, decision must be FLAGGED for human review.
2. **Line items second**: Each invoice line item must be mapped to a contracted row. If any item is unmapped or ambiguous, decision must be FLAGGED (or ask clarification earlier).
3. **Unit price of each item third**: For each line item, compare the invoice unit_price to the contracted unit_price. Compute variance_percent = |invoice_unit_price - contracted_unit_price| / contracted_unit_price * 100. If variance_percent is greater than {variance_threshold_pct:.0f}% for any item, do NOT approve: set status to "FLAGGED" for human review, and set within_threshold to false for that line.

**Exception**: If the user has explicitly asked to approve the invoice in the clarification Q&A (e.g. "approve it", "go ahead and approve", "I approve despite the variance"), then set status to "APPROVED" even when variance exceeds {variance_threshold_pct:.0f}%.

Produce a Human Reconciliation Report: vendor_name, invoice_total, and for each line: line_item_description, invoice_unit_price, contracted_unit_price, variance_percent, within_threshold (true only if variance_percent <= {variance_threshold_pct:.0f}%), decision_note. End with a short summary.

Return a single JSON object with:
- "status": "APPROVED" or "FLAGGED"
- "vendor_match_confidence": number 0-1
- "variance_detected": boolean (true if any line has variance_percent > {variance_threshold_pct:.0f}%)
- "reasoning": "short explanation"
- "reconciliation_report": {{
  "vendor_name": "...",
  "invoice_total": number,
  "lines": [
    {{"line_item_description": "...", "invoice_unit_price": number, "contracted_unit_price": number, "variance_percent": number, "within_threshold": true/false, "decision_note": "..."}}
  ],
  "summary": "..."
}}"""


def _parse_report_lines(raw: List[Any]) -> List[ReportLine]:
    out: List[ReportLine] = []
    for x in raw:
        if not isinstance(x, dict):
            continue
        try:
            out.append(ReportLine(
                line_item_description=str(x.get("line_item_description", "")),
                invoice_unit_price=float(x.get("invoice_unit_price", 0)),
                contracted_unit_price=float(x.get("contracted_unit_price", 0)),
                variance_percent=float(x.get("variance_percent", 0)),
                within_threshold=bool(x.get("within_threshold", True)),
                decision_note=str(x.get("decision_note", "")),
            ))
        except (TypeError, ValueError):
            continue
    return out


def get_decision_and_report(
    extraction: ExtractionObject,
    matching: MatchingObject,
    clarification_qa: Optional[List[dict]] = None,
) -> Tuple[DecisionResult, ReconciliationReport, Optional[LLMThoughtEntry]]:
    """
    Call LLM for final decision and full Human Reconciliation Report.
    Returns (DecisionResult, ReconciliationReport, LLMThoughtEntry for audit).
    """
    variance_pct = get_config().variance_threshold * 100.0
    system_prompt = _system_completion(variance_pct)

    user = f"""Extracted invoice:
- Vendor: {extraction.vendor_name}
- Total: {extraction.total_invoice_price}
- Items: {len(extraction.items)}
"""
    for it in extraction.items:
        user += f"  {it.item_id}: {it.item_name} unit_price={it.unit_price} total={it.total_price_of_item}\n"
    user += f"\nMatched vendor: {matching.vendor}\nMapping (item_id -> excel row): {list(matching.mapping.keys())}\n"
    # Include contracted unit prices for variance check (from matching mapping)
    for item_id, excel_obj in matching.mapping.items():
        d = excel_obj.model_dump() if hasattr(excel_obj, "model_dump") else (excel_obj if isinstance(excel_obj, dict) else {})
        up = d.get("unit_price") or d.get("Unit Price") or d.get("Unit price") or d.get("Price")
        if up is not None:
            user += f"  Contracted for {item_id}: unit_price={up}\n"
    if clarification_qa:
        user += "\nClarification Q&A (if user said to approve despite variance, set status APPROVED):\n" + json.dumps(clarification_qa) + "\n"
    user += "\nReturn the single JSON object with status, vendor_match_confidence, variance_detected, reasoning, and reconciliation_report."

    content, thought = call_llm(system_prompt, user)
    if thought:
        thought.phase = "Completion"
        thought.step = "decision"

    # Defaults if LLM fails or no key
    default_decision = DecisionResult(
        status="FLAGGED",
        vendor_match_confidence=0.0,
        variance_detected=True,
        clarification_questions=None,
    )
    default_report = ReconciliationReport(
        vendor_name=extraction.vendor_name,
        invoice_total=extraction.total_invoice_price,
        lines=[],
        summary="LLM did not return a valid reconciliation report.",
    )

    if not content:
        return default_decision, default_report, thought

    content = content.strip()
    start = content.find("{")
    if start == -1:
        return default_decision, default_report, thought
    depth = 0
    end = -1
    for i in range(start, len(content)):
        if content[i] == "{":
            depth += 1
        elif content[i] == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end == -1:
        return default_decision, default_report, thought
    try:
        obj = json.loads(content[start:end])
    except json.JSONDecodeError:
        return default_decision, default_report, thought

    status = obj.get("status", "FLAGGED")
    if str(status).upper() not in ("APPROVED", "FLAGGED"):
        status = "FLAGGED"
    else:
        status = str(status).upper()
    decision = DecisionResult(
        status=status,
        vendor_match_confidence=float(obj.get("vendor_match_confidence", 0)),
        variance_detected=bool(obj.get("variance_detected", True)),
        clarification_questions=None,
    )

    rr = obj.get("reconciliation_report") or {}
    lines = _parse_report_lines(rr.get("lines") or [])
    report = ReconciliationReport(
        vendor_name=str(rr.get("vendor_name") or extraction.vendor_name),
        invoice_total=float(rr.get("invoice_total")) if rr.get("invoice_total") is not None else extraction.total_invoice_price,
        lines=lines,
        summary=str(rr.get("summary") or obj.get("reasoning") or "No summary."),
    )
    return decision, report, thought
