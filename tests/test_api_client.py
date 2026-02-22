"""
Client-style tests: call the running API over HTTP like a frontend or external client.

Usage:
  1. Start the server:  uv run uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
  2. Run these tests:  uv run pytest tests/test_api_client.py -v
  3. Or set BASE_URL:  BASE_URL=http://localhost:8000 uv run pytest tests/test_api_client.py -v

Requires: MongoDB and SQLite configured; OPENAI_API_KEY set if you run the full-flow test.
For the full-flow test, put a PDF in data/ (e.g. data/sample.pdf) or the test uses a minimal PDF.
"""

import base64
import os
from pathlib import Path

import pytest

# Project root (parent of tests/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _get_test_pdf_base64() -> str:
    """Use a PDF from data/ if present, else a minimal single-page PDF."""
    data_dir = PROJECT_ROOT / "data"
    if data_dir.is_dir():
        for p in data_dir.glob("*.pdf"):
            try:
                return base64.b64encode(p.read_bytes()).decode("ascii")
            except Exception:
                continue
    # Minimal valid PDF (single empty page)
    return (
    "JVBERi0xLjQKJcOkw7zDtsOcCjIgMCBvYmoKPDwKL0xlbmd0aCAzNAovRmlsdGVyIC9GbGF0ZURlY29kZQo+PgpzdHJlYW0KeJwr5HIK4TI2U9"
    "BRyE9MUXBxdVFwAYoLWRqZKBhYmoK4AQDnEAguCgplbmRzdHJlYW0KZW5kb2JqCjQgMCBvYmoKPDwKL1R5cGUgL0ZvbnQKL1N1YnR5cGUgL0"
    "tpZC0xCi9CYXNlRm9udCAvSGVsdmV0aWNhCj4+CmVuZG9iagoxIDAgb2JqCjw8Ci9UeXBlIC9QYWdlCi9QYXJlbnQgNSAwIFIKL01lZGlhQm"
    "94IFswIDAgNjEyIDc5Ml0KL0NvbnRlbnRzIDIgMCBSCj4+CmVuZG9iago1IDAgb2JqCjw8Ci9UeXBlIC9QYWdlcwovS2lkcyBbMSAwIFJdCi9"
    "Db3VudCAxCj4+CmVuZG9iago2IDAgb2JqCjw8Ci9UeXBlIC9DYXRhbG9nCi9QYWdlcyA1IDAgUgo+PgplbmRvYmoKdHJhaWxlcgo8PAovU2"
    "l6ZSA3Ci9Sb290IDYgMCBSCj4+CnN0YXJ0eHJlZgo5NQolJUVPRgo="
    )


def get_test_pdf_base64() -> str:
    return _get_test_pdf_base64()


def get_base_url() -> str:
    return os.environ.get("BASE_URL", "http://localhost:8000")


@pytest.fixture
def base_url() -> str:
    return get_base_url()


@pytest.fixture
def client(base_url):
    import httpx
    return httpx.Client(base_url=base_url, timeout=60.0)


# --- Health ---


def test_health(client):
    """GET /health returns 200 and status ok."""
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data.get("status") == "ok"


# --- Processing list ---


def test_get_processing_requires_customer_id_or_inbox(client):
    """GET /processing without customer_id or inbox_email returns 400."""
    r = client.get("/processing")
    assert r.status_code == 400


def test_get_processing_empty(client):
    """GET /processing?customer_id=... returns 200 and a list (may be empty)."""
    r = client.get("/processing", params={"customer_id": "test-client-nonexistent"})
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)


# --- Full flow: create invoice, then inspect processing and completion ---


