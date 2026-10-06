$ErrorActionPreference = "Stop"

Write-Host "Health Monitoring - Windows setup" -ForegroundColor Cyan

if (-not (Test-Path ".env")) {
    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        throw "Python is not installed or is not on PATH."
    }

    $lines = python scripts/gen_secrets.py
    if ($LASTEXITCODE -ne 0) {
        throw "Could not generate secrets."
    }

    @"
APP_ENV=development
LOG_LEVEL=INFO
DATABASE_URL=postgresql+asyncpg://health:CHANGE_ME@postgres:5432/health
REDIS_URL=redis://:CHANGE_ME@redis:6379/0
HEALTH_ENCRYPTION_KEY=CHANGE_ME
ACTIVE_KEY_VERSION=1
HEALTH_ENCRYPTION_KEYS_PREVIOUS=
HEALTH_ENCRYPTION_KEYS_FILE=
KEY_REFRESH_SECONDS=60
HEALTH_API_TOKEN=CHANGE_ME
CRAWLER_WS_TOKEN=CHANGE_ME
HEARTBEAT_INTERVAL_SECONDS=20
HEARTBEAT_TTL_SECONDS=40
HEARTBEAT_MAX_AGE_SECONDS=300
CRAWLER_UNHEALTHY_AFTER_SECONDS=300
DATABASE_TIMEOUT_SECONDS=1
REDIS_TIMEOUT_SECONDS=1
HEALTH_BUDGET_SECONDS=1.8
PUBLIC_HEALTH_ENDPOINT=false
MONITOR_ENABLED=true
MONITOR_PUSH_INTERVAL_SECONDS=3
HEALTH_WS_URL=ws://localhost:8000/api/v1/ws/health
WORKER_ID=cw-1
POSTGRES_USER=health
POSTGRES_DB=health
POSTGRES_PASSWORD=CHANGE_ME
REDIS_PASSWORD=CHANGE_ME
"@ | Set-Content .env -Encoding utf8

    foreach ($line in $lines) {
        if ($line -match "^([^=]+)=(.+)$") {
            $name = $Matches[1]
            $value = $Matches[2]
            (Get-Content .env) -replace "^$name=.*$", "$name=$value" | Set-Content .env -Encoding utf8
        }
    }
    Write-Host ".env created." -ForegroundColor Green
}

Write-Host "Validating Docker Compose..." -ForegroundColor Yellow
docker compose config | Out-Null
if ($LASTEXITCODE -ne 0) { throw "docker compose config failed." }

Write-Host "Starting API, PostgreSQL and Redis..." -ForegroundColor Yellow
docker compose up -d --build
if ($LASTEXITCODE -ne 0) { throw "docker compose up failed." }

Write-Host ""
Write-Host "Services:" -ForegroundColor Green
docker compose ps
Write-Host ""
Write-Host "API:      http://localhost:8000/"
Write-Host "Swagger:  http://localhost:8000/docs"
Write-Host "Dashboard:http://localhost:8000/dashboard"
Write-Host ""
Write-Host "For the demo crawler run:"
Write-Host "  docker compose --profile demo up -d --build"
