"""Client API asynchrone et coordinateur de données ACWA Connect."""

from __future__ import annotations

import json
import logging
import os
import ssl
import tempfile
import threading
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    API_BASE_URL,
    API_TIMEOUT,
    API_USER_AGENT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    GOOGLE_CLIENT_ID,
    GOOGLE_SERVER_CLIENT_ID,
    GOOGLE_TOKEN_URL,
    MQTT_BROKER_HOST,
    MQTT_BROKER_PORT,
    MQTT_SLOT_LIGHT,
    MQTT_SLOT_ROBOT,
    MQTT_SLOT_PH_PRIME,
)

_LOGGER = logging.getLogger(__name__)

# Certificat auto-signé Scaleway — on désactive la vérification
_SSL_CONTEXT = ssl.create_default_context()
_SSL_CONTEXT.check_hostname = False
_SSL_CONTEXT.verify_mode = ssl.CERT_NONE


# ---------------------------------------------------------------------------
# Modèle de données
# ---------------------------------------------------------------------------

@dataclass
class PoolState:
    """État consolidé de la piscine."""

    # Sonde (snS)
    ph: float = 0.0
    orp_mv: int = 0
    temperature: float = 0.0
    flow: bool = False
    ph_probe_ok: bool = True
    rx_probe_ok: bool = True

    # Pompe filtration vitesse variable (fvs)
    pump_running: bool = False
    pump_mode: int = 0          # 0=off, 1=manuel, 2=auto
    pump_speed: int = 0         # 0-4
    pump_manual_speed: int = 3
    pump_power_w: float = 0.0
    pump_current_a: float = 0.0

    # Volet (vo230)
    cover_closed: bool = True
    cover_moving: bool = False
    cover_opening: bool = False
    cover_closing: bool = False

    # Électrolyseur (es)
    electro_running: bool = False
    electro_mode: int = 0
    electro_rx_setpoint: int = 720
    electro_alarm: bool = False
    electro_winter: bool = False
    electro_temperature: float = 0.0

    # Pompe pH (iph)
    ph_regulation: bool = False
    ph_setpoint: float = 7.3
    ph_injecting: bool = False
    ph_overdose: bool = False
    ph_tank_empty: bool = False

    # Connexion
    mqtt_connected: bool = False

    # Lumière et robot (MQTT uniquement)
    light_on: bool = False
    robot_on: bool = False

    # Compteurs énergie (issus des champs fvs* du pool data)
    energy_wh_total: int = 0       # fvsSCompteurPuissanceActiveTotale (Wh cumulés)
    apparent_wh_total: int = 0     # fvsSCompteurPuissanceApparenteTotale

    # Dernière alerte
    last_event_message: str = ""
    last_event_type: str = ""
    last_event_at: str = ""

    # Brut (pour debug)
    raw: dict = field(default_factory=dict)

    @classmethod
    def from_api(cls, data_list: list[dict]) -> "PoolState":
        s = cls()
        merged: dict[str, Any] = {}
        for block in data_list:
            merged.update(block)
        s.raw = merged

        # Sonde
        s.ph = merged.get("snSMesurePhCompenseCentieme", 0) / 100.0
        s.orp_mv = merged.get("snSMesureRxCompense", 0)
        s.temperature = merged.get("snSMesureTemperatureEau", 0) / 10.0
        s.flow = bool(merged.get("snSPresenceDebit", 0))
        s.ph_probe_ok = not bool(merged.get("snSDefautSondePh", 0))
        s.rx_probe_ok = not bool(merged.get("snSDefautSondeRx", 0))

        # Pompe filtration (vitesse variable)
        s.pump_running = bool(merged.get("fvsSFonctionnementPompe", 0))
        s.pump_mode = merged.get("fvsCModeFonctionnement", 0)
        s.pump_speed = merged.get("fvsSVitesseFiltration", 0)
        s.pump_manual_speed = merged.get("fvsCVitesseManuelle", 3)
        s.pump_power_w = float(merged.get("fvsSPuissanceActive", 0))
        s.pump_current_a = merged.get("fvsSCourantConsommePompe", 0) / 10.0

        # Volet
        s.cover_closed = bool(merged.get("vo230SEtatVolet", 1))
        s.cover_moving = bool(merged.get("vo230SEtatMoteur", 0))
        s.cover_opening = bool(merged.get("vo230SCommandeOuverture", 0))
        s.cover_closing = bool(merged.get("vo230SCommandeFermeture", 0))

        # Électrolyseur
        s.electro_running = bool(merged.get("esSEtatSortieElectrolyseur", 0))
        s.electro_mode = merged.get("esCModeFonctionnement", 0)
        s.electro_rx_setpoint = merged.get("esPConsigneRx", 720)
        s.electro_alarm = bool(merged.get("esSAlarme", 0))
        s.electro_winter = bool(merged.get("esSProtectionHivernage", 0))
        s.electro_temperature = merged.get("esSMesureTemperature", 0) / 10.0

        # Pompe pH
        s.ph_regulation = bool(merged.get("iphCActivationRegulation", 0))
        s.ph_setpoint = merged.get("iphPConsigneRegulationPh", 73) / 10.0
        s.ph_injecting = bool(merged.get("iphSCommandeInjection", 0))
        s.ph_overdose = bool(merged.get("iphSProtectionSurdosage", 0))
        s.ph_tank_empty = bool(merged.get("iphSFinBidon", 0))

        # Connexion
        s.mqtt_connected = bool(merged.get("cnSEtatConnexionMQTT", 0))

        # Compteurs énergie
        s.energy_wh_total = merged.get("fvsSCompteurPuissanceActiveTotale", 0)
        s.apparent_wh_total = merged.get("fvsSCompteurPuissanceApparenteTotale", 0)

        return s


