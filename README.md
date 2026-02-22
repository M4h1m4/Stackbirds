# Invoice Processor

An invoice processing application that takes invoices from your email inbox, extracts line items and vendor information, matches them against approved vendors and contracted rates, and produces an **APPROVE** or **FLAGGED** decision with a human-readable reconciliation report. The pipeline is driven by an LLM and supports clarification questions when the system needs your input.

## Features

- **Email-driven input** — Polls a configured inbox (IMAP) for unread emails with PDF or image attachments; each attachment is treated as an invoice and processed automatically.
- **Four-phase workflow** — **Extraction** (PDF/image → vendor, line items, totals) → **Matching** (invoice matched to approved vendor and contracted rows) ↔ **Clarification** (LLM can ask questions; you submit answers to resume) → **Completion** (APPROVE or FLAGGED with reconciliation report).
- **Vendor and price checks** — The system checks vendor match first, then line-item mapping, then unit prices. If any line’s unit price varies more than a configurable threshold (default 10%) from the contracted price, the invoice is FLAGGED for human review unless you explicitly approve in clarification.
- **Web UI** — React frontend to enter your inbox email, view processings, see extraction and matching, answer clarification questions, and view the final decision and reconciliation report.
- **Audit trail** — Full trail including LLM reasoning from extraction, matching, and completion.
- **Docker** — Single image for API + frontend; optional email poller in the same image. Run the full stack with Docker Compose (app + MongoDB + poller).

## Tech stack

| Layer      | Technology |
|-----------|------------|
| Backend   | Python 3.9+, FastAPI, SQLAlchemy (SQLite), MongoDB |
| Frontend  | React (Vite) |
| Pipeline  | pdfplumber (PDF), PIL + Tesseract (images), OpenAI API (LLM), pandas + openpyxl (Excel) |
| Email     | IMAP (inbox polling) |

## Prerequisites

