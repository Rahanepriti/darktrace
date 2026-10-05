# DarkTrace Health Monitoring Service

## Overview

The **DarkTrace Health Monitoring Service** is a FastAPI-based service that monitors the health of the PostgreSQL database and crawler workers.

The service combines:

* PostgreSQL database health checks
* Crawler worker health monitoring
* Redis-based heartbeat tracking
* WebSocket-based crawler heartbeats
* AES-256-GCM encrypted heartbeat messages
* Replay protection
* Multi-worker health monitoring
* Automated health and security tests

The main health endpoint is:

```text
GET /api/v1/health
```

---

## Architecture

Crawler workers act as **WebSocket clients** and establish outbound connections to the FastAPI service.

```text
Crawler Worker
     |
     | Outbound WebSocket
     | Encrypted heartbeat
     v
FastAPI Health Service
     |
     +----> Decrypt + Validate heartbeat
     |
     +----> Redis
     |       |
     |       +---- Latest heartbeat per worker
     |       +---- TTL / freshness
     |
     +----> PostgreSQL health check
     |
     v
GET /api/v1/health
```

The FastAPI service:

1. Receives encrypted crawler heartbeats.
2. Decrypts and validates each heartbeat.
3. Checks the heartbeat timestamp for replay protection.
4. Stores the latest heartbeat for each worker in Redis.
5. Uses heartbeat freshness to determine crawler health.
6. Checks PostgreSQL availability.
7. Combines database and crawler health.
8. Returns the overall health status through the health API.

---

## Health States

### Healthy

The service reports `healthy` when:

* PostgreSQL is reachable.
* At least one crawler heartbeat is fresh.
* Crawler workers are reporting a healthy state.

### Degraded

The service reports `degraded` when:

* PostgreSQL is available, but crawler heartbeats are missing or stale.
* A crawler worker reports a degraded state.
* A heartbeat contains invalid health information but the database remains usable.

### Unhealthy

The service reports `unhealthy` when:

* PostgreSQL is unavailable.

If no usable crawler heartbeat is available, the crawler component is reported as degraded.

---



# Requirements

## Software

The project requires:

* Python 3.12+
* PostgreSQL
* Redis
* Git

Python packages are listed in:

```text
requirements.txt
```

---

# Installation

## 1. Clone the repository

```bash
git clone https://github.com/Rahanepriti/darktrace.git
```

Move into the project:

```bash
cd darktrace
```

---

## 2. Create a Python virtual environment

Create the virtual environment:

```bash
python3 -m venv .venv
```

Activate it on Linux/macOS:

```bash
source .venv/bin/activate
```

Verify Python:

```bash
python --version
```

Python 3.12 or newer is recommended.

---

## 3. Install dependencies

Upgrade pip:

```bash
python -m pip install --upgrade pip
```

Install project dependencies:

```bash
pip install -r requirements.txt
```

---

# PostgreSQL Setup

The service requires PostgreSQL for database health monitoring.

## 1. Start PostgreSQL

On Linux:

```bash
sudo systemctl start postgresql
```

Check PostgreSQL:

```bash
sudo systemctl status postgresql
```

---

## 2. Create the database

Create a database named:

```text
darktrace_health
```

Example:

```bash
sudo -u postgres psql
```

Inside PostgreSQL:

```sql
CREATE DATABASE darktrace_health;
```

Exit:

```sql
\q
```

---

## 3. Database connection

The application uses the `DATABASE_URL` environment variable.

Example:

```text
DATABASE_URL=postgresql+psycopg://postgres:<password>@localhost:5432/darktrace_health
```

Replace `<password>` with the local PostgreSQL password.

---

# Redis Setup

Redis is used to store the latest crawler heartbeat for each worker.

## Start Redis

On Linux:

```bash
sudo systemctl start redis
```

Check Redis:

```bash
redis-cli ping
```

Expected response:

```text
PONG
```

The application expects Redis on:

```text
localhost:6379
```

---

# Environment Configuration

Create a local `.env` file in the project root:

