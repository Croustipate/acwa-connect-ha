# ACWA Connect — Intégration Home Assistant

Intégration non-officielle pour piloter une piscine équipée d'une **ACWA e.Box** depuis Home Assistant.

Cette intégration a été développée par rétro-ingénierie de l'application officielle ACWA Connect (iOS/Android). Elle utilise à la fois l'API REST ACWA et le broker MQTT Scaleway IoT embarqué dans le système.

---

## Fonctionnalités

### Capteurs (lecture)
| Entité | Description |
|--------|-------------|
| Température eau | °C, depuis la sonde |
| pH | Valeur compensée en centièmes |
| ORP / Redox | mV |
| Puissance pompe | W (en temps réel) |
| Courant pompe | A |
| Vitesse pompe | 0–4 |
| Énergie totale pompe | Wh cumulés (compteur `fvsSCompteurPuissanceActiveTotale`) |
| Dernière alerte | Message texte |
| Connexion cloud | Binaire (MQTT e.Box connecté) |
| Débit eau | Binaire (présence débit) |
| Alarme électrolyseur | Binaire |
| Protection hivernage | Binaire |
| Surdosage pH | Binaire |
| Bidon pH vide | Binaire |
| Défaut sonde pH/Rx | Binaire |

### Commandes (écriture)
| Entité | Type | Protocole |
|--------|------|-----------|
| Pompe filtration | Switch on/off | REST PATCH |
| Électrolyseur | Switch on/off | REST PATCH |
| Régulation pH | Switch on/off | REST PATCH |
| **Éclairage piscine** | Light on/off | **MQTT** |
| **Robot / Surpresseur** | Switch on/off | **MQTT** |
| **Amorçage pompe pH** | Button | **MQTT** |
| Volet piscine | Cover open/close/stop | REST PATCH |
| Consigne pH | Number 6.8–7.8 | REST PATCH |
| Consigne ORP | Number 550–850 mV | REST PATCH |
| Vitesse manuelle pompe | Number 1–4 | REST PATCH |
| Mode pompe | Select Arrêt/Manuel/Auto | REST PATCH |
| Mode électrolyseur | Select Arrêt/Manuel/Horloge/Rx | REST PATCH |

---

## Architecture technique

### API REST
- Base URL : `https://api.acwa-connect.com/api/v1`
- Authentification : Bearer token (JWT Google → ACWA)
- Lecture : `GET /pool/{id}/data` — retourne une liste de blocs de données
- Écriture : `PATCH /pool/{id}/data` avec les champs à modifier
- Certificat TLS : auto-signé (vérification désactivée)

### MQTT Scaleway IoT
La lumière, le robot/surpresseur et l'amorçage pH ne sont **pas accessibles via REST**. Ils passent par un broker MQTT Scaleway hébergé sur `iot.fr-par.scw.cloud:8883`.

**Protocole des topics :**
```
DEVICE_ID/CRX/DATA/SLOT   → commande app → device (retained)
DEVICE_ID/CTX/DATA/SLOT   → état device → cloud (live)
```

**Slots découverts par analyse différentielle :**
| Slot | Équipement | Payload ON | Payload OFF |
|------|------------|-----------|-------------|
| `0300` | Lumière | `0100` | `0000` |
| `2700` | Robot/Surpresseur | `0001` | `0000` |
| `1B00` | Amorçage pompe pH | `0800` | — |

Les payloads sont des chaînes ASCII représentant des octets en hexadécimal.

**Authentification MQTT :**  
Certificat client TLS (X.509) récupéré depuis `GET /me` :
- `scalewayKey` → clé privée PEM
- `scalewayCert` → certificat client PEM

**Découverte du device_id du module relais :**  
Au premier démarrage, l'intégration s'abonne à `+/CRX/DATA/0300` etc. Le premier message retenu (retained) contient le device_id dans le premier segment du topic. Ce device_id est ensuite persisté dans le Store HA (`acwa_connect_mqtt_{pool_id}`) pour éviter une redécouverte à chaque redémarrage.

### Renouvellement automatique du token
Le token ACWA expire toutes les ~24h. Pour un renouvellement automatique :
1. Fournir le **Google refresh token** à la configuration
2. L'intégration l'utilise pour obtenir un nouvel `id_token` via `oauth2.googleapis.com/token`
3. Cet `id_token` est échangé contre un nouveau token ACWA via `POST /public/signingoogle`

---

## Installation

### Prérequis
- Home Assistant 2024.1 ou supérieur
- Python 3.12+
- Accès au réseau ACWA Connect (pas de proxy requis en prod)

### 1. Copier les fichiers

```bash
cp -r custom_components/acwa_connect /config/custom_components/
```

### 2. Redémarrer Home Assistant

```
Paramètres → Système → Redémarrer
```

### 3. Ajouter l'intégration

```
Paramètres → Appareils et services → Ajouter une intégration → ACWA Connect
```

Renseignez :
- **Token Bearer** : récupéré depuis l'app (voir section suivante)
- **Google refresh token** : optionnel, pour renouvellement automatique

---

## Obtenir les tokens

L'API ACWA Connect n'est pas publique. Les tokens doivent être capturés depuis le trafic réseau de l'application officielle.

### Méthode recommandée : Proxyman (macOS/iOS)

[Proxyman](https://proxyman.io) est un proxy HTTPS avec une interface graphique simple.

#### Étape 1 : Installer le certificat Proxyman sur iOS

1. Lancez Proxyman sur votre Mac
2. Dans l'app iOS Proxyman (ou via Safari sur l'iPhone) : installez le certificat racine Proxyman
3. Activez-le dans `Réglages → Général → Gestion des profils et de l'appareil`
4. Activez la confiance dans `Réglages → Général → À propos → Réglages de confiance des certificats`

