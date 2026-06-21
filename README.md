# Swedish Bathing Water Quality

> Home Assistant integration name: **Swedish Bathing Water Quality** (English), **Badplatsen** (Swedish). Domain: `hav_badvatten`.

[![Validate](https://github.com/delize/home-assistant-hav-badvatten/actions/workflows/validate.yaml/badge.svg)](https://github.com/delize/home-assistant-hav-badvatten/actions/workflows/validate.yaml)
[![hacs](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

[![Open your Home Assistant instance and open this repository inside HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=delize&repository=home-assistant-hav-badvatten&category=integration)

Home Assistant custom integration for Swedish bathing-water quality from the
Havs- och vattenmyndigheten (HaV) *Badplatsen* open API. For each bathing site it
provides the EU water-quality classification, the latest sample result (E. coli
and intestinal enterococci), the measured water temperature, an air and wind
forecast, and any active advisory ("avrådan från bad").

One config entry is one bathing site, and each becomes a Home Assistant device.

> Sweden has roughly 2,600 registered bathing waters. There was no Home
> Assistant integration for this data before this one.

## Data source

This integration uses HaV's official, versioned public API (`bathing-waters`, v2):

```
https://gw.havochvatten.se/external-public/bathing-waters/v2
```

- `GET /bathing-waters` returns the national list of active baths, which drives
  search.
- `GET /bathing-waters/{id}` returns a combined object for one bath (profile,
  sample results, forecast, advisories) in a single call per update.

It needs no API key and returns JSON. Data updates a few times per day at most.
See HaV's [API documentation][hav-api] and the [open-data usage terms][hav-terms].
The bathing-water id (`bathingWaterId`, formerly `nutsCode`, e.g.
`SE0110180000007461`) is the same id used by doppkartan's `?site=` parameter.

### Weather (air temperature and wind)

The HaV API has no air-temperature or wind forecast, only the Copernicus
water-temperature one. The Air temperature and Wind speed sensors therefore come
from a provider you pick per entry in the options flow:

- **SMHI SNOW** (default). The Swedish Meteorological and Hydrological Institute's
  operational forecast (`snow1g`). Swedish-specific, m/s, CC BY 4.0.
- **Open-Meteo**. Global, m/s, CC BY 4.0. This is the source
  [doppkartan](https://www.doppkartan.se/) uses.

Both providers are normalised to the same fields, so switching does not change
the entities. Only the data source and the attribution change (the two weather
sensors carry their provider's attribution, and everything else is attributed to
HaV). Each sensor's `provider` attribute records which one produced the value.

> Open-Meteo's *marine* (sea-surface-temperature) API is not used. It snaps
> inland coordinates to the nearest sea cell, so for a lake it reports the Baltic
> rather than the lake. Inland water temperature comes only from HaV's physical
> samples (the *Water temperature (measured)* sensor).

For sun position (doppkartan uses suncalc), Home Assistant's built-in
[`sun`](https://www.home-assistant.io/integrations/sun/) integration already
exposes elevation and azimuth via `sun.sun`. See the example card.

### Baltic cyanobacteria (coastal baths)

[SMHI Algae Maps](https://opendata.smhi.se/algaemaps/introduction) publishes a
daily satellite cyanobacteria-bloom compilation for the Baltic (June to
September), with bilingual text summaries. It is free and needs no key
(CC BY 4.0). The data is regional rather than per-bath, so the Baltic cyanobacteria
sensor is added only to coastal ("Hav") baths. Inland lakes do not get it; their
algae situation is covered by the per-bath *Advice against bathing* signal from
HaV. The sensor's `map_url` attribute points at the current bloom-map PNG, which
you can render with a markdown card:

```yaml
type: markdown
content: >
  {{ state_attr('sensor.<bath>_baltic_cyanobacteria', 'summary_en') }}

  ![bloom map]({{ state_attr('sensor.<bath>_baltic_cyanobacteria', 'map_url') }})
```

[hav-api]: https://www.havochvatten.se/data-kartor-och-rapporter/data-och-statistik/data-och-apier/api-badplatser-och-badvatten.html
[hav-terms]: https://www.havochvatten.se/data-kartor-och-rapporter/data-och-statistik/om-oppna-data-och-statistik/om-oppna-data-pa-havs--och-vattenmyndigheten.html

## Installation

### HACS (recommended)

Use the "Open inside HACS" badge above, or add it manually:

1. HACS → ⋮ → **Custom repositories**.
2. Add `https://github.com/delize/home-assistant-hav-badvatten` with category
   **Integration**.
3. Install **Swedish Bathing Water Quality**, then restart Home Assistant.

(Maintainers: see [`PUBLISHING.md`](PUBLISHING.md) for releasing and for getting
into the HACS default store.)

### Manual

Copy `custom_components/hav_badvatten/` into your Home Assistant
`config/custom_components/` directory and restart.

## Configuration

Add it via **Settings → Devices & Services → Add Integration → Swedish Bathing
Water Quality**. The config flow is search-based:

- **Search** by name or municipality (for example `Sjövik` or `Stockholm`), then
  pick a site from the dropdown.
- **Leave both fields empty** to list the sites nearest your Home Assistant home
  location.
- **Advanced:** paste a `bathingWaterId` (for example `SE0110180000007461`) or a
  doppkartan/karta link to skip search.

Repeat for each additional bathing site.

Each entry's options let you change the update interval (default 180 minutes,
range 30 to 1440) and the weather provider (SMHI SNOW or Open-Meteo). Changing an
option reloads that bath.

## Entities

Each bathing site is one device with these entities.

| Entity | Type | Notes |
| --- | --- | --- |
| Bathing status | sensor | The headline "can I swim?" verdict. It combines the live advisory with the latest sample into one value (*OK to bathe*, *Caution*, *Not suitable*, *Advisory*, or *No recent sample*). A live advisory overrides the sample. A stale sample (older than about 2× the bath's own sampling interval, or from a previous season) reads as *No recent sample* rather than a confident "OK". Attributes carry the reasoning plus `sample_age_days` and `sample_interval_days`. |
| Advisory since | sensor | Timestamp when the active advisory began, so you can tell whether it is newer than the sample. *Unknown* when there is none; the `active` attribute and *Advice against bathing* make that explicit. |
| Water quality classification | sensor | EU classification (for example *Excellent*). Attributes include 4-year history, the EU-bathing flag, the profile summary, and municipality and responsible-authority contact. |
| Water temperature (measured) | sensor | °C from the latest physical sample. |
| Water temperature (forecast) | sensor | °C from the Copernicus forecast, with an Open-Meteo fallback inland. |
| Air temperature | sensor | °C at the bath from SMHI SNOW or Open-Meteo. `apparent_temperature` and `provider` attributes. |
| Wind speed | sensor | m/s at the bath from SMHI SNOW or Open-Meteo. `direction`, `gusts`, and `provider` attributes. |
| Bathing season | sensor | `open` or `closed`. Attributes are the season start and end. |
| Latest sample assessment | sensor (diagnostic) | Bacteria verdict of the most recent lab sample (*Suitable*, and so on). It is a periodic test, so it sits under Diagnostic. Attributes include the per-sample algae observation (HaV's "Algae occurrence" column), the E. coli, enterococci and temperature for that sample, and dated history. |
| E. coli | sensor (diagnostic) | Count per 100 mL from the latest sample. `prefix` and history attributes. |
| Intestinal enterococci | sensor (diagnostic) | Count per 100 mL from the latest sample. History attribute. |
| Last sample | sensor (diagnostic) | Timestamp of the most recent lab sample. |
| Baltic cyanobacteria (past week) | sensor | Coastal baths only. SMHI satellite bloom compilation, diagnostic. The state is the map date; attributes hold the EN/SV summary and `map_url`. |
| Advice against bathing | binary_sensor | The live safety signal. On when an advisory (such as an algal bloom or a swimming ban) is active. |
| Susceptible to algal blooms | binary_sensor | A static diagnostic flag for whether this site is historically susceptible to algal or cyanobacteria blooms. It is awareness, not a live alert. |
| Advisory may be outdated | binary_sensor (diagnostic) | On when an advisory has been active for at least 16 days, in season, and the bath has been sampled since it was issued (for example a recurring-bloom advisory that was never lifted). A "worth re-checking" hint. Attributes: `advisory_age_days`, `samples_since_advisory`, `in_season`. It does not clear the safety signal. |

## Caveats

- **Inland water-temp forecast is an approximation.** HaV's Copernicus forecast
  (`waterTemperature`) only covers coastal ("Hav") sites. On lakes ("Sjö") the
  *Water temperature (forecast)* sensor falls back to Open-Meteo's sea-surface
  temperature at the bath's coordinates. That is accurate for coastal and
  Baltic-adjacent sites, but for a lake far from the sea it snaps to the nearest
  sea cell and may be wrong. The sensor's `source` attribute reports
  `hav-copernicus` or `open-meteo`, and the attribution updates to match. The
  *Water temperature (measured)* sensor (from physical samples) is the more
  reliable inland value.
- **`Advice against bathing` is the live signal; `Susceptible to algal blooms` is
  not.** The latter is a static profile flag for whether a site tends to bloom.
  *Advice against bathing* reflects an actual current advisory.
- **Nearest-first search needs a real home location.** Home Assistant defaults
  latitude and longitude to `0,0` on a fresh install. Until you set your real
  home location (Settings → System → General), the "leave fields empty for
  nearest sites" path ranks against the Gulf of Guinea rather than Sweden. Search
  by name or municipality works regardless.
- **Not real-time.** HaV publishes data a few times per day, so the default
  3-hour poll is conservative.

## Dashboard card

Two example cards are in [`lovelace/`](lovelace):

- [`badvatten-card-auto.yaml`](lovelace/badvatten-card-auto.yaml) needs no
  configuration. It uses `custom:auto-entities` (HACS) to pull in every entity
  for a bath by its device name, so there are no entity-id slugs to copy. Use
  this if you just want all the values listed.
- [`badvatten-card.yaml`](lovelace/badvatten-card.yaml) is a hand-styled,
  colour-coded card (live advisory in red, safe sample in green, sample age as a
  relative "För N dgr sedan"), using `custom:template-entity-row` and `card-mod`
  (both HACS). It references entity-ids directly, so replace the prefix with your
  bath's slug (`sensor.<device-name-slug>_<entity-name-slug>`; copy the exact ids
  from **Developer Tools → States**).

## Development

```bash
# byte-compile + JSON validation
python3 -m py_compile custom_components/hav_badvatten/*.py
python3 -c "import json,glob;[json.load(open(f)) for f in glob.glob('custom_components/**/*.json',recursive=True)];print('json ok')"

# smoke tests (stub HA/aiohttp; run against captured API fixtures)
pip install -r tests/requirements_test.txt
python -m pytest tests/ -q
```

The smoke tests check id extraction, API parsing, and the value of every sensor
and binary sensor. They run against fixtures captured from the live HaV v2,
Open-Meteo and SMHI APIs.

### CI/CD

**CI.** [`.github/workflows/validate.yaml`](.github/workflows/validate.yaml) runs
on every push and PR, and weekly to catch upstream HA or HACS drift:

| Job | What it does |
| --- | --- |
| Ruff | `ruff check` + `ruff format --check` (config in [`pyproject.toml`](pyproject.toml)) |
| Hassfest | Home Assistant's manifest/structure validation |
| HACS | HACS repository validation |
| Smoke tests | `pytest` on Python 3.12 and 3.13 (stubbed HA) |
| Import against HA | installs real Home Assistant and imports every module |
| Config/Options flow | runs the real flow under HA (`pytest-homeassistant-custom-component`) |

Mirror it locally with [pre-commit](https://pre-commit.com):
`pip install pre-commit && pre-commit install`.

**CD.** Releasing is driven by GitHub Releases (the HACS-native pattern):

1. Merge PRs to `main`. [Release Drafter](.github/workflows/release-drafter.yaml)
   keeps a draft release updated from PR labels and proposes the next version.
2. Publish the draft with a `vX.Y.Z` tag.
3. [`release.yaml`](.github/workflows/release.yaml) stamps the tag into
   `manifest.json`, then builds and attaches `hav_badvatten.zip`. HACS installs
   that asset (`hacs.json` `zip_release`), so the published version always matches
   the tag, with no manual manifest bump.

[Dependabot](.github/dependabot.yml) keeps the GitHub Actions and test
dependencies current.

## Disclaimer

Advisories here mirror HaV's published data and can lag real conditions. Always
check official local signage and HaV's [Badplatsen][badplatsen] before swimming.
This integration is not affiliated with or endorsed by Havs- och
vattenmyndigheten.

[badplatsen]: https://www.havochvatten.se/badplatser-och-badvatten.html

---

Data: Havs- och vattenmyndigheten (Badplatsen).
