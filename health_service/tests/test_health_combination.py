from health_service.health import combine_overall_status
from health_service.schemas import CrawlerComponent, DatabaseComponent


def test_both_healthy_is_healthy():
    db = DatabaseComponent(status="healthy", latency_ms=5)
    crawler = CrawlerComponent(status="healthy", active_workers=2, queue_depth=10)
    assert combine_overall_status(db, crawler) == "healthy"


def test_database_unreachable_is_unhealthy_regardless_of_crawler():
    db = DatabaseComponent(status="unhealthy", latency_ms=None)
    crawler = CrawlerComponent(status="healthy", active_workers=2, queue_depth=10)
    assert combine_overall_status(db, crawler) == "unhealthy"


def test_crawler_unhealthy_is_unhealthy_regardless_of_database():
    db = DatabaseComponent(status="healthy", latency_ms=5)
    crawler = CrawlerComponent(status="unhealthy", active_workers=0, queue_depth=0)
    assert combine_overall_status(db, crawler) == "unhealthy"


def test_crawler_degraded_with_healthy_db_is_degraded():
    db = DatabaseComponent(status="healthy", latency_ms=5)
    crawler = CrawlerComponent(status="degraded", active_workers=1, queue_depth=10)
    assert combine_overall_status(db, crawler) == "degraded"
