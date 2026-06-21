# HaV Badvatten — Claude Code handoff

Home Assistant custom integration that surfaces Swedish bathing-water quality
from the Havs- och vattenmyndigheten (HaV) "Badplatsen" open API. Built in a
chat session to the point of a loadable-but-incomplete scaffold. This file is
the brief to finish it. Rename to `CLAUDE.md` if you want it auto-loaded as
project context.

---

## ✅ BUILD STATUS (2026-06-21) — complete; read this first

The integration is finished and loadable. One decision below overrode the
brief, after verifying the live API from a host that can reach it:

**Migrated from the legacy `badplatsen/api/*` endpoints to HaV's official,
versioned public API (`bathing-waters` v2).** Reasons, all verified live:

- The legacy national list `badplatsen/api/feature/` is **broken** — HTTP 400
  for everyone, including HaV's own map app. The search-based config flow
  cannot work on it.
- HaV publishes a documented, versioned, terms-of-use'd API:
  `https://gw.havochvatten.se/external-public/bathing-waters/v2`
  (`apiStatus: active`, `apiVersion: 2.3.0`). `GET /bathing-waters` is the
  national list; `GET /bathing-waters/{id}` returns profile + sample results +
  water-temp forecast + live advisories **in one call**.
- The id is unchanged (former `nutsCode`, e.g. `SE0110180000007461`).

Consequences for the entity list vs. the brief:

- **Dropped** `air_temp_forecast` and `wind_speed_forecast` — the v2 API has
  no SMHI weather forecast, only the Copernicus water-temp forecast.
- **Added** (the "safe to swim today" data the brief's open question #1 hoped
  `detail` held — now confirmed in v2 `results[]`/`adviceAgainstBathing[]`):
  `sample_assessment` (latest verdict, *Tjänligt*/safe), `water_temp_measured`
  (from physical samples — works on inland baths where the forecast doesn't),
  `e_coli`, `intestinal_enterococci`, `last_sample`, and a **live**
  `advice_against_bathing` binary_sensor (algal-bloom/swim-ban advisories).
- `bloom_risk` binary_sensor kept as the static diagnostic flag
  (`profile.bloomRisk.algae/cyano`).

Open questions resolved: (1) the verdict/advisory data lives in v2
`results[]` + `adviceAgainstBathing[]`, schema confirmed and consumed.
(2) Reachability confirmed from a normal host — if your HA box can't reach
`gw.havochvatten.se`, that's a local egress issue. (3) Poll default kept at
180 min; sample data updates a few times/day at most.

All Python byte-compiles under 3.13; all JSON validates; every `value_fn` was
exercised against saved real v2 payloads for an inland site (with a live
advisory) and a coastal site (with a forecast). See `README.md` for the
authoritative entity list and caveats. The checklist below is retained for
history; everything in it is done (with the substitutions noted above).

### Added after the initial build (v0.3.0)

- **Open-Meteo** air-temperature + wind-speed sensors (`air_temperature`,
  `wind_speed`), per bath coordinate, CC BY 4.0 — restores the air/wind the v2
  HaV API lacks. SMHI's forecast API (metfcst) was unreachable (404 even for
  its documented example); SMHI metobs is station-based (worse per-bath than
  Open-Meteo's modeled point data), so Open-Meteo was chosen (also doppkartan's
  source).
- **SMHI Algae Maps** `baltic_cyanobacteria` sensor (`opendata-download-algae`),
  **coastal baths only** — Baltic cyanobacteria compilation + EN/SV summaries +
  bloom-map image URL, CC BY 4.0. SMHI's observation APIs have no algae param;
  this `algaemaps` service is the real one.
- **Smoke tests** under `tests/` (26, runnable with just pytest via stubbed
  HA/aiohttp), wired into CI. **Example Lovelace card** in `lovelace/`.
- `.gitignore` added; manifest bumped to 0.3.0.

### Added in v0.4.0

- **Selectable weather provider** (options flow): **SMHI SNOW** (default, the
  authoritative Swedish operational forecast — the retired `pmp3g` category is
  now `snow1g`) or **Open-Meteo**. Both are normalised to one shape in `api.py`
  (`_normalize_smhi` / `_normalize_open_meteo`), so the sensors are
  provider-agnostic; the chosen provider's attribution is baked onto the
  weather sensors at setup, and changing the option reloads the entry.
- **Zero-slug dashboard card** `lovelace/badvatten-card-auto.yaml` using
  `custom:auto-entities` (filter by device name) — no entity-ids to copy.
