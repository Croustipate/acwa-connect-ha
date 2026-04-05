#!/usr/bin/env python3
"""
Outil d'analyse différentielle MQTT pour ACWA Connect.

Permet de découvrir les topics et payloads MQTT utilisés par l'app officielle
pour contrôler les équipements (lumière, robot, pompe pH...).

Usage:
  1. Copiez vos certificats dans ~/acwa_mqtt_certs/ :
       - client.crt  (scalewayCert du GET /me)
       - client.key  (scalewayKey du GET /me)
  2. Lancez ce script
  3. Appuyez ENTRÉE pour marquer l'état "AVANT"
  4. Activez un équipement depuis l'app officielle ACWA
  5. Appuyez ENTRÉE pour marquer l'état "APRÈS" et voir le diff

Les topics qui changent entre les deux snapshots correspondent aux commandes
envoyées par l'app. Le topic CRX/DATA/XXXX contient la commande, CTX/DATA/XXXX
contient l'état retourné par le device.
"""

import ssl
import time
import json
import threading
from collections import defaultdict
from pathlib import Path

try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("Installez paho-mqtt : pip install 'paho-mqtt>=2.0'")
    raise

# ── Config ──────────────────────────────────────────────────────────────────
BROKER_HOST = "iot.fr-par.scw.cloud"
BROKER_PORT = 8883
CERT_DIR = Path.home() / "acwa_mqtt_certs"

# ── État ─────────────────────────────────────────────────────────────────────
lock = threading.Lock()
latest: dict[str, bytes] = {}   # topic → dernière payload
snapshots: list[dict] = []       # liste de snapshots pris par l'utilisateur
log_entries: list[dict] = []     # tous les messages reçus avec timestamp

def on_connect(client, userdata, flags, reason_code, properties=None):
    if reason_code == 0:
        print(f"[MQTT] Connecté au broker {BROKER_HOST}")
        client.subscribe("#")
        print("[MQTT] Abonné à # (tous les topics)")
    else:
        print(f"[MQTT] Échec connexion : code {reason_code}")

def on_message(client, userdata, msg):
    with lock:
        latest[msg.topic] = msg.payload
        log_entries.append({
            "t": time.time(),
            "topic": msg.topic,
            "payload": msg.payload.hex(),
        })

def take_snapshot(label: str) -> dict:
    with lock:
        snap = {k: v.hex() for k, v in latest.items()}
    snapshots.append({"label": label, "data": snap})
    print(f"[SNAP] '{label}' — {len(snap)} topics capturés")
    return snap

def diff_snapshots(a: dict, b: dict) -> None:
    all_topics = set(a) | set(b)
    changed = []
    new_topics = []
    for t in sorted(all_topics):
        pa = a.get(t)
        pb = b.get(t)
        if pa is None:
            new_topics.append((t, pb))
        elif pa != pb:
            changed.append((t, pa, pb))

    if not changed and not new_topics:
        print("\n[DIFF] Aucune différence détectée.")
        return

    print(f"\n{'='*70}")
    print(f"DIFF : {len(changed)} topic(s) modifié(s), {len(new_topics)} nouveau(x)")
    print('='*70)

    if new_topics:
        print("\n--- Nouveaux topics ---")
        for t, p in new_topics:
            print(f"  {t}")
            print(f"    AFTER : {p}")

    if changed:
        print("\n--- Topics modifiés ---")
        for t, pa, pb in changed:
            print(f"\n  TOPIC : {t}")
            print(f"  AVANT : {pa}")
            print(f"  APRÈS : {pb}")
            # Analyse byte par byte
            ba = bytes.fromhex(pa)
            bb = bytes.fromhex(pb)
            if len(ba) == len(bb):
                diffs = [(i, ba[i], bb[i]) for i in range(len(ba)) if ba[i] != bb[i]]
                if diffs:
                    print(f"  Bytes différents ({len(diffs)}) :")
                    for i, vb, va in diffs:
                        print(f"    offset {i:4d} (0x{i:04x}) : {vb:3d} (0x{vb:02x}) → {va:3d} (0x{va:02x})")
            else:
                print(f"  Taille changée : {len(ba)} → {len(bb)} bytes")

def print_recent_log(seconds: float = 5.0) -> None:
    """Affiche les messages des N dernières secondes."""
    cutoff = time.time() - seconds
    with lock:
        recent = [e for e in log_entries if e["t"] >= cutoff]
    if not recent:
        print(f"[LOG] Aucun message dans les {seconds:.0f} dernières secondes")
        return
    print(f"\n[LOG] {len(recent)} message(s) dans les {seconds:.0f} dernières secondes :")
    for e in recent:
        print(f"  {e['topic']:50s}  {e['payload'][:80]}{'...' if len(e['payload'])>80 else ''}")

def main():
    # Connexion MQTT
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message

    crt = CERT_DIR / "client.crt"
    key = CERT_DIR / "client.key"

    # TLS : on désactive la vérification du CA serveur (cert auto-signé Scaleway)
    # mais on fournit le certificat client pour l'authentification mutuelle
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    if crt.exists() and key.exists():
        ctx.load_cert_chain(certfile=str(crt), keyfile=str(key))
        print(f"[TLS] Certificats client chargés depuis {CERT_DIR}")
    else:
        print(f"[WARN] Certificats client non trouvés dans {CERT_DIR}")
        print(f"  → Récupérez-les depuis GET /me (scalewayKey et scalewayCert)")
        print(f"  → Enregistrez-les dans {CERT_DIR}/client.key et client.crt")
    client.tls_set_context(ctx)

    print(f"[MQTT] Connexion à {BROKER_HOST}:{BROKER_PORT}...")
    client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
    client.loop_start()

    # Attendre la connexion
    time.sleep(2)

    print("\n" + "="*70)
    print("ANALYSE DIFFÉRENTIELLE MQTT — ACWA Connect")
    print("="*70)
    print("""
Commandes disponibles :
  ENTRÉE         → Prendre un snapshot
  r              → Voir les messages récents (5s)
  d              → Diff entre les 2 derniers snapshots
  q              → Quitter
""")

    while True:
        try:
            cmd = input(">>> ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            break

        if cmd == "q":
            break
        elif cmd == "r":
            print_recent_log(5.0)
        elif cmd == "d":
            if len(snapshots) < 2:
                print("[!] Besoin d'au moins 2 snapshots. Prenez-en d'abord avec ENTRÉE.")
            else:
                a = snapshots[-2]["data"]
                b = snapshots[-1]["data"]
                diff_snapshots(a, b)
        elif cmd == "":
            label = f"snap_{len(snapshots)+1}_{time.strftime('%H:%M:%S')}"
            snap = take_snapshot(label)
            if len(snapshots) >= 2:
                print("  (tapez 'd' pour voir le diff avec le snapshot précédent)")
        else:
            print(f"Commande inconnue : '{cmd}'")

    client.loop_stop()
    client.disconnect()

    # Sauvegarde du log complet
    outfile = Path("/tmp/mqtt_acwa_log.json")
    with lock:
        data = list(log_entries)
    with open(outfile, "w") as f:
        json.dump(data, f, indent=2)
    print(f"\n[LOG] Log complet sauvegardé dans {outfile} ({len(data)} messages)")

if __name__ == "__main__":
    main()
