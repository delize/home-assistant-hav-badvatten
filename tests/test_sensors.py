"""Every sensor value_fn / attribute against real fixtures."""

from datetime import datetime

from hav_badvatten import sensor as S
from hav_badvatten.const import ATTRIBUTION, WEATHER_ATTRIBUTION


def _by_key(coord):
    return {d.key: S.BadvattenSensor(coord, "entry", d) for d in S.SENSORS}


def test_sensor_set_is_complete():
    keys = {d.key for d in S.SENSORS}
    assert keys == {
        "bathing_status",
        "advisory_since",
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


def test_bathing_status_advisory_overrides(inland):
    status = _by_key(inland)["bathing_status"]
    assert status.native_value == "advisory"  # live advisory beats the sample
    assert status.extra_state_attributes["based_on"] == "advisory"
    assert status.extra_state_attributes["advisory"]  # description present


def test_bathing_status_from_latest_sample(coastal):
    status = _by_key(coastal)["bathing_status"]
    assert status.native_value == "suitable"
    assert status.extra_state_attributes["based_on"] == "latest_sample"


def test_bathing_status_stale_sample_guard():
    # Norraryd: no advisory, but the only sample is from last August (~313 days).
    # The verdict must not read as a confident "OK to bathe".
    from conftest import FakeCoordinator, load_fixture

    coord = FakeCoordinator("SE0920763000001135", load_fixture("bath_stale.json"))
    status = _by_key(coord)["bathing_status"]
    assert status.native_value == "no_recent_sample"
    attrs = status.extra_state_attributes
    assert attrs["based_on"] == "no_recent_sample"
    assert attrs["sample_age_days"] > 45


def test_bathing_status_cadence_is_adaptive(coastal):
    # Threshold follows the bath's own sampling rhythm, not a fixed day count.
    attrs = _by_key(coastal)["bathing_status"].extra_state_attributes
    assert isinstance(attrs["sample_interval_days"], int)
    assert attrs["sample_interval_days"] > 0
    # coastal sample is recent (well within ~2 intervals) -> not stale
    assert attrs["based_on"] == "latest_sample"


def test_advisory_since_active(inland):
    from datetime import datetime

    sensor = _by_key(inland)["advisory_since"]
    # Sjöviken's advisory starts 2026-06-15T13:28:51Z
    assert isinstance(sensor.native_value, datetime)
    assert sensor.native_value.isoformat().startswith("2026-06-15")
    attrs = sensor.extra_state_attributes
    assert attrs["active"] is True
    assert attrs["type"] == "Algblomning"


def test_advisory_since_empty_is_unambiguous(coastal):
    # No advisory (like Tanto) -> value is None (HA "Unknown"), and the
    # `active` attribute makes the empty state explicit.
    sensor = _by_key(coastal)["advisory_since"]
    assert sensor.native_value is None
    assert sensor.extra_state_attributes["active"] is False
    assert sensor.extra_state_attributes["advisories"] == []


def test_lab_sensors_are_diagnostic():
    cats = {d.key: d.entity_category for d in S.SENSORS}
    for key in ("e_coli", "intestinal_enterococci", "sample_assessment", "last_sample"):
        assert cats[key] == "diagnostic", key
    # the verdict + advisory date stay primary (no category)
    assert cats["bathing_status"] is None
    assert cats["advisory_since"] is None


def test_sample_includes_algae_observation(inland):
    # HaV's "Algae occurrence" column — was missing before.
    attrs = _by_key(inland)["sample_assessment"].extra_state_attributes
    assert attrs["algae_observation"]  # e.g. "Ingen uppgift" / "Ingen blomning"
    assert "algae" in attrs["history"][0]


def test_classification_includes_bath_info(inland):
    attrs = _by_key(inland)["classification"].extra_state_attributes
    assert attrs["summary"]  # profile summary text
    assert attrs["municipality_contact"]  # {email, phone, url}
    assert attrs["supervisory_authority"]  # responsible authority contact


def test_bacteria_history_exposes_trend(inland):
    s = _by_key(inland)
    ecoli_hist = s["e_coli"].extra_state_attributes["history"]
    assert ecoli_hist[0]["value"] == 46  # newest sample first
    assert ecoli_hist[0]["assessment"]  # carries the per-sample verdict
    assert s["sample_assessment"].extra_state_attributes["e_coli"] == 46


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
