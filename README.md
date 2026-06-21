# Swedish Bathing Water Quality

> Home Assistant integration name: **Swedish Bathing Water Quality** (English) /
> **Badplatsen** (Swedish). Domain: `hav_badvatten`.

[![Validate](https://github.com/delize/home-assistant-hav-badvatten/actions/workflows/validate.yaml/badge.svg)](https://github.com/delize/home-assistant-hav-badvatten/actions/workflows/validate.yaml)
[![hacs](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

[![Open your Home Assistant instance and open this repository inside HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=delize&repository=home-assistant-hav-badvatten&category=integration)

Home Assistant custom integration for Swedish **bathing-water quality**, sourced
from the Havs- och vattenmyndigheten (HaV) *Badplatsen* open API. It surfaces the
EU water-quality classification, the latest sample verdict (E. coli / intestinal
enterococci), the measured water temperature, the SMHI/Copernicus water-temp
forecast, and any live advisories ("avrådan från bad") for a bathing site.

One config entry == one bathing site == one Home Assistant device.

> Sweden has ~2 600 registered bathing waters. There is no existing Home
> Assistant integration for this data set — this fills that gap.

## Data source

This integration uses HaV's **official, versioned public API**
(`bathing-waters`, v2):

```
https://gw.havochvatten.se/external-public/bathing-waters/v2
```

- `GET /bathing-waters` — national list of active baths (drives search)
- `GET /bathing-waters/{id}` — combined profile + sample results + forecast +
  advisories for one bath (one call per update)

No API key, unauthenticated, JSON. Data updates a few times per day at most.
See HaV's [API documentation][hav-api] and the
[open-data usage terms][hav-terms]. The bathing-water id (`bathingWaterId`,
formerly `nutsCode`, e.g. `SE0110180000007461`) is the same id used by
doppkartan's `?site=` parameter.

### Weather (air temperature + wind)

The HaV API has no air-temperature or wind forecast (only the Copernicus
water-temperature one), so the **Air temperature** and **Wind speed** sensors
come from a **selectable provider** (per entry, in the options flow):

- **SMHI SNOW** (default) — the Swedish Meteorological and Hydrological
  Institute's operational forecast (`snow1g`); authoritative for Sweden, m/s,
  **CC BY 4.0**.
- **Open-Meteo** — global, current conditions, m/s, **CC BY 4.0**; the source
  [doppkartan](https://www.doppkartan.se/) uses.

Both are normalised to the same fields, so switching providers doesn't change
the entities — only the data source and attribution (the two weather sensors
carry their provider's attribution; everything else is attributed to HaV). The
`provider` attribute on each sensor records which one produced the value.

> Open-Meteo's *marine* (sea-surface-temperature) API is deliberately not used:
> it snaps inland coordinates to the nearest sea cell, so for a lake it reports
> the Baltic instead of the lake. Inland water temperature is only available
> from HaV's physical samples (the *Water temperature (measured)* sensor).

For **sun position** (doppkartan uses suncalc), Home Assistant's built-in
[`sun`](https://www.home-assistant.io/integrations/sun/) integration already
exposes elevation/azimuth via `sun.sun` — see the example card.

### Baltic cyanobacteria (coastal baths)

[SMHI Algae Maps](https://opendata.smhi.se/algaemaps/introduction) publishes a
daily satellite cyanobacteria-bloom compilation for the Baltic (June–September),
with bilingual text summaries — free, no key, **CC BY 4.0**. This is *regional*,
not per-bath, so the **Baltic cyanobacteria** sensor is only added to **coastal
("Hav") baths**; inland lakes don't get it (their algae situation is covered by
the per-bath *Advice against bathing* signal from HaV). The sensor's `map_url`
attribute points at the current bloom-map PNG — render it with a markdown card:

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

Click the **"Open inside HACS"** badge above, or add it manually:

1. HACS → ⋮ → **Custom repositories**.
2. Add `https://github.com/delize/home-assistant-hav-badvatten` with category
   **Integration**.
3. Install **HaV Badvatten**, then restart Home Assistant.

(Maintainers: see [`PUBLISHING.md`](PUBLISHING.md) for releasing and getting
into the HACS default store.)

### Manual

Copy `custom_components/hav_badvatten/` into your Home Assistant
`config/custom_components/` directory and restart.

## Configuration

Add via **Settings → Devices & Services → Add Integration → HaV Badvatten**.
The config flow is search-based:

- **Search** by name or municipality (e.g. `Sjövik`, `Stockholm`), then pick a
  site from the dropdown.
- **Leave both fields empty** to list the sites nearest your Home Assistant
  home location.
- **Advanced:** paste a `bathingWaterId` (e.g. `SE0110180000007461`) or a
  doppkartan/karta link to skip search entirely.

Add the integration again for each additional bathing site.

Per-entry **options** let you change the update interval (default 180 minutes,
range 30–1440) and the **weather provider** (SMHI SNOW or Open-Meteo). Changing
an option reloads that bath.

## Entities

Each bathing site is one device with these entities:

| Entity | Type | Notes |
| --- | --- | --- |
| **Bathing status** | sensor | **Headline "can I swim?"** — combines the live advisory with the latest sample into one verdict (*OK to bathe* / *Caution* / *Not suitable* / *Advisory*). |
| Water quality classification | sensor | EU classification (e.g. *Excellent*); attrs include 4-year history + EU-bathing flag. |
| Latest sample assessment | sensor | Verdict of the most recent sample (*Suitable* …); attrs carry the sample's E. coli/enterococci/temp + recent history. |
| Water temperature (measured) | sensor | °C, from the latest physical sample. |
| Water temperature (forecast) | sensor | °C, Copernicus forecast. **Coastal sites only** (see caveats). |
| Air temperature | sensor | °C at the bath from SMHI SNOW (or Open-Meteo); `apparent_temperature`/`provider` attributes. |
| Wind speed | sensor | m/s at the bath from SMHI SNOW (or Open-Meteo); `direction`/`gusts`/`provider` attributes. |
| E. coli | sensor | Count per 100 mL from the latest sample; `prefix` (`<`/`=`) attribute. |
| Intestinal enterococci | sensor | Count per 100 mL from the latest sample. |
| Last sample | sensor | Timestamp of the most recent sample. |
| Bathing season | sensor | `open` / `closed`; attrs are season start/end. |
| Baltic cyanobacteria (past week) | sensor | **Coastal baths only.** SMHI satellite bloom compilation; diagnostic. State is the map date; attrs hold the EN/SV summary and `map_url`. |
| Advice against bathing | binary_sensor | **Live** safety signal — on when an advisory (e.g. algal bloom, swimming ban) is active. |
| Susceptible to algal blooms | binary_sensor | **Static** diagnostic flag — this site is historically *susceptible* to algal/cyanobacteria blooms (awareness, not a live alert). |

## Caveats

- **Inland water-temp forecast is an approximation.** HaV's Copernicus forecast
  (`waterTemperature`) only covers coastal ("Hav") sites. On lakes ("Sjö") the
  *Water temperature (forecast)* sensor falls back to **Open-Meteo's sea-surface
  temperature** at the bath's coordinates — accurate for coastal/Baltic-adjacent
  sites, but for a lake far from the sea it snaps to the nearest sea cell and may
  be off. The sensor's `source` attribute reports `hav-copernicus` or
  `open-meteo`, and the attribution updates accordingly. The *Water temperature
  (measured)* sensor (from physical samples) is the most reliable inland signal.
- **`Advice against bathing` is the live signal; `Susceptible to algal blooms` is not.**
  The latter is a static profile flag ("this site tends to bloom" — awareness),
  while *Advice against bathing* reflects an actual current advisory.
- **Nearest-first search needs a real home location.** Home Assistant defaults
  latitude/longitude to `0,0` on a fresh install. Until you set your real home
  location (Settings → System → General), the "leave fields empty for nearest
  sites" path ranks against the Gulf of Guinea, not Sweden. Search by name or
  municipality works regardless.
- **Not real-time.** HaV publishes data a few times per day; the default
  3-hour poll is intentionally gentle.

## Dashboard card

Two example cards are in [`lovelace/`](lovelace):

- **[`badvatten-card-auto.yaml`](lovelace/badvatten-card-auto.yaml)** — zero
  config: uses `custom:auto-entities` (HACS) to pull in every entity for a bath
  by its **device name**, so there are no entity-id slugs to copy. Recommended
  if you just want all the values listed.
- **[`badvatten-card.yaml`](lovelace/badvatten-card.yaml)** — a hand-styled
  colour-coded card (live advisory in red, safe sample in green, sample age as a
  relative "För N dgr sedan"), using `custom:template-entity-row` + `card-mod`
  (both HACS). This one references entity-ids directly — replace the prefix with
  your bath's slug (`sensor.<device-name-slug>_<entity-name-slug>`; copy the
  exact ids from **Developer Tools → States**).

## Development

```bash
# byte-compile + JSON validation
python3 -m py_compile custom_components/hav_badvatten/*.py
python3 -c "import json,glob;[json.load(open(f)) for f in glob.glob('custom_components/**/*.json',recursive=True)];print('json ok')"

# smoke tests (stub HA/aiohttp; run against captured API fixtures)
pip install -r tests/requirements_test.txt
python -m pytest tests/ -q
```

The smoke tests cover id extraction, API parsing, and every sensor /
binary-sensor value against fixtures captured from the live HaV v2, Open-Meteo
and SMHI APIs.

### CI/CD

**CI** — [`.github/workflows/validate.yaml`](.github/workflows/validate.yaml) runs on every push/PR (and weekly, to catch upstream HA/HACS drift):

| Job | What it does |
| --- | --- |
| Ruff | `ruff check` + `ruff format --check` (config in [`pyproject.toml`](pyproject.toml)) |
| Hassfest | Home Assistant's manifest/structure validation |
| HACS | HACS repository validation |
| Smoke tests | `pytest` on Python 3.12 and 3.13 |

Mirror it locally with [pre-commit](https://pre-commit.com):
`pip install pre-commit && pre-commit install`.

**CD** — releasing is GitHub-Release-driven (the HACS-native pattern):

1. Merge PRs to `main`. [Release Drafter](.github/workflows/release-drafter.yaml)
   keeps a draft release updated from PR labels and proposes the next version.
2. Publish the draft with a `vX.Y.Z` tag.
3. [`release.yaml`](.github/workflows/release.yaml) stamps the tag into
   `manifest.json`, zips the integration to `hav_badvatten.zip`, and attaches it
   to the release. HACS installs that asset (`hacs.json` → `zip_release`), so the
   published version always matches the tag — no manual manifest bump needed.

Dependencies (GitHub Actions + test deps) are kept current by
[Dependabot](.github/dependabot.yml).

## Disclaimer

Bathing-water advisories here mirror HaV's published data and can lag real
conditions. Always check official local signage and HaV's
[Badplatsen][badplatsen] before swimming. This integration is not affiliated
with or endorsed by Havs- och vattenmyndigheten.

[badplatsen]: https://www.havochvatten.se/badplatser-och-badvatten.html

---

Data: Havs- och vattenmyndigheten (Badplatsen).