# ---------------------------------------------------------------------------
# Client API asynchrone
# ---------------------------------------------------------------------------

class AcwaApiError(Exception):
    """Erreur générique API."""


class AcwaAuthError(AcwaApiError):
    """Erreur d'authentification (401)."""


class AcwaApiClient:
    """Client HTTP asynchrone pour l'API ACWA Connect."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        access_token: str,
        refresh_token: str | None = None,
        google_refresh_token: str | None = None,
    ) -> None:
        self._session = session
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._google_refresh_token = google_refresh_token

    @property
    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": API_USER_AGENT,
        }

    async def _request(self, method: str, path: str, **kwargs) -> Any:
        url = f"{API_BASE_URL}/{path}"
        try:
            async with self._session.request(
                method,
                url,
                headers=self._headers,
                ssl=_SSL_CONTEXT,
                timeout=aiohttp.ClientTimeout(total=API_TIMEOUT),
                **kwargs,
            ) as resp:
                if resp.status == 401:
                    if self._google_refresh_token:
                        await self._refresh()
                        # Rejouer avec le nouveau token
                        async with self._session.request(
                            method,
                            url,
                            headers=self._headers,
                            ssl=_SSL_CONTEXT,
                            timeout=aiohttp.ClientTimeout(total=API_TIMEOUT),
                            **kwargs,
                        ) as resp2:
                            if resp2.status == 401:
                                raise AcwaAuthError("Token expiré — reconfigurer l'intégration")
                            resp2.raise_for_status()
                            return await self._parse(resp2)
                    raise AcwaAuthError("Token expiré — reconfigurer l'intégration")
                resp.raise_for_status()
                return await self._parse(resp)
        except AcwaAuthError:
            raise
        except aiohttp.ClientError as err:
            raise AcwaApiError(f"Erreur réseau : {err}") from err

    @staticmethod
    async def _parse(resp: aiohttp.ClientResponse) -> Any:
        """Parse la réponse JSON — fonctionne même en transfer-encoding: chunked."""
        text = await resp.text()
        if not text.strip():
            return {}
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {}

    async def _refresh(self) -> None:
        """
        Renouvelle le token ACWA via le circuit Google OAuth2 :
          1. Refresh token Google → nouvel id_token (avec audience ACWA)
          2. id_token → POST /signingoogle → nouveaux tokens ACWA
        """
        if not self._google_refresh_token:
            raise AcwaAuthError(
                "Google refresh token manquant. "
                "Capturez-le une fois via Proxyman (voir README)."
            )
        try:
            # Étape 1 : obtenir un nouvel id_token Google avec la bonne audience
            form = aiohttp.FormData()
            form.add_field("client_id", GOOGLE_CLIENT_ID)
            form.add_field("grant_type", "refresh_token")
            form.add_field("refresh_token", self._google_refresh_token)
            form.add_field("audience", GOOGLE_SERVER_CLIENT_ID)

            async with self._session.post(
                GOOGLE_TOKEN_URL,
                data=form,
                timeout=aiohttp.ClientTimeout(total=API_TIMEOUT),
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise AcwaAuthError(f"Échec refresh Google ({resp.status}): {body[:200]}")
                google_data = await resp.json()

            id_token = google_data.get("id_token")
            if not id_token:
                raise AcwaAuthError("Google n'a pas retourné d'id_token")

            # Étape 2 : échanger l'id_token contre des tokens ACWA
            async with self._session.post(
                f"{API_BASE_URL}/public/signingoogle",
                json={"access_token": id_token, "lang": "fr", "name": ""},
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": API_USER_AGENT,
                    "Accept": "application/json",
                },
                ssl=_SSL_CONTEXT,
                timeout=aiohttp.ClientTimeout(total=API_TIMEOUT),
            ) as resp:
                if resp.status not in (200, 202):
                    body = await resp.text()
                    raise AcwaAuthError(f"Échec signingoogle ({resp.status}): {body[:200]}")
                acwa_data = await resp.json()

            self._access_token = acwa_data["access_token"]
            if "refresh_token" in acwa_data:
                self._refresh_token = acwa_data["refresh_token"]
            _LOGGER.info("Token ACWA Connect renouvelé automatiquement via Google OAuth2")

        except AcwaAuthError:
            raise
        except aiohttp.ClientError as err:
            raise AcwaAuthError(f"Erreur réseau lors du refresh : {err}") from err

    async def get_pools(self) -> list:
        return await self._request("GET", "pool")

    async def get_pool_data(self, pool_id: str) -> list:
        return await self._request("GET", f"pool/{pool_id}/data")

    async def get_last_events(self, pool_id: str, length: int = 1) -> list:
        import time
        now = int(time.time())
        start = now - 180 * 24 * 3600  # 180 jours en arrière
        return await self._request(
            "GET",
            f"pool/{pool_id}/lastEvents?length={length}&offset=0&startDate={start}&endDate={now}",
        )

    async def send_command(self, pool_id: str, payload: dict) -> None:
        await self._request("PATCH", f"pool/{pool_id}/data", json=payload)

    async def get_me(self) -> dict:
        return await self._request("GET", "me")

    @property
    def access_token(self) -> str:
        return self._access_token


# ---------------------------------------------------------------------------
# Client MQTT Scaleway IoT (lumière + robot)
# ---------------------------------------------------------------------------

class AcwaMqttClient:
    """
    Client MQTT pour les équipements non accessibles via REST.

    Se connecte au broker Scaleway avec les certificats du compte (issus
    de GET /me) et auto-découvre le device_id des relais en écoutant les
    topics CRX (commandes app→device) — le premier device à recevoir des
    commandes CRX est le module relais.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        scaleway_key: str,
        scaleway_cert: str,
        coordinator: "AcwaDataUpdateCoordinator",
        device_id: str | None = None,
        on_device_discovered: Any = None,
    ) -> None:
        self._hass = hass
        self._scaleway_key = scaleway_key
        self._scaleway_cert = scaleway_cert
        self._coordinator = coordinator
        self._client = None
        self._device_id: str | None = device_id
        self._on_device_discovered = on_device_discovered  # callback(device_id)
        self._tmp_files: list[str] = []
        self._lock = threading.Lock()
        if device_id:
            _LOGGER.warning("MQTT ACWA : device_id chargé depuis config : %s", device_id)

    # ── Cycle de vie ────────────────────────────────────────────────────────

    def start(self) -> None:
        """Lance le client paho en thread background."""
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            _LOGGER.warning("MQTT ACWA : paho-mqtt non disponible")
            return

        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        client.on_connect = self._on_connect
        client.on_message = self._on_message
        client.on_disconnect = self._on_disconnect

        try:
            ctx = self._create_ssl_context()
            client.tls_set_context(ctx)
            client.connect_async(MQTT_BROKER_HOST, MQTT_BROKER_PORT, keepalive=60)
            client.loop_start()
            with self._lock:
                self._client = client
            _LOGGER.debug("MQTT ACWA : connexion lancée vers %s", MQTT_BROKER_HOST)
        except Exception as err:
            _LOGGER.warning("MQTT ACWA : démarrage impossible : %s", err)

    def stop(self) -> None:
        """Arrête proprement le client MQTT."""
        with self._lock:
            client = self._client
            self._client = None
        if client:
            try:
                client.loop_stop()
                client.disconnect()
            except Exception:
                pass
        for path in self._tmp_files:
            try:
                os.unlink(path)
            except OSError:
                pass
        self._tmp_files.clear()

    @property
    def is_ready(self) -> bool:
        """Vrai si le client MQTT est connecté et le device découvert."""
        with self._lock:
            return self._client is not None and self._device_id is not None

    # ── Commandes publiques ──────────────────────────────────────────────────

    def publish_light(self, on: bool) -> None:
        payload = b"0100" if on else b"0000"
        self._publish(MQTT_SLOT_LIGHT, payload)

    def publish_robot(self, on: bool) -> None:
        payload = b"0001" if on else b"0000"
        self._publish(MQTT_SLOT_ROBOT, payload)

    def publish_ph_prime(self) -> None:
        """Déclenche l'amorçage de la pompe doseuse pH (impulsion 0800)."""
        self._publish(MQTT_SLOT_PH_PRIME, b"0800")

    # ── Interne ─────────────────────────────────────────────────────────────

    def _create_ssl_context(self) -> ssl.SSLContext:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with tempfile.NamedTemporaryFile(mode="w", suffix=".pem", delete=False) as f:
            f.write(self._scaleway_cert)
            cert_path = f.name
        with tempfile.NamedTemporaryFile(mode="w", suffix=".pem", delete=False) as f:
            f.write(self._scaleway_key)
            key_path = f.name
        self._tmp_files.extend([cert_path, key_path])
        ctx.load_cert_chain(certfile=cert_path, keyfile=key_path)
        return ctx

    def _publish(self, slot: str, payload: bytes) -> None:
        with self._lock:
            client = self._client
            device_id = self._device_id
        if not client or not device_id:
            _LOGGER.warning("MQTT ACWA : client non prêt (device_id=%s)", device_id)
            return
        topic = f"{device_id}/CRX/DATA/{slot}"
        client.publish(topic, payload)
        _LOGGER.debug("MQTT ACWA : publish %s ← %s", topic, payload)

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code == 0:
            _LOGGER.warning("MQTT ACWA : connecté au broker Scaleway")
            # CRX = commandes app→device : retained → donne immédiatement le bon device_id
            client.subscribe(f"+/CRX/DATA/{MQTT_SLOT_LIGHT}")
            client.subscribe(f"+/CRX/DATA/{MQTT_SLOT_ROBOT}")
            client.subscribe(f"+/CRX/DATA/{MQTT_SLOT_PH_PRIME}")
            # CTX = état device→cloud : mises à jour en temps réel
            client.subscribe(f"+/CTX/DATA/{MQTT_SLOT_LIGHT}")
            client.subscribe(f"+/CTX/DATA/{MQTT_SLOT_ROBOT}")
        else:
            _LOGGER.warning("MQTT ACWA : connexion refusée (code %s)", reason_code)

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties=None):
        _LOGGER.warning("MQTT ACWA : déconnecté (code %s)", reason_code)

    def _on_message(self, client, userdata, msg):
        """Appelé depuis le thread paho — mise à jour thread-safe du coordinateur."""
        parts = msg.topic.split("/")
        if len(parts) < 4:
            return
        device_id = parts[0]
        direction = parts[1]  # CTX ou CRX
        slot = parts[-1]
        payload_str = msg.payload.decode("ascii", errors="replace")

        # CRX = commandes venant de l'app → ce device est le module relais
        if direction == "CRX":
            with self._lock:
                if self._device_id is not None:
                    # Device déjà connu — on ignore tous les autres CRX
                    return
                # Premier CRX reçu → c'est notre module relais
                self._device_id = device_id
                _LOGGER.warning(
                    "MQTT ACWA : device relais découvert via CRX : %s", device_id
                )
            if self._on_device_discovered:
                # call_soon_threadsafe car on est dans le thread paho
                self._hass.loop.call_soon_threadsafe(
                    self._on_device_discovered, device_id
                )
                with self._lock:
                    self._on_device_discovered = None
            return  # les CRX ne portent pas l'état courant

        # CTX = état publié par le device
        if direction != "CTX":
            return

        if slot == MQTT_SLOT_LIGHT:
            light_on = payload_str in ("0100", "01")
            self._hass.loop.call_soon_threadsafe(self._set_light, light_on)
        elif slot == MQTT_SLOT_ROBOT:
            robot_on = payload_str in ("0001", "01")
            self._hass.loop.call_soon_threadsafe(self._set_robot, robot_on)

    def _set_light(self, on: bool) -> None:
        if self._coordinator.data is not None:
            self._coordinator.data.light_on = on
            self._coordinator.async_set_updated_data(self._coordinator.data)

    def _set_robot(self, on: bool) -> None:
        if self._coordinator.data is not None:
            self._coordinator.data.robot_on = on
            self._coordinator.async_set_updated_data(self._coordinator.data)


