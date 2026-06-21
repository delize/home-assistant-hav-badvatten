from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfSpeed, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.util import dt as dt_util

from .const import (
    ALGAE_ATTRIBUTION,
    CONF_WEATHER_PROVIDER,
    DEFAULT_WEATHER_PROVIDER,
    DOMAIN,
    PROVIDER_SMHI,
    SMHI_WEATHER_ATTRIBUTION,
    WATER_TYPE_SEA_ID,
    WEATHER_ATTRIBUTION,
)
from .entity import BadvattenEntity

# Sensor keys whose attribution depends on the selected weather provider.
WEATHER_KEYS = ("air_temperature", "wind_speed")


def weather_attribution(provider: str) -> str:
    return (
        SMHI_WEATHER_ATTRIBUTION if provider == PROVIDER_SMHI else WEATHER_ATTRIBUTION
    )


# Bacterial counts are reported per 100 mL. HaV does not state CFU vs MPN, so
# keep a neutral unit; the prefix ("<"/"=") is exposed as an attribute.
COUNT_UNIT = "/100 mL"


# --- pure helpers over the combined v2 payload -------------------------------
def _latest_result(data: dict) -> dict:
    """Newest monitoring sample (results are usually newest-first; sort anyway)."""
    results = data.get("results") or []
    if not results:
        return {}
    return max(results, key=lambda r: r.get("takenAt") or "")


def _latest_classification(data: dict) -> dict:
    """Newest EU water-quality classification by year."""
    profile = data.get("profile") or {}
    items = profile.get("lastFourClassifications") or []
    if not items:
        return {}
    return max(items, key=lambda c: c.get("year") or 0)


