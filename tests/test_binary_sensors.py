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


def test_empty_payload_is_off(empty):
    for desc in B.BINARY_SENSORS:
        assert B.BadvattenBinarySensor(empty, "e", desc).is_on is False
