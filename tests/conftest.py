"""Test bootstrap for the hav_badvatten component.

Home Assistant is a heavy dependency, so these smoke tests stub just enough of
the `homeassistant.*` and `aiohttp` namespaces for the component modules to
import and run. The component's own logic (API parsing, every sensor value_fn,
binary-sensor state) is exercised against fixtures captured from the live HaV
v2 and Open-Meteo APIs. For full end-to-end coverage inside Home Assistant, run
hassfest and a manual load (see README); this suite is the fast regression net.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
import types

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
# Fixed "now": season fixtures are open, and the coastal forecast hour resolves
# to 13:00 (closest to 14:00) deterministically.
FAKE_NOW = datetime(2026, 6, 21, 14, 0, tzinfo=UTC)


# --------------------------------------------------------------------------- #
# Stub the homeassistant/aiohttp imports the component needs, before importing.
# --------------------------------------------------------------------------- #
def _mod(name: str, pkg: bool = False) -> types.ModuleType:
    m = types.ModuleType(name)
    if pkg:
        m.__path__ = []  # mark as package so submodule imports resolve
    sys.modules[name] = m
    return m


def _install_stubs() -> None:
    if "homeassistant" in sys.modules:
        return

    ha = _mod("homeassistant", pkg=True)
    helpers = _mod("homeassistant.helpers", pkg=True)
    ha.helpers = helpers
    components = _mod("homeassistant.components", pkg=True)
    ha.components = components
    util = _mod("homeassistant.util", pkg=True)
    ha.util = util

    dt = _mod("homeassistant.util.dt")

    def parse_datetime(s):
        if not s:
            return None
        try:
            return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        except ValueError:
            return None

    dt.parse_datetime = parse_datetime
    dt.now = lambda: FAKE_NOW
    dt.utcnow = lambda: FAKE_NOW
    dt.utc_from_timestamp = lambda ts: datetime.fromtimestamp(ts, tz=UTC)
    util.dt = dt

    const = _mod("homeassistant.const")

    class UnitOfTemperature:
        CELSIUS = "°C"

    class UnitOfSpeed:
        METERS_PER_SECOND = "m/s"

    class EntityCategory:
        DIAGNOSTIC = "diagnostic"

    class Platform:
        SENSOR = "sensor"
        BINARY_SENSOR = "binary_sensor"

    const.UnitOfTemperature = UnitOfTemperature
    const.UnitOfSpeed = UnitOfSpeed
    const.EntityCategory = EntityCategory
    const.Platform = Platform
    const.CONF_NAME = "name"

    core = _mod("homeassistant.core")
    core.HomeAssistant = type("HomeAssistant", (), {})

    ce = _mod("homeassistant.config_entries")
    ce.ConfigEntry = type("ConfigEntry", (), {})

    he = _mod("homeassistant.helpers.entity")
    helpers.entity = he
    he.DeviceInfo = lambda **kw: kw

    uc = _mod("homeassistant.helpers.update_coordinator")
    helpers.update_coordinator = uc

    class CoordinatorEntity:
        def __init__(self, coordinator):
            self.coordinator = coordinator

        def __class_getitem__(cls, item):
            return cls

    class DataUpdateCoordinator:
        def __class_getitem__(cls, item):
            return cls

    uc.CoordinatorEntity = CoordinatorEntity
    uc.DataUpdateCoordinator = DataUpdateCoordinator
    uc.UpdateFailed = type("UpdateFailed", (Exception,), {})

    ac = _mod("homeassistant.helpers.aiohttp_client")
    helpers.aiohttp_client = ac
    ac.async_get_clientsession = lambda hass: None

    ep = _mod("homeassistant.helpers.entity_platform")
    helpers.entity_platform = ep
    ep.AddEntitiesCallback = object
    typ = _mod("homeassistant.helpers.typing")
    helpers.typing = typ
    typ.StateType = object

    smod = _mod("homeassistant.components.sensor")
    components.sensor = smod

    class SensorDeviceClass:
        TEMPERATURE = "temperature"
        TIMESTAMP = "timestamp"
        ENUM = "enum"
        WIND_SPEED = "wind_speed"

    class SensorStateClass:
        MEASUREMENT = "measurement"

    @dataclass(frozen=True, kw_only=True)
    class SensorEntityDescription:
        key: str
        name: object = None
        icon: object = None
        device_class: object = None
        native_unit_of_measurement: object = None
        state_class: object = None
        options: object = None
        entity_category: object = None
        translation_key: object = None

    smod.SensorDeviceClass = SensorDeviceClass
    smod.SensorStateClass = SensorStateClass
    smod.SensorEntity = type("SensorEntity", (), {})
    smod.SensorEntityDescription = SensorEntityDescription

    bmod = _mod("homeassistant.components.binary_sensor")
    components.binary_sensor = bmod

    class BinarySensorDeviceClass:
        SAFETY = "safety"
        PROBLEM = "problem"

    @dataclass(frozen=True, kw_only=True)
    class BinarySensorEntityDescription:
        key: str
        name: object = None
        device_class: object = None
        entity_category: object = None
        translation_key: object = None

    bmod.BinarySensorDeviceClass = BinarySensorDeviceClass
    bmod.BinarySensorEntity = type("BinarySensorEntity", (), {})
    bmod.BinarySensorEntityDescription = BinarySensorEntityDescription

    aio = _mod("aiohttp")
    aio.ClientSession = type("ClientSession", (), {})
    aio.ClientTimeout = lambda *a, **k: None

    # Make `custom_components/hav_badvatten` importable as `hav_badvatten`.
    sys.path.insert(0, str(Path(__file__).parents[1] / "custom_components"))


_install_stubs()


# --------------------------------------------------------------------------- #
# Shared test helpers
# --------------------------------------------------------------------------- #
def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def load_text(name: str) -> str:
    return (FIXTURES / name).read_text()


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def raise_for_status(self):
        return None

    async def json(self, content_type=None):
        return self._payload

    async def text(self):
        return self._payload


class FakeSession:
    """Minimal aiohttp-session stand-in routing URLs to fixture payloads."""

    def __init__(self, routes: list[tuple[str, dict]]):
        self._routes = routes

    def get(self, url, headers=None, timeout=None):
        for substr, payload in self._routes:
            if substr in url:
                return _FakeResponse(payload)
        raise AssertionError(f"no fake route for {url}")


class FakeCoordinator:
    last_update_success = True

    def __init__(self, bath_id, bath, weather=None):
        self.data = {"bath_id": bath_id, "bath": bath, "weather": weather}


@pytest.fixture
def weather_current() -> dict:
    # Coordinator stores the provider-agnostic shape; normalize the raw fixture.
    from hav_badvatten.api import _normalize_open_meteo

    return _normalize_open_meteo(load_fixture("weather.json")["current"])


@pytest.fixture
def inland(weather_current) -> FakeCoordinator:
    return FakeCoordinator(
        "SE0110180000007461", load_fixture("bath_inland.json"), weather_current
    )


@pytest.fixture
def coastal(weather_current) -> FakeCoordinator:
    return FakeCoordinator(
        "SE0441264000000306", load_fixture("bath_coastal.json"), weather_current
    )


@pytest.fixture
def empty() -> FakeCoordinator:
    return FakeCoordinator("SE0000000000000000", {}, None)
