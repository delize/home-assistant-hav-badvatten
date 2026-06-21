"""Selectable weather provider: normalization parity + attribution wiring."""

from dataclasses import replace

from conftest import FakeCoordinator, load_fixture
from hav_badvatten import sensor as S
from hav_badvatten.api import _normalize_open_meteo, _normalize_smhi
from hav_badvatten.const import (
    DEFAULT_WEATHER_PROVIDER,
    PROVIDER_OPEN_METEO,
    PROVIDER_SMHI,
    SMHI_WEATHER_ATTRIBUTION,
    WEATHER_ATTRIBUTION,
)


def test_default_provider_is_smhi():
    assert DEFAULT_WEATHER_PROVIDER == PROVIDER_SMHI


def test_both_providers_yield_the_same_keys():
    om = _normalize_open_meteo(load_fixture("weather.json")["current"])
    smhi = _normalize_smhi(load_fixture("weather_smhi.json"))
    assert set(om) == set(smhi)
    for key in ("temperature", "wind_speed", "wind_direction", "provider"):
        assert key in om and key in smhi


def test_attribution_helper():
    assert S.weather_attribution(PROVIDER_SMHI) == SMHI_WEATHER_ATTRIBUTION
    assert S.weather_attribution(PROVIDER_OPEN_METEO) == WEATHER_ATTRIBUTION


def test_weather_sensor_attribution_follows_provider():
    smhi = _normalize_smhi(load_fixture("weather_smhi.json"))
    coord = FakeCoordinator(
        "SE0441264000000306", load_fixture("bath_coastal.json"), smhi
    )
    air = next(d for d in S.SENSORS if d.key == "air_temperature")

    # as the platform does: bake the chosen provider's attribution
    desc = replace(air, attribution=S.weather_attribution(PROVIDER_SMHI))
    sensor = S.BadvattenSensor(coord, "entry", desc)
    assert sensor._attr_attribution == SMHI_WEATHER_ATTRIBUTION
    assert sensor.native_value == 24.0  # SMHI air_temperature from the fixture
    assert sensor.extra_state_attributes["provider"] == "smhi"
