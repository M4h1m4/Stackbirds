"""FastAPI application: user-facing API and optional invoice creation."""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root (parent of backend/) so env vars are set before config is read
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.api.routes import router
from backend.storage import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create DB tables on startup."""
    init_db()
    yield
    # shutdown: nothing to close for SQLite/Mongo


app = FastAPI(
    title="StackBirds Invoice Processor",
    description="Invoice processing: Extraction → Matching ↔ Clarification → Completion. Input from email inbox (IMAP).",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# When serving frontend (e.g. Docker), API is under /api and static SPA at /
if os.getenv("SERVE_FRONTEND"):
    app.include_router(router, prefix="/api", tags=["api"])
    # Static dir: project root / static (in Docker: /app/static)
    static_dir = Path(__file__).resolve().parent.parent / "static"
    if static_dir.is_dir():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
else:
    app.include_router(router, tags=["api"])
