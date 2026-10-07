# DarkTrace `/health` Endpoint

Health check service for CyArt DarkTrace. Reports whether the system is actually working by checking two things:

1. **Database** — can the API reach it?
2. **Crawlers** — are they still alive, based on encrypted heartbeats
   they send over a WebSocket?

Both are combined into one status: `healthy`, `degraded`, or `unhealthy`.

## How it works

Crawlers run in an isolated network zone and can't be reached directly
by the API. Instead, each crawler connects outward to us and pushes an encrypted message (AES-256-GCM encrypted - heartbeat) every few seconds.
 

A heartbeat is rejected (and logged, connection stays open) if:
- it was encrypted with the wrong key, or tampered with in transit
- it's missing a required field or has the wrong shape
- it's older than 5 minutes (replay protection)

## Project files

| File | What it does |
|---|---|
| `config.py` | Every setting (Redis URL, AES key, DB URL) in one place, loaded from `.env` |
| `crypto_utils.py` | AES-256-GCM encrypt/decrypt — the shared contract between crawler and API |
| `redis_cache.py` | Stores/reads each crawler's last known status in Redis |
| `db_check.py` | Runs `SELECT 1` against the database with a timeout |
| `ws_server.py` | The WebSocket endpoint (`/ws/heartbeat`) that receives crawler heartbeats |
| `main.py` | The FastAPI app — exposes `GET /api/v1/health` |
| `crawler_client.py` | A simulated crawler, for testing the server without the real crawler code |
| `tests/` | Standalone scripts that verify encryption and Redis caching work correctly |

 

## Setup on Linux

**1. Install Redis**

```bash
# Arch
sudo pacman -S redis
sudo systemctl start redis

# Verify it's running
redis-cli ping   # should print PONG
```

**2. Clone/copy the project, then set up a virtual environment**

```bash
cd health_endpoint
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**3. Configure environment variables**

```bash
cp .env.example .env
```

Generate an AES-256 key and paste it into `.env` as `HEALTH_AES_KEY_V1`:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

 
## Running it

Open 3 terminals.

**Terminal 1 — start the API server:**

```bash
source venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8001 --reload
```

**Terminal 2 — simulate a crawler sending heartbeats:**

```bash
source venv/bin/activate
python crawler_client.py
```

**Terminal 3 — check the health endpoint:**

```bash
curl localhost:8001/api/v1/health
```

Expected response once a heartbeat has come in:

```json
{
  "status": "degraded",
  "checked_at": 1791269743.64,
  "database": {"ok": false, "detail": "DATABASE_URL not configured"},
  "crawlers": {"crawler-01": "ok"}
}
```

`status` will be `unhealthy` until `DATABASE_URL` is set to a real,
reachable database.

## Running the tests

```bash
python tests/test_crypto_utils.py
python tests/test_redis_cache.py
```

Both should print `All ... tests passed.` with no errors. These check:
- encrypt → decrypt returns the original message
- a tampered message is rejected
- a wrong key is rejected
- Redis correctly stores and reads back crawler status

### status

- **unhealthy** - database unreachable
- **degraded** - database OK, but at least one crawler is stale/down/error
- **healthy** - database OK and every known crawler reporting `ok`

 <img width="1920" height="1080" alt="Image" src="https://github.com/user-attachments/assets/b597278e-7c2f-4e81-9117-e572de443450" />
