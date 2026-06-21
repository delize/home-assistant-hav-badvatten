from __future__ import annotations

import logging
import re
from typing import Any

from aiohttp import ClientSession, ClientTimeout

from .const import (
    ALGAE_LATEST_DAY_URL,
    BATH_URL,
    LIST_URL,
    OPEN_METEO_MARINE_URL,
    OPEN_METEO_URL,
    PROVIDER_SMHI,
    SMHI_FORECAST_URL,
    USER_AGENT,
)

_LOGGER = logging.getLogger(__name__)

_TIMEOUT = ClientTimeout(total=30)
# Bath ids look like SE0110180000007461 or SE0A21494000000947.
_ID_RE = re.compile(r"SE0[0-9A-Z]{6,}", re.IGNORECASE)
_SITE_PARAM_RE = re.compile(r"[?&]site=([^&\s]+)")
# Algae product filenames embed the data date, e.g. ..._20260620.png.
_DATE8_RE = re.compile(r"(\d{4})(\d{2})(\d{2})")


def extract_bath_id(raw: str | None) -> str | None:
    """Pull a bathingWaterId out of a raw id, a doppkartan ?site= URL, or any string.

    The public HaV page URL does not contain the id, so the user should paste
    either the bathingWaterId itself or a doppkartan/karta link.
    """
    if not raw:
        return None
    raw = raw.strip()
    site = _SITE_PARAM_RE.search(raw)
    candidate = site.group(1) if site else raw
    match = _ID_RE.search(candidate)
    return match.group(0).upper() if match else None


class BadvattenApi:
    """Thin async wrapper over the HaV bathing-waters public API (v2)."""

    def __init__(self, session: ClientSession) -> None:
        self._session = session

    async def _get_json(self, url: str) -> Any:
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        async with self._session.get(url, headers=headers, timeout=_TIMEOUT) as resp:
            resp.raise_for_status()
            # The gateway sometimes serves JSON without a strict content-type.
            return await resp.json(content_type=None)

    async def _get_text(self, url: str) -> str:
        headers = {"User-Agent": USER_AGENT}
        async with self._session.get(url, headers=headers, timeout=_TIMEOUT) as resp:
            resp.raise_for_status()
            return await resp.text()

    async def fetch(self, bath_id: str) -> dict[str, Any]:
        """Return {bath_id, bath} for one bathing water.

        ``bath`` is the combined v2 object from GET /bathing-waters/{id}:
        ``bathingWater`` (name, municipality, position, water type),
        ``profile`` (EU classification history, bathing season, bloom risk,
        responsible authorities), ``results`` (monitoring samples: E. coli,
        intestinal enterococci, measured water temp, verdict), ``waterTemperature``
        (Copernicus water-temp forecast, coastal sites only) and
        ``adviceAgainstBathing`` / ``abnormalSituations`` (live advisories).
        """
        bath = await self._get_json(BATH_URL.format(bath_id=bath_id))
        return {"bath_id": bath_id, "bath": bath or {}}

    async def fetch_weather(
        self, lat: float, lon: float, provider: str
    ) -> dict[str, Any]:
        """Air conditions at a coordinate from the selected provider.

        Returns a provider-agnostic dict: temperature, apparent_temperature,
        humidity, wind_speed [m/s], wind_gust, wind_direction, weather_symbol,
        observed_at, provider. Best-effort: the caller treats failures as
        "no weather" so the HaV data still loads.
        """
        if provider == PROVIDER_SMHI:
            data = await self._get_json(
                SMHI_FORECAST_URL.format(lon=round(lon, 6), lat=round(lat, 6))
            )
            return _normalize_smhi(data)
        data = await self._get_json(OPEN_METEO_URL.format(lat=lat, lon=lon))
        return _normalize_open_meteo(data.get("current") or {})

    async def fetch_water_temp(self, lat: float, lon: float) -> float | None:
        """Open-Meteo sea-surface temperature — fallback when HaV has no forecast.

        Accurate near the coast; for an inland lake it snaps to the nearest sea
        cell and may be off. Best-effort.
        """
        data = await self._get_json(OPEN_METEO_MARINE_URL.format(lat=lat, lon=lon))
        value = (data.get("current") or {}).get("sea_surface_temperature")
        return _to_float(value)

    async def fetch_algae(self) -> dict[str, Any]:
        """Latest Baltic cyanobacteria compilation (SMHI Algae Maps).

        Returns {date, updated, map_url, summary_en, summary_sv} from the
        past-7-days ``COMP7`` product. Regional (the Baltic), so the caller
        only uses it for coastal baths. Best-effort: failures degrade to None.
        """
        day = await self._get_json(ALGAE_LATEST_DAY_URL)
        products = {p.get("key"): p for p in (day.get("dataMap") or [])}

        def _href(key: str, suffix: str) -> str | None:
            for link in (products.get(key) or {}).get("link", []):
                href = link.get("href", "")
                if href.endswith(suffix):
                    return href
            return None

        map_url = _href("Baltic_algae_COMP7", ".png")
        return {
            "date": _date_from_href(map_url),
            "updated": day.get("updated"),
            "map_url": map_url,
            "summary_en": await self._maybe_text(
                _href("Baltic_algae_COMP7_eng", ".txt")
            ),
            "summary_sv": await self._maybe_text(
                _href("Baltic_algae_COMP7_swe", ".txt")
            ),
        }

    async def _maybe_text(self, url: str | None) -> str | None:
        if not url:
            return None
        try:
            return (await self._get_text(url)).strip()
        except Exception as err:  # noqa: BLE001 - summary text is optional
            _LOGGER.debug("algae summary fetch failed (%s): %s", url, err)
            return None

    async def list_baths(self) -> list[dict[str, Any]]:
        """Return the national bath list as flat dicts for search.

        One fetch covering all of Sweden. Call it once during config and filter
        in memory. Keys: id, name, kommun, lat, lon, water_type.
        """
        data = await self._get_json(LIST_URL)
        out: list[dict[str, Any]] = []
        for item in data.get("watersAndAdvisories", []):
            bw = item.get("bathingWater") or {}
            bath_id = bw.get("id")
            if not bath_id:
                continue
            pos = bw.get("samplingPointPosition") or {}
            municipality = bw.get("municipality") or {}
            out.append(
                {
                    "id": bath_id,
                    "name": bw.get("name") or bath_id,
                    "kommun": municipality.get("name") or "",
                    "lat": _to_float(pos.get("latitude")),
                    "lon": _to_float(pos.get("longitude")),
                    "water_type": bw.get("waterTypeIdText") or "",
                }
            )
        return out


