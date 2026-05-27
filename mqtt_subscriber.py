"""Subscriber MQTT — reçoit les mesures et les erreurs capteur de l'ESP32
et les transmet à la BDD / au service de mails.

Corrections appliquées :
- Rejet de toute mesure sans timestamp (le timestamp doit venir de l'ESP32,
  jamais de l'heure d'insertion).
- Throttling des emails d'alerte (anti-spam).
- Handler dédié pour le topic entrepot/<id>/erreurs (panne capteur).
"""

import os
import json
import time
import threading
from datetime import datetime, timedelta
import paho.mqtt.client as mqtt
from sqlalchemy import text

MQTT_BROKER = os.getenv("MQTT_BROKER", "mosquitto")
MQTT_PORT   = 1883
MQTT_TOPIC_MESURES = "entrepot/+/mesures"
MQTT_TOPIC_ERREURS = "entrepot/+/erreurs"

# Anti-spam : on ne renvoie pas un mail identique avant ce délai
ALERT_COOLDOWN = timedelta(minutes=int(os.getenv("ALERT_COOLDOWN_MIN", "30")))

# Mémoire process : { (idEntrepot, kind) : datetime_dernier_envoi }
_last_sent = {}
_lock = threading.Lock()


def _should_send(id_entrepot: int, kind: str) -> bool:
    """True si on n'a pas envoyé d'alerte de ce type récemment."""
    with _lock:
        key = (id_entrepot, kind)
        last = _last_sent.get(key)
        now = datetime.utcnow()
        if last is None or (now - last) > ALERT_COOLDOWN:
            _last_sent[key] = now
            return True
        return False


def wait_for_db_ready(max_wait_seconds: int = 60) -> bool:
    """Attend que la base soit up et que le seed soit terminé."""
    from database import get_db
    start = time.time()
    while time.time() - start < max_wait_seconds:
        try:
            session = get_db()
            count = session.execute(text("SELECT COUNT(*) FROM Entrepot")).scalar()
            session.close()
            if count and count > 0:
                print(f"✅ Base prête ({count} entrepôts détectés)")
                return True
        except Exception as e:
            print(f"⏳ Base pas encore prête : {e}")
        time.sleep(2)
    print("⚠️  Timeout en attendant la base — démarrage du subscriber quand même")
    return False


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("✅ Connecté au broker MQTT")
        client.subscribe(MQTT_TOPIC_MESURES)
        client.subscribe(MQTT_TOPIC_ERREURS)
        print(f"   Abonné à {MQTT_TOPIC_MESURES} et {MQTT_TOPIC_ERREURS}")
    else:
        print(f"❌ Connexion MQTT échouée, code: {rc}")


def on_message(client, userdata, msg):
    """Dispatch selon le topic."""
    if msg.topic.endswith("/erreurs"):
        handle_error_message(msg)
    else:
        handle_mesure_message(msg)


