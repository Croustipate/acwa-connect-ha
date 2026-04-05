"""Capteurs ACWA Connect : pH, ORP, température, pompe."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfElectricCurrent,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import AcwaDataUpdateCoordinator, PoolState
from .entity import AcwaEntity


@dataclass(frozen=True, kw_only=True)
class AcwaSensorDescription(SensorEntityDescription):
    value_fn: Callable[[PoolState], float | int | None] = lambda _: None


SENSORS: tuple[AcwaSensorDescription, ...] = (
    AcwaSensorDescription(
        key="temperature",
        translation_key="temperature",
        name="Température eau",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda s: s.temperature,
    ),
    AcwaSensorDescription(
        key="ph",
        translation_key="ph",
        name="pH",
        native_unit_of_measurement="pH",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        icon="mdi:ph",
        value_fn=lambda s: s.ph,
    ),
    AcwaSensorDescription(
        key="orp",
        translation_key="orp",
        name="ORP / Redox",
        native_unit_of_measurement=UnitOfElectricPotential.MILLIVOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda s: s.orp_mv,
    ),
    AcwaSensorDescription(
        key="pump_power",
        translation_key="pump_power",
        name="Puissance pompe",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda s: s.pump_power_w,
    ),
    AcwaSensorDescription(
        key="pump_current",
        translation_key="pump_current",
        name="Courant pompe",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda s: s.pump_current_a,
    ),
    AcwaSensorDescription(
        key="pump_speed",
        translation_key="pump_speed",
        name="Vitesse pompe",
        native_unit_of_measurement=None,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        icon="mdi:speedometer",
        value_fn=lambda s: s.pump_speed,
    ),
    AcwaSensorDescription(
        key="electro_temperature",
        translation_key="electro_temperature",
        name="Température électrolyseur",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
        value_fn=lambda s: s.electro_temperature,
    ),
    AcwaSensorDescription(
        key="last_event",
        translation_key="last_event",
        name="Dernière alerte",
        native_unit_of_measurement=None,
        icon="mdi:bell",
        value_fn=lambda s: s.last_event_message or None,
    ),
    AcwaSensorDescription(
        key="last_event_type",
        translation_key="last_event_type",
        name="Type dernière alerte",
        native_unit_of_measurement=None,
        icon="mdi:bell-badge",
        entity_registry_enabled_default=False,
        value_fn=lambda s: s.last_event_type or None,
    ),
    AcwaSensorDescription(
        key="energy_total",
        translation_key="energy_total",
        name="Énergie totale pompe",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=0,
        entity_registry_enabled_default=True,
        value_fn=lambda s: s.energy_wh_total if s.energy_wh_total else None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: AcwaDataUpdateCoordinator = entry.runtime_data
    async_add_entities(
        AcwaSensor(coordinator, description) for description in SENSORS
    )


class AcwaSensor(AcwaEntity, SensorEntity):
    """Capteur ACWA Connect."""

    entity_description: AcwaSensorDescription

    def __init__(
        self,
        coordinator: AcwaDataUpdateCoordinator,
        description: AcwaSensorDescription,
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | int | None:
        return self.entity_description.value_fn(self.pool)
