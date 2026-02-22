# Docker deployment

One image runs the **full application**: API, frontend, and email inbox processing. Use Docker Compose to run app + MongoDB + email poller together.

## Prerequisites

- Docker and Docker Compose
- A `.env` file (copy from `.env.example`):
  - **OPENAI_API_KEY** (required)
  - **IMAP_HOST**, **IMAP_USER**, **IMAP_PASSWORD** (for email poller; e.g. Gmail App Password)

## One-command run (full stack)

```bash
# From project root
cp .env.example .env
# Edit .env: OPENAI_API_KEY and IMAP_* for inbox processing
docker compose up -d
```

This starts:
- **app** – API + frontend on http://localhost:8000
- **mongodb** – document and metadata store
- **poller** – email inbox processor (polls every 5 min, creates invoices from PDF/image attachments)

Then open **http://localhost:8000** and enter your inbox email to see processings.

## Commands

| Command | Description |
|--------|-------------|
| `docker compose up -d` | Start app + MongoDB + poller |
| `docker compose down` | Stop and remove containers |
| `docker compose up -d --build` | Rebuild image and start |
| `docker compose logs -f app` | App logs |
| `docker compose logs -f poller` | Email poller logs |

## Volumes

- **app_data**: SQLite DB and app data (shared by app and poller).
- **./data**: Mounted to `/app/data` for Excel files (and optional PDFs) on the host.

## Email poller

The poller is included in the default stack. Set `IMAP_HOST`, `IMAP_USER`, `IMAP_PASSWORD` in `.env`. It runs in a separate container using the same image, shares the same DB and MongoDB with the app, and processes unread emails with PDF/image attachments. To disable it, comment out the `poller` service in `docker-compose.yml`.

## Build only (no compose)

Image name is **invoiceapproverbot** (lowercase; required by Docker Hub).

```bash
docker build -t invoiceapproverbot:latest .
docker run -p 8000:8000 -e OPENAI_API_KEY=sk-... -e MONGODB_URI=mongodb://host.docker.internal:27017 invoiceapproverbot:latest
```

Note: Without compose, you must run MongoDB elsewhere and set `MONGODB_URI` to reach it.

## Build and push to Docker Hub

Docker Hub requires **lowercase** repository names. Use the image name **invoiceapproverbot**.

1. **Log in**
   ```bash
   docker login
   ```

2. **Build** (replace `YOUR_DOCKERHUB_USERNAME` with your actual username, e.g. `johndoe`)
   ```bash
   docker build -t YOUR_DOCKERHUB_USERNAME/invoiceapproverbot:latest .
   ```

3. **Push**
   ```bash
   docker push YOUR_DOCKERHUB_USERNAME/invoiceapproverbot:latest
   ```

Example if your Docker Hub username is `johndoe`:
```bash
docker build -t johndoe/invoiceapproverbot:latest .
docker push johndoe/invoiceapproverbot:latest
```

## Customer / client deployment

After a customer **pulls** your image, they run the app with **their own** configuration. No email or keys are baked into the image.

1. **Pull and run with Docker Compose (recommended)**  
   They create a project folder with a `docker-compose.yml` that uses your image and a `.env` with their settings:

   - **OPENAI_API_KEY** – their OpenAI key  
   - **IMAP_HOST**, **IMAP_USER**, **IMAP_PASSWORD** – their inbox (e.g. Gmail App Password)  
   - Optionally **IMAP_FOLDER** (default `INBOX`)

   The poller in the stack will then poll **their** inbox and create invoices from emails with PDF/image attachments. Each customer uses their own `.env`; they never see your credentials.

2. **Or use `docker run`**  
   They pass the same variables via `-e` or `--env-file` when running the container.

So: **yes, each customer/client configures their own email to poll** by setting `IMAP_*` in their `.env` (or environment) when they run the image.