- Manifest 0.4.0.

### CI/CD (added)

- **CI** (`.github/workflows/validate.yaml`): ruff (lint + format, pinned
  0.15.18, config in `pyproject.toml`), hassfest, HACS, and pytest on 3.12/3.13.
- **CD**: GitHub-Release-driven. `release-drafter` keeps a draft from PR labels;
  publishing a `vX.Y.Z` tag triggers `release.yaml`, which stamps the tag into
  `manifest.json`, zips the integration to `hav_badvatten.zip`, and attaches it.
  `hacs.json` has `zip_release` + `filename`, so HACS installs that asset and the
  published version always matches the tag (no manual manifest bump).
- `.github/dependabot.yml` (actions + test deps), `.pre-commit-config.yaml`
  (ruff + basic hygiene). All ruff-clean; the release stamping + zip were
  dry-run-verified locally.

## Goal

A `cloud_polling` integration, one config entry per bathing site, that exposes
the EU water-quality classification plus the SMHI/Copernicus forecast for a
site. Primary motivation is publishing to HACS (no Swedish badvatten
integration exists today), not a single private panel. If scope ever collapses
back to one site, a REST sensor would have been enough and that's fine.

Reference site for testing: **Sjövikskajens bryggbad**, nutsCode
`SE0110180000007461` (Stockholm, Mälaren, inland/brackish).

## Decisions already made (don't relitigate)

- Custom integration over YAML REST sensor, justified by the HACS-publish goal.
- One config entry == one bath == one HA device. No proxy-sensor / active-station
  select (that pattern came from the reference repo but doesn't fit; each bath
  is naturally its own entry).
- Declarative `EntityDescription` + `value_fn(profile)` pattern for sensors.
- `_attr_has_entity_name = True`; entity names come from `strings.json`
  translation keys.
