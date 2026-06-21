"""SMHI Baltic cyanobacteria: API client + coastal-only sensor."""

import asyncio

from conftest import FakeCoordinator, FakeSession, load_fixture, load_text
from hav_badvatten import sensor as S
from hav_badvatten.api import BadvattenApi
from hav_badvatten.const import ALGAE_ATTRIBUTION, WATER_TYPE_SEA_ID


def _algae_session():
    return FakeSession(
        [
            ("day/latest.json", load_fixture("algae_day.json")),
            ("Baltic_algae_COMP7_eng.txt", load_text("algae_eng.txt")),
            ("Baltic_algae_COMP7_swe.txt", load_text("algae_swe.txt")),
        ]
    )


def test_fetch_algae_extracts_date_summaries_and_image():
    api = BadvattenApi(_algae_session())
    out = asyncio.run(api.fetch_algae())
    assert out["date"] == "2026-06-20"
    assert out["map_url"].endswith("Baltic_algae_COMP7_20260620.png")
    assert "cyanobacteria" in out["summary_en"].lower()
    assert "cyanobakterier" in out["summary_sv"].lower()


def test_algae_sensor_reads_compilation():
    algae = asyncio.run(BadvattenApi(_algae_session()).fetch_algae())
    coord = FakeCoordinator("SE0441264000000306", load_fixture("bath_coastal.json"))
    coord.data["algae"] = algae

    sensor = S.BadvattenSensor(coord, "entry", S.ALGAE_SENSOR)
    assert sensor.native_value == "2026-06-20"
    attrs = sensor.extra_state_attributes
    assert attrs["map_url"].endswith(".png")
    assert attrs["summary_en"]
    assert attrs["updated"].startswith("2026-")
    assert sensor._attr_attribution == ALGAE_ATTRIBUTION


def test_algae_sensor_unknown_when_inland(inland):
    # inland coordinator has algae=None; the sensor (if created) is unknown
    sensor = S.BadvattenSensor(inland, "entry", S.ALGAE_SENSOR)
    assert sensor.native_value is None


def test_water_type_constant():
    # Mossbylund (coastal) is waterTypeId 1; the gate that adds the sensor.
    coastal = load_fixture("bath_coastal.json")
    assert coastal["bathingWater"]["waterTypeId"] == WATER_TYPE_SEA_ID
    inland = load_fixture("bath_inland.json")
    assert inland["bathingWater"]["waterTypeId"] != WATER_TYPE_SEA_ID