def test_full_flow_create_invoice_get_processing_and_completion(client):
    """
    As a client: POST /invoice with a PDF, then GET /processing, then GET /extraction,
    GET /matching or GET /completion as applicable. Requires server + MongoDB + OPENAI_API_KEY.
    """
    customer_id = "test-api-client@example.com"
    payload = {
        "customer_id": customer_id,
        "data": {
            "document_base64": get_test_pdf_base64(),
        },
    }
    r = client.post("/invoice", json=payload)
    if r.status_code == 500 and "OPENAI" in (r.text or ""):
        pytest.skip("OPENAI_API_KEY not set or pipeline failed; skip full flow")
    assert r.status_code == 200, r.text
    body = r.json()
    invoice_id = body.get("invoice_id")
    assert invoice_id

    # Get processings for this customer
    r = client.get("/processing", params={"customer_id": customer_id})
    assert r.status_code == 200
    processings = r.json()
    assert len(processings) >= 1
    proc = next((p for p in processings if p.get("invoice_id") == invoice_id), None)
    assert proc is not None, "expected to find processing for created invoice"
    processing_id = proc["processing_id"]
    states = proc.get("states") or []
    user_visible_phase = proc.get("user_visible_phase", "")

    # If we have states with state_id, try GET /extraction for first Extraction state
    for s in states:
        if isinstance(s, dict) and s.get("state_name") == "Extraction":
            state_id = s.get("state_id")
            if state_id:
                r_ext = client.get("/extraction", params={"state_id": state_id})
                if r_ext.status_code == 200:
                    ext = r_ext.json()
                    assert "vendor_name" in ext and "items" in ext
                break

    # If we have a Matching state, try GET /matching
    for s in states:
        if isinstance(s, dict) and s.get("state_name") == "Matching":
            state_id = s.get("state_id")
            if state_id:
                r_mat = client.get("/matching", params={"state_id": state_id})
                if r_mat.status_code == 200:
                    mat = r_mat.json()
                    assert "vendor" in mat and "mapping" in mat
                break

    # If Completion, GET /completion
    if user_visible_phase == "Completion":
        r_comp = client.get("/completion", params={"processing_id": processing_id})
        assert r_comp.status_code == 200
        comp = r_comp.json()
        assert "decision_result" in comp
        assert "reconciliation_report" in comp
        assert "audit_trail" in comp


# --- Clarification (standalone: need an existing clarification_id to test GET/POST) ---


def test_get_clarification_404_when_not_found(client):
    """GET /clarification?clarification_id=invalid returns 404."""
    r = client.get("/clarification", params={"clarification_id": "nonexistent_clar_id"})
    assert r.status_code == 404


def test_get_completion_404_when_not_completed(client):
    """GET /completion for a non-completed processing returns 404."""
    r = client.get("/completion", params={"processing_id": "nonexistent_proc_id"})
    assert r.status_code == 404


# --- Extraction / Matching 404 when not found ---


def test_get_extraction_404_when_not_found(client):
    """GET /extraction?state_id=invalid returns 404."""
    r = client.get("/extraction", params={"state_id": "nonexistent_state_id"})
    assert r.status_code == 404


def test_get_matching_404_when_not_found(client):
    """GET /matching?state_id=invalid returns 404."""
    r = client.get("/matching", params={"state_id": "nonexistent_state_id"})
    assert r.status_code == 404


# --- Optional: run as script for manual client check ---

if __name__ == "__main__":
    """Run as: python tests/test_api_client.py   (pytest not required; minimal smoke check)."""
    import sys
    try:
        import httpx
    except ImportError:
        print("Install httpx: uv pip install httpx")
        sys.exit(1)
    base = get_base_url()
    print(f"Client smoke check against {base}")
    with httpx.Client(base_url=base, timeout=10.0) as c:
        r = c.get("/health")
        if r.status_code != 200:
            print(f"FAIL /health -> {r.status_code}")
            sys.exit(1)
        print("  GET /health -> 200 OK")
        r = c.get("/processing", params={"customer_id": "smoke-test"})
        if r.status_code != 200:
            print(f"FAIL GET /processing -> {r.status_code}")
            sys.exit(1)
        print("  GET /processing?customer_id=... -> 200 OK")
    print("Smoke check passed.")
