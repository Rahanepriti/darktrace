"""Quick verification for redis_cache.py -- requires a running Redis
(see .env REDIS_URL). Run with: python tests/test_redis_cache.py"""
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from redis_cache import set_crawler_status, get_crawler_status, get_all_crawler_statuses


def test_set_and_get():
    set_crawler_status("test-crawler-1", "ok", time.time())
    result = get_crawler_status("test-crawler-1")

    assert result is not None, "expected a status dict, got None"
    assert result["status"] == "ok"
    assert "received_at" in result
    print("[PASS] set_crawler_status -> get_crawler_status round trip works")


def test_unknown_crawler_returns_none():
    result = get_crawler_status("this-crawler-does-not-exist")
    assert result is None
    print("[PASS] unknown crawler_id returns None")


def test_get_all_includes_known_crawlers():
    set_crawler_status("test-crawler-2", "degraded", time.time())
    all_statuses = get_all_crawler_statuses()
    assert "test-crawler-1" in all_statuses
    assert "test-crawler-2" in all_statuses
    assert all_statuses["test-crawler-2"]["status"] == "degraded"
    print("[PASS] get_all_crawler_statuses includes all known crawlers")


if __name__ == "__main__":
    test_set_and_get()
    test_unknown_crawler_returns_none()
    test_get_all_includes_known_crawlers()
    print("\nAll redis_cache tests passed.")
