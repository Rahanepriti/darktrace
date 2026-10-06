from datetime import datetime, timedelta, timezone

from health_service.replay import is_replayed


def test_recent_timestamp_is_not_replayed():
    now = datetime.now(timezone.utc)
    assert is_replayed(now - timedelta(seconds=10), now, max_age_seconds=300) is False


def test_old_timestamp_is_replayed():
    now = datetime.now(timezone.utc)
    assert is_replayed(now - timedelta(minutes=10), now, max_age_seconds=300) is True


def test_future_timestamp_beyond_window_is_replayed():
    now = datetime.now(timezone.utc)
    assert is_replayed(now + timedelta(minutes=10), now, max_age_seconds=300) is True


def test_timestamp_exactly_at_boundary_is_not_replayed():
    now = datetime.now(timezone.utc)
    assert is_replayed(now - timedelta(seconds=300), now, max_age_seconds=300) is False
