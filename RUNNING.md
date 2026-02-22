# Running the application

This guide covers: creating `.env`, configuration, running the API, frontend, and email poller (locally and with Docker).

**Note:** `.env` is in `.gitignore`; never commit it. Use `.env.example` as a template.

---

## 1. Create `.env`

From the project root:

```bash
cp .env.example .env
```

Edit `.env` and set at least the variables below.

### Minimal (API + pipeline, no email)

```env
OPENAI_API_KEY=sk-your-actual-key-here
OPENAI_MODEL=gpt-4o-mini

SQLITE_PATH=./data/jobs.db
MONGODB_URI=mongodb://localhost:27017
MONGODB_DB=stackbirds

BASE_URL=http://localhost:5173
```

### With email (IMAP) polling

Add:

```env
IMAP_HOST=imap.gmail.com
IMAP_USER=your-email@gmail.com
IMAP_PASSWORD=your-app-password
IMAP_FOLDER=INBOX
```

For Gmail, use an [App Password](https://support.google.com/accounts/answer/185833), not your normal password.

---

## 2. Configuration reference

| Variable | Required | Notes |
|----------|----------|--------|
| **OPENAI_API_KEY** | Yes (for full pipeline) | From [OpenAI API keys](https://platform.openai.com/api-keys). |
| **OPENAI_MODEL** | No | Default `gpt-4o-mini`. |
| **SQLITE_PATH** | No | Default `./data/jobs.db`. Parent dir must exist. |
| **MONGODB_URI** | No | Default `mongodb://localhost:27017`. MongoDB must be running. |
| **MONGODB_DB** | No | Default `stackbirds`. |
| **EXCEL_PATH** | No | If unset, any `.xlsx` in `data/` is used for matching. |
| **VARIANCE_THRESHOLD** | No | Default `0.10` (10%). Unit price variance above this flags the invoice unless user approves in clarification. |
| **BASE_URL** | No | Used for results link in logs (e.g. frontend URL). |
| **IMAP_*** | No | Only if using the email poller. |

### Before first run

1. **Create `./data`** (if using default paths):
   ```bash
   mkdir -p data
   ```
2. **Start MongoDB** (if using default URI):
   ```bash
   brew services start mongodb-community   # macOS Homebrew
   ```
3. **Put an Excel file** in `data/` (any `.xlsx`) for the matching phase, or set `EXCEL_PATH`.
4. **Image invoices (optional):** For image extraction the app uses Tesseract. Install if needed: `brew install tesseract` (macOS).

---

## 3. Run the API

From project root:

```bash
uv run uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

- **Health:** http://localhost:8000/health  
- **API docs:** http://localhost:8000/docs  
- **Processing list:** http://localhost:8000/processing?inbox_email=your@email.com  

Tables are created automatically on first request.

---

## 4. Run the frontend

In a separate terminal, from project root:

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. Enter your inbox email (the one that receives invoice emails) and click **Load** to see processings. Set `VITE_API_URL=http://localhost:8000` in `frontend/.env` if the API is on a different host.

---

## 5. Run the email poller

If `.env` has `IMAP_HOST`, `IMAP_USER`, and `IMAP_PASSWORD`:

**Run once (check inbox and exit):**
```bash
uv run python -m backend.ingestion.email_poller
```

**Run in a loop (poll every 5 minutes):**
```bash
uv run python -m backend.ingestion.email_poller --loop --interval 300
```

The poller finds **unread** emails with **PDF or image** attachments, creates an invoice for each, runs the pipeline, and marks the message as seen. The sender’s email is used as `customer_id`; the inbox owner can then enter that inbox email in the frontend to see processings.

---

## 6. Test as a client (inbox email → decisions)

1. Start the API (section 3).
2. Start the poller with `--loop` (section 5).
3. Start the frontend (section 4).
4. Open http://localhost:5173, enter the **same email** you set as `IMAP_USER`, click **Load**.
5. Send an email **to** that inbox with a PDF or image attachment. After the poller runs, click **Load** again to see the new processing; click **View** to see extraction, matching, clarification (if any), and the final decision.

---

## 7. API client tests

With the API running:

```bash
uv run pytest tests/test_api_client.py -v
```

Optional base URL:

```bash
BASE_URL=http://localhost:8000 uv run pytest tests/test_api_client.py -v
```

Quick smoke check (no pytest):

```bash
uv run python tests/test_api_client.py
```

---

## 8. Docker

For running the full stack (API + frontend + MongoDB + poller) with Docker, see [DOCKER.md](DOCKER.md).

```bash
cp .env.example .env
# Edit .env: OPENAI_API_KEY and IMAP_*
docker compose up -d
```

Then open http://localhost:8000.
