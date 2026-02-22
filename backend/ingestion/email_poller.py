"""IMAP poller: read inbox, create invoice from PDF attachment, trigger pipeline, optionally send results link."""

from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root so IMAP_* and other vars are set before config is read
_load_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(_load_env_path)

import email
import imaplib
import logging
import uuid
from email.utils import parseaddr
from typing import List, Optional, Tuple

from backend.config import get_config
from backend.storage import get_document_store
from backend.storage.database import get_session_factory
from backend.storage.repositories import (
    create_invoice,
    create_processing,
    create_state,
)
from backend.pipeline.runner import run_pipeline

logger = logging.getLogger(__name__)


def _get_sender_address(msg: email.message.Message) -> str:
    """Derive sender email address. Used as customer_id if no mapping configured."""
    from_header = msg.get("From", "") or msg.get("Sender", "")
    _, addr = parseaddr(from_header)
    return addr.strip() or "unknown@unknown"


# Accepted invoice attachment types: PDF or image
_INVOICE_CONTENT_TYPES = frozenset({
    "application/pdf",
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/gif",
    "image/webp",
})


def _extract_invoice_attachments(
    msg: email.message.Message,
) -> List[Tuple[bytes, Optional[str], str]]:
    """Return list of (content_bytes, filename, content_type) for each PDF or image attachment."""
    out: List[Tuple[bytes, Optional[str], str]] = []
    for part in msg.walk():
        content_type = (part.get_content_type() or "").lower().split(";")[0].strip()
        if content_type not in _INVOICE_CONTENT_TYPES:
            continue
        payload = part.get_payload(decode=True)
        if not payload:
            continue
        filename = part.get_filename()
        out.append((payload, filename, content_type))
    return out


def _mark_seen(imap: imaplib.IMAP4_SSL, msg_id: bytes) -> None:
    """Mark message as seen (\\Seen flag)."""
    try:
        imap.store(msg_id, "+FLAGS", "\\Seen")
    except Exception as e:
        logger.warning("Could not mark message as seen: %s", e)


def process_inbox_once() -> int:
    """
    Connect to IMAP, fetch UNSEEN messages, for each message with a PDF or image attachment:
    save document to MongoDB, create invoice + processing + first Extraction state, run pipeline,
    optionally send results link email, mark message as seen.
    Returns number of invoices created.
    """
    config = get_config()
    if not all([config.imap_host, config.imap_user, config.imap_password]):
        logger.warning("IMAP not configured (IMAP_HOST, IMAP_USER, IMAP_PASSWORD); skipping poll.")
        return 0

    created = 0
    try:
        imap = imaplib.IMAP4_SSL(config.imap_host)
        imap.login(config.imap_user, config.imap_password)
        imap.select(config.imap_folder or "INBOX")
    except Exception as e:
        logger.error("IMAP connect failed: %s", e)
        return 0

    try:
        _, message_ids = imap.search(None, "UNSEEN")
        for msg_id in (message_ids or [b""])[0].split():
            if not msg_id:
                continue
            try:
                _, data = imap.fetch(msg_id, "(RFC822)")
                if not data or not data[0]:
                    continue
                raw = data[0][1]
                if isinstance(raw, bytes):
                    msg = email.message_from_bytes(raw)
                else:
                    msg = email.message_from_string(str(raw))
                sender = _get_sender_address(msg)
                customer_id = sender  # Use sender as customer_id (config mapping could override later)
                attachments = _extract_invoice_attachments(msg)
                if not attachments:
                    _mark_seen(imap, msg_id)
                    continue
                # Process first PDF or image attachment only (one invoice per email)
                content_bytes, filename, content_type = attachments[0]
                store = get_document_store()
                invoice_id = f"inv_{uuid.uuid4().hex[:12]}"
                doc_id = store.save(
                    content=content_bytes,
                    invoice_id=invoice_id,
                    filename=filename,
                    content_type=content_type,
                )
                session = get_session_factory()()
                try:
                    create_invoice(
                        session,
                        invoice_id=invoice_id,
                        customer_id=customer_id,
                        document_id=doc_id,
                    )
                    processing_id = f"proc_{uuid.uuid4().hex[:12]}"
                    extraction_state_id = f"state_{uuid.uuid4().hex[:12]}"
                    create_processing(
                        session,
                        processing_id=processing_id,
                        invoice_id=invoice_id,
                        customer_id=customer_id,
                        user_visible_phase="Extraction",
                        states=[{"state_name": "Extraction", "state_id": extraction_state_id}],
                        inbox_email=config.imap_user,
                    )
                    create_state(
                        session,
                        state_id=extraction_state_id,
                        processing_id=processing_id,
                        state_name="Extraction",
                    )
                    session.commit()
                    err = run_pipeline(session, processing_id)
                    if err:
                        logger.error("Pipeline error for %s: %s", processing_id, err)
                    else:
                        created += 1
                        # Optional: send results link email (SMTP not implemented here; BASE_URL for link)
                        results_link = f"{config.base_url}/processing?customer_id={customer_id}"
                        logger.info("Invoice %s created; results link: %s", invoice_id, results_link)
                finally:
                    session.close()
                _mark_seen(imap, msg_id)
            except Exception as e:
                logger.exception("Error processing message %s: %s", msg_id, e)
    finally:
        try:
            imap.logout()
        except Exception:
            pass
    return created


def run_poller_loop(interval_seconds: int = 300) -> None:
    """Run process_inbox_once in a loop every interval_seconds. For use as a long-running worker."""
    import time
    while True:
        process_inbox_once()
        time.sleep(interval_seconds)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Email poller: read inbox, create invoice from PDF, run pipeline.")
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Run in a loop (default: run once and exit).",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=300,
        metavar="SECONDS",
        help="Polling interval in seconds when using --loop (default: 300).",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.loop:
        run_poller_loop(interval_seconds=args.interval)
    else:
        n = process_inbox_once()
        print(f"Invoices created this run: {n}")
