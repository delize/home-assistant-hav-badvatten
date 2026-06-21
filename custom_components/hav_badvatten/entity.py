from __future__ import annotations

from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import ATTRIBUTION, DOMAIN, MANUFACTURER, MAP_URL


class BadvattenEntity(CoordinatorEntity[DataUpdateCoordinator]):
    """Base entity: shared device, attribution and combined-data accessors."""

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        entry_id: str,
        key: str,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry_id}_{key}"
        self._attr_translation_key = key

        bath_id = self._bath_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name=self._bathing_water.get("name") or "Badplats",
            manufacturer=MANUFACTURER,
            model=bath_id,
            configuration_url=(MAP_URL.format(bath_id=bath_id) if bath_id else None),
        )

    @property
    def _data(self) -> dict:
        """The combined v2 /bathing-waters/{id} object, with weather attached.

        The Open-Meteo ``current`` block and the SMHI algae compilation (each
        or None) are exposed under the ``weather`` / ``algae`` keys so those
        sensors share the same ``value_fn(data)`` contract as the HaV sensors.
        """
        payload = self.coordinator.data or {}
        bath = payload.get("bath") or {}
        return {
            **bath,
            "weather": payload.get("weather"),
            "algae": payload.get("algae"),
        }

    @property
    def _bath_id(self) -> str | None:
        return (self.coordinator.data or {}).get("bath_id")

    @property
    def _bathing_water(self) -> dict:
        return self._data.get("bathingWater") or {}

    @property
    def _profile(self) -> dict:
        return self._data.get("profile") or {}

    @property
    def _results(self) -> list[dict]:
        return self._data.get("results") or []