- No `requirements` in the manifest (uses `aiohttp` via HA's shared session).

## Reference design

Borrowed structure from `Howard0000/home-assistant-hav-og-vind` (MIT, HACS).
Kept: config flow, `DataUpdateCoordinator`, options flow for scan interval,
declarative sensor descriptions. Dropped: its proxy_sensor.py / select.py
active-station mechanism, and all of its Norwegian data sources (MET Norway,
Havvarsel, Kartverket) — that repo is oceanographic conditions, NOT bathing-water
quality, and its sources don't cover inland Sweden. It is a structural reference
only.

## API ground truth

Two hosts. `www.havochvatten.se` is just the agency website. The live API is on
`badplatsen.havochvatten.se`. Unauthenticated, JSON, no key.

- Docs page (developer docs zip + usage-terms PDF):
  `https://www.havochvatten.se/data-kartor-och-rapporter/data-och-statistik/data-och-apier/api-badplatser-och-badvatten.html`
- National list (GeoJSON): `.../badplatsen/api/feature/`
  Each feature: `properties.NUTSKOD`, `properties.NAMN`, `properties.KMN_NAMN`,
  `geometry.coordinates = [lon, lat]`. Drives the config-flow search.
- Per-site profile (**CONFIRMED**, load-bearing):
  `.../badplatsen/api/testlocationprofile/{nutsCode}`
- Per-site detail (**UNVERIFIED** — see open questions):
  `.../badplatsen/api/detail/{nutsCode}`
- Map deep-link (used as device `configuration_url`):
  `.../badplatsen/karta/#/bath/{nutsCode}`

`nutsCode` is the same id as doppkartan's `?site=` query param.

No documented stability guarantee ("vi gör ändringar vid behov"). Pull the dev
docs zip from the docs page before trusting `detail`.

### Confirmed `testlocationprofile` shape

Trimmed real response (from sibling site Sickla, `SE0110182000001238`; schema is
identical across sites). Fields the scaffold relies on:

```json
{
  "name": "Sickla strandbad",
  "nutsCode": "SE0110182000001238",
  "decLat": 59.3017, "decLong": 18.1241,
  "euType": true, "algae": true, "cyano": true,
  "bathingSeasonStart": 1781992800000, "bathingSeasonEnd": 1786744800000,
  "classification": [
    {"classificationYear": 2025, "rating": 1, "ratingText": "Utmärkt kvalitet"},
    {"classificationYear": 2024, "rating": 1, "ratingText": "Utmärkt kvalitet"}
  ],
  "coperSmhi": [
    {"copernicusData": "-", "smhiTemp": "7.8", "smhiWs": "5.7",
     "smhiWsymb": "3", "smhiPmean": "0.0", "smhiWindDir": "262", "measHour": "12"}
  ],
  "summary": "..."
}
```

Notes that bite:
- `classification[0]` is newest, but sort by `classificationYear` defensively.
- `coperSmhi[].smhiTemp` is **air** temp; `copernicusData` is **water** temp and
  is the string `"-"` on inland/lake baths (so Sjöviken has no water-temp value).
  Treat `"-"`/`""`/`None` as unknown.
- Season fields are epoch **milliseconds**.
- `algae`/`cyano` are static "this site is prone to..." profile flags, NOT a live
  bloom alert. Model them as a diagnostic risk indicator, not a current warning.

## Current repo state

```
custom_components/hav_badvatten/
  manifest.json        done (codeowner/repo are @delize placeholders — fix)
  const.py             done (DOMAIN, endpoints, defaults)
  api.py               done (fetch profile+detail; list_baths for search)
  __init__.py          done (coordinator, options listener, unload)
  config_flow.py       done (search by name/kommun OR nearest-to-home; paste-id fallback)
  entity.py            done (CoordinatorEntity base + DeviceInfo)
  strings.json         done (incl. select step + entity names)
  translations/en.json done (copy of strings.json)
```

All Python byte-compiles; all JSON validates. Not yet loadable in HA because the
two platforms below are missing.

## Remaining work

- [ ] `sensor.py` — build from the CONFIRMED profile schema. Entities:
      classification (state = `ratingText`, attrs = year/rating/history),
      water_temp_forecast (`coperSmhi[0].copernicusData`, °C, None on `"-"`),
      air_temp_forecast (`coperSmhi[0].smhiTemp`, °C),
      wind_speed_forecast (`coperSmhi[0].smhiWs`, m/s),
      season (open/closed from the epoch-ms season bounds, attrs = start/end ISO).
      Use the `@dataclass(frozen=True, kw_only=True)` + `value_fn(profile)`
      pattern; subclass the `BadvattenEntity` base in `entity.py`.
- [ ] `binary_sensor.py` — algae_risk (`algae or cyano`), `EntityCategory.DIAGNOSTIC`,
      device_class safety. Clearly a static risk flag, not a live alert.
- [ ] `translations/sv.json` — Swedish names (this is a Swedish data source;
      worth doing properly for the HACS audience).
- [ ] `hacs.json` (`{"name": ..., "render_readme": true, "homeassistant": "2024.1.0"}`)
      and `.github/workflows/` for hassfest + HACS validation (copy the reference
      repo's two workflows).
- [ ] `README.md` — install, the search-based config flow, the entity list, and
      the two caveats: water temp is absent on inland baths, and home lat/long
      defaults to 0,0 on fresh installs so nearest-first ranking needs a real
      home location set.
- [ ] Fix `@delize` codeowner + repo URLs in manifest.json once the real GitHub
      repo exists.
- [ ] Smoke test: load in a dev HA, add Sjövikskajen via search, confirm entities
      populate. Run `python -m script.hassfest` if developing in a HA checkout.

## Open questions / verify before coding those parts

1. **`detail/{nutsCode}` schema is unverified.** The container this was built in
   can't reach havochvatten (not in its egress allowlist). From a host that can,
   `curl -s https://badplatsen.havochvatten.se/badplatsen/api/detail/SE0110180000007461 | jq .`
   and record the structure. The live sample result (the tjänlig/otjänlig verdict
   + sample date — the real "safe to swim today" signal) most likely lives here,
   not in the profile. `api.fetch()` already pulls `detail` best-effort and stashes
   it under `coordinator.data["detail"]`; no entity consumes it yet. Add a
   sample sensor only after confirming the field names.
2. **Network reachability from the HA host.** If HA sits behind the same egress
   rules, the integration won't reach the API at runtime. Confirm the HA host can
   hit `badplatsen.havochvatten.se` directly before debugging "unavailable".
3. **Default poll interval** is 180 min. Data updates a few times/day at most;
   fine, but confirm it doesn't miss in-season same-day sample updates if those
   turn out to be more frequent.

## Validation commands

```bash
# from custom_components/hav_badvatten/
python3 -m py_compile *.py
python3 -c "import json,glob;[json.load(open(f)) for f in glob.glob('**/*.json',recursive=True)];print('json ok')"
```
