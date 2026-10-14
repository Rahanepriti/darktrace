# DarkTrace development setup

This repository now includes a minimal development API so the frontend can run without a database, crawler, or external services.The development API uses Redis to persist alerts across backend restarts. Accounts, sessions, and queued jobs remain in memory and are cleared when the backend restarts. Configure the `REDIS_URL` environment variable before starting the API.

## Requirements

- Node.js 18+
- Python 3.11+

## Redis configuration

The development API uses Redis to persist alerts across backend restarts. The Redis instance for this development setup is hosted on Railway.

### Configuration

Set the `REDIS_URL` environment variable to your Redis connection URL before starting the backend. For local development, you can store it in a `.env` file.

Keep Redis credentials private. Never commit `.env` or publish the Redis connection URL in the README or source code.

### Dependencies

Install the development dependencies:

```powershell
cd backend
python -m pip install -r requirements-dev.txt
```

### Persistence behavior

- Alerts are stored in Redis and remain available after backend restarts, provided the Redis data is retained.
- Accounts, sessions, and queued jobs remain in memory and are cleared when the backend restarts.
- The Redis service must be available and reachable for alert operations to work.

## Run locally

Open two PowerShell terminals from the repository root.

### 1. Start the minimal development API

```powershell
cd backend
python -m pip install -r requirements-dev.txt
uvicorn dev_server:app --reload --port 8000
```

Check that it is running:

```powershell
Invoke-RestMethod http://localhost:8000/health
```

### 2. Start the frontend

```powershell
cd frontend
npm ci
npm run dev
```

Open [http://localhost:5173](http://localhost:5173), create an account, and sign in. The Vite development server automatically forwards `/api/*` requests to `http://localhost:8000`.

## What works in development

- Register, sign in, sign out, and session validation
- Dashboard reads alerts and severity summaries from Redis; sources and crawl jobs use the existing development implementation
- Threat Intelligence reads in-memory alerts
- Crawler page queues jobs against one safe, local development source

Queued jobs remain in `queued` state. No URLs are fetched and no crawler is started.

## Deliberately not implemented

The production-oriented `backend/main.py` remains untouched and is not the local development entry point. It requires modules that are not present in this workspace.

Do **not** run `uvicorn main:app` for the minimal setup. Run `uvicorn dev_server:app` instead.

See [unimplimented.md](unimplimented.md) for every deferred module, where it will be used, the endpoints involved, and its expected inputs/outputs.

## Verify

```powershell
python -m py_compile backend\dev_server.py
cd frontend
npm run build
```

The development API does not use database files or migrations. Alerts are stored in Redis and survive backend restarts. Accounts, sessions, and queued jobs remain in memory and are cleared when the backend restarts.
