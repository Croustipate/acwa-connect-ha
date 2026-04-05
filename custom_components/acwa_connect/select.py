"""Sélecteurs de mode ACWA Connect : pompe, électrolyseur."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ELECTRO_MODES, PUMP_MODES
from .coordinator import AcwaDataUpdateCoordinator, PoolState
from .entity import AcwaEntity

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class AcwaSelectDescription(SelectEntityDescription):
    current_option_fn: Callable[[PoolState], str] = lambda _: ""
    # Retourne le payload à envoyer pour une option donnée
    select_payload_fn: Callable[[str], dict] = lambda _: {}
    # Mapping option_label → valeur
    options_map: dict[str, int] = None  # type: ignore[assignment]


SELECTS: tuple[AcwaSelectDescription, ...] = (
    AcwaSelectDescription(
        key="pump_mode",
        name="Mode pompe filtration",
        icon="mdi:pump",
        options=list(PUMP_MODES.values()),
        options_map={v: k for k, v in PUMP_MODES.items()},
        current_option_fn=lambda s: PUMP_MODES.get(s.pump_mode, "Arrêt"),
        select_payload_fn=lambda opt: {
            "fvsCModeFonctionnement": {v: k for k, v in PUMP_MODES.items()}.get(opt, 0)
        },
    ),
    AcwaSelectDescription(
        key="electro_mode",
        name="Mode électrolyseur",
        icon="mdi:lightning-bolt-circle",
        options=list(ELECTRO_MODES.values()),
        options_map={v: k for k, v in ELECTRO_MODES.items()},
        current_option_fn=lambda s: ELECTRO_MODES.get(s.electro_mode, "Arrêt"),
        select_payload_fn=lambda opt: {
            "esCModeFonctionnement": {v: k for k, v in ELECTRO_MODES.items()}.get(opt, 0)
        },
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: AcwaDataUpdateCoordinator = entry.runtime_data
    async_add_entities(AcwaSelect(coordinator, desc) for desc in SELECTS)


class AcwaSelect(AcwaEntity, SelectEntity):
    """Sélecteur de mode ACWA Connect."""

    entity_description: AcwaSelectDescription

    def __init__(
        self,
        coordinator: AcwaDataUpdateCoordinator,
        description: AcwaSelectDescription,
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._attr_options = description.options

    @property
    def current_option(self) -> str:
        return self.entity_description.current_option_fn(self.pool)

    async def async_select_option(self, option: str) -> None:
        payload = self.entity_description.select_payload_fn(option)
        await self.coordinator.client.send_command(self.coordinator.pool_id, payload)
        await self.coordinator.async_request_refresh()
