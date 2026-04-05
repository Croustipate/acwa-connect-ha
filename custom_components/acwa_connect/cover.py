"""Volet piscine ACWA Connect."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import COVER_CMD_CLOSE, COVER_CMD_OPEN, COVER_CMD_STOP, COVER_CODE
from .coordinator import AcwaDataUpdateCoordinator
from .entity import AcwaEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: AcwaDataUpdateCoordinator = entry.runtime_data
    async_add_entities([AcwaCover(coordinator)])


class AcwaCover(AcwaEntity, CoverEntity):
    """Volet de la piscine."""

    _attr_name = "Volet piscine"
    _attr_device_class = CoverDeviceClass.SHUTTER
    _attr_supported_features = (
        CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP
    )
    _attr_icon = "mdi:roller-shade"

    def __init__(self, coordinator: AcwaDataUpdateCoordinator) -> None:
        super().__init__(coordinator, "cover")

    @property
    def is_closed(self) -> bool | None:
        return self.pool.cover_closed

    @property
    def is_opening(self) -> bool:
        return self.pool.cover_opening

    @property
    def is_closing(self) -> bool:
        return self.pool.cover_closing

    async def async_open_cover(self, **kwargs: Any) -> None:
        await self.coordinator.client.send_command(
            self.coordinator.pool_id,
            {"vo230CCommandeCloud": COVER_CMD_OPEN, "vo230CCodeSaisi": COVER_CODE},
        )
        await self.coordinator.async_request_refresh()

    async def async_close_cover(self, **kwargs: Any) -> None:
        await self.coordinator.client.send_command(
            self.coordinator.pool_id,
            {"vo230CCommandeCloud": COVER_CMD_CLOSE, "vo230CCodeSaisi": COVER_CODE},
        )
        await self.coordinator.async_request_refresh()

    async def async_stop_cover(self, **kwargs: Any) -> None:
        await self.coordinator.client.send_command(
            self.coordinator.pool_id,
            {"vo230CCommandeCloud": COVER_CMD_STOP},
        )
        await self.coordinator.async_request_refresh()
