from __future__ import annotations

from datetime import datetime, timedelta
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
from homeassistant.util import dt as dt_util

from .api import BadvattenApi
from .const import (
    CONF_BATH_ID,
    CONF_SCAN_INTERVAL_MINUTES,
    CONF_WEATHER_PROVIDER,
    DEFAULT_SCAN_MINUTES,
    DEFAULT_WEATHER_PROVIDER,
    DOMAIN,
    FAILURE_CLEAR_THRESHOLD,
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


def classify_error(err: Exception) -> str:
    """Short status string for the 'last fetch status' diagnostic.

    HTTP failures keep their code (``http_500`` / ``http_404``), since that's the
    most actionable signal; timeouts and connection failures get their own
    labels. aiohttp's ClientResponseError carries ``.status``.
    """
    status = getattr(err, "status", None)
    if isinstance(status, int):
        return f"http_{status}"
    name = type(err).__name__.lower()
    if isinstance(err, TimeoutError) or "timeout" in name:
        return "timeout"
    if "connect" in name:
        return "unreachable"
    return "error"


def _is_backend_data_error(err: Exception) -> bool:
    """True for an HTTP response that carried no data (status >= 400).

    Only these advance the give-up counter: the backend actively returned
    nothing usable (the 400/500 family). Timeouts and connection failures keep
    serving cached data but do not count, since they're as likely a transient or
    client-side network blip as a persistently broken backend.
    """
    status = getattr(err, "status", None)
    return isinstance(status, int) and status >= 400


class FetchHealth:
    """Outcome tracker that lets the coordinator ride out transient HaV failures.

    On failure it hands back the last good payload to keep serving, until
    ``clear_threshold`` consecutive failures, after which it returns ``None`` to
    signal "give up, mark unavailable". Pure/stdlib-only so it unit-tests without
    Home Assistant. The diagnostic sensors read this object directly (not the
    bath payload), so they keep reporting why the data went away.
    """

    def __init__(self, clear_threshold: int = FAILURE_CLEAR_THRESHOLD) -> None:
        self.clear_threshold = clear_threshold
        self.status = "pending"
        self.detail: str | None = None
        self.last_attempt: datetime | None = None
        self.last_success: datetime | None = None
        self.consecutive_failures = 0
        self.serving_cached = False
        self._last_good: dict[str, Any] | None = None

    def record_attempt(self, now: datetime) -> None:
        self.last_attempt = now

    def record_success(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.status = "ok"
        self.detail = None
        self.last_success = self.last_attempt
        self.consecutive_failures = 0
        self.serving_cached = False
        self._last_good = payload
        return payload

    def record_failure(self, err: Exception) -> dict[str, Any] | None:
        """Register a failed fetch.

        Returns the cached payload to serve, or ``None`` when the data should be
        cleared (threshold reached, or nothing has ever succeeded). Only HTTP
        no-data responses (4xx/5xx) advance the give-up counter; a timeout or
        connection blip still serves cached but leaves the counter untouched
        (and a success is what resets it).
        """
        self.status = classify_error(err)
        self.detail = str(err) or self.status
        if _is_backend_data_error(err):
            self.consecutive_failures += 1
        if (
            self.consecutive_failures < self.clear_threshold
            and self._last_good is not None
        ):
            self.serving_cached = True
            return self._last_good
        self.serving_cached = False
        return None


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    session = async_get_clientsession(hass)
    api = BadvattenApi(session)
    bath_id = entry.data[CONF_BATH_ID]
    scan_minutes = entry.options.get(CONF_SCAN_INTERVAL_MINUTES, DEFAULT_SCAN_MINUTES)
    weather_provider = entry.options.get(
        CONF_WEATHER_PROVIDER, DEFAULT_WEATHER_PROVIDER
    )
    health = FetchHealth()

    async def _fetch_all() -> dict[str, Any]:
        # The core HaV bath fetch is the only call that may fail the update; the
        # weather / water-temp / algae fetches below are best-effort.
        payload = await api.fetch(bath_id)

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

        # Water-temp forecast fallback: HaV (Copernicus) is sea-only, so inland
        # baths have an empty waterTemperature. Fill it from Open-Meteo's
        # sea-surface temperature (best-effort; approximate for remote lakes).
        water_temp_fallback: float | None = None
        has_hav_forecast = bool((payload.get("bath") or {}).get("waterTemperature"))
        if not has_hav_forecast and lat is not None and lon is not None:
            try:
                water_temp_fallback = await api.fetch_water_temp(lat, lon)
            except Exception as err:  # noqa: BLE001 - fallback is optional
                _LOGGER.debug("water-temp fallback failed for %s: %s", bath_id, err)
        payload["water_temp_fallback"] = water_temp_fallback

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

    async def _async_update() -> Any:
        health.record_attempt(dt_util.utcnow())
        try:
            payload = await _fetch_all()
        except Exception as err:  # classified, then cached-or-raised below
            cached = health.record_failure(err)
            if cached is not None:
                # Transient: keep showing the last good data rather than wiping
                # everything (incl. a live "Unsafe" advisory) over a blip.
                _LOGGER.warning(
                    "HaV fetch failed for %s (%s); serving cached data "
                    "(failure %d of %d before clearing)",
                    bath_id,
                    health.status,
                    health.consecutive_failures,
                    FAILURE_CLEAR_THRESHOLD,
                )
                return cached
            # Persistent: the backend is genuinely broken — go unavailable.
            _LOGGER.error(
                "HaV fetch failed for %s (%s); %d consecutive failures, "
                "clearing entities until it recovers",
                bath_id,
                health.status,
                health.consecutive_failures,
            )
            raise UpdateFailed(str(err)) from err
        return health.record_success(payload)

    coordinator: DataUpdateCoordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"{DOMAIN}_{entry.entry_id}",
        update_method=_async_update,
        update_interval=timedelta(minutes=scan_minutes),
    )
    # Exposed so the fetch-health diagnostic sensors can read it (and survive an
    # outage, when coordinator.data may be stale or last_update_success False).
    coordinator.health = health

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