# ============================================================================
# Handler : mesure température / humidité
# ============================================================================
def handle_mesure_message(msg):
    session = None
    try:
        data = json.loads(msg.payload.decode())
        print(f"📨 Mesure reçue : {data}")

        from database import get_db
        from models import Mesure
        from services.alert_email_service import send_alerte_email

        # === Garde-fou : pas de timestamp = pas d'insertion ===================
        # Le timestamp DOIT venir de l'ESP32 (heure de prélèvement). Si l'ESP32
        # n'a pas pu synchroniser son horloge NTP, il ne doit pas publier.
        if 'datMesure' not in data or not data['datMesure']:
            print(f"⚠️  Mesure sans timestamp - rejet "
                  f"(entrepot={data.get('idEntrepot')})")
            return

        session = get_db()

        entrepot_exists = session.execute(
            text("SELECT 1 FROM Entrepot WHERE idEntrepot = :id"),
            {"id": data['idEntrepot']}
        ).fetchone()

        if not entrepot_exists:
            print(f"⚠️  idEntrepot={data['idEntrepot']} inconnu — message ignoré")
            session.close()
            return

        mesure = Mesure(
            idEntrepot=data['idEntrepot'],
            temperature=float(data['temperature']),
            humidite=float(data['humidite']),
            datMesure=datetime.fromisoformat(
                data['datMesure'].replace('Z', '+00:00')
            )
        )
        session.add(mesure)

        row = session.execute(text("""
            SELECT p.temperatureMin, p.temperatureMax,
                   p.humiditeMin, p.humiditeMax,
                   e.nom AS entrepotNom
            FROM Entrepot e
            JOIN Exploitation ex ON e.idExploitation = ex.idExploitation
            JOIN Pays p ON ex.idPays = p.idPays
            WHERE e.idEntrepot = :id
        """), {"id": data['idEntrepot']}).fetchone()

        email_payload = None
        alert_kind = None

        if row:
            session.flush()   # nécessaire pour récupérer mesure.idMesure
            t_ko = mesure.temperature < float(row.temperatureMin) or \
                   mesure.temperature > float(row.temperatureMax)
            h_ko = mesure.humidite    < float(row.humiditeMin)    or \
                   mesure.humidite    > float(row.humiditeMax)

            if t_ko or h_ko:
                session.execute(text(
                    "INSERT INTO Alertes (idMesure) VALUES (:id)"),
                    {"id": mesure.idMesure}
                )

                alert_kind = ("temp" if t_ko else "") + ("hum" if h_ko else "")
                email_payload = {
                    'id_entrepot': data['idEntrepot'],
                    'entrepot_nom': row.entrepotNom,
                    'temperature': float(mesure.temperature),
                    'humidite': float(mesure.humidite),
                    'temp_hors_plage': t_ko,
                    'hum_hors_plage': h_ko,
                    'seuils': {
                        'temperatureMin': float(row.temperatureMin),
                        'temperatureMax': float(row.temperatureMax),
                        'humiditeMin':    float(row.humiditeMin),
                        'humiditeMax':    float(row.humiditeMax),
                    },
                    'dat_mesure': mesure.datMesure.strftime('%d/%m/%Y %H:%M:%S')
                }
        else:
            print(f"⚠️  Aucun pays trouvé pour entrepot {data['idEntrepot']} "
                  f"- vérifie les jointures Entrepot->Exploitation->Pays")

        session.commit()
        session.close()
        session = None
        print("✅ Mesure insérée en BDD")

        # Envoi mail en dehors de la session SQLAlchemy
        if email_payload is not None:
            if _should_send(email_payload['id_entrepot'], alert_kind):
                try:
                    send_alerte_email(**email_payload)
                except Exception as mail_error:
                    print(f"❌ Erreur envoi email : {mail_error}")
            else:
                print(f"🔕 Alerte ignorée (cooldown actif pour "
                      f"{email_payload['id_entrepot']}/{alert_kind})")

    except Exception:
        import traceback
        traceback.print_exc()
        if session is not None:
            try:
                session.rollback()
                session.close()
            except Exception:
                pass


# ============================================================================
# Handler : erreur capteur (NaN, valeurs aberrantes, retour à la normale)
# ============================================================================
def handle_error_message(msg):
    """
    Payload attendu (publié par l'ESP32 sur entrepot/<id>/erreurs) :
      { "idEntrepot": 1, "code": "DHT_NAN", "details": "...",
        "datSignal": "2026-05-22T10:00:00Z" }
    """
    try:
        data = json.loads(msg.payload.decode())
        print(f"🚨 Erreur capteur reçue : {data}")

        from services.alert_email_service import send_sensor_error_email

        id_entrepot = data.get('idEntrepot')
        code        = data.get('code', 'UNKNOWN')
        details     = data.get('details', '')

        if id_entrepot is None:
            print("⚠️  Erreur sans idEntrepot - ignorée")
            return

        # Cooldown spécifique aux erreurs capteur
        if not _should_send(id_entrepot, f"err_{code}"):
            print(f"🔕 Erreur capteur ignorée (cooldown actif)")
            return

        try:
            send_sensor_error_email(id_entrepot, code, details)
        except Exception as mail_error:
            print(f"❌ Erreur envoi email panne capteur : {mail_error}")

    except Exception:
        import traceback
        traceback.print_exc()


# ============================================================================
# Démarrage
# ============================================================================
def start_mqtt_subscriber():
    wait_for_db_ready()

    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message

    for attempt in range(10):
        try:
            client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
            break
        except Exception as e:
            print(f"⏳ Broker MQTT pas joignable ({attempt+1}/10) : {e}")
            time.sleep(3)
    else:
        print("❌ Impossible de joindre le broker MQTT — abandon")
        return

    thread = threading.Thread(target=client.loop_forever)
    thread.daemon = True
    thread.start()
    print("🚀 Subscriber MQTT démarré")