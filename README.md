# DarkTrace Health Monitoring Service

## Overview

The DarkTrace Health Monitoring Service provides a health endpoint for monitoring the availability of the PostgreSQL database and crawler workers.

The service combines:

- PostgreSQL database health
- Crawler worker health
- Redis-based heartbeat tracking
- WebSocket-based crawler heartbeats
- AES-256-GCM encrypted heartbeat messages
- Replay protection
- Multi-worker health monitoring
- Automated health and security tests

### Architecture

Crawler workers act as WebSocket clients and establish outbound connections to the FastAPI service.

The FastAPI service:

1. Receives encrypted crawler heartbeats.
2. Decrypts and validates each heartbeat.
3. Stores the latest heartbeat for each worker in Redis.
4. Uses heartbeat freshness to determine crawler health.
5. Combines crawler health with PostgreSQL health.
6. Exposes the overall result through `GET /api/v1/health`.

### Health States

- **Healthy** — PostgreSQL is reachable and crawler heartbeats are fresh.
- **Degraded** — PostgreSQL is available but crawler heartbeats are missing, stale, or a worker reports a degraded state.
- **Unhealthy** — PostgreSQL is unavailable or the crawler service has no usable heartbeat.


## Project Structure

darktrace_health_monitor/
├── app/
│   ├── api/
│   │   ├── health.py
│   │   └── health_ws.py
│   ├── core/
│   │   └── config.py
│   ├── services/
│   │   ├── crawler_health.py
│   │   └── database_health.py
│   ├── database.py
│   └── main.py
│
├── crawler_client/
│   └── heartbeat.py
│
├── tests/
│   └── test_websocket.py
│
├── .env
├── .gitignore
├── requirements.txt
└── README.md
