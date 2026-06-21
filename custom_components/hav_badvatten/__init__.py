from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import BadvattenApi
from .const import (
    CONF_BATH_ID,
    CONF_SCAN_INTERVAL_MINUTES,
    CONF_WEATHER_PROVIDER,
    DEFAULT_SCAN_MINUTES,
    DEFAULT_WEATHER_PROVIDER,
    DOMAIN,
    WATER_TYPE_SEA_ID,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]


def _coord(value: Any) -> float | None:
    """Sampling-point coordinates arrive as strings; tolerate missing values."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    session = async_get_clientsession(hass)
    api = BadvattenApi(session)
    bath_id = entry.data[CONF_BATH_ID]
    scan_minutes = entry.options.get(CONF_SCAN_INTERVAL_MINUTES, DEFAULT_SCAN_MINUTES)
    weather_provider = entry.options.get(
        CONF_WEATHER_PROVIDER, DEFAULT_WEATHER_PROVIDER
    )

    async def _async_update() -> Any:
        try:
            payload = await api.fetch(bath_id)
        except Exception as err:
            raise UpdateFailed(str(err)) from err

        bathing_water = (payload.get("bath") or {}).get("bathingWater") or {}

        # Air temperature / wind at the bath come from Open-Meteo (the HaV API
        # has no weather forecast). Best-effort: a weather failure must not make
        # the whole bath unavailable.
        weather: dict | None = None
        pos = bathing_water.get("samplingPointPosition") or {}
        lat = _coord(pos.get("latitude"))
        lon = _coord(pos.get("longitude"))
        if lat is not None and lon is not None:
            try:
                weather = await api.fetch_weather(lat, lon, weather_provider)
            except Exception as err:  # noqa: BLE001 - weather is optional
                _LOGGER.debug("weather fetch failed for %s: %s", bath_id, err)
        payload["weather"] = weather

        # SMHI Baltic cyanobacteria map (regional) — only relevant for coastal
        # baths. Best-effort, same as weather.
        algae: dict | None = None
        if bathing_water.get("waterTypeId") == WATER_TYPE_SEA_ID:
            try:
                algae = await api.fetch_algae()
            except Exception as err:  # noqa: BLE001 - algae map is optional
                _LOGGER.debug("algae fetch failed for %s: %s", bath_id, err)
        payload["algae"] = algae
        return payload

    coordinator: DataUpdateCoordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"{DOMAIN}_{entry.entry_id}",
        update_method=_async_update,
        update_interval=timedelta(minutes=scan_minutes),
    )

    # Reload on any options change so a new poll interval or weather provider
    # (which is read at setup and baked into entity attribution) takes effect.
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unload_ok
