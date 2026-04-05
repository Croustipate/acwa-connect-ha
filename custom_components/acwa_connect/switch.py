"""Interrupteurs ACWA Connect : pompe, électrolyseur, régulation pH."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ELECTRO_MODE_AUTO_RX, ELECTRO_MODE_OFF, PUMP_MODE_AUTO, PUMP_MODE_MANUAL, PUMP_MODE_OFF
from .coordinator import AcwaDataUpdateCoordinator, PoolState
from .entity import AcwaEntity

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class AcwaSwitchDescription(SwitchEntityDescription):
    is_on_fn: Callable[[PoolState], bool] = lambda _: False
    turn_on_payload: dict = None  # type: ignore[assignment]
    turn_off_payload: dict = None  # type: ignore[assignment]


SWITCHES: tuple[AcwaSwitchDescription, ...] = (
    AcwaSwitchDescription(
        key="pump",
        name="Pompe filtration",
        device_class=SwitchDeviceClass.SWITCH,
        icon="mdi:pump",
        is_on_fn=lambda s: s.pump_running or s.pump_mode in (PUMP_MODE_MANUAL, PUMP_MODE_AUTO),
        # L'allumage passe en mode manuel vitesse 3 par défaut
        # La commande exacte est gérée dans turn_on/turn_off
        turn_on_payload={"fvsCModeFonctionnement": PUMP_MODE_MANUAL, "fvsCVitesseManuelle": 3},
        turn_off_payload={"fvsCModeFonctionnement": PUMP_MODE_OFF},
    ),
    AcwaSwitchDescription(
        key="electrolysis",
        name="Électrolyseur",
        device_class=SwitchDeviceClass.SWITCH,
        icon="mdi:lightning-bolt-circle",
        is_on_fn=lambda s: s.electro_running or s.electro_mode != ELECTRO_MODE_OFF,
        turn_on_payload={"esCModeFonctionnement": ELECTRO_MODE_AUTO_RX},
        turn_off_payload={"esCModeFonctionnement": ELECTRO_MODE_OFF},
    ),
    AcwaSwitchDescription(
        key="ph_regulation",
        name="Régulation pH",
        device_class=SwitchDeviceClass.SWITCH,
        icon="mdi:flask",
        is_on_fn=lambda s: s.ph_regulation,
        turn_on_payload={"iphCActivationRegulation": 1},
        turn_off_payload={"iphCActivationRegulation": 0},
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: AcwaDataUpdateCoordinator = entry.runtime_data
    entities: list = [AcwaSwitch(coordinator, desc) for desc in SWITCHES]
    entities.append(AcwaRobotSwitch(coordinator))
    async_add_entities(entities)


class AcwaSwitch(AcwaEntity, SwitchEntity):
    """Interrupteur ACWA Connect."""

    entity_description: AcwaSwitchDescription

    def __init__(
        self,
        coordinator: AcwaDataUpdateCoordinator,
        description: AcwaSwitchDescription,
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool:
        return self.entity_description.is_on_fn(self.pool)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.client.send_command(
            self.coordinator.pool_id, self.entity_description.turn_on_payload
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.client.send_command(
            self.coordinator.pool_id, self.entity_description.turn_off_payload
        )
        await self.coordinator.async_request_refresh()


class AcwaRobotSwitch(AcwaEntity, SwitchEntity):
    """Surpresseur/robot piscine — on/off via MQTT."""

    _attr_translation_key = "robot"
    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_icon = "mdi:robot-vacuum"

    def __init__(self, coordinator: AcwaDataUpdateCoordinator) -> None:
        super().__init__(coordinator, "robot")

    @property
    def is_on(self) -> bool:
        return self.pool.robot_on

    @property
    def available(self) -> bool:
        return self.coordinator.mqtt is not None and super().available

    async def async_turn_on(self, **kwargs: Any) -> None:
        if self.coordinator.mqtt:
            self.coordinator.mqtt.publish_robot(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        if self.coordinator.mqtt:
            self.coordinator.mqtt.publish_robot(False)
