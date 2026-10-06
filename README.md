# Health Monitoring Service

`GET /api/v1/health` reports the combined health of the PostgreSQL database and
the crawler subsystem. Crawler status is never queried directly — the crawler
zone is egress-only (zero-trust network design), so the crawler connects
**outbound** to a WebSocket endpoint hosted by this API and reports its own
status over an AES-256-GCM encrypted channel. The API never initiates a
connection toward the crawler.

```
Crawler worker (egress-only) ──outbound WS──> API: /api/v1/ws/health
                                                      │
                                              decrypt, validate, replay-check
                                                      │
                                           Redis cache (TTL ≈ 2x interval)
                                                      │
                          GET /api/v1/health  <───────┘  (reads cache, never touches WS layer)
                                │
                        PostgreSQL ping (timeout-bounded, parallel)
```

## Project layout

```
health_service/
  config.py              all tunables, environment-driven
  schemas.py               HeartbeatPayload, DatabaseComponent, CrawlerComponent, HealthResponse
  crypto.py                 shared AES-256-GCM encrypt/decrypt, versioned-key envelope
  secrets.py                 key provisioning interface (Env provider for local dev, Vault-class stub for production)
  replay.py                   heartbeat replay-window check
  cache.py                     Redis-backed + in-memory heartbeat cache (same interface)
  db_check.py                  PostgreSQL ping with hard timeout
  crawler_health.py            per-worker staleness classification + fleet aggregation
  health.py                    combines database + crawler into one overall status
  api.py                        FastAPI: GET /api/v1/health, WS /api/v1/ws/health
  crawler_client/
    heartbeat_client.py          crawler-side WebSocket client (outbound-only)
  tests/                          pytest suite
run_crawler_client.py             local entrypoint for the crawler-side client
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate          # .venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env
```

## Key provisioning

Keys are **never** hardcoded, committed, or passed as a URL/query parameter.
`secrets.py` defines a `SecretProvider` interface with two implementations:

- **`EnvSecretProvider`** (used by default, suitable for local dev and until
  the real Vault-class integration is wired up): reads a base64-encoded
  32-byte key from `AES_KEY_<VERSION>` (e.g. `AES_KEY_V1`), and the active
  version from `ACTIVE_AES_KEY_VERSION`.
- **`VaultSecretProvider`**: a stub with the correct method signatures
  (`get_key(version)`, `get_active_version()`) that raises `NotImplementedError`
  — wire this to your organization's actual Vault-class client before
  production use. The rest of the system (crypto, API, crawler client) only
  depends on the `SecretProvider` protocol, so swapping the implementation
  requires no other code changes.

Generate a key for local testing:

```bash
python -c "import os, base64; print(base64.b64encode(os.urandom(32)).decode())"
```

Put the result in `.env` as `AES_KEY_V1`.

## Key rotation (target cadence: 30 days, per project convention)

1. Generate a new key, store it in the secrets store under a new version,
   e.g. `AES_KEY_V2`.
2. Update `ACTIVE_AES_KEY_VERSION` to `v2`. New crawler connections (and any
   crawler that reloads its config) start encrypting with `v2`.
3. Every encrypted envelope carries its own `key_version`, so the API can
   decrypt `v1` and `v2` messages simultaneously during the rollover window —
   `decrypt_message()` looks up whichever version the message says it used.
   **No crawler redeploy is required**: workers still running with the old
   key keep working until they next read config and pick up `v2`.
4. Once no `v1` traffic is observed for a safety window, retire `AES_KEY_V1`
   from the secrets store.

This is why keys are resolved **by version/reference**, never by a single
fixed value baked into the process.

## Running the API

```bash
uvicorn health_service.api:app --reload
```

- `GET /api/v1/health` — see Section 4 response shape below.
- `WS /api/v1/ws/health` — crawler workers connect here and send one
  AES-256-GCM-encrypted JSON envelope per heartbeat.

## Running the crawler-side client locally

```bash
export AES_KEY_V1=$(python -c "import os, base64; print(base64.b64encode(os.urandom(32)).decode())")
export ACTIVE_AES_KEY_VERSION=v1
export HEALTH_WEBSOCKET_URL=ws://localhost:8000/api/v1/ws/health
export HEALTH_CRAWLER_WORKER_ID=cw-local
python run_crawler_client.py
```

Make sure the API is started with the **same** `AES_KEY_V1` value, or the API
will reject every heartbeat with an authentication-tag failure (which is the
correct, expected behavior for a key mismatch — see "Encryption" below).

