"""Invoice extraction: PDF or image bytes → ExtractionObject (state_id, extracted_text, vendor_name, items, tax, shipping, total)."""

import io
import re
from typing import Any, Dict, List, Optional

import pdfplumber

from backend.models import ExtractionObject, ItemObject

# Supported invoice content types
CONTENT_TYPE_PDF = "application/pdf"
CONTENT_TYPES_IMAGE = ("image/jpeg", "image/jpg", "image/png", "image/gif", "image/webp")


def _coerce_int(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(round(value))
    try:
        s = str(value).strip()
        s = re.sub(r"[^\d.-]", "", s) or "0"
        return int(round(float(s)))
    except (ValueError, TypeError):
        return 0


def _coerce_float(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    try:
        s = str(value).strip()
        s = re.sub(r"[^\d.-]", "", s) or "0"
        return float(s)
    except (ValueError, TypeError):
        return 0.0


def _find_line_items_from_tables(pages: list) -> List[Dict[str, Any]]:
    """Heuristic: collect rows that look like line items (description, qty, price, total) from tables."""
    rows: List[Dict[str, Any]] = []
    for page in pages:
        tables = page.extract_tables() or []
        for table in tables:
            if not table or len(table) < 2:
                continue
            header = [str(c or "").strip().lower() for c in table[0]]
            # Find column indices by common names
            desc_idx = None
            qty_idx = None
            price_idx = None
            total_idx = None
            for i, h in enumerate(header):
                if "desc" in h or "item" in h or "product" in h:
                    desc_idx = i
                if "qty" in h or "quantity" in h or "number" in h:
                    qty_idx = i
                if "unit" in h and "price" in h:
                    price_idx = i
                if "total" in h or "amount" in h or "line" in h:
                    total_idx = i
            if price_idx is None:
                for i, h in enumerate(header):
                    if "price" in h:
                        price_idx = i
                        break
            if desc_idx is None:
                desc_idx = 0
            if qty_idx is None:
                qty_idx = 1 if len(header) > 1 else 0
            if total_idx is None:
                total_idx = len(header) - 1 if header else 0
            for r in table[1:]:
                if not r:
                    continue
                desc = (r[desc_idx] if desc_idx < len(r) else None) or ""
                if not str(desc).strip():
                    continue
                qty = _coerce_float(r[qty_idx] if qty_idx < len(r) else None) or 1.0
                unit_price = _coerce_float(r[price_idx] if price_idx < len(r) else None)
                line_total = _coerce_float(r[total_idx] if total_idx < len(r) else None)
                if unit_price == 0 and line_total and qty:
                    unit_price = line_total / qty
                elif line_total == 0 and unit_price and qty:
                    line_total = unit_price * qty
                rows.append({
                    "item_name": str(desc).strip(),
                    "number_of_items": int(round(qty)),
                    "unit_price": unit_price,
                    "total_price_of_item": line_total,
                })
    return rows


def _find_totals_from_text(text: str) -> Dict[str, float]:
    """Heuristic: find tax, shipping, total from extracted text."""
    out: Dict[str, float] = {"tax": 0.0, "shipping": 0.0, "total": 0.0}
    lower = text.lower()
    # Look for patterns like "tax: 10.00" or "total 123.45"
    for name, key in [("tax", "tax"), ("shipping", "shipping"), ("total", "total"), ("grand total", "total")]:
        pat = re.compile(rf"{re.escape(name)}\s*[:\$]?\s*([\d,]+\.?\d*)", re.I)
        m = pat.search(lower)
        if m:
            try:
                out[key] = float(m.group(1).replace(",", ""))
            except ValueError:
                pass
    return out


# Document titles to skip when inferring vendor (read vendor from invoice body, not title)
_INVOICE_TITLE_PATTERNS = re.compile(
    r"^(invoice|tax\s+invoice|bill|quote|purchase\s+order|po\s*#?|receipt|statement)"
    r"(\s*#?\s*[\w-]*)?\s*$",
    re.I,
)
# Line that *starts with* a title (so we skip "Invoice from Acme" as vendor; we use Acme from content)
_INVOICE_TITLE_PREFIX = re.compile(
    r"^(invoice|tax\s+invoice|bill|quote|purchase\s+order|po\s*#?|receipt|statement)\s*",
    re.I,
)
# Words that indicate the rest of a title line is document-type text, not a vendor name
_NON_VENDOR_TITLE_WORDS = frozenset(
    {"copy", "scanned", "ocr", "type", "pdf", "image", "attachment", "messy", "scanned)"}
)


def _is_invoice_title_line(line: str) -> bool:
    """True if line looks like a document title (INVOICE, BILL, etc.), not a vendor name."""
    s = line.strip()
    if not s or len(s) < 2:
        return True
    if re.match(r"^[\d\s\$\.,\-]+$", s):
        return True
    if _INVOICE_TITLE_PATTERNS.match(s):
        return True
    if s.upper() in ("INVOICE", "BILL", "QUOTE", "RECEIPT", "STATEMENT", "TAX INVOICE"):
        return True
    return False


def _line_starts_with_invoice_title(line: str) -> bool:
    """True if line starts with a document title (e.g. 'Invoice', 'Tax Invoice'), even if more text follows."""
    return bool(_INVOICE_TITLE_PREFIX.match(line.strip()))


def _vendor_after_title_prefix(line: str) -> Optional[str]:
    """
    If line is like 'Invoice from Acme Corp' or 'Tax Invoice - Acme', return the vendor part (Acme Corp / Acme).
    Return None for title-only text (e.g. 'Invoice Copy (Scanned)') so we use the next line from invoice body.
    """
    s = line.strip()
    m = _INVOICE_TITLE_PREFIX.match(s)
    if not m:
        return None
    rest = s[m.end() :].strip()
    # Strip common separators: "from Acme" -> "Acme", " - Acme" -> "Acme", "#123 from Acme" -> "Acme"
    rest = re.sub(r"^[#\d\s\-]+", "", rest).strip()
    # Strip leading "from " / "from:" so "from Acme Corp" -> "Acme Corp"
    rest = re.sub(r"^from\s*:?\s*", "", rest, flags=re.I).strip()
    for sep in (" from ", " - ", ": ", " – "):
        if sep in rest:
            rest = rest.split(sep, 1)[-1].strip()
            break
    if not rest or _is_invoice_title_line(rest) or re.match(r"^[\d\s\$\.,]+$", rest) or len(rest) < 2:
        return None
    # Reject document-type fragments (e.g. "Copy (Scanned)", "Type 2", "Messy OCR") — not vendor names
    rest_lower = rest.lower()
    words = set(re.findall(r"[a-z]+", rest_lower))
    if words and words <= _NON_VENDOR_TITLE_WORDS:
        return None
    if rest_lower in _NON_VENDOR_TITLE_WORDS or any(rest_lower == w for w in _NON_VENDOR_TITLE_WORDS):
        return None
    return rest


def _infer_vendor_from_text(text: str) -> str:
    """
    Read vendor name from the invoice body, not from the document title.
    Prefers lines after labels like From:, Vendor:, Bill From:, Seller:.
    Skips document titles (INVOICE, TAX INVOICE, BILL, etc.). Never uses the title line itself as vendor.
    """
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    # 1) Look for label lines: "From: Acme Corp", "Vendor:", "Bill From:", "Seller:", etc.
    vendor_labels = ("from", "vendor", "bill from", "seller", "supplier", "company", "sold by", "issued by")
    for i, line in enumerate(lines):
        lower = line.lower().strip()
        for label in vendor_labels:
            if not lower.startswith(label):
                continue
            # Rest of line after label (and optional colon)
            rest = line[len(label) :].strip().lstrip(":").strip()
            if rest and not _is_invoice_title_line(rest) and not re.match(r"^[\d\s\$\.,]+$", rest):
                return rest
            # Vendor name may be on the next line
            for j in range(i + 1, len(lines)):
                cand = lines[j]
                if cand and not _is_invoice_title_line(cand) and not re.match(r"^[\d\s\$\.,]+$", cand):
                    return cand
            break
    # 2) Vendor from a line that starts with title but has content (e.g. "Invoice from Acme Corp")
    for line in lines:
        if _line_starts_with_invoice_title(line):
            candidate = _vendor_after_title_prefix(line)
            if candidate:
                return candidate
    # 3) First substantive line that is not a document title and does not start with a title
    for line in lines:
        if (
            len(line) > 2
            and not _is_invoice_title_line(line)
            and not _line_starts_with_invoice_title(line)
            and not re.match(r"^[\d\s\$\.,]+$", line)
        ):
            return line
    return "Unknown Vendor"


def extract_from_image(image_bytes: bytes, state_id: str) -> ExtractionObject:
    """
    Extract invoice data from image bytes (JPEG, PNG, etc.) using OCR.
    Requires Tesseract installed (e.g. brew install tesseract on macOS).
    """
    try:
        from PIL import Image
        import pytesseract
    except ImportError:
        return ExtractionObject(
            state_id=state_id,
            extracted_text="(PIL/pytesseract not available for image OCR)",
            vendor_name="Unknown Vendor",
            items=[],
            tax=0,
            shipping=0,
            total_invoice_price=0.0,
        )
    try:
        img = Image.open(io.BytesIO(image_bytes))
        if img.mode not in ("L", "RGB", "RGBA"):
            img = img.convert("RGB")
        extracted_text = pytesseract.image_to_string(img) or ""
    except Exception:
        return ExtractionObject(
            state_id=state_id,
            extracted_text="(Image could not be opened or OCR failed)",
            vendor_name="Unknown Vendor",
            items=[],
            tax=0,
            shipping=0,
            total_invoice_price=0.0,
        )
    extracted_text = extracted_text.strip()
    vendor_name = _infer_vendor_from_text(extracted_text)
    totals = _find_totals_from_text(extracted_text)
    # Heuristic: try to find line-like patterns (description followed by number) in OCR text
    raw_rows: List[Dict[str, Any]] = []
    for line in extracted_text.splitlines():
        line = line.strip()
        if not line or len(line) < 2:
            continue
        # Match trailing number (price or total)
        match = re.search(r"\s+([\d,]+\.?\d*)\s*$", line)
        if match:
            desc = line[: match.start()].strip()
            if desc and not re.match(r"^[\d\s\$\.,]+$", desc):
                try:
                    val = float(match.group(1).replace(",", ""))
                    raw_rows.append({
                        "item_name": desc,
                        "number_of_items": 1,
                        "unit_price": val,
                        "total_price_of_item": val,
                    })
                except ValueError:
                    pass
    if not raw_rows:
        total_val = totals["total"]
        if total_val > 0:
            raw_rows = [{
                "item_name": "Invoice total (OCR)",
                "number_of_items": 1,
                "unit_price": total_val,
                "total_price_of_item": total_val,
            }]
    items: List[ItemObject] = []
    for i, r in enumerate(raw_rows, start=1):
        items.append(ItemObject(
            item_id=f"item_{i}",
            item_name=r.get("item_name", ""),
            number_of_items=r.get("number_of_items", 1),
            total_price_of_item=r.get("total_price_of_item", 0.0),
            unit_price=r.get("unit_price", 0.0),
            estimated_shipping=None,
            estimated_tax=None,
        ))
    total_invoice = totals["total"]
    if total_invoice == 0 and items:
        total_invoice = sum(it.total_price_of_item for it in items)
    return ExtractionObject(
        state_id=state_id,
        extracted_text=extracted_text or "(no text from OCR)",
        vendor_name=vendor_name,
        items=items,
        tax=_coerce_int(totals["tax"]),
        shipping=_coerce_int(totals["shipping"]),
        total_invoice_price=round(total_invoice, 2),
    )


def extract_from_document(content: bytes, state_id: str, content_type: Optional[str] = None) -> ExtractionObject:
    """
    Extract invoice data from document bytes (PDF or image).
    Dispatches to extract_from_pdf or extract_from_image based on content_type.
    """
    ct = (content_type or "").strip().lower()
    if ct in CONTENT_TYPES_IMAGE or (ct.startswith("image/")):
        return extract_from_image(content, state_id)
    return extract_from_pdf(content, state_id)


def extract_from_pdf(pdf_bytes: bytes, state_id: str) -> ExtractionObject:
    """
    Extract invoice data from PDF bytes. Returns ExtractionObject for the given state_id.
    Uses pdfplumber for text and table extraction; heuristics for vendor, line items, tax, shipping, total.
    """
    items: List[ItemObject] = []
    full_text_parts: List[str] = []
    pages_list: list = []

    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    full_text_parts.append(t)
                pages_list.append(page)
    except Exception:
        return ExtractionObject(
            state_id=state_id,
            extracted_text="(PDF could not be opened)",
            vendor_name="Unknown Vendor",
            items=[],
            tax=0,
            shipping=0,
            total_invoice_price=0.0,
        )

    extracted_text = "\n".join(full_text_parts) if full_text_parts else ""

    # Line items from tables
    raw_rows = _find_line_items_from_tables(pages_list)
    if not raw_rows:
        # Fallback: try to parse from text (minimal - single fake line)
        totals = _find_totals_from_text(extracted_text)
        if totals["total"] > 0:
            raw_rows = [{
                "item_name": "Invoice total (no table parsed)",
                "number_of_items": 1,
                "unit_price": totals["total"],
                "total_price_of_item": totals["total"],
            }]
    for i, r in enumerate(raw_rows, start=1):
        items.append(ItemObject(
            item_id=f"item_{i}",
            item_name=r.get("item_name", ""),
            number_of_items=r.get("number_of_items", 1),
            total_price_of_item=r.get("total_price_of_item", 0.0),
            unit_price=r.get("unit_price", 0.0),
            estimated_shipping=None,
            estimated_tax=None,
        ))

    totals = _find_totals_from_text(extracted_text)
    tax_int = _coerce_int(totals["tax"])
    shipping_int = _coerce_int(totals["shipping"])
    total_invoice = totals["total"]
    if total_invoice == 0 and items:
        total_invoice = sum(it.total_price_of_item for it in items)
    vendor_name = _infer_vendor_from_text(extracted_text)

    return ExtractionObject(
        state_id=state_id,
        extracted_text=extracted_text or "(no text extracted)",
        vendor_name=vendor_name,
        items=items,
        tax=tax_int,
        shipping=shipping_int,
        total_invoice_price=round(total_invoice, 2),
    )
