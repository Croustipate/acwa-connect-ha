"""Boutons ACWA Connect : amorçage pompe pH."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
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
    async_add_entities([AcwaPhPrimingButton(coordinator)])


class AcwaPhPrimingButton(AcwaEntity, ButtonEntity):
    """
    Amorçage de la pompe doseuse pH-.

    Publie l'impulsion MQTT 0800 sur le slot 1B00 du device relais.
    Déclenche une injection forcée pour purger le tuyau.
    """

    _attr_translation_key = "ph_priming"
    _attr_icon = "mdi:water-pump"

    def __init__(self, coordinator: AcwaDataUpdateCoordinator) -> None:
        super().__init__(coordinator, "ph_priming")

    @property
    def available(self) -> bool:
        return self.coordinator.mqtt is not None and super().available

    async def async_press(self) -> None:
        if self.coordinator.mqtt:
            self.coordinator.mqtt.publish_ph_prime()