def _to_float(value: Any) -> float | None:
    """Coordinates arrive as strings; tolerate missing/blank values."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_open_meteo(current: dict) -> dict[str, Any]:
    """Map the Open-Meteo ``current`` block to the common weather shape."""
    return {
        "temperature": current.get("temperature_2m"),
        "apparent_temperature": current.get("apparent_temperature"),
        "humidity": current.get("relative_humidity_2m"),
        "wind_speed": current.get("wind_speed_10m"),
        "wind_gust": current.get("wind_gusts_10m"),
        "wind_direction": current.get("wind_direction_10m"),
        "weather_symbol": current.get("weather_code"),
        "observed_at": current.get("time"),
        "provider": "open_meteo",
    }


def _normalize_smhi(data: dict) -> dict[str, Any]:
    """Map SMHI SNOW's first time step to the common weather shape."""
    series = (data.get("timeSeries") or [{}])[0]
    values = series.get("data") or {}
    return {
        "temperature": values.get("air_temperature"),
        "apparent_temperature": None,  # SMHI has no feels-like parameter
        "humidity": values.get("relative_humidity"),
        "wind_speed": values.get("wind_speed"),
        "wind_gust": values.get("wind_speed_of_gust"),
        "wind_direction": values.get("wind_from_direction"),
        "weather_symbol": values.get("symbol_code"),
        "observed_at": series.get("time"),
        "provider": "smhi",
    }


def _date_from_href(href: str | None) -> str | None:
    """Extract YYYY-MM-DD from an algae filename like ..._20260620.png."""
    if not href:
        return None
    match = _DATE8_RE.search(href)
    return "-".join(match.groups()) if match else None