def _to_float(value: Any) -> float | None:
    """Temperatures/counts arrive as strings; '-'/''/None mean unknown."""
    if value in (None, "", "-"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    if value in (None, "", "-"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    return dt_util.parse_datetime(str(value))


def _forecast_entry_now(data: dict) -> dict | None:
    """Water-temp forecast entry closest to the current local hour.

    ``waterTemperature`` is a same-day hourly series of {measHour, waterTemp};
    it is empty on inland (lake) baths, which have no Copernicus coverage.
    """
    forecast = data.get("waterTemperature") or []
    now_hour = dt_util.now().hour
    candidates = [(e, _to_int(e.get("measHour"))) for e in forecast]
    candidates = [(e, h) for e, h in candidates if h is not None]
    if not candidates:
        return None
    return min(candidates, key=lambda eh: abs(eh[1] - now_hour))[0]


def _weather(data: dict) -> dict:
    """The Open-Meteo ``current`` block (empty if weather is unavailable)."""
    return data.get("weather") or {}


def _algae(data: dict) -> dict:
    """The SMHI Baltic algae compilation (empty if unavailable)."""
    return data.get("algae") or {}


def _ms_to_iso(value: Any) -> str | None:
    """Algae 'updated' is a Unix timestamp in milliseconds."""
    if not value:
        return None
    try:
        return dt_util.utc_from_timestamp(int(value) / 1000).isoformat()
    except (TypeError, ValueError):
        return None


def _season_state(data: dict) -> str | None:
    profile = data.get("profile") or {}
    season = profile.get("bathingSeason") or {}
    start = _parse_dt(season.get("startsAt"))
    end = _parse_dt(season.get("endsAt"))
    if start is None or end is None:
        return None
    return "open" if start <= dt_util.utcnow() <= end else "closed"


@dataclass(frozen=True, kw_only=True)
class BadvattenSensorDescription(SensorEntityDescription):
    """Sensor description plus a value/attribute extractor over the v2 payload."""

    value_fn: Callable[[dict], StateType | datetime]
    attr_fn: Callable[[dict], dict[str, Any]] | None = None
    # Override the device attribution (weather sensors credit Open-Meteo).
    attribution: str | None = None


# API numeric ids -> stable enum keys so Home Assistant can translate the state
# into the user's language (the raw *IdText is Swedish). The EU bathing-water
# classes are 1=Excellent..4=Poor, 0=Not classified; sample assessment is
# 1=Tjänligt, 2=Tjänligt med anm., 3=Otjänligt. The Swedish text is kept as an
# attribute. Unmapped ids fall through to None (state "unknown").
CLASSIFICATION_BY_ID = {
    0: "not_classified",
    1: "excellent",
    2: "good",
    3: "sufficient",
    4: "poor",
}
CLASSIFICATION_OPTIONS = list(CLASSIFICATION_BY_ID.values())

SAMPLE_ASSESS_BY_ID = {1: "suitable", 2: "suitable_with_remarks", 3: "unsuitable"}
SAMPLE_ASSESS_OPTIONS = list(SAMPLE_ASSESS_BY_ID.values())


SENSORS: tuple[BadvattenSensorDescription, ...] = (
    BadvattenSensorDescription(
        key="classification",
        device_class=SensorDeviceClass.ENUM,
        options=CLASSIFICATION_OPTIONS,
        icon="mdi:water-check",
        value_fn=lambda d: CLASSIFICATION_BY_ID.get(
            _latest_classification(d).get("qualityClassId")
        ),
        attr_fn=lambda d: {
            "year": _latest_classification(d).get("year"),
            "quality_class_id": _latest_classification(d).get("qualityClassId"),
            "rating_text": _latest_classification(d).get("qualityClassIdText"),
            "history": [
                {
                    "year": c.get("year"),
                    "rating": c.get("qualityClassId"),
                    "text": c.get("qualityClassIdText"),
                }
                for c in sorted(
                    (d.get("profile") or {}).get("lastFourClassifications") or [],
                    key=lambda c: c.get("year") or 0,
                    reverse=True,
                )
            ],
        },
    ),
    BadvattenSensorDescription(
        key="sample_assessment",
        device_class=SensorDeviceClass.ENUM,
        options=SAMPLE_ASSESS_OPTIONS,
        icon="mdi:swim",
        value_fn=lambda d: SAMPLE_ASSESS_BY_ID.get(
            _latest_result(d).get("sampleAssessId")
        ),
        attr_fn=lambda d: {
            "assessment_id": _latest_result(d).get("sampleAssessId"),
            "assessment_text": _latest_result(d).get("sampleAssessIdText"),
            "suitable": (
                None
                if _latest_result(d).get("sampleAssessId") is None
                else _latest_result(d).get("sampleAssessId") in (1, 2)
            ),
            "sampled_at": _latest_result(d).get("takenAt"),
            "weather": _latest_result(d).get("weatherIdText"),
            "complete": _latest_result(d).get("sampleComplete"),
        },
    ),
    BadvattenSensorDescription(
        key="water_temp_measured",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _to_float(_latest_result(d).get("waterTemp")),
        attr_fn=lambda d: {"sampled_at": _latest_result(d).get("takenAt")},
    ),
    BadvattenSensorDescription(
        key="water_temp_forecast",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _to_float((_forecast_entry_now(d) or {}).get("waterTemp")),
        attr_fn=lambda d: {
            "hour": (_forecast_entry_now(d) or {}).get("measHour"),
            "forecast": [
                {"hour": e.get("measHour"), "water_temp": _to_float(e.get("waterTemp"))}
                for e in (d.get("waterTemperature") or [])
            ],
        },
    ),
    BadvattenSensorDescription(
        key="air_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        attribution=WEATHER_ATTRIBUTION,
        value_fn=lambda d: _to_float(_weather(d).get("temperature")),
        attr_fn=lambda d: {
            "apparent_temperature": _to_float(_weather(d).get("apparent_temperature")),
            "relative_humidity": _to_int(_weather(d).get("humidity")),
            "weather_symbol": _weather(d).get("weather_symbol"),
            "observed_at": _weather(d).get("observed_at"),
            "provider": _weather(d).get("provider"),
        },
    ),
    BadvattenSensorDescription(
        key="wind_speed",
        device_class=SensorDeviceClass.WIND_SPEED,
        native_unit_of_measurement=UnitOfSpeed.METERS_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        attribution=WEATHER_ATTRIBUTION,
        value_fn=lambda d: _to_float(_weather(d).get("wind_speed")),
        attr_fn=lambda d: {
            "direction": _to_int(_weather(d).get("wind_direction")),
            "gusts": _to_float(_weather(d).get("wind_gust")),
            "observed_at": _weather(d).get("observed_at"),
            "provider": _weather(d).get("provider"),
        },
    ),
    BadvattenSensorDescription(
        key="e_coli",
        icon="mdi:bacteria",
        native_unit_of_measurement=COUNT_UNIT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _to_int(_latest_result(d).get("escherichiaColiCount")),
        attr_fn=lambda d: {
            "prefix": _latest_result(d).get("escherichiaColiPrefix"),
            "assessment": _latest_result(d).get("escherichiaColiAssessIdText"),
            "assessment_id": _latest_result(d).get("escherichiaColiAssessId"),
            "sampled_at": _latest_result(d).get("takenAt"),
        },
    ),
    BadvattenSensorDescription(
        key="intestinal_enterococci",
        icon="mdi:bacteria",
        native_unit_of_measurement=COUNT_UNIT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _to_int(_latest_result(d).get("intestinalEnterococciCount")),
        attr_fn=lambda d: {
            "prefix": _latest_result(d).get("intestinalEnterococciPrefix"),
            "assessment": _latest_result(d).get("intestinalEnterococciAssessIdText"),
            "assessment_id": _latest_result(d).get("intestinalEnterococciAssessId"),
            "sampled_at": _latest_result(d).get("takenAt"),
        },
    ),
    BadvattenSensorDescription(
        key="last_sample",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: _parse_dt(_latest_result(d).get("takenAt")),
    ),
    BadvattenSensorDescription(
        key="bathing_season",
        device_class=SensorDeviceClass.ENUM,
        options=["open", "closed"],
        icon="mdi:calendar-range",
        value_fn=_season_state,
        attr_fn=lambda d: {
            "starts_at": ((d.get("profile") or {}).get("bathingSeason") or {}).get(
                "startsAt"
            ),
            "ends_at": ((d.get("profile") or {}).get("bathingSeason") or {}).get(
                "endsAt"
            ),
        },
    ),
)


# Regional SMHI Baltic cyanobacteria compilation — only added for coastal baths
# (a Baltic bloom map is meaningless for an inland lake). Diagnostic; state is
# the map date, with the bilingual summaries and image URL as attributes.
ALGAE_SENSOR = BadvattenSensorDescription(
    key="baltic_cyanobacteria",
    icon="mdi:flower-pollen",
    entity_category=EntityCategory.DIAGNOSTIC,
    attribution=ALGAE_ATTRIBUTION,
    value_fn=lambda d: _algae(d).get("date"),
    attr_fn=lambda d: {
        "summary_en": _algae(d).get("summary_en"),
        "summary_sv": _algae(d).get("summary_sv"),
        "map_url": _algae(d).get("map_url"),
        "updated": _ms_to_iso(_algae(d).get("updated")),
    },
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    provider = entry.options.get(CONF_WEATHER_PROVIDER, DEFAULT_WEATHER_PROVIDER)
    attribution = weather_attribution(provider)

    entities = [
        BadvattenSensor(
            coordinator,
            entry.entry_id,
            replace(description, attribution=attribution)
            if description.key in WEATHER_KEYS
            else description,
        )
        for description in SENSORS
    ]
    water_type = (
        ((coordinator.data or {}).get("bath") or {})
        .get("bathingWater", {})
        .get("waterTypeId")
    )
    if water_type == WATER_TYPE_SEA_ID:
        entities.append(BadvattenSensor(coordinator, entry.entry_id, ALGAE_SENSOR))
    async_add_entities(entities)


class BadvattenSensor(BadvattenEntity, SensorEntity):
    """A single declarative HaV badvatten sensor."""

    entity_description: BadvattenSensorDescription

    def __init__(
        self,
        coordinator,
        entry_id: str,
        description: BadvattenSensorDescription,
    ) -> None:
        super().__init__(coordinator, entry_id, description.key)
        self.entity_description = description
        if description.attribution is not None:
            self._attr_attribution = description.attribution

    @property
    def native_value(self) -> StateType | datetime:
        return self.entity_description.value_fn(self._data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attr_fn is None:
            return None
        return self.entity_description.attr_fn(self._data)
