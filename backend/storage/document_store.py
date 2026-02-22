"""MongoDB document store for PDF and image invoice attachment bytes."""

from typing import Optional, Tuple

from pymongo import MongoClient
from pymongo.database import Database
from pymongo.collection import Collection

from backend.config import get_config

_DB: Optional[Database] = None
_COLLECTION_NAME = "documents"


def _get_client() -> MongoClient:
    config = get_config()
    return MongoClient(config.mongodb_uri)


def _get_db() -> Database:
    global _DB
    if _DB is None:
        config = get_config()
        _DB = _get_client()[config.mongodb_db]
    return _DB


def _collection() -> Collection:
    return _get_db()[_COLLECTION_NAME]


def save_document(
    *,
    content: bytes,
    invoice_id: Optional[str] = None,
    processing_id: Optional[str] = None,
    filename: Optional[str] = None,
    content_type: Optional[str] = None,
) -> str:
    """Save document bytes to MongoDB. Returns document_id (MongoDB _id as string)."""
    doc = {"content": content}
    if invoice_id is not None:
        doc["invoice_id"] = invoice_id
    if processing_id is not None:
        doc["processing_id"] = processing_id
    if filename is not None:
        doc["filename"] = filename
    if content_type is not None:
        doc["content_type"] = content_type
    result = _collection().insert_one(doc)
    return str(result.inserted_id)


def get_document_by_id(document_id: str) -> Optional[bytes]:
    """Load document bytes by MongoDB _id. Returns None if not found."""
    content, _ = get_document_with_type(document_id)
    return content


def get_document_with_type(document_id: str) -> Tuple[Optional[bytes], Optional[str]]:
    """Load document bytes and content_type by MongoDB _id. Returns (content, content_type) or (None, None)."""
    from bson import ObjectId

    try:
        oid = ObjectId(document_id)
    except Exception:
        return None, None
    doc = _collection().find_one({"_id": oid})
    if doc is None:
        return None, None
    content = doc.get("content")
    content_type = doc.get("content_type") or "application/pdf"
    return content, content_type


def get_document_by_invoice_id(invoice_id: str) -> Optional[bytes]:
    """Load document bytes by invoice_id (first match). Returns None if not found."""
    doc = _collection().find_one({"invoice_id": invoice_id})
    if doc is None:
        return None
    return doc.get("content")


def get_document_by_processing_id(processing_id: str) -> Optional[bytes]:
    """Load document bytes by processing_id (first match). Returns None if not found."""
    doc = _collection().find_one({"processing_id": processing_id})
    if doc is None:
        return None
    return doc.get("content")


def get_document_id_by_invoice_id(invoice_id: str) -> Optional[str]:
    """Return MongoDB _id (as string) for the document with this invoice_id, or None."""
    doc = _collection().find_one(
        {"invoice_id": invoice_id},
        projection=["_id"],
    )
    if doc is None:
        return None
    return str(doc["_id"])


class DocumentStore:
    """Namespace for document store functions (for dependency injection)."""

    save = staticmethod(save_document)
    get_by_id = staticmethod(get_document_by_id)
    get_by_invoice_id = staticmethod(get_document_by_invoice_id)
    get_by_processing_id = staticmethod(get_document_by_processing_id)
    get_document_id_by_invoice_id = staticmethod(get_document_id_by_invoice_id)
    get_with_type = staticmethod(get_document_with_type)


def get_document_store() -> DocumentStore:
    """Return the document store instance."""
    return DocumentStore()
