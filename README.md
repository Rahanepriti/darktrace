# CyArt DarkTrace Health Monitoring Service

A health monitoring service for the CyArt DarkTrace platform.

The service monitors:

- PostgreSQL database health
- Crawler health
- Crawler heartbeat freshness
- Active crawler workers
- Queue depth
- Encrypted crawler-to-API heartbeat communication

## Architecture

The crawler zone is egress-only.

The crawler acts as a WebSocket client and connects outbound to the API:

Crawler
    |
    | WebSocket + AES-256-GCM encrypted heartbeat
    v
FastAPI Health Service
    |
    +---- PostgreSQL health check
    |
    +---- Redis heartbeat cache
    |
    v
GET /api/v1/health

The API does not initiate a connection to the crawler.

## Features

- FastAPI health endpoint
- WebSocket heartbeat ingestion
- AES-256-GCM encryption
- Fresh random nonce for every encrypted message
- PostgreSQL connectivity check
- Redis-backed heartbeat cache
- Heartbeat TTL
- Stale heartbeat detection
- Crawler status monitoring
- WebSocket reconnection
- Invalid/tampered message rejection
- Replay/stale timestamp protection
- Automated tests

## API Endpoint

### GET /api/v1/health

Example:

```json
{
  "status": "healthy",
  "checked_at": "2026-10-01T09:00:00Z",
  "components": {
    "database": {
      "status": "healthy",
      "latency_ms": 12
    },
    "crawler": {
      "status": "healthy",
      "last_heartbeat": "2026-10-01T08:59:50Z",
      "active_workers": 8,
      "queue_depth": 14
    }
  }
}