#### Étape 2 : Capturer le trafic de l'app ACWA

1. Connectez votre iPhone au même réseau que votre Mac
2. Dans Proxyman : `Certificat → Installer sur iOS via WiFi`
3. Lancez l'app ACWA Connect sur l'iPhone
4. Dans Proxyman : activez le SSL Pinning Bypass pour l'app ACWA
5. Ouvrez une page de l'app (ex: votre piscine)
6. Dans Proxyman, cherchez les requêtes vers `api.acwa-connect.com`

#### Étape 3 : Récupérer les tokens

**Token Bearer (access token) :**  
Dans n'importe quelle requête `GET /api/v1/pool` ou `GET /api/v1/me`, copiez la valeur du header :
```
Authorization: Bearer eyJhbGciOi...
```

**Google refresh token (pour renouvellement automatique) :**  
Cherchez une requête POST vers `oauth2.googleapis.com/token` dans le trafic capturé.
Dans le corps de la réponse, copiez la valeur `refresh_token` (commence par `1//034...`).

> **Note :** Le token Bearer expire en ~24h. Sans Google refresh token, vous devrez le renouveler manuellement. Avec le refresh token, le renouvellement est automatique et permanent.

### Alternative : mitmproxy (CLI)

```bash
pip install mitmproxy
mitmproxy --listen-port 8080
```

Configurez votre iPhone pour utiliser ce proxy, installez le certificat mitmproxy, puis capturez le même trafic.

---

## Récupérer les certificats MQTT (optionnel, pour les outils de debug)

Les certificats MQTT sont disponibles dans la réponse de `GET /api/v1/me` :

```json
{
  "scalewayKey": "-----BEGIN RSA PRIVATE KEY-----\n...",
  "scalewayCert": "-----BEGIN CERTIFICATE-----\n..."
}
```

Pour les utiliser avec les scripts `tools/` :

```bash
mkdir -p ~/acwa_mqtt_certs
# Copiez scalewayKey dans client.key
# Copiez scalewayCert dans client.crt
```

---

## Outils de debug (répertoire `tools/`)

### `mqtt_diff.py` — Analyse différentielle MQTT

Permet de découvrir les topics MQTT utilisés par l'app officielle.

```bash
pip install paho-mqtt>=2.0
python tools/mqtt_diff.py
```

1. Appuyez ENTRÉE → snapshot "avant"
2. Activez un équipement depuis l'app ACWA
3. Appuyez ENTRÉE → snapshot "après"
4. Tapez `d` → affiche les topics qui ont changé

C'est ainsi que les slots `0300` (lumière), `2700` (robot) et `1B00` (amorçage pH) ont été découverts.

### `mqtt_test_cmd.py` — Test direct des commandes

Permet de tester les commandes MQTT indépendamment de Home Assistant.

```bash
# Modifiez DEVICE_ID dans le script avec votre device_id
python tools/mqtt_test_cmd.py light on
python tools/mqtt_test_cmd.py robot off
```

---

## Dépannage

### La lumière / le robot ne répondent pas

1. Vérifiez les logs HA : `Paramètres → Journaux → Filtre "acwa"`
2. Cherchez `MQTT ACWA : connecté au broker Scaleway` — si absent, le certificat est invalide
3. Cherchez `MQTT ACWA : device relais découvert` — si absent, déclenchez une action depuis l'app officielle pour forcer la découverte
4. Vérifiez que `paho-mqtt` est installé (présent dans `manifest.json`)

### Le token expire toutes les 24h

Fournissez le Google refresh token à la configuration. Il est permanent et permet un renouvellement automatique silencieux.

### Home Assistant ne charge pas l'intégration

Supprimez le cache Python avant de redémarrer :
```bash
rm -rf /config/custom_components/acwa_connect/__pycache__
```

### Les entités lumière/robot/amorçage sont "indisponibles"

C'est normal au premier démarrage si le device_id n'a pas encore été découvert. Utilisez l'app officielle une fois pour déclencher des messages CRX — l'intégration découvrira le device automatiquement et persistera l'ID.

---

## Structure du code

```
custom_components/acwa_connect/
├── __init__.py          # Setup entry, init MQTT
├── manifest.json        # Métadonnées HA
├── const.py             # Constantes (API, MQTT slots, modes)
├── coordinator.py       # AcwaApiClient + AcwaMqttClient + DataUpdateCoordinator
├── config_flow.py       # UI de configuration HA
├── entity.py            # Entité de base (DeviceInfo, unique_id)
├── sensor.py            # Capteurs (pH, T°, ORP, énergie...)
├── binary_sensor.py     # Capteurs binaires (alarmes, débit...)
├── switch.py            # Interrupteurs (pompe, électro, robot)
├── light.py             # Lumière (MQTT)
├── button.py            # Bouton amorçage pH (MQTT)
├── cover.py             # Volet (REST)
├── number.py            # Consignes numériques
├── select.py            # Sélecteurs de mode
└── translations/
    └── fr.json          # Traductions françaises

tools/
├── mqtt_diff.py         # Analyse différentielle MQTT
└── mqtt_test_cmd.py     # Test direct des commandes MQTT
```

---

## Avertissements

- Cette intégration est **non-officielle** et n'est pas affiliée à ACWA.
- Elle repose sur une API privée qui peut changer sans préavis.
- La désactivation de la vérification TLS est nécessaire car le broker Scaleway utilise un certificat auto-signé non reconnu par les CA standards.
- Ne commitez jamais vos tokens ou certificats dans un dépôt Git.

---

## Licence

MIT
