from __future__ import annotations

DOMAIN = "hav_badvatten"

# HaV updates badvatten data a few times per day at most, so poll gently.
DEFAULT_SCAN_MINUTES = 180
CONF_SCAN_INTERVAL_MINUTES = "scan_interval_minutes"

CONF_BATH_ID = "bath_id"
# Free-text field in the config flow: accepts a raw bathingWaterId or a URL.
CONF_INPUT = "bath"

# Air-temperature / wind source is selectable per entry in the options flow.
CONF_WEATHER_PROVIDER = "weather_provider"
PROVIDER_SMHI = "smhi"
PROVIDER_OPEN_METEO = "open_meteo"
DEFAULT_WEATHER_PROVIDER = PROVIDER_SMHI

USER_AGENT = "ha-hav-badvatten/0.2 (Home Assistant custom component)"

# --- HaV "bathing-waters" official public API (v2) ---------------------------
# Documented, versioned REST API. The legacy badplatsen/api/* map endpoints
# (feature/, testlocationprofile/, detail/) are undocumented internals; the
# national feature/ list is currently broken (HTTP 400), so we target the
# official API instead. See:
#   https://www.havochvatten.se/data-kartor-och-rapporter/data-och-statistik/
#       data-och-apier/api-badplatser-och-badvatten.html
# Server template from the OpenAPI spec:
#   https://{subdomain}.havochvatten.se/{applicationpath}/{version}
#   subdomain=gw (prod), applicationpath=external-public/bathing-waters, version=v2
API_BASE = "https://gw.havochvatten.se/external-public/bathing-waters/v2"

# National list of active baths (+ active advisories). One JSON fetch covering
# all of Sweden; drives the config-flow search. Key: watersAndAdvisories[].
LIST_URL = f"{API_BASE}/bathing-waters"

# Per-bath combined object: bathingWater, profile, results, waterTemperature,
# adviceAgainstBathing, abnormalSituations. One call has everything an entity
# needs. The id is the former nutsCode, unchanged, e.g. SE0110180000007461.
BATH_URL = f"{API_BASE}/bathing-waters/{{bath_id}}"

# Cheap liveness probe (apiStatus/apiVersion); not used at runtime.
METADATA_URL = f"{API_BASE}/operations/metadata"

# Map deep-link, used as the device configuration_url. The per-bath modal is
# served from the legacy map app (its detail/profile endpoints still work).
# bathingWaterId == the doppkartan ?site= id.
MAP_URL = "https://badplatsen.havochvatten.se/badplatsen/karta/#/bath/{bath_id}"

ATTRIBUTION = "Data: Havs- och vattenmyndigheten (Badplatsen)"
MANUFACTURER = "Havs- och vattenmyndigheten"

# --- Air temperature + wind at the bath --------------------------------------
# The HaV v2 API has no air/wind forecast (only the Copernicus water-temp one),
# so air conditions at the bath come from a selectable provider. Both are free,
# no key, report wind in m/s and are CC BY 4.0.
#
# SMHI SNOW (default) is the authoritative Swedish operational forecast. The
# legacy pmp3g category was retired; the current one is snow1g.
SMHI_FORECAST_URL = (
    "https://opendata-download-metfcst.smhi.se"
    "/api/category/snow1g/version/1/geotype/point/lon/{lon}/lat/{lat}/data.json"
)
SMHI_WEATHER_ATTRIBUTION = "Väder: SMHI (CC BY 4.0)"

# Open-Meteo (alternative) — global, current conditions; the source doppkartan
# uses. Note: its marine (sea-surface-temp) API is deliberately NOT used — it
# snaps inland coordinates to the nearest sea cell (reports the Baltic, not the
# lake). Inland water temp is only available from HaV samples (water_temp_measured).
OPEN_METEO_URL = (
    "https://api.open-meteo.com/v1/forecast"
    "?latitude={lat}&longitude={lon}"
    "&current=temperature_2m,apparent_temperature,relative_humidity_2m,"
    "wind_speed_10m,wind_direction_10m,wind_gusts_10m,weather_code"
    "&wind_speed_unit=ms&timezone=auto"
)
WEATHER_ATTRIBUTION = "Väder: Open-Meteo (CC BY 4.0)"

# --- SMHI Algae Maps (Baltic cyanobacteria) ----------------------------------
# Satellite-derived cyanobacteria-bloom maps + bilingual weekly text summaries
# for the Baltic, updated daily June–September. Regional (the Baltic), not
# per-bath, so the derived sensor is attached to COASTAL baths only — a Baltic
# bloom map says nothing about an inland lake. The "latest" alias always
# resolves to the most recent day; from there each product links to dated files.
# Entry point: https://opendata-download-algae.smhi.se/api.json
ALGAE_LATEST_DAY_URL = (
    "https://opendata-download-algae.smhi.se"
    "/api/version/latest/year/latest/month/latest/day/latest.json"
)
ALGAE_ATTRIBUTION = "Algkartor: SMHI (CC BY 4.0)"

# waterTypeId 1 == "Hav" (sea/coastal); 3 == "Sjö" (lake). The Baltic algae
# map is only meaningful for coastal baths.
WATER_TYPE_SEA_ID = 1

# sampleAssessId == 1 means "Tjänligt" (suitable / safe to swim). Higher ids
# are "Tjänligt med anmärkning" / "Otjänligt". Used to derive a safe/unsafe hint.
SAMPLE_ASSESS_SAFE_ID = 1