By default the client reports a static `healthy` status with `queue_depth: 0`.
Wire `status_provider` (passed into `run_heartbeat_client`) to a callable that
returns the crawler's real `{status, queue_depth, last_successful_fetch}` once
integrated into the actual crawler process.

## Encryption

- **Mode**: AES-256-GCM — authenticated encryption, so a tampered or
  corrupted message is rejected (`DecryptionError`) rather than silently
  decrypted into garbage.
- **Nonce**: a fresh random 12-byte nonce per message (`os.urandom`), never
  reused under the same key.
- **Envelope**: `{"key_version": "...", "nonce": "<base64>", "ciphertext": "<base64>"}`,
  sent as WebSocket text frames. `key_version` is also bound in as AEAD
  associated data, so an attacker cannot swap the declared version without
  invalidating the authentication tag.
- **Replay protection**: any heartbeat whose timestamp is more than 5 minutes
  away from "now" (past or future) is rejected (`replay.py`), consistent with
  the project's existing webhook replay-protection pattern.

## Staleness and status semantics

| Signal | Classification |
|---|---|
| Heartbeat age ≤ `HEALTH_HEARTBEAT_FRESHNESS_SECONDS` and self-reported `healthy` | worker: healthy |
| Heartbeat age > freshness window, but cache entry still present (within TTL) | worker: **degraded** (stale, not assumed crashed) |
| Self-reported `status: degraded` or `status: down` | worker: degraded |
| No cache entry for *any* worker at all | crawler component: **unhealthy** |
| At least one worker healthy, one or more degraded/stale | crawler component: degraded |
| All reporting workers healthy and fresh | crawler component: healthy |

Overall status (`health.py`):

```
database unreachable  OR  crawler unhealthy  → unhealthy
crawler degraded                              → degraded
otherwise                                      → healthy
```

`active_workers` counts workers not self-reporting `down`; `queue_depth` is
summed across all currently-reporting workers.

## Latency budget

`GET /api/v1/health` targets under 2 seconds even if a downstream check is
slow:

- The database check uses `asyncio.wait_for` with `HEALTH_DATABASE_CHECK_TIMEOUT_SECONDS`
  (default 1.5s) around both the connect and the query — a hang is treated as
  `unhealthy`, not an indefinite block.
- The database and crawler checks run concurrently via FastAPI's dependency
  injection (both dependencies are resolved in parallel by Starlette).
- The crawler check only reads from Redis (no WebSocket involvement), so it
  is fast by construction.

## Open question — public vs. authenticated detail (not yet decided)

The task spec flags this as something to confirm with the assigning lead
before the response schema is finalized: should `GET /health` be publicly
reachable with only a minimal `{status, checked_at}` string (useful for load
balancers), while the full per-component breakdown sits behind
authentication, to avoid exposing internal topology to an unauthenticated
caller?

This implementation does **not** silently pick one side. It implements
Section 4's full detailed response by default (`HEALTH_DETAILED_REQUIRES_AUTH=false`),
and a working authenticated-detail mode is already built and tested:

```
HEALTH_DETAILED_REQUIRES_AUTH=true
HEALTH_API_KEY=<a long random secret>
```

With the flag on, any caller still gets `HTTP 200` with `{"status": ..., "checked_at": ...}`
(so load balancers keep working unauthenticated), and only a caller supplying
a matching `X-API-Key` header gets the full `components` breakdown. Flip the
flag once the lead confirms which behavior is wanted — no code change
required either way.

## Security notes

- No encryption key appears in source control (`.env` is gitignored,
  `.env.example` has placeholders only), logs, or API responses at any point.
- A tampered or incorrectly-keyed WebSocket message is logged and dropped;
  the handler loop continues to the next message rather than raising out of
  the WebSocket route or crashing the process.
- The database check never blocks indefinitely — see "Latency budget" above.

## Run the test suite

```bash
pytest
```

37 tests cover: AES-256-GCM round-trip, fresh-nonce-per-message, tampered
ciphertext rejection, wrong-key rejection, unknown key version rejection,
malformed envelope rejection, multi-version key rotation support, the secrets
provider, replay-window edge cases, per-worker staleness classification and
fleet aggregation (including the "stale, not crashed" distinction), the
overall-status combinator, and the full `GET /api/v1/health` response shape
under healthy/degraded/unhealthy conditions and both auth modes, plus
WebSocket heartbeat ingestion — including that a tampered or malformed
message is dropped without the handler crashing and a subsequent valid
message still gets processed on the same connection.
