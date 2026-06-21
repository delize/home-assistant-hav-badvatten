from custom_components.hav_badvatten.const import (
    CONF_BATH_ID,
    CONF_SCAN_INTERVAL_MINUTES,
    CONF_WEATHER_PROVIDER,
    DOMAIN,
    PROVIDER_SMHI,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry


async def test_options_flow_loads_the_form(hass: HomeAssistant):
    """Reproduces the gear -> 500 bug: the options flow must load its form."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_BATH_ID: "SE0110180000007461", "name": "Test bath"},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"


async def test_options_flow_saves(hass: HomeAssistant):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_BATH_ID: "SE0110180000007461", "name": "Test bath"},
    )
    entry.add_to_hass(hass)
    init = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        init["flow_id"],
        {CONF_SCAN_INTERVAL_MINUTES: 90, CONF_WEATHER_PROVIDER: PROVIDER_SMHI},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_WEATHER_PROVIDER] == PROVIDER_SMHI
