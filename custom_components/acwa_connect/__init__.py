"""Intégration ACWA Connect pour Home Assistant."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_ACCESS_TOKEN,
    CONF_GOOGLE_REFRESH_TOKEN,
    CONF_MQTT_DEVICE_ID,
    CONF_POOL_ID,
    CONF_POOL_NAME,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import AcwaApiClient, AcwaDataUpdateCoordinator, AcwaMqttClient

_LOGGER = logging.getLogger(__name__)

type AcwaConfigEntry = ConfigEntry[AcwaDataUpdateCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: AcwaConfigEntry) -> bool:
    """Initialise l'intégration depuis une entrée de configuration."""
    session = async_get_clientsession(hass)
    client = AcwaApiClient(
        session=session,
        access_token=entry.data[CONF_ACCESS_TOKEN],
        google_refresh_token=entry.data.get(CONF_GOOGLE_REFRESH_TOKEN),
    )

    coordinator = AcwaDataUpdateCoordinator(
        hass=hass,
        client=client,
        pool_id=entry.data[CONF_POOL_ID],
        pool_name=entry.data.get(CONF_POOL_NAME, "Piscine"),
    )

    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    # Client MQTT pour la lumière, le robot et l'amorçage pH (certificats via GET /me).
    # Le device_id du module relais doit être renseigné dans les options.
    device_id = (entry.options.get(CONF_MQTT_DEVICE_ID) or "").strip()
    if not device_id:
        _LOGGER.info(
            "ACWA MQTT : device_id du module relais non configuré "
            "(Options de l'intégration) — lumière/robot/amorçage pH indisponibles"
        )
    else:
        try:
            me = await client.get_me()
            scaleway_key = me.get("scalewayKey", "")
            scaleway_cert = me.get("scalewayCert", "")
            if scaleway_key and scaleway_cert:
                mqtt_client = AcwaMqttClient(
                    hass, scaleway_key, scaleway_cert, coordinator, device_id=device_id
                )
                await hass.async_add_executor_job(mqtt_client.start)
                if mqtt_client.is_ready:
                    coordinator.mqtt = mqtt_client
            else:
                _LOGGER.warning(
                    "ACWA MQTT : certificats absents dans /me — lumière/robot indisponibles"
                )
        except Exception as err:
            _LOGGER.warning("ACWA MQTT : erreur initialisation : %s", err, exc_info=True)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: AcwaConfigEntry) -> bool:
    """Décharge l'intégration."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok and (mqtt_client := entry.runtime_data.mqtt) is not None:
        entry.runtime_data.mqtt = None
        # stop() joint le thread paho : hors event loop
        await hass.async_add_executor_job(mqtt_client.stop)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: AcwaConfigEntry) -> None:
    """Recharge l'intégration si les options changent."""
    await hass.config_entries.async_reload(entry.entry_id)
