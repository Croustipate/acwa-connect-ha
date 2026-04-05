"""Consignes numériques ACWA Connect : pH cible, ORP cible."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfElectricPotential
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import AcwaDataUpdateCoordinator, PoolState
from .entity import AcwaEntity

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class AcwaNumberDescription(NumberEntityDescription):
    value_fn: Callable[[PoolState], float] = lambda _: 0.0
    # Fonction qui convertit la valeur HA en payload API
    payload_fn: Callable[[float], dict] = lambda _: {}


NUMBERS: tuple[AcwaNumberDescription, ...] = (
    AcwaNumberDescription(
        key="ph_setpoint",
        name="Consigne pH",
        icon="mdi:ph",
        native_unit_of_measurement="pH",
        native_min_value=6.8,
        native_max_value=7.8,
        native_step=0.1,
        mode=NumberMode.BOX,
        value_fn=lambda s: s.ph_setpoint,
        # L'API attend pH × 10 (ex: 7.3 → 73)
        payload_fn=lambda v: {"iphPConsigneRegulationPh": round(v * 10)},
    ),
    AcwaNumberDescription(
        key="orp_setpoint",
        name="Consigne ORP / Redox",
        native_unit_of_measurement=UnitOfElectricPotential.MILLIVOLT,
        device_class=NumberDeviceClass.VOLTAGE,
        icon="mdi:lightning-bolt",
        native_min_value=550,
        native_max_value=850,
        native_step=5,
        mode=NumberMode.BOX,
        value_fn=lambda s: float(s.electro_rx_setpoint),
        payload_fn=lambda v: {"esPConsigneRx": int(v)},
    ),
    AcwaNumberDescription(
        key="pump_speed_manual",
        name="Vitesse manuelle pompe",
        icon="mdi:speedometer",
        native_unit_of_measurement=None,
        native_min_value=1,
        native_max_value=4,
        native_step=1,
        mode=NumberMode.SLIDER,
        value_fn=lambda s: float(s.pump_manual_speed),
        payload_fn=lambda v: {"fvsCVitesseManuelle": int(v)},
    ),
    AcwaNumberDescription(
        key="electro_winter_temp",
        name="Seuil température hivernage",
        native_unit_of_measurement="°C",
        icon="mdi:snowflake-thermometer",
        native_min_value=1,
        native_max_value=20,
        native_step=1,
        mode=NumberMode.BOX,
        entity_registry_enabled_default=False,
        value_fn=lambda s: float(s.raw.get("esPTemperatureHivernage", 15)),
        payload_fn=lambda v: {"esPTemperatureHivernage": int(v)},
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: AcwaDataUpdateCoordinator = entry.runtime_data
    async_add_entities(AcwaNumber(coordinator, desc) for desc in NUMBERS)


class AcwaNumber(AcwaEntity, NumberEntity):
    """Consigne numérique ACWA Connect."""

    entity_description: AcwaNumberDescription

    def __init__(
        self,
        coordinator: AcwaDataUpdateCoordinator,
        description: AcwaNumberDescription,
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float:
        return self.entity_description.value_fn(self.pool)

    async def async_set_native_value(self, value: float) -> None:
        payload = self.entity_description.payload_fn(value)
        await self.coordinator.client.send_command(self.coordinator.pool_id, payload)
        await self.coordinator.async_request_refresh()
