"""Entité de base pour l'intégration ACWA Connect."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import AcwaDataUpdateCoordinator


class AcwaEntity(CoordinatorEntity[AcwaDataUpdateCoordinator]):
    """Entité de base liée au coordinateur ACWA Connect."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: AcwaDataUpdateCoordinator,
        unique_id_suffix: str,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.pool_id}_{unique_id_suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.pool_id)},
            name=coordinator.pool_name,
            manufacturer="ACWA",
            model="e.Box",
        )

    @property
    def pool(self):
        """Raccourci vers les données de la piscine."""
        return self.coordinator.data
