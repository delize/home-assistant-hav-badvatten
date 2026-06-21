"""API parsing against fixtures, using a fake aiohttp session."""

import asyncio

from conftest import FakeSession, load_fixture
from hav_badvatten.api import BadvattenApi


def _run(coro):
    return asyncio.run(coro)


def test_list_baths_parses_flat_records():
    api = BadvattenApi(FakeSession([("/bathing-waters", load_fixture("list.json"))]))
    baths = _run(api.list_baths())
    by_id = {b["id"]: b for b in baths}

    assert "SE0110180000007461" in by_id
    sjovik = by_id["SE0110180000007461"]
    assert sjovik["name"] == "Sjövikskajens bryggbad"
    assert sjovik["kommun"] == "Stockholm"
    assert isinstance(sjovik["lat"], float) and isinstance(sjovik["lon"], float)
    assert sjovik["water_type"]  # waterTypeIdText present


def test_list_baths_skips_records_without_id():
    payload = {"watersAndAdvisories": [{"bathingWater": {"name": "no id"}}]}
    api = BadvattenApi(FakeSession([("/bathing-waters", payload)]))
    assert _run(api.list_baths()) == []


def test_fetch_returns_bath_id_and_combined_object():
    api = BadvattenApi(
        FakeSession(
            [("/bathing-waters/SE0110180000007461", load_fixture("bath_inland.json"))]
        )
    )
    out = _run(api.fetch("SE0110180000007461"))
    assert out["bath_id"] == "SE0110180000007461"
    assert out["bath"]["bathingWater"]["name"] == "Sjövikskajens bryggbad"


def test_fetch_weather_open_meteo_normalized():
    from hav_badvatten.const import PROVIDER_OPEN_METEO

    api = BadvattenApi(FakeSession([("open-meteo", load_fixture("weather.json"))]))
    w = _run(api.fetch_weather(59.3073, 18.0334, PROVIDER_OPEN_METEO))
    assert w["provider"] == "open_meteo"
    assert w["temperature"] == 22.3
    assert w["wind_speed"] == 3.5
    assert w["wind_direction"] == 280


def test_fetch_weather_smhi_normalized():
    from hav_badvatten.const import PROVIDER_SMHI

    api = BadvattenApi(FakeSession([("smhi.se", load_fixture("weather_smhi.json"))]))
    w = _run(api.fetch_weather(55.413289, 13.625274, PROVIDER_SMHI))
    assert w["provider"] == "smhi"
    # both providers map onto the same keys, in m/s
    assert w["temperature"] == 24.0
    assert w["wind_speed"] == 3.4
    assert w["wind_gust"] == 7.2
    assert w["apparent_temperature"] is None  # SMHI has no feels-like
