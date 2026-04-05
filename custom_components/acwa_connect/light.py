"""Lumière piscine ACWA Connect (commande via MQTT Scaleway)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import AcwaDataUpdateCoordinator
from .entity import AcwaEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: AcwaDataUpdateCoordinator = entry.runtime_data
    async_add_entities([AcwaLight(coordinator)])


class AcwaLight(AcwaEntity, LightEntity):
    """Lumière piscine — on/off via MQTT."""

    _attr_translation_key = "light"
    _attr_icon = "mdi:pool"
    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes = {ColorMode.ONOFF}

    def __init__(self, coordinator: AcwaDataUpdateCoordinator) -> None:
        super().__init__(coordinator, "light")

    @property
    def is_on(self) -> bool:
        return self.pool.light_on

    @property
    def available(self) -> bool:
        return self.coordinator.mqtt is not None and super().available

    async def async_turn_on(self, **kwargs: Any) -> None:
        if self.coordinator.mqtt:
            self.coordinator.mqtt.publish_light(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        if self.coordinator.mqtt:
            self.coordinator.mqtt.publish_light(False)
