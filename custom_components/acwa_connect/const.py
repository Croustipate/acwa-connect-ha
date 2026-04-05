"""Constantes pour l'intégration ACWA Connect."""

DOMAIN = "acwa_connect"

# Configuration
CONF_ACCESS_TOKEN = "access_token"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_POOL_ID = "pool_id"
CONF_POOL_NAME = "pool_name"

# API
API_BASE_URL = "https://api.acwa-connect.com/api/v1"
API_USER_AGENT = "edroapp/26020202 CFNetwork/3860.400.51 Darwin/25.3.0"
API_TIMEOUT = 15
DEFAULT_SCAN_INTERVAL = 30  # secondes

# Google OAuth2 (pour le renouvellement automatique du token ACWA)
CONF_GOOGLE_REFRESH_TOKEN = "google_refresh_token"
# client_id mobile de l'app ACWA Connect (Android/iOS)
GOOGLE_CLIENT_ID = "1098272619367-3hkvu6iolg6moth3qcsmejbc0rrspecc.apps.googleusercontent.com"
# server client_id utilisé comme audience dans l'id_token
GOOGLE_SERVER_CLIENT_ID = "1098272619367-bvdci02mleu8mj10t83mvggl0l3ga843.apps.googleusercontent.com"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"

# Plateformes
PLATFORMS = ["sensor", "binary_sensor", "switch", "cover", "number", "select", "light", "button"]

# Modes pompe filtration (fvsCModeFonctionnement)
PUMP_MODE_OFF = 0
PUMP_MODE_MANUAL = 1
PUMP_MODE_AUTO = 2
PUMP_MODES = {
    PUMP_MODE_OFF: "Arrêt",
    PUMP_MODE_MANUAL: "Manuel",
    PUMP_MODE_AUTO: "Automatique",
}

# Modes électrolyseur (esCModeFonctionnement)
ELECTRO_MODE_OFF = 0
ELECTRO_MODE_MANUAL = 1
ELECTRO_MODE_TIMER = 2
ELECTRO_MODE_AUTO_RX = 3
ELECTRO_MODES = {
    ELECTRO_MODE_OFF: "Arrêt",
    ELECTRO_MODE_MANUAL: "Manuel",
    ELECTRO_MODE_TIMER: "Horloge",
    ELECTRO_MODE_AUTO_RX: "Régulation Rx",
}

# Commandes volet (vo230CCommandeCloud)
COVER_CMD_STOP = 0
COVER_CMD_OPEN = 1
COVER_CMD_CLOSE = 2
COVER_CODE = 10000  # vo230CCodeSaisi

# Vitesses pompe (1–4)
PUMP_SPEED_MIN = 1
PUMP_SPEED_MAX = 4

# MQTT Scaleway IoT
MQTT_BROKER_HOST = "iot.fr-par.scw.cloud"
MQTT_BROKER_PORT = 8883
# Slots DATA dans le protocole binaire ASCII-hex
MQTT_SLOT_LIGHT    = "0300"  # CTX/DATA/0300 → lumière (0100=on, 0000=off)
MQTT_SLOT_ROBOT    = "2700"  # CTX/DATA/2700 → robot/surpresseur (0001=on, 0000=off)
MQTT_SLOT_PH_PRIME = "1B00"  # CRX/DATA/1B00 → amorçage pompe pH (0800=déclencher)
