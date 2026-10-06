# CyArt DarkTrace - Health Monitoring Module

Secure health monitoring for the CyArt DarkTrace platform: PostgreSQL check, crawler heartbeat over an
**outbound** (crawler -> API) AES-256-GCM-encrypted WebSocket, Redis TTL cache, a consolidated
`GET /api/v1/health`, and a **real-time dashboard** (`/dashboard`, live feed over `/api/v1/ws/monitor`).

## 1. Architecture

```
Crawler zone (egress-only)                     API zone
 HeartbeatClient ──outbound wss──►  /api/v1/ws/health (FastAPI WebSocket SERVER)
   every ~20 s, AES-256-GCM            │ bearer auth → decrypt → JSON → Pydantic → replay check
                                       ▼
                                  Redis  crawler:heartbeat:<worker_id>  (TTL ≈ 2×interval)
                                         crawler:last_seen (hash, outlives TTL → "stale" vs "never seen")
                                         crawler:nonce:<hex> (replay protection)
                                       │
 Ops browser ◄── /api/v1/ws/monitor ◄──┤  HealthService (DB ∥ crawler, concurrent, 1.8 s budget)
 curl / LB   ◄── GET /api/v1/health ◄──┘            ▲ SELECT 1 (1 s timeout)  PostgreSQL
```
The API never initiates a connection toward the crawler.

## 2. Install & run (local)

```bash
python -m venv .venv && . .venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
cp .env.example .env && python scripts/gen_secrets.py   # paste output into .env (replace CHANGE_ME values)
uvicorn app.main:app --reload                           # API + dashboard
python -m app.crawler.heartbeat_client                  # demo crawler (separate terminal)
```
* PostgreSQL: create a DB/user, set `DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/db` (`postgres://` is auto-converted).
* Redis: any Redis 6+; `REDIS_URL=redis://:password@host:6379/0`.
* Dashboard: open `http://localhost:8000/dashboard`, paste `HEALTH_API_TOKEN`.
* To embed in your real crawler: `HeartbeatClient(url, token, crypto, worker_id, your_status_provider).run(stop_event)`
  where the provider returns `WorkerSnapshot(status, queue_depth, last_successful_fetch)`.

### Docker
```bash
cp .env.example .env && python scripts/gen_secrets.py   # fill ALL CHANGE_ME values incl. POSTGRES/REDIS_PASSWORD
docker compose up --build                 # api + postgres + redis
docker compose --profile demo up --build  # + demo crawler
```
Compose contains no secrets; it refuses to start if `POSTGRES_PASSWORD`/`REDIS_PASSWORD` are unset.

## 3. Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `APP_ENV` | development | `production` disables `/docs`, client refuses `ws://` |
| `DATABASE_URL`, `REDIS_URL` | - | connections (never logged / returned) |
| `HEALTH_ENCRYPTION_KEY` | - | 256-bit key (base64/hex) for `ACTIVE_KEY_VERSION`; `CHANGE_ME` is rejected |
| `ACTIVE_KEY_VERSION` | 1 | key version used to encrypt |
| `HEALTH_ENCRYPTION_KEYS_PREVIOUS` | - | JSON `{"1":"..."}` old keys kept for decryption |
| `HEALTH_ENCRYPTION_KEYS_FILE` | - | JSON key file `{"active_version":2,"keys":{"1":"..","2":".."}}` (hot reload) |
| `KEY_REFRESH_SECONDS` | 60 | how often keys are re-read |
| `HEALTH_API_TOKEN` | - | Bearer token for detailed `/health` and the live monitor |
| `CRAWLER_WS_TOKEN` | - | Bearer token the crawler presents on `/ws/health` |
| `HEARTBEAT_INTERVAL_SECONDS` | 20 | crawler send interval (15-30 recommended) |
| `HEARTBEAT_TTL_SECONDS` | 2×interval | Redis TTL = freshness window |
| `HEARTBEAT_MAX_AGE_SECONDS` | 300 | replay window |
| `CRAWLER_UNHEALTHY_AFTER_SECONDS` | 300 | all heartbeats stale this long ⇒ `unhealthy` |
| `DATABASE_TIMEOUT_SECONDS` / `REDIS_TIMEOUT_SECONDS` | 1 / 1 | per-operation timeouts |
| `HEALTH_BUDGET_SECONDS` | 1.8 | hard cap for the whole `/health` computation |
| `PUBLIC_HEALTH_ENDPOINT` | false | see §6 |
| `MONITOR_ENABLED`, `MONITOR_PUSH_INTERVAL_SECONDS` | true, 3 | live dashboard |
| `HEALTH_WS_URL`, `WORKER_ID` | - | crawler client settings |

## 4. Health status logic

* **unhealthy** - database unreachable/timed out; OR no heartbeat ever received; OR every known worker has been silent longer than `CRAWLER_UNHEALTHY_AFTER_SECONDS`.
* **degraded** - heartbeat expired past TTL but within that window (treated as *stale*, not crashed); some workers stale/degraded/down; DB slower than 500 ms; Redis unreachable (crawler state unknown).
* **healthy** - DB reachable and every known worker has a fresh, healthy heartbeat.

Design decision: the spec says a stale heartbeat is *degraded* yet "no heartbeat within the required window" is *unhealthy*. These are reconciled with a two-stage rule: expiry at TTL ⇒ stale/degraded; continued silence beyond `CRAWLER_UNHEALTHY_AFTER_SECONDS` ⇒ unhealthy.
HTTP status: `200` healthy/degraded, `503` unhealthy.