# ---------------------------------------------------------------------------
# Coordinateur de données
# ---------------------------------------------------------------------------

class AcwaDataUpdateCoordinator(DataUpdateCoordinator[PoolState]):
    """Coordinateur qui interroge l'API ACWA Connect toutes les 30 secondes."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: AcwaApiClient,
        pool_id: str,
        pool_name: str,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{pool_id}",
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.client = client
        self.pool_id = pool_id
        self.pool_name = pool_name
        self.mqtt: AcwaMqttClient | None = None

    async def _async_update_data(self) -> PoolState:
        try:
            raw = await self.client.get_pool_data(self.pool_id)
            state = PoolState.from_api(raw)

            # Dernier événement (non bloquant — on ignore si ça échoue)
            try:
                events = await self.client.get_last_events(self.pool_id, length=1)
                if events:
                    ev = events[0]
                    state.last_event_message = ev.get("message", "")
                    state.last_event_type = ev.get("type", "")
                    state.last_event_at = ev.get("createdAt", "")
            except Exception:
                pass

            # Conserver l'état MQTT (lumière/robot) entre les refreshes HTTP
            if self.data is not None:
                state.light_on = self.data.light_on
                state.robot_on = self.data.robot_on

            return state
        except AcwaAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except AcwaApiError as err:
            if self.data is not None:
                # Erreur passagère : on conserve les dernières valeurs connues
                _LOGGER.warning("ACWA : erreur API, données précédentes conservées : %s", err)
                return self.data
            raise UpdateFailed(str(err)) from err
