from __future__ import annotations

from math import asin, cos, radians, sin, sqrt
from typing import Any

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
import voluptuous as vol

from .api import BadvattenApi, extract_bath_id
from .const import (
    CONF_BATH_ID,
    CONF_INPUT,
    CONF_SCAN_INTERVAL_MINUTES,
    CONF_WEATHER_PROVIDER,
    DEFAULT_SCAN_MINUTES,
    DEFAULT_WEATHER_PROVIDER,
    DOMAIN,
    PROVIDER_OPEN_METEO,
    PROVIDER_SMHI,
)

CONF_QUERY = "query"
CONF_SELECTION = "selection"
MAX_RESULTS = 25


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = (
        sin(dlat / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    )
    return 2 * 6371.0 * asin(sqrt(a))


class BadvattenConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._matches: list[dict[str, Any]] = []

    def _user_schema(self) -> vol.Schema:
        # Leave both blank to get the nearest baths to your HA home location.
        return vol.Schema(
            {
                vol.Optional(CONF_QUERY): str,
                vol.Optional(CONF_INPUT): str,
            }
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            raw = (user_input.get(CONF_INPUT) or "").strip()
            query = (user_input.get(CONF_QUERY) or "").strip()

            # Power-user path: a pasted id or doppkartan URL skips search.
            if raw:
                bath_id = extract_bath_id(raw)
                if not bath_id:
                    errors["base"] = "invalid_id"
                else:
                    return await self._create_for_id(bath_id)

            if not errors:
                api = BadvattenApi(async_get_clientsession(self.hass))
                try:
                    baths = await api.list_baths()
                except Exception:  # noqa: BLE001
                    errors["base"] = "cannot_connect"
                else:
                    self._matches = self._rank(baths, query)
                    if not self._matches:
                        errors["base"] = "no_matches"
                    else:
                        return await self.async_step_select()

        return self.async_show_form(
            step_id="user", data_schema=self._user_schema(), errors=errors
        )

    async def async_step_select(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        if user_input is not None:
            return await self._create_for_id(user_input[CONF_SELECTION])

        options = [
            SelectOptionDict(
                value=b["id"],
                label=f"{b['name']} ({b['kommun']})" if b["kommun"] else b["name"],
            )
            for b in self._matches
        ]
        schema = vol.Schema(
            {
                vol.Required(CONF_SELECTION): SelectSelector(
                    SelectSelectorConfig(
                        options=options, mode=SelectSelectorMode.DROPDOWN
                    )
                ),
            }
        )
        return self.async_show_form(step_id="select", data_schema=schema)

    def _rank(self, baths: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
        if query:
            q = query.lower()
            baths = [
                b for b in baths if q in b["name"].lower() or q in b["kommun"].lower()
            ]

        home_lat = self.hass.config.latitude
        home_lon = self.hass.config.longitude
        if home_lat is not None and home_lon is not None:

            def _dist(b: dict[str, Any]) -> float:
                if b["lat"] is None or b["lon"] is None:
                    return float("inf")
                return _haversine_km(home_lat, home_lon, b["lat"], b["lon"])

            baths = sorted(baths, key=_dist)
        else:
            baths = sorted(baths, key=lambda b: b["name"].lower())

        return baths[:MAX_RESULTS]

    async def _create_for_id(self, bath_id: str) -> config_entries.ConfigFlowResult:
        await self.async_set_unique_id(bath_id)
        self._abort_if_unique_id_configured()

        api = BadvattenApi(async_get_clientsession(self.hass))
        try:
            data = await api.fetch(bath_id)
            bathing_water = (data.get("bath") or {}).get("bathingWater") or {}
            official = bathing_water.get("name") or bath_id
        except Exception:  # noqa: BLE001
            return self.async_show_form(
                step_id="user",
                data_schema=self._user_schema(),
                errors={"base": "cannot_connect"},
            )

        return self.async_create_entry(
            title=official, data={CONF_BATH_ID: bath_id, CONF_NAME: official}
        )

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        return BadvattenOptionsFlow()


class BadvattenOptionsFlow(config_entries.OptionsFlow):
    # Do NOT set self.config_entry — since HA 2024.11 it's a read-only property
    # the framework provides after init (assigning it raises -> options flow 500).

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        opts = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL_MINUTES,
                    default=opts.get(CONF_SCAN_INTERVAL_MINUTES, DEFAULT_SCAN_MINUTES),
                ): vol.All(vol.Coerce(int), vol.Range(min=30, max=1440)),
                vol.Required(
                    CONF_WEATHER_PROVIDER,
                    default=opts.get(CONF_WEATHER_PROVIDER, DEFAULT_WEATHER_PROVIDER),
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            SelectOptionDict(value=PROVIDER_SMHI, label="SMHI (SNOW)"),
                            SelectOptionDict(
                                value=PROVIDER_OPEN_METEO, label="Open-Meteo"
                            ),
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