## 5. WebSocket protocol

`wss://<host>/api/v1/ws/health`, header `Authorization: Bearer <CRAWLER_WS_TOKEN>` (never in the URL).
Every text frame is `base64url( key_version[2] ‖ nonce[12] ‖ ciphertext ‖ tag[16] )`, AAD = version ‖ `cyart-darktrace-health-v1`.
Plaintext heartbeat:
```json
{"worker_id":"cw-14","status":"healthy","timestamp":"2026-10-01T08:59:50Z","queue_depth":14,"last_successful_fetch":"2026-10-01T08:59:40Z"}
```
Server replies (also encrypted): `{"type":"ack","ok":true,"active_key_version":2,...}` or `{"type":"nack","ok":false,"reason":"<code>"}` with codes
`decrypt_failed, invalid_json, invalid_schema, stale_timestamp, future_timestamp, replay, payload_too_large, invalid_frame, cache_unavailable`.
Rejected messages never crash the handler; 5 consecutive rejects close that connection (1008). Idle > 90 s closes it.

Live monitor: `/api/v1/ws/monitor` - first message `{"type":"auth","token":"<HEALTH_API_TOKEN>"}`, then a `snapshot` every 3 s.

## 6. Public vs. detailed `/health`

* Valid Bearer token → full detail (`status`, `checked_at`, `components`).
* No token + `PUBLIC_HEALTH_ENDPOINT=true` → `{"status":"healthy"}` only.
* No token + `PUBLIC_HEALTH_ENDPOINT=false` (default) → `401`. Wrong token → `401`.

Example (authenticated):
```json
{"status":"healthy","checked_at":"2026-10-01T09:00:00Z","components":{
 "database":{"status":"healthy","latency_ms":12},
 "crawler":{"status":"healthy","last_heartbeat":"2026-10-01T08:59:50Z","active_workers":8,"queue_depth":14,"stale_workers":0,"workers":[...]}}}
```

## 7. Encryption, key provisioning & rotation

* AES-256-GCM (`cryptography`), key must be exactly 32 bytes, fresh `os.urandom(12)` nonce per message, tag verified on decrypt; tampering, wrong key, unknown version → generic `CryptoError` (no oracle). Keys never logged (logger redacts, `KeyRing.__repr__` hides material).
* Random 96-bit nonces are safe for ~2³² messages per key; at 1 msg/20 s per worker that is far beyond the 30-day rotation period.
* **Provisioning**: `python scripts/gen_secrets.py`; inject via env (dev) or a mounted file (`HEALTH_ENCRYPTION_KEYS_FILE`) written by Vault Agent / K8s secret. For direct Vault/KMS access implement `KeyProvider.load() -> KeyRing` (`app/crypto/aes_gcm.py`) and return it from `build_key_provider`.
* **Rotation (every ~30 days, no crawler redeploy)** - use the key file:
  1. Generate key v2. Add it to the secret store for **both** API and crawlers, keeping v1; leave `active_version: 1`.
  2. Wait ≥ `KEY_REFRESH_SECONDS` so everyone can decrypt v2.
  3. Set `active_version: 2` on the API. Acks advertise it; crawlers that hold v2 switch automatically (the crawler's own active version also follows its file).
  4. After in-flight messages age out (> `HEARTBEAT_MAX_AGE_SECONDS`), remove v1.
* Replay protection: timestamp window (`HEARTBEAT_MAX_AGE_SECONDS`, UTC) **plus** one-time nonce stored in Redis, so a captured ciphertext cannot be re-sent even within the window.

## 8. Tests

```bash
pip install -r requirements-dev.txt && pytest -q       # 59 tests
```
Covers crypto, health logic/schema, DB/Redis failure and slowness, staleness + TTL, WebSocket (valid, bad JSON/schema/crypto, tamper, replay, multi-worker), live monitor, and a real-socket end-to-end test (uvicorn + real crawler client). Tests use fakeredis and SQLite - no services required.

## 9. Security considerations / limits

* TLS: terminate `wss://`/`https://` at your reverse proxy; the crawler client refuses `ws://` when `APP_ENV=production`.
* Tokens are compared in constant time; unset or `CHANGE_ME` tokens/keys reject everyone.
* Responses expose only generic error codes (`timeout`, `unreachable`) - never DSNs or driver messages.
* The monitor token is sent in the first WebSocket message (browsers can't set headers) - not in URLs, so it stays out of access logs.
* Not included: per-IP rate limiting (do it at the proxy), mTLS between zones, multi-region Redis.
* Single-process caveat: `monitor_connections` is per process; heartbeat state is in Redis so multiple workers are safe.


## Windows Docker quick start

From the directory containing `docker-compose.yml`:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\setup.ps1
```

Or, if `.env` already exists:

```powershell
docker compose config
docker compose up -d --build
docker compose ps
```

Open:
- http://localhost:8000/
- http://localhost:8000/docs
- http://localhost:8000/dashboard

Start the demo crawler:

```powershell
docker compose --profile demo up -d --build
```

Check logs:

```powershell
docker compose logs -f api
docker compose logs -f crawler
```

Stop everything:

```powershell
docker compose down
```

If you want a completely fresh PostgreSQL database:

```powershell
docker compose down -v
docker compose up -d --build
```

The included `.env` is generated for local development and is ignored by Git. Do not commit it or reuse its credentials in production.
