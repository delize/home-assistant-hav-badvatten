from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .entity import BadvattenEntity

# How long an advisory can sit unchanged before it's worth a human re-check.
# Recurring summer blooms sometimes get a "set-and-forget" advisory that's never
# lifted, so flag it (diagnostic) — without ever clearing the safety signal.
ADVISORY_REVIEW_DAYS = 30


def _advisories(data: dict) -> list[dict]:
    return data.get("adviceAgainstBathing") or []


def _latest_advisory(data: dict) -> dict:
    advisories = _advisories(data)
    return advisories[0] if advisories else {}


def _parse_dt(value):
    return dt_util.parse_datetime(str(value)) if value else None


def _advisory_started(data: dict):
    starts = [_parse_dt(a.get("startsAt")) for a in _advisories(data)]
    starts = [s for s in starts if s is not None]
    return min(starts) if starts else None


def _advisory_age_days(data: dict) -> int | None:
    started = _advisory_started(data)
    return (dt_util.utcnow() - started).days if started is not None else None


def _samples_since_advisory(data: dict) -> int:
    started = _advisory_started(data)
    if started is None:
        return 0
    count = 0
    for result in data.get("results") or []:
        taken = _parse_dt(result.get("takenAt"))
        if taken is not None and taken > started:
            count += 1
    return count


@dataclass(frozen=True, kw_only=True)
class BadvattenBinaryDescription(BinarySensorEntityDescription):
    """Binary sensor description plus value/attribute extractors."""

    value_fn: Callable[[dict], bool]
    attr_fn: Callable[[dict], dict[str, Any]] | None = None


BINARY_SENSORS: tuple[BadvattenBinaryDescription, ...] = (
    # LIVE signal: any current "advice against bathing" advisory (e.g. an
    # algal-bloom warning or a swimming ban). on == unsafe.
    BadvattenBinaryDescription(
        key="advice_against_bathing",
        device_class=BinarySensorDeviceClass.SAFETY,
        value_fn=lambda d: bool(_advisories(d)),
        attr_fn=lambda d: {
            "count": len(_advisories(d)),
            "latest": _latest_advisory(d).get("description"),
            "latest_type": _latest_advisory(d).get("typeIdText"),
            "advisories": [
                {
                    "type": a.get("typeIdText"),
                    "type_id": a.get("typeId"),
                    "description": a.get("description"),
                    "starts_at": a.get("startsAt"),
                }
                for a in _advisories(d)
            ],
            "abnormal_situations": [
                {
                    "type": s.get("typeIdText"),
                    "description": s.get("description"),
                    "starts_at": s.get("startsAt"),
                }
                for s in (d.get("abnormalSituations") or [])
            ],
        },
    ),
    # STATIC profile flag: this site is prone to algal/cyanobacterial blooms.
    # NOT a live bloom alert. Deliberately no `safety` device class — it must not
    # read as a live "Safe/Unsafe" verdict competing with advice_against_bathing;
    # it's a diagnostic on/off flag. The live signal is advice_against_bathing.
    BadvattenBinaryDescription(
        key="bloom_risk",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: bool(
            ((d.get("profile") or {}).get("bloomRisk") or {}).get("algae")
            or ((d.get("profile") or {}).get("bloomRisk") or {}).get("cyano")
        ),
        attr_fn=lambda d: {
            "algae": ((d.get("profile") or {}).get("bloomRisk") or {}).get("algae"),
            "cyano": ((d.get("profile") or {}).get("bloomRisk") or {}).get("cyano"),
        },
    ),
    # DIAGNOSTIC: an active advisory left unchanged for a long time (e.g. a
    # recurring-bloom advisory that's never lifted) is worth a human re-check.
    # This does NOT clear the safety signal — advice_against_bathing stays on.
    BadvattenBinaryDescription(
        key="advisory_possibly_outdated",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: (_advisory_age_days(d) or 0) > ADVISORY_REVIEW_DAYS,
        attr_fn=lambda d: {
            "advisory_age_days": _advisory_age_days(d),
            "advisory_since": (
                _advisory_started(d).isoformat()
                if _advisory_started(d) is not None
                else None
            ),
            "samples_since_advisory": _samples_since_advisory(d),
            "note": "Diagnostic only — Advice against bathing is unaffected.",
        },
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        BadvattenBinarySensor(coordinator, entry.entry_id, description)
        for description in BINARY_SENSORS
    )


class BadvattenBinarySensor(BadvattenEntity, BinarySensorEntity):
    """A single declarative HaV badvatten binary sensor."""

    entity_description: BadvattenBinaryDescription

    def __init__(
        self,
        coordinator,
        entry_id: str,
        description: BadvattenBinaryDescription,
    ) -> None:
        super().__init__(coordinator, entry_id, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool:
        return self.entity_description.value_fn(self._data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attr_fn is None:
            return None
        return self.entity_description.attr_fn(self._data)
