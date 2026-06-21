"""Every sensor value_fn / attribute against real fixtures."""

from datetime import datetime

from hav_badvatten import sensor as S
from hav_badvatten.const import ATTRIBUTION, WEATHER_ATTRIBUTION


def _by_key(coord):
    return {d.key: S.BadvattenSensor(coord, "entry", d) for d in S.SENSORS}


def test_sensor_set_is_complete():
    keys = {d.key for d in S.SENSORS}
    assert keys == {
        "classification",
        "sample_assessment",
        "water_temp_measured",
        "water_temp_forecast",
        "air_temperature",
        "wind_speed",
        "e_coli",
        "intestinal_enterococci",
        "last_sample",
        "bathing_season",
    }


def test_inland_values(inland):
    s = _by_key(inland)
    classification = s["classification"]
    assert classification.native_value == "not_classified"
    assert classification.extra_state_attributes["year"] == 2025
    assert classification.extra_state_attributes["rating_text"] == "Ej klassificerad"
    assert len(classification.extra_state_attributes["history"]) == 4

    assessment = s["sample_assessment"]
    assert assessment.native_value == "suitable"
    assert assessment.extra_state_attributes["suitable"] is True
    assert assessment.extra_state_attributes["assessment_text"] == "Tjänligt"

    assert s["water_temp_measured"].native_value == 19.0
    # inland lakes have no Copernicus forecast
    assert s["water_temp_forecast"].native_value is None

    assert s["e_coli"].native_value == 46
    assert s["intestinal_enterococci"].native_value == 10
    assert isinstance(s["last_sample"].native_value, datetime)
    assert s["bathing_season"].native_value == "open"


def test_inland_weather_from_open_meteo(inland):
    s = _by_key(inland)
    assert s["air_temperature"].native_value == 22.3
    assert s["wind_speed"].native_value == 3.5
    assert s["wind_speed"].extra_state_attributes["direction"] == 280


def test_coastal_forecast_picks_nearest_hour(coastal):
    s = _by_key(coastal)
    # forecast hours 10/13/16, fixed now=14:00 -> 13:00 -> 12.8 °C
    forecast = s["water_temp_forecast"]
    assert forecast.native_value == 12.8
    assert forecast.extra_state_attributes["source"] == "hav-copernicus"
    assert forecast.attribution == ATTRIBUTION  # HaV, not Open-Meteo
    assert s["classification"].native_value == "excellent"


def test_inland_water_temp_falls_back_to_open_meteo():
    from conftest import FakeCoordinator, load_fixture

    coord = FakeCoordinator("SE0110180000007461", load_fixture("bath_inland.json"))
    coord.data["water_temp_fallback"] = 20.2  # Open-Meteo SST (no HaV forecast)
    forecast = _by_key(coord)["water_temp_forecast"]
    assert forecast.native_value == 20.2
    assert forecast.extra_state_attributes["source"] == "open-meteo"
    assert forecast.attribution == WEATHER_ATTRIBUTION  # credits Open-Meteo


def test_inland_water_temp_unknown_without_fallback(inland):
    forecast = _by_key(inland)["water_temp_forecast"]
    assert forecast.native_value is None
    assert forecast.extra_state_attributes["source"] is None


def test_weather_sensors_credit_open_meteo(inland):
    s = _by_key(inland)
    assert s["air_temperature"]._attr_attribution == WEATHER_ATTRIBUTION
    assert s["wind_speed"]._attr_attribution == WEATHER_ATTRIBUTION
    # HaV sensors keep the HaV attribution
    assert s["classification"]._attr_attribution == ATTRIBUTION


def test_empty_payload_is_all_unknown(empty):
    for desc in S.SENSORS:
        assert S.BadvattenSensor(empty, "e", desc).native_value is None


def test_missing_weather_is_unknown_not_error():
    from conftest import FakeCoordinator, load_fixture

    coord = FakeCoordinator(
        "SE0110180000007461", load_fixture("bath_inland.json"), weather=None
    )
    s = _by_key(coord)
    assert s["air_temperature"].native_value is None
    assert s["wind_speed"].native_value is None
    # HaV-sourced sensors still work without weather
    assert s["water_temp_measured"].native_value == 19.0


def test_device_info_named_from_bath(inland):
    ent = S.BadvattenSensor(inland, "entry", S.SENSORS[0])
    assert ent._attr_device_info["name"] == "Sjövikskajens bryggbad"
    assert ent._attr_device_info["model"] == "SE0110180000007461"
