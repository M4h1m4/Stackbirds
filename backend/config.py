"""Configuration from environment variables."""

import os
from typing import Optional


def _str(value: Optional[str], default: str) -> str:
    return value.strip() if (value and value.strip()) else default


def _float(value: Optional[str], default: float) -> float:
    if value is None or not value.strip():
        return default
    try:
        return float(value)
    except ValueError:
        return default


class Settings:
    """Application settings read from environment (once at import)."""

    def __init__(self) -> None:
        self.excel_path: str = _str(
            os.getenv("EXCEL_PATH"),
            "./data/Stackbirds_Assignment_Invoice_Extract_100_Rows.xlsx",
        )
        self.variance_threshold: float = _float(os.getenv("VARIANCE_THRESHOLD"), 0.10)
        self.base_url: str = _str(os.getenv("BASE_URL"), "http://localhost:5173")
        self.sqlite_path: str = _str(os.getenv("SQLITE_PATH"), "./data/jobs.db")
        self.mongodb_uri: str = _str(
            os.getenv("MONGODB_URI"), "mongodb://localhost:27017"
        )
        self.mongodb_db: str = _str(os.getenv("MONGODB_DB"), "stackbirds")
        # Optional IMAP / email
        self.imap_host: Optional[str] = os.getenv("IMAP_HOST") or None
        self.imap_user: Optional[str] = os.getenv("IMAP_USER") or None
        self.imap_password: Optional[str] = os.getenv("IMAP_PASSWORD") or None
        self.imap_folder: str = _str(os.getenv("IMAP_FOLDER"), "INBOX")
        # Optional SMTP for sending results link
        self.smtp_host: Optional[str] = os.getenv("SMTP_HOST") or None
        self.smtp_port: Optional[str] = os.getenv("SMTP_PORT") or None
        self.smtp_user: Optional[str] = os.getenv("SMTP_USER") or None
        self.smtp_password: Optional[str] = os.getenv("SMTP_PASSWORD") or None


_settings: Optional[Settings] = None


def get_config() -> Settings:
    """Return singleton settings (read from env on first call)."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
