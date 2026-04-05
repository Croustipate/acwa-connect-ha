"""Config flow pour ACWA Connect."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_ACCESS_TOKEN,
    CONF_GOOGLE_REFRESH_TOKEN,
    CONF_POOL_ID,
    CONF_POOL_NAME,
    CONF_REFRESH_TOKEN,
    DOMAIN,
)
from .coordinator import AcwaApiClient, AcwaAuthError, AcwaApiError

_LOGGER = logging.getLogger(__name__)

STEP_TOKEN_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ACCESS_TOKEN): str,
        vol.Optional(CONF_GOOGLE_REFRESH_TOKEN, default=""): str,
    }
)


class AcwaConnectConfigFlow(ConfigFlow, domain=DOMAIN):
    """Gère le flux de configuration ACWA Connect."""

    VERSION = 1

    def __init__(self) -> None:
        self._access_token: str = ""
        self._google_refresh_token: str = ""
        self._pools: list[dict] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Étape 1 : saisie du token Bearer."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._access_token = user_input[CONF_ACCESS_TOKEN].strip()
            self._google_refresh_token = user_input.get(CONF_GOOGLE_REFRESH_TOKEN, "").strip()

            session = async_get_clientsession(self.hass)
            client = AcwaApiClient(
                session=session,
                access_token=self._access_token,
                google_refresh_token=self._google_refresh_token or None,
            )

            try:
                self._pools = await client.get_pools()
            except AcwaAuthError:
                errors["base"] = "invalid_auth"
            except AcwaApiError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Erreur inattendue lors de la connexion ACWA")
                errors["base"] = "unknown"
            else:
                if len(self._pools) == 1:
                    return await self._create_entry(self._pools[0])
                # Plusieurs piscines → étape de sélection
                return await self.async_step_pick_pool()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_TOKEN_SCHEMA,
            errors=errors,
            description_placeholders={
                "help": (
                    "Capturez le token Bearer depuis l'app ACWA Connect "
                    "avec un proxy (ex : mitmproxy, Charles) et collez-le ici. "
                    "Le token expire toutes les 24h."
                )
            },
        )

    async def async_step_pick_pool(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Étape 2 (optionnelle) : choix de la piscine si plusieurs."""
        if user_input is not None:
            pool_id = user_input["pool"]
            pool = next(p for p in self._pools if p["id"] == pool_id)
            return await self._create_entry(pool)

        pool_options = {p["id"]: p.get("name", p["id"]) for p in self._pools}
        return self.async_show_form(
            step_id="pick_pool",
            data_schema=vol.Schema({vol.Required("pool"): vol.In(pool_options)}),
        )

    async def async_step_reauth(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ré-authentification quand le token expire."""
        return await self.async_step_reauth_confirm(user_input)

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirme la ré-authentification avec un nouveau token."""
        errors: dict[str, str] = {}

        if user_input is not None:
            new_token = user_input[CONF_ACCESS_TOKEN].strip()
            new_refresh = user_input.get(CONF_REFRESH_TOKEN, "").strip()

            session = async_get_clientsession(self.hass)
            client = AcwaApiClient(
                session=session,
                access_token=new_token,
                refresh_token=new_refresh or None,
            )
            try:
                await client.get_pools()
            except (AcwaAuthError, AcwaApiError):
                errors["base"] = "invalid_auth"
            else:
                entry = self._get_reauth_entry()
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={
                        CONF_ACCESS_TOKEN: new_token,
                        CONF_REFRESH_TOKEN: new_refresh or None,
                    },
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_TOKEN_SCHEMA,
            errors=errors,
        )

    async def _create_entry(self, pool: dict) -> ConfigFlowResult:
        pool_id = pool["id"]
        pool_name = pool.get("name", "Piscine")

        await self.async_set_unique_id(pool_id)
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title=pool_name,
            data={
                CONF_ACCESS_TOKEN: self._access_token,
                CONF_GOOGLE_REFRESH_TOKEN: self._google_refresh_token or None,
                CONF_POOL_ID: pool_id,
                CONF_POOL_NAME: pool_name,
            },
        )
