"""LLM for clarification questions after Extraction. Appends to audit trail."""

from typing import List, Optional, Tuple

from backend.models import ExtractionObject, LLMThoughtEntry
from backend.pipeline.llm_client import call_llm, parse_json_array_from_llm


SYSTEM_EXTRACTION_QUESTIONS = """You are an invoice review assistant. Given an extracted invoice (vendor, line items, totals), list any clarification questions for the user. Ask about ambiguous vendor names, missing or unclear line items, or unclear amounts. Return ONLY a JSON array of objects with "id" and "text" keys. If nothing needs clarification, return []. Example: [{"id": "q1", "text": "Is vendor X the same as approved vendor Y?"}]"""


def get_clarification_questions(
    extraction: ExtractionObject,
    extracted_text: Optional[str] = None,
) -> Tuple[List[dict], Optional[LLMThoughtEntry]]:
    """
    Call LLM to get clarification questions for the extracted invoice.
    Returns (list of {"id": str, "text": str}, LLMThoughtEntry for audit trail).
    """
    user = f"""Extracted invoice:
- Vendor: {extraction.vendor_name}
- Items: {len(extraction.items)} line(s)
- Tax: {extraction.tax}, Shipping: {extraction.shipping}, Total: {extraction.total_invoice_price}

Line items:
"""
    for it in extraction.items:
        user += f"  - {it.item_name}: qty={it.number_of_items}, unit_price={it.unit_price}, total={it.total_price_of_item}\n"
    if extracted_text:
        user += f"\nRaw extracted text (first 1500 chars):\n{extracted_text[:1500]}"
    user += "\n\nReturn a JSON array of clarification questions (id, text) or []."

    content, thought = call_llm(SYSTEM_EXTRACTION_QUESTIONS, user)
    questions = parse_json_array_from_llm(content) if content else []
    if thought:
        thought.phase = "Extraction"
        thought.step = "clarification_questions"
    return questions, thought