```text
darktrace_health_monitor/
├── .env
├── README.md
├── requirements.txt
└── ...
```

The `.env` file should contain:

```env
DATABASE_URL=postgresql+psycopg://postgres:<password>@localhost:5432/darktrace_health
HEALTH_ENCRYPTION_KEY=<64-character-hex-key>
```

## Encryption Key

`HEALTH_ENCRYPTION_KEY` must contain:

* 64 hexadecimal characters
* 32 bytes of key material
* AES-256 compatible key length


Generate a secure key with Python:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Copy the generated value into `.env`.

---


# Running the FastAPI Service

Activate the virtual environment:

```bash
source .venv/bin/activate
```

Start the API:

```bash
uvicorn app.main:app --reload
```

The service runs by default on:

```text
http://127.0.0.1:8000
```

---

# Health API

The main endpoint is:

```text
GET /api/v1/health
```

Open:

```text
http://127.0.0.1:8000/api/v1/health
```

Or use:

```bash
curl http://127.0.0.1:8000/api/v1/health
```

---

## Example Healthy Response

```json
{
  "status": "healthy",
  "checked_at": "2026-10-05T06:38:43.939617+00:00",
  "components": {
    "database": {
      "status": "healthy",
      "latency_ms": 16.9
    },
    "crawler": {
      "status": "healthy",
      "last_heartbeat": "2026-10-05T06:38:43.939617Z",
      "active_workers": 2,
      "queue_depth": 21
    }
  }
}
```


# Crawler Heartbeat

The crawler-side WebSocket client is located at:

```text
crawler_client/heartbeat.py
```

The client sends a heartbeat every 20 seconds during local testing.

The heartbeat contains:

```json
{
  "worker_id": "cw-test-01",
  "status": "healthy",
  "timestamp": "2026-10-05T06:38:43Z",
  "queue_depth": 14,
  "last_successful_fetch": "2026-10-05T06:38:43Z"
}
```

---

## Run the Local Crawler Client

Make sure the FastAPI server is already running.

From the project root:

```bash
PYTHONPATH=. python crawler_client/heartbeat.py
```

Expected output:

```text
Heartbeat sent
Heartbeat sent
Heartbeat sent
```

The crawler continues sending heartbeats every 20 seconds.

---

















# Testing

The project uses `pytest` and `pytest-asyncio`.

Run the complete test suite:

```bash
pytest
```

Expected result:

```text
5 passed
```

---

## Tests Included

### 1. WebSocket heartbeat test

Checks that an encrypted heartbeat can be sent through the WebSocket endpoint.

### 2. Encryption roundtrip test

Verifies:

```text
plaintext
   ↓
encrypt
   ↓
decrypt
   ↓
original plaintext
```

### 3. Tampered message test

Modifies an encrypted heartbeat and verifies that decryption rejects it.

### 4. Stale heartbeat test

Stores an old heartbeat and verifies that crawler health becomes degraded.

### 5. Health endpoint response test

Verifies that:

```text
GET /api/v1/health
```

returns HTTP 200 and contains:

```text
status
checked_at
components
database
crawler
```

---










# Development Notes

## Local API

```text
http://127.0.0.1:8000
```

## Health endpoint

```text
GET /api/v1/health
```

## WebSocket endpoint

```text
ws://127.0.0.1:8000/api/v1/ws/health
```

## Redis

```text
localhost:6379
```

## PostgreSQL

```text
localhost:5432
```

---

# Typical Local Workflow

Start PostgreSQL:

```bash
sudo systemctl start postgresql
```

Start Redis:

```bash
sudo systemctl start redis
```

Activate the virtual environment:

```bash
source .venv/bin/activate
```

Start FastAPI:

```bash
uvicorn app.main:app --reload
```

In another terminal, start the crawler:

```bash
cd /path/to/darktrace_health_monitor
source .venv/bin/activate
PYTHONPATH=. python crawler_client/heartbeat.py
```

Check health:

```bash
curl http://127.0.0.1:8000/api/v1/health
```

Run tests:

```bash
pytest
```

---