- **OpenAI API key** — Required for extraction, matching, and completion.
- **MongoDB** — For document storage (PDF/image bytes). Run locally or use a hosted instance.
- **Excel file (optional)** — Approved vendors and contracted line items for the matching phase. Place any `.xlsx` in `data/` or set `EXCEL_PATH`.
- **IMAP credentials (optional)** — For email polling. Gmail users: use an [App Password](https://support.google.com/accounts/answer/185833).

## How to run

The application is **dockerized** and can be run with Docker or Docker Compose. A pre-built image is available on **Docker Hub**:

- **Docker Hub:** The image is published as **invoiceapproverbot** (lowercase). Image link:  
  **https://hub.docker.com/r/m4h1m416/invoiceapproverbot**

### Option A: Run from Docker Hub (pull image)

If you have Docker and Docker Compose, create a folder with a `docker-compose.yml` that uses the image and a `.env` file, then start the stack:

```bash
# Create a directory and .env (see .env.example in the repo for variables)
mkdir invoice-processor && cd invoice-processor
# Copy docker-compose.yml from the repo or use one that references the image:
# image: invoiceapproverbot/invoiceapproverbot:latest  (or your-username/invoiceapproverbot:latest)
cp .env.example .env
# Edit .env: OPENAI_API_KEY and IMAP_HOST, IMAP_USER, IMAP_PASSWORD

docker compose up -d
```

Then open **http://localhost:8000** and enter your inbox email to see processings.

### Option B: Build and run from source

```bash
git clone <repository-url>
cd <project-directory>

cp .env.example .env
# Edit .env: set OPENAI_API_KEY and IMAP_HOST, IMAP_USER, IMAP_PASSWORD (for inbox polling)

docker compose up -d
```

Then open **http://localhost:8000**, enter the email address that receives invoice emails, and click **Load** to see processings.

For more (build only, push to Docker Hub, customer deployment), see [DOCKER.md](DOCKER.md).

## Running locally (without Docker)

### 1. Backend

- **Python:** 3.9+ (recommended: 3.12). The project uses [uv](https://docs.astral.sh/uv/) for dependencies.

  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  uv venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
  uv sync
  ```

- **Environment:** Copy `.env.example` to `.env` and set at least `OPENAI_API_KEY`. Set `IMAP_*` if you want the email poller to run.

- **MongoDB:** Start MongoDB (e.g. `brew services start mongodb-community` on macOS). Default URI: `mongodb://localhost:27017`.

- **Data directory:** Create `./data` and optionally put an Excel file (`.xlsx`) there for the matching phase.

- **Start the API:**

  ```bash
  uv run uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
  ```

  API docs: **http://localhost:8000/docs**

### 2. Frontend

  ```bash
  cd frontend
  npm install
  npm run dev
  ```

  Open **http://localhost:5173**. Set `VITE_API_URL=http://localhost:8000` in `frontend/.env` if the API runs on a different host.

### 3. Email poller (optional)

  If `.env` contains `IMAP_HOST`, `IMAP_USER`, and `IMAP_PASSWORD`, run the poller to process the inbox:

  ```bash
  uv run python -m backend.ingestion.email_poller --loop --interval 300
  ```

  This polls every 5 minutes, creates invoices from unread emails with PDF/image attachments, runs the pipeline, and marks messages as seen.

## Configuration

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes | OpenAI API key for extraction, matching, and completion. |
| `OPENAI_MODEL` | No | Default `gpt-4o-mini`. |
| `SQLITE_PATH` | No | Default `./data/jobs.db`. Metadata DB path. |
| `MONGODB_URI` | No | Default `mongodb://localhost:27017`. |
| `MONGODB_DB` | No | Default `stackbirds`. |
| `EXCEL_PATH` | No | Path to Excel file. If unset, any `.xlsx` in `data/` is used. |
| `VARIANCE_THRESHOLD` | No | Default `0.10` (10%). Unit price variance above this flags the invoice unless the user approves in clarification. |
| `BASE_URL` | No | Base URL for results link in logs (e.g. frontend URL). |
| `IMAP_HOST`, `IMAP_USER`, `IMAP_PASSWORD` | For poller | Inbox credentials. Gmail: use an App Password. |
| `IMAP_FOLDER` | No | Default `INBOX`. |

See `.env.example` for a full template.

## API overview

- **GET** `/health` — Health check.
- **GET** `/processing?customer_id=...` or `?inbox_email=...` — List processings for a customer or inbox.
- **GET** `/extraction?state_id=...` — Get extraction result for a state.
- **GET** `/matching?state_id=...` — Get matching result for a state.
- **GET** `/clarification?clarification_id=...` — Get clarification questions (and answers if any).
- **POST** `/clarification?clarification_id=...` — Submit answers and mark completed (resumes pipeline).
- **GET** `/completion?processing_id=...` — Get final decision and reconciliation report when processing is complete.
- **POST** `/invoice` — (Testing only.) Create an invoice from a JSON body (e.g. `document_base64` + `customer_id`). Primary input in production is the email inbox.

When running in Docker with the frontend served by the backend, the API is under the `/api` prefix (e.g. `/api/health`, `/api/processing`).

## Project structure

```
├── backend/           # FastAPI app, pipeline, storage
│   ├── api/           # Routes and dependencies
│   ├── models/        # Pydantic API models
│   ├── pipeline/     # Extractor, LLM (matching, decision), runner
│   ├── storage/       # SQLAlchemy, MongoDB document store
│   └── ingestion/     # Email poller (IMAP)
├── frontend/          # React (Vite) UI
├── data/              # Excel, optional PDFs (mount or copy for Docker)
├── tests/             # Pytest (including API client tests)
├── docker-compose.yml # App + MongoDB + poller
├── Dockerfile         # Single image (API + frontend + poller code)
├── .env.example       # Environment template
├── DOCKER.md          # Docker build, push, and customer deployment
└── RUNNING.md         # Detailed run and email setup
```

## Testing

- **API client tests** (run against a live server):  
  Start the API, then from the project root:
  ```bash
  uv run pytest tests/test_api_client.py -v
  ```
  See `tests/test_api_client.py` and [RUNNING.md](RUNNING.md) for details.

## License

See the repository for license information.
