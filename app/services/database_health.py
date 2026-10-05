import time

from sqlalchemy import text

from app.database import engine


def check_database_health():
    start_time = time.perf_counter()

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)

        return {
            "status": "healthy",
            "latency_ms": latency_ms,
        }

    except Exception:
        return {
            "status": "unhealthy",
            "latency_ms": None,
        }
