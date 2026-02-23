"""LLM for matching: ExtractionObject + Excel context → MatchingObject or clarification questions."""

import json
from typing import Any, Dict, List, Optional, Tuple, Union

from backend.models import ExcelObject, ExtractionObject, MatchingObject
from backend.pipeline.excel_loader import ExcelContext
from backend.pipeline.llm_client import call_llm
from backend.models import LLMThoughtEntry


SYSTEM_MATCHING = """You are an invoice matching assistant. You have:
1. An extracted invoice (vendor, line items with unit prices). Invoice total = subtotal + tax + shipping (do not ask about the total).
2. A list of approved vendors.
3. A table of contracted line items (excel_row_id, vendor, description, unit price, etc.).

You must check in this order:
1. **Vendor match first**: The invoice vendor must match one of the approved vendors. If the vendor is ambiguous or not in the approved list, return clarification_questions.
2. **Line items second**: Map each invoice line item to the best-matching contracted row (by excel_row_id). If you cannot match a line item confidently, return clarification_questions.
3. **Unit prices** will be checked later in the approval step (if any item's unit price varies more than 10% from the contracted price, the invoice will be FLAGGED for human review unless the user explicitly approves in clarification).

If at any step you are not confident, return clarification_questions. You may ask at most the number of questions indicated (max 3 in total for this invoice across all rounds). Do not ask about the invoice total.

Return JSON in one of two forms:

A) Matching result:
{"vendor": "<approved vendor name>", "mapping": {"<item_id>": "<excel_row_id>", ...}}

B) Need clarification:
{"clarification_questions": [{"id": "q1", "text": "..."}, ...]}

Use the exact item_id values from the invoice (e.g. item_1, item_2). Use the exact excel_row_id values from the contracted table (e.g. row_1, row_2)."""


def _excel_rows_by_id(context: ExcelContext) -> Dict[str, ExcelObject]:
    return {row.excel_row_id: row for row in context.excel_rows}


def _resolve_mapping(
    mapping_raw: Dict[str, str],
    context: ExcelContext,
) -> Dict[str, ExcelObject]:
    """Convert item_id -> excel_row_id to item_id -> ExcelObject."""
    by_id = _excel_rows_by_id(context)
    return {k: by_id[v] for k, v in mapping_raw.items() if v in by_id}


def get_matching(
    state_id: str,
    extraction: ExtractionObject,
    context: ExcelContext,
    clarification_qa: Optional[List[dict]] = None,
    max_clarification_questions: int = 3,
) -> Tuple[Optional[MatchingObject], Optional[List[dict]], Optional[LLMThoughtEntry]]:
    """
    Call LLM to match invoice to vendor and map items to contracted rows.
    Returns (MatchingObject or None, clarification_questions or None, LLMThoughtEntry for audit).
    max_clarification_questions: max questions to return (0 = do not ask; force a matching result).
    """
    approved_str = ", ".join(context.approved_vendors[:50])
    user = f"""Approved vendors: {approved_str}

Contracted rows (excel_row_id, then fields): 
"""
    for r in context.excel_rows[:80]:
        user += f"  {r.excel_row_id}: {r.model_dump()}\n"
    user += f"""

Invoice (total = subtotal + tax + shipping; do not ask about total):
- Vendor: {extraction.vendor_name}
- Line items:
"""
    for it in extraction.items:
        user += f"  {it.item_id}: {it.item_name} (qty={it.number_of_items}, unit_price={it.unit_price}, total={it.total_price_of_item})\n"
    if clarification_qa:
        user += "\nUser clarification answers:\n" + json.dumps(clarification_qa) + "\n"
    if max_clarification_questions <= 0:
        user += "\nDo not return clarification_questions. You must return a vendor and mapping (best effort)."
    else:
        user += f"\nYou may ask at most {max_clarification_questions} clarification question(s) (max 3 total for this invoice)."
    user += "\nReturn JSON: either {\"vendor\": \"...\", \"mapping\": {\"item_1\": \"row_5\", ...}} or {\"clarification_questions\": [{\"id\": \"...\", \"text\": \"...\"}]}."

    content, thought = call_llm(SYSTEM_MATCHING, user)
    if thought:
        thought.phase = "Matching"
        thought.step = "matching"

    if not content:
        return None, [], thought

    # Parse JSON object
    content = content.strip()
    start = content.find("{")
    if start == -1:
        return None, [], thought
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
        return None, [], thought
    try:
        obj = json.loads(content[start:end])
    except json.JSONDecodeError:
        return None, [], thought

    if obj.get("clarification_questions") and max_clarification_questions > 0:
        qs = obj["clarification_questions"]
        if isinstance(qs, list):
            questions = [{"id": str(x.get("id", i)), "text": str(x.get("text", ""))} for i, x in enumerate(qs) if isinstance(x, dict)]
            questions = questions[:max_clarification_questions]
            return None, questions, thought
        return None, [], thought

    vendor = obj.get("vendor") or extraction.vendor_name
    mapping_raw = obj.get("mapping") or {}
    if not isinstance(mapping_raw, dict):
        mapping_raw = {}
    mapping = _resolve_mapping(mapping_raw, context)
    matching = MatchingObject(state_id=state_id, vendor=vendor, mapping=mapping)
    return matching, None, thought
