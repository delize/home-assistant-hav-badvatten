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

from .const import DOMAIN
from .entity import BadvattenEntity


def _advisories(data: dict) -> list[dict]:
    return data.get("adviceAgainstBathing") or []


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
