"""Load Excel (Approved Vendors + Extracted_LineItems_100) and expose ExcelObject list + context for LLM."""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from backend.config import get_config
from backend.models import ExcelObject


# Default sheet names (assignment file)
SHEET_APPROVED_VENDORS = "Approved Vendors"
SHEET_LINE_ITEMS = "Extracted_LineItems_100"

# Possible column name variants for vendor / description / unit price
VENDOR_COLUMNS = ("Vendor", "vendor", "Vendor Name", "vendor_name")
DESCRIPTION_COLUMNS = (
    "Line Item Description",
    "line_item_description",
    "Description",
    "Line Description",
    "Item Description",
)
UNIT_PRICE_COLUMNS = ("Unit Price", "unit_price", "Unit price", "Price", "Contracted Unit Price")


def _find_column(df: pd.DataFrame, candidates: Tuple[str, ...]) -> Optional[str]:
    for c in candidates:
        if c in df.columns:
            return c
    for col in df.columns:
        if isinstance(col, str) and col.strip():
            for c in candidates:
                if c.lower() in col.lower():
                    return col
    return None


def _row_to_excel_object(row: pd.Series, excel_row_id: str) -> ExcelObject:
    """Convert a DataFrame row to ExcelObject with excel_row_id and all columns as extra."""
    data: Dict[str, Any] = {"excel_row_id": excel_row_id}
    for k, v in row.items():
        if pd.isna(v):
            continue
        key = str(k).strip() if k is not None else ""
        if not key:
            continue
        if isinstance(v, (int, float)) and key != "excel_row_id":
            data[key] = v
        else:
            data[key] = str(v) if v is not None else ""
    return ExcelObject(**data)


def load_excel(
    excel_path: Optional[str] = None,
) -> Tuple[List[str], List[ExcelObject]]:
    """
    Load Excel from config EXCEL_PATH (or provided path).
    Returns (approved_vendors, excel_rows).
    - approved_vendors: list of vendor names from sheet "Approved Vendors".
    - excel_rows: list of ExcelObject from sheet "Extracted_LineItems_100" (excel_row_id = row_1, row_2, ...).
    """
    path = excel_path or get_config().excel_path
    path_obj = Path(path)
    if not path_obj.is_file():
        return [], []

    approved: List[str] = []
    rows: List[ExcelObject] = []

    with pd.ExcelFile(path, engine="openpyxl") as xl:
        sheet_names = xl.sheet_names

        if SHEET_APPROVED_VENDORS in sheet_names:
            df_v = pd.read_excel(xl, sheet_name=SHEET_APPROVED_VENDORS, header=0)
            if not df_v.empty:
                first_col = df_v.columns[0]
                approved = df_v[first_col].dropna().astype(str).str.strip().unique().tolist()

        if SHEET_LINE_ITEMS in sheet_names:
            df = pd.read_excel(xl, sheet_name=SHEET_LINE_ITEMS, header=0)
            for i, (_, row) in enumerate(df.iterrows(), start=1):
                excel_row_id = f"row_{i}"
                rows.append(_row_to_excel_object(row, excel_row_id))

    return approved, rows


class ExcelContext:
    """Excel data + contracted-rate lookup for matching phase and LLM."""

    def __init__(
        self,
        approved_vendors: List[str],
        excel_rows: List[ExcelObject],
        contracted_lookup: Optional[Dict[Tuple[str, str], float]] = None,
    ):
        self.approved_vendors = approved_vendors
        self.excel_rows = excel_rows
        self._contracted_lookup = contracted_lookup or {}

    @property
    def contracted_lookup(self) -> Dict[Tuple[str, str], float]:
        """(vendor, line_description) -> unit_price. Built from excel_rows if not provided."""
        if self._contracted_lookup:
            return self._contracted_lookup
        return _build_contracted_lookup(self.excel_rows)

    def get_unit_price(self, vendor: str, line_description: str) -> Optional[float]:
        """Return contracted unit price for (vendor, line_description) if present."""
        key = (vendor.strip(), line_description.strip())
        return self.contracted_lookup.get(key)


def _build_contracted_lookup(excel_rows: List[ExcelObject]) -> Dict[Tuple[str, str], float]:
    """Build (vendor, line_description) -> unit_price from excel_rows. First occurrence wins."""
    lookup: Dict[Tuple[str, str], float] = {}
    vendor_col = None
    desc_col = None
    price_col = None
    for row in excel_rows:
        d = row.model_dump()
        if vendor_col is None:
            for c in VENDOR_COLUMNS:
                if c in d:
                    vendor_col = c
                    break
            if vendor_col is None:
                for k in d:
                    if k != "excel_row_id" and "vendor" in k.lower():
                        vendor_col = k
                        break
        if desc_col is None:
            for c in DESCRIPTION_COLUMNS:
                if c in d:
                    desc_col = c
                    break
            if desc_col is None:
                for k in d:
                    if k != "excel_row_id" and ("desc" in k.lower() or "item" in k.lower() or "line" in k.lower()):
                        desc_col = k
                        break
        if price_col is None:
            for c in UNIT_PRICE_COLUMNS:
                if c in d:
                    price_col = c
                    break
            if price_col is None:
                for k in d:
                    if k != "excel_row_id" and ("price" in k.lower() or "unit" in k.lower()):
                        price_col = k
                        break
        if not all([vendor_col, desc_col, price_col]):
            continue
        v = d.get(vendor_col)
        desc = d.get(desc_col)
        price = d.get(price_col)
        if v is None or desc is None or price is None:
            continue
        try:
            p = float(price)
        except (TypeError, ValueError):
            continue
        key = (str(v).strip(), str(desc).strip())
        if key not in lookup:
            lookup[key] = p
    return lookup


def load_excel_context(excel_path: Optional[str] = None) -> ExcelContext:
    """
    Load Excel and return ExcelContext (approved_vendors, excel_rows, contracted_lookup).
    Used by Matching phase and LLM prompts.
    """
    approved, rows = load_excel(excel_path)
    lookup = _build_contracted_lookup(rows)
    return ExcelContext(approved_vendors=approved, excel_rows=rows, contracted_lookup=lookup)
