#!/usr/bin/env python3
"""
Test direct des commandes MQTT ACWA.

Permet de vérifier que les commandes MQTT fonctionnent avant d'installer
l'intégration Home Assistant.

Prérequis :
  - Certificats dans ~/acwa_mqtt_certs/client.crt et client.key
  - DEVICE_ID : ID du module relais, découvert avec mqtt_diff.py
    (topic de la forme DEVICE_ID/CRX/DATA/0300)

Usage:
  python mqtt_test_cmd.py light on
  python mqtt_test_cmd.py light off
  python mqtt_test_cmd.py robot on
  python mqtt_test_cmd.py robot off
"""
import ssl, sys, time
from pathlib import Path
import paho.mqtt.client as mqtt

BROKER_HOST = "iot.fr-par.scw.cloud"
BROKER_PORT = 8883
CERT_DIR = Path.home() / "acwa_mqtt_certs"

# Remplacez par votre device_id découvert avec mqtt_diff.py
# (premier segment des topics CRX, ex: "12345678")
DEVICE_ID = "VOTRE_DEVICE_ID_ICI"

COMMANDS = {
    "light": {
        "topic": f"{DEVICE_ID}/CRX/DATA/0300",
        "on":    b"0100",
        "off":   b"0000",
        "state": f"{DEVICE_ID}/CTX/DATA/0300",
    },
    "robot": {
        "topic": f"{DEVICE_ID}/CRX/DATA/2700",
        "on":    b"0001",
        "off":   b"0000",
        "state": f"{DEVICE_ID}/CTX/DATA/2700",
    },
}

def main():
    if len(sys.argv) != 3 or sys.argv[1] not in COMMANDS or sys.argv[2] not in ("on", "off"):
        print("Usage: python mqtt_test_cmd.py <light|robot> <on|off>")
        sys.exit(1)

    if DEVICE_ID == "VOTRE_DEVICE_ID_ICI":
        print("[ERREUR] Modifiez DEVICE_ID dans ce script avant de l'utiliser.")
        print("  → Utilisez mqtt_diff.py pour découvrir votre device_id.")
        sys.exit(1)

    device = sys.argv[1]
    action = sys.argv[2]
    cmd = COMMANDS[device]
    payload = cmd[action]
    topic_cmd = cmd["topic"]
    topic_state = cmd["state"]

    received_state = []

    def on_connect(c, u, f, rc, p=None):
        if rc == 0:
            print(f"[OK] Connecté")
            c.subscribe(topic_state)
            print(f"[>] Envoi commande : {topic_cmd} ← {payload.decode()}")
            c.publish(topic_cmd, payload)
        else:
            print(f"[ERR] Connexion échouée : {rc}")

    def on_message(c, u, m):
        val = m.payload.decode('ascii', errors='replace')
        received_state.append(val)
        state_str = "ON" if val in ("0100", "0001") else "OFF" if val in ("0000",) else val
        print(f"[<] État reçu : {m.topic} = '{val}' → {state_str}")

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    ctx.load_cert_chain(
        certfile=str(CERT_DIR / "client.crt"),
        keyfile=str(CERT_DIR / "client.key"),
    )
    client.tls_set_context(ctx)

    print(f"[..] Connexion à {BROKER_HOST}...")
    client.connect(BROKER_HOST, BROKER_PORT, 60)
    client.loop_start()
    time.sleep(5)
    client.loop_stop()
    client.disconnect()

    if received_state:
        print(f"\n[RÉSULTAT] Commande acceptée — état confirmé par le device")
    else:
        print("\n[WARN] Aucun retour d'état reçu (topic CTX non mis à jour ?)")

if __name__ == "__main__":
    main()
