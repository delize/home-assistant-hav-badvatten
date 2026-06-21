"""Fetch resilience: classify errors, ride out transient failures, then clear.

The coordinator keeps serving the last good payload through transient HaV
failures and only marks everything unavailable after FAILURE_CLEAR_THRESHOLD
consecutive failures. The state machine lives in FetchHealth (pure stdlib), so
it's tested directly without spinning up Home Assistant.
"""

from __future__ import annotations

from datetime import UTC, datetime

from hav_badvatten import FetchHealth, classify_error

NOW = datetime(2026, 6, 21, 18, 0, tzinfo=UTC)


def _err(status: int | None = None, name: str = "Exception") -> Exception:
    """Build an exception that mimics the shapes the API can raise."""
    err = type(name, (Exception,), {})("boom")
    if status is not None:
        err.status = status  # aiohttp.ClientResponseError carries .status
    return err


def test_classify_http_codes_keep_the_status():
    assert classify_error(_err(status=500, name="ClientResponseError")) == "http_500"
    assert classify_error(_err(status=404, name="ClientResponseError")) == "http_404"


def test_classify_timeout_and_connection_and_other():
    assert classify_error(TimeoutError()) == "timeout"
    assert classify_error(_err(name="ServerTimeoutError")) == "timeout"
    assert classify_error(_err(name="ClientConnectorError")) == "unreachable"
    assert classify_error(_err(name="ValueError")) == "error"


def test_serves_cached_until_threshold_then_clears():
    health = FetchHealth(clear_threshold=4)
    good = {"bath_id": "SE0110180000007461", "bath": {"v": 1}}

    health.record_attempt(NOW)
    assert health.record_success(good) is good
    assert health.status == "ok"
    assert health.last_success == NOW
    assert health.consecutive_failures == 0
    assert health.serving_cached is False

    # Failures 1..3 keep serving the cached payload.
    for expected in (1, 2, 3):
        health.record_attempt(NOW)
        assert health.record_failure(_err(status=500)) is good
        assert health.serving_cached is True
        assert health.consecutive_failures == expected
        assert health.status == "http_500"
        assert health.last_success == NOW  # freshness frozen at last good fetch

    # The 4th consecutive failure clears (returns None -> coordinator UpdateFailed).
    health.record_attempt(NOW)
    assert health.record_failure(_err(status=404)) is None
    assert health.serving_cached is False
    assert health.consecutive_failures == 4
    assert health.status == "http_404"


def test_recovery_resets_the_streak():
    health = FetchHealth(clear_threshold=4)
    first = {"v": 1}
    health.record_attempt(NOW)
    health.record_success(first)
    health.record_attempt(NOW)
    health.record_failure(_err(status=500))
    assert health.consecutive_failures == 1

    second = {"v": 2}
    health.record_attempt(NOW)
    assert health.record_success(second) is second
    assert health.consecutive_failures == 0
    assert health.status == "ok"
    assert health.serving_cached is False


def test_first_ever_failure_has_nothing_to_serve():
    health = FetchHealth(clear_threshold=4)
    health.record_attempt(NOW)
    assert health.record_failure(_err(status=500)) is None  # no cache yet
    assert health.serving_cached is False
    assert health.consecutive_failures == 1


def test_health_sensor_value_and_attr_fns_read_the_coordinator():
    from hav_badvatten.sensor import HEALTH_SENSORS

    class _Coord:
        pass

    coord = _Coord()
    coord.health = FetchHealth(clear_threshold=4)
    coord.health.record_attempt(NOW)
    coord.health.record_success({"v": 1})

    by_key = {d.key: d for d in HEALTH_SENSORS}
    assert by_key["last_fetch_status"].value_fn(coord) == "ok"
    assert by_key["last_fetch_time"].value_fn(coord) == NOW

    attrs = by_key["last_fetch_status"].attr_fn(coord)
    assert attrs["serving_cached"] is False
    assert attrs["consecutive_failures"] == 0
    assert attrs["clear_threshold"] == 4
    assert attrs["last_success"] == NOW.isoformat()
    assert attrs["detail"] is None
