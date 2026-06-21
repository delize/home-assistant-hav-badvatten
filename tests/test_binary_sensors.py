"""advice_against_bathing (live) and bloom_risk (static) state."""

from hav_badvatten import binary_sensor as B


def _by_key(coord):
    return {d.key: B.BadvattenBinarySensor(coord, "entry", d) for d in B.BINARY_SENSORS}


def test_inland_has_live_advisory(inland):
    b = _by_key(inland)
    advice = b["advice_against_bathing"]
    assert advice.is_on is True
    attrs = advice.extra_state_attributes
    assert attrs["count"] == 1
    assert attrs["advisories"][0]["type"] == "Algblomning"
    # static bloom-risk flags are both false for this site
    assert b["bloom_risk"].is_on is False


def test_coastal_no_advisory_but_bloom_prone(coastal):
    b = _by_key(coastal)
    assert b["advice_against_bathing"].is_on is False
    assert b["bloom_risk"].is_on is True
    assert b["bloom_risk"].extra_state_attributes["algae"] is True


def test_bloom_risk_is_diagnostic():
    desc = {d.key: d for d in B.BINARY_SENSORS}["bloom_risk"]
    assert desc.entity_category == "diagnostic"


def test_advisory_outdated_off_for_fresh_advisory(inland):
    b = _by_key(inland)
    # Sjöviken's advisory is ~6 days old (< 30) -> not flagged for review,
    # but the safety signal is unaffected.
    assert b["advisory_possibly_outdated"].is_on is False
    assert b["advice_against_bathing"].is_on is True


def _advisory_bath(season=True, sample_since=True, start="2026-05-01T00:00:00Z"):
    # FAKE_NOW is 2026-06-21
    current = {"startsAt": "2026-06-01T00:00:00Z", "endsAt": "2026-08-31T00:00:00Z"}
    past = {"startsAt": "2025-06-01T00:00:00Z", "endsAt": "2025-08-31T00:00:00Z"}
    return {
        "bathingWater": {},
        "profile": {"bathingSeason": current if season else past},
        "results": (
            [{"takenAt": "2026-06-10T00:00:00Z", "sampleAssessId": 1}]
            if sample_since
            else []
        ),
        "adviceAgainstBathing": [
            {"typeIdText": "Algblomning", "startsAt": start, "description": "x"}
        ],
    }


def test_advisory_outdated_on_in_season_with_samples():
    from conftest import FakeCoordinator

    b = _by_key(FakeCoordinator("x", _advisory_bath()))  # ~51d old, in season, sampled
    flag = b["advisory_possibly_outdated"]
    assert flag.is_on is True
    assert flag.extra_state_attributes["advisory_age_days"] >= 16
    # the safety verdict still says avoid
    assert b["advice_against_bathing"].is_on is True


def test_advisory_outdated_respects_16_day_threshold():
    from conftest import FakeCoordinator

    # advisory only 10 days old (< 16) -> not flagged
    b = _by_key(FakeCoordinator("x", _advisory_bath(start="2026-06-11T00:00:00Z")))
    assert b["advisory_possibly_outdated"].is_on is False


def test_advisory_outdated_off_out_of_season_or_no_samples():
    from conftest import FakeCoordinator

    off_season = _by_key(FakeCoordinator("x", _advisory_bath(season=False)))
    assert off_season["advisory_possibly_outdated"].is_on is False

    no_samples = _by_key(FakeCoordinator("x", _advisory_bath(sample_since=False)))
    assert no_samples["advisory_possibly_outdated"].is_on is False


def test_advisory_outdated_is_diagnostic():
    desc = {d.key: d for d in B.BINARY_SENSORS}["advisory_possibly_outdated"]
    assert desc.entity_category == "diagnostic"


def test_empty_payload_is_off(empty):
    for desc in B.BINARY_SENSORS:
        assert B.BadvattenBinarySensor(empty, "e", desc).is_on is False
