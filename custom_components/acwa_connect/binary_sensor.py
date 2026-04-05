"""Capteurs binaires ACWA Connect : alarmes, débit, hivernage."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import AcwaDataUpdateCoordinator, PoolState
from .entity import AcwaEntity


@dataclass(frozen=True, kw_only=True)
class AcwaBinarySensorDescription(BinarySensorEntityDescription):
    value_fn: Callable[[PoolState], bool] = lambda _: False


BINARY_SENSORS: tuple[AcwaBinarySensorDescription, ...] = (
    AcwaBinarySensorDescription(
        key="flow",
        name="Débit eau",
        device_class=BinarySensorDeviceClass.RUNNING,
        icon="mdi:water-pump",
        value_fn=lambda s: s.flow,
    ),
    AcwaBinarySensorDescription(
        key="mqtt_connected",
        name="Connexion cloud",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        value_fn=lambda s: s.mqtt_connected,
    ),
    AcwaBinarySensorDescription(
        key="electro_alarm",
        name="Alarme électrolyseur",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda s: s.electro_alarm,
    ),
    AcwaBinarySensorDescription(
        key="electro_winter",
        name="Protection hivernage",
        device_class=BinarySensorDeviceClass.COLD,
        icon="mdi:snowflake",
        value_fn=lambda s: s.electro_winter,
    ),
    AcwaBinarySensorDescription(
        key="ph_overdose",
        name="Protection surdosage pH",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:flask-minus",
        value_fn=lambda s: s.ph_overdose,
    ),
    AcwaBinarySensorDescription(
        key="ph_tank_empty",
        name="Bidon pH vide",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:bottle-tonic-skull-outline",
        value_fn=lambda s: s.ph_tank_empty,
    ),
    AcwaBinarySensorDescription(
        key="ph_probe_ok",
        name="Sonde pH OK",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:ph",
        # PROBLEM = True quand il y a un problème → on inverse
        value_fn=lambda s: not s.ph_probe_ok,
    ),
    AcwaBinarySensorDescription(
        key="rx_probe_ok",
        name="Sonde Rx OK",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:lightning-bolt",
        value_fn=lambda s: not s.rx_probe_ok,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: AcwaDataUpdateCoordinator = entry.runtime_data
    async_add_entities(
        AcwaBinarySensor(coordinator, description) for description in BINARY_SENSORS
    )


class AcwaBinarySensor(AcwaEntity, BinarySensorEntity):
    """Capteur binaire ACWA Connect."""

    entity_description: AcwaBinarySensorDescription

    def __init__(
        self,
        coordinator: AcwaDataUpdateCoordinator,
        description: AcwaBinarySensorDescription,
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool:
        return self.entity_description.value_fn(self.pool)
