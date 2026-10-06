# CyArt DarkTrace — Health Monitoring Service

A clean, runnable implementation of the `/api/v1/health` task specification:
FastAPI REST health endpoint, outbound crawler WebSocket heartbeats, AES-256-GCM,
PostgreSQL ping, TTL status storage, and unit tests.

## Architecture

```text
Crawler worker (outbound WebSocket)
        | AES-256-GCM heartbeat
        v
wss://API/api/v1/ws/health ---> decrypt + validate ---> Redis TTL cache
                                                        |
GET /api/v1/health ---> PostgreSQL SELECT 1 ------------+--> consolidated JSON
```

The API never opens a connection to the crawler. For production, terminate TLS at a trusted
reverse proxy and use `wss://`; the `ws://` default is only for local development.

## 1. Install

Python 3.11+ recommended.

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Kali/Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
```

## 2. Configure a key (required)

Generate a random 32-byte AES-256 key:

```bash
python -c "import secrets,base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"
```

Set the printed value in `HEALTH_SHARED_KEY_B64`. Do not commit it or paste it into logs.
For local testing, environment variables are enough; production should load the key from
Vault or another approved secret manager. Use a key reference/version and a coordinated
rotation process in production.

**PowerShell**
```powershell
$env:HEALTH_SHARED_KEY_B64="PASTE_GENERATED_BASE64_KEY"
```

**Kali/Linux/macOS**
```bash
export HEALTH_SHARED_KEY_B64='PASTE_GENERATED_BASE64_KEY'
```

## 3. Start the API

Without PostgreSQL or Redis, the service starts in local demo mode. Database status will be
`degraded` because no `DATABASE_URL` is configured; crawler status is `unhealthy` until a
heartbeat arrives. This is intentional and avoids reporting fake health.

```bash
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs` for interactive API documentation and
`http://127.0.0.1:8000/api/v1/health` for the health response.

## 4. Send crawler heartbeats

Open a second terminal, activate the same virtual environment, and export the **same** key.

```bash
export HEALTH_SHARED_KEY_B64='SAME_GENERATED_BASE64_KEY'
export HEALTH_WS_URL='ws://127.0.0.1:8000/api/v1/ws/health'
python -m crawler.client
```

Windows PowerShell:
```powershell
$env:HEALTH_SHARED_KEY_B64="SAME_GENERATED_BASE64_KEY"
$env:HEALTH_WS_URL="ws://127.0.0.1:8000/api/v1/ws/health"
python -m crawler.client
```

The client connects outbound and sends an encrypted heartbeat every 20 seconds by default.
After the first heartbeat, query the health endpoint again.

## 5. PostgreSQL and Redis

For a real database health check, set `DATABASE_URL` to an async PostgreSQL URL, e.g.
`postgresql+asyncpg://user:password@localhost:5432/dbname`. The service executes `SELECT 1`
with a 1.25-second timeout. Use a least-privilege database account.

Set `REDIS_URL=redis://localhost:6379/0` to use Redis TTL storage. If `REDIS_URL` is omitted,
an in-memory TTL store is used for local development only (not suitable for multiple API
replicas). The default TTL is 60 seconds (3× the 20-second client interval; set TTL to about
2× your chosen interval for production, as the task spec recommends).

## 6. Run tests

```bash
pytest -q
```

Tests cover AES-GCM round-trip, tampered-message rejection, and health response shape.

## Status behavior

- `healthy`: database and crawler are healthy.
- `degraded`: a component is degraded, stale, or not configured.
- `unhealthy`: database is unreachable or no usable crawler heartbeat is available.
- A missing heartbeat expires from the TTL cache; stale workers are not automatically called
  crashed.
- Heartbeats older than the configured replay window or more than 60 seconds in the future
  are rejected.
- Tokens, plaintext heartbeat payloads, and keys are never logged.

## Production checklist

- Confirm with the lead whether detailed health output is public or authenticated.
- Use HTTPS/WSS and network policies; restrict who can submit heartbeats.
- Store the AES key in Vault/secret manager; implement versioned key rotation.
- Use Redis in production and set TTL close to 2× heartbeat interval.
- Consider per-worker identity authentication in addition to shared-key encryption.
- Add rate limits, alerting, and structured audit events without secrets.
