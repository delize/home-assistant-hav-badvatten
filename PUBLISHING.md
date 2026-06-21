# Publishing to HACS

This repo is structured and validated to meet [HACS](https://www.hacs.xyz/)
integration requirements. Publishing itself happens from **your** GitHub
account (pushing the repo, cutting a release, and — for the default store —
opening inclusion PRs). This file is the runbook.

> **Critical:** the GitHub repository root must be the **contents** of this
> folder — `custom_components/`, `hacs.json`, `README.md`, `pyproject.toml`,
> `.github/` etc. at the top level. Do **not** commit a nested
> `hav-badvatten/` directory, or HACS won't find `custom_components/`.

## 1. Create and push the repository

```bash
# from inside this folder (the one containing custom_components/)
git init -b main
git add .
git commit -m "Initial release of HaV Badvatten"

# create the public repo and push (GitHub CLI)
gh repo create delize/home-assistant-hav-badvatten \
  --public --source=. --remote=origin --push \
  --description "Swedish bathing-water quality (Havs- och vattenmyndigheten) for Home Assistant"
```

Then on the repo's GitHub page add **topics** (HACS default inclusion needs a
description *and* topics), e.g.:
`home-assistant`, `hacs`, `homeassistant`, `home-assistant-component`,
`badvatten`, `sweden`, `smhi`.

## 2. Cut the first release (required)

`hacs.json` sets `zip_release`, so HACS installs the `hav_badvatten.zip` asset
from a GitHub Release — there must be at least one.

```bash
gh release create v0.4.0 --generate-notes --title "v0.4.0"
```

Publishing the release triggers `.github/workflows/release.yaml`, which stamps
the tag into `manifest.json` and attaches `hav_badvatten.zip`. (After this, you
can let Release Drafter draft future releases from PR labels.)

## 3. Confirm CI is green

The **Validate** workflow (ruff, hassfest, HACS, pytest) runs on push. The
**HACS** job needs the release from step 2 to be fully green (because of
`zip_release`). Check the Actions tab.

## 4a. Use it now (custom repository — no approval needed)

Anyone can install immediately by adding the repo as a HACS custom repository:

- HACS → ⋮ → **Custom repositories** → URL
  `https://github.com/delize/home-assistant-hav-badvatten`, category
  **Integration** → install → restart HA → add via **Settings → Devices &
  Services**.

One-click link (also in the README):
`https://my.home-assistant.io/redirect/hacs_repository/?owner=delize&repository=home-assistant-hav-badvatten&category=integration`

## 4b. Get into the HACS default store (searchable, no custom repo)

Two PRs, in this order:

1. **Brand icon** — required for integrations in the default store. Add
   `icon.png` (256×256) and `logo.png` to
   `custom_integrations/hav_badvatten/` in
   [home-assistant/brands](https://github.com/home-assistant/brands) and open a
   PR. Use an original icon (e.g. a water/wave motif) — do **not** use HaV's
   official logo. See the brands repo guidelines for sizing/transparency.
2. **HACS default** — add `delize/home-assistant-hav-badvatten` to the
   `integration` list in
   [hacs/default](https://github.com/hacs/default) and open a PR. The HACS bot
   re-runs validation; a maintainer merges once it (and the brand) pass.

## What HACS validates (all already satisfied here)

- `custom_components/hav_badvatten/` with a valid `manifest.json`
  (`domain`, `name`, `version`, `documentation`, `issue_tracker`, `codeowners`,
  `iot_class`).
- `hacs.json` with `name` (+ `zip_release`/`filename` here).
- A `README.md` and a `LICENSE`.
- The repo is public, with a description and topics.
- Passes `hassfest` and the `hacs/action` validation (both run in CI).

## Notes

- License is **MIT** (`LICENSE`); change the holder/license if you prefer.
- `manifest.json` `version` is a placeholder between releases — the release
  workflow overwrites it with the tag, which is what ships in the zip.
