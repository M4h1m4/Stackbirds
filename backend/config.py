"""Configuration from environment variables."""

import os
from pathlib import Path
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


def _find_excel_in_data_dir() -> str:
    """If EXCEL_PATH is not set, look for any .xlsx in project data/ directory."""
    default = "./data/Stackbirds_Assignment_Invoice_Extract_100_Rows.xlsx"
    # Project root: parent of backend/
    project_root = Path(__file__).resolve().parent.parent
    data_dir = project_root / "data"
    if not data_dir.is_dir():
        return default
    # Prefer the known assignment filename, then any .xlsx
    preferred = data_dir / "Stackbirds_Assignment_Invoice_Extract_100_Rows.xlsx"
    if preferred.is_file():
        return str(preferred)
    for p in sorted(data_dir.glob("*.xlsx")):
        return str(p)
    return default


class Settings:
    """Application settings read from environment (once at import)."""

    def __init__(self) -> None:
        excel_env = os.getenv("EXCEL_PATH")
        if excel_env and str(excel_env).strip():
            self.excel_path = str(excel_env).strip()
        else:
            self.excel_path = _find_excel_in_data_dir()
        self.variance_threshold: float = _float(os.getenv("VARIANCE_THRESHOLD"), 0.10)
        self.base_url: str = _str(os.getenv("BASE_URL"), "http://localhost:5173")
        self.sqlite_path: str = _str(os.getenv("SQLITE_PATH"), "./data/jobs.db")
        self.mongodb_uri: str = _str(
            os.getenv("MONGODB_URI"), "mongodb://localhost:27017"
        )
        self.mongodb_db: str = _str(os.getenv("MONGODB_DB"), "stackbirds")
        self.openai_api_key: Optional[str] = os.getenv("OPENAI_API_KEY") or None
        self.openai_model: str = _str(os.getenv("OPENAI_MODEL"), "gpt-4o-mini")
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
