"""User-facing API Pydantic models"""

from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict


class Phase(str, Enum):
    EXTRACTION = "Extraction"
    MATCHING = "Matching"
    CLARIFICATION = "Clarification"
    COMPLETION = "Completion"


class UserVisiblePhase(str, Enum):
    EXTRACTION = "Extraction"
    MATCHING = "Matching"
    COMPLETION = "Completion"


class InvoiceCreate(BaseModel):
    data: Dict[str, Any]
    customer_id: str


class InvoiceCreateResponse(BaseModel):
    invoice_id: str


class StateObject(BaseModel):
    state_name: Literal["Extraction", "Matching", "Clarification", "Completion"]
    state_id: str


class ProcessingObject(BaseModel):
    invoice_id: str
    user_visible_phase: UserVisiblePhase
    states: List[Union[StateObject, str]]
    processing_id: str
    customer_id: str


class ItemObject(BaseModel):
    item_id: str
    item_name: str
    number_of_items: int
    total_price_of_item: float
    unit_price: float
    estimated_shipping: Optional[int] = None
    estimated_tax: Optional[int] = None


class ExtractionObject(BaseModel):
    state_id: str
    extracted_text: str
    vendor_name: str
    items: List[ItemObject]
    tax: int
    shipping: int
    total_invoice_price: float


class ExcelObject(BaseModel):
    model_config = ConfigDict(extra="allow")
    excel_row_id: str


class MatchingObject(BaseModel):
    state_id: str
    vendor: str
    mapping: Dict[str, ExcelObject]


class ClarificationObject(BaseModel):
    questions: List[Any]  # List[str] or List[{"id": str, "text": str}]
    answers: Optional[List[Any]] = None  # List[{"question_id": str, "value": str}]
    completed: bool
