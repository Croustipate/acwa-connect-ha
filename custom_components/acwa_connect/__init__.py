"""Intégration ACWA Connect pour Home Assistant."""

from __future__ import annotations

import logging

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store

from .const import (
    CONF_ACCESS_TOKEN,
    CONF_GOOGLE_REFRESH_TOKEN,
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

    # Client MQTT pour la lumière et le robot (certificats depuis GET /me)
    try:
        _LOGGER.warning("ACWA MQTT : récupération des certificats via /me...")
        me = await client.get_me()
        scaleway_key = me.get("scalewayKey", "")
        scaleway_cert = me.get("scalewayCert", "")
        _LOGGER.warning(
            "ACWA MQTT : /me reçu — scalewayKey=%s scalewayP12=%s",
            "présent" if scaleway_key else "ABSENT",
            "présent" if me.get("scalewayP12") else "absent",
        )
        if scaleway_key and scaleway_cert:
            # Stockage persistant du device_id sans déclencher de reload
            store = Store(hass, 1, f"acwa_connect_mqtt_{entry.data[CONF_POOL_ID]}")
            stored = await store.async_load() or {}
            saved_device_id: str | None = stored.get("device_id")

            async def on_device_discovered(device_id: str) -> None:
                """Persiste le device_id via Store (pas de reload)."""
                await store.async_save({"device_id": device_id})
                _LOGGER.warning("ACWA MQTT : device_id %s sauvegardé", device_id)

            mqtt_client = AcwaMqttClient(
                hass, scaleway_key, scaleway_cert, coordinator,
                device_id=saved_device_id,
                on_device_discovered=lambda did: hass.async_create_task(
                    on_device_discovered(did)
                ),
            )
            coordinator.mqtt = mqtt_client
            await hass.async_add_executor_job(mqtt_client.start)
            entry.async_on_unload(mqtt_client.stop)
            _LOGGER.warning("ACWA MQTT : client démarré (device_id=%s)", saved_device_id or "à découvrir")
        else:
            _LOGGER.warning("ACWA MQTT : certificats absents dans /me — lumière/robot indisponibles")
    except Exception as err:
        _LOGGER.warning("ACWA MQTT : erreur initialisation : %s", err, exc_info=True)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: AcwaConfigEntry) -> bool:
    """Décharge l'intégration."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(hass: HomeAssistant, entry: AcwaConfigEntry) -> None:
    """Recharge l'intégration si les options changent."""
    await hass.config_entries.async_reload(entry.entry_id)
