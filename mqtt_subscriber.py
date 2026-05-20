"""Subscriber MQTT — reçoit les mesures de l'ESP32 et les insère en BDD"""

import os
import json
import time
import threading
from datetime import datetime
import paho.mqtt.client as mqtt
from sqlalchemy import text

MQTT_BROKER = os.getenv("MQTT_BROKER", "mosquitto")
MQTT_PORT   = 1883
MQTT_TOPIC  = "entrepot/+/mesures"


def wait_for_db_ready(max_wait_seconds: int = 60) -> bool:
    """
    Attend que la base soit non seulement up, mais aussi que le seed
    (table Entrepot peuplée) soit terminé.
    """
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
        client.subscribe(MQTT_TOPIC)
    else:
        print(f"❌ Connexion MQTT échouée, code: {rc}")


def on_message(client, userdata, msg):
    session = None
    try:
        data = json.loads(msg.payload.decode())
        print(f"📨 Message reçu : {data}")

        from database import get_db
        from models import Mesure
        from services.alert_email_service import send_alerte_email

        session = get_db()

        # Vérifier que l'entrepôt existe avant d'insérer
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
            datMesure=datetime.fromisoformat(data['datMesure'].replace('Z', '+00:00'))
                      if 'datMesure' in data else datetime.utcnow()
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

        t_ko = False
        h_ko = False

        if row:
            session.flush()
            t_ko = mesure.temperature < row.temperatureMin or \
                   mesure.temperature > row.temperatureMax
            h_ko = mesure.humidite < row.humiditeMin or \
                   mesure.humidite > row.humiditeMax

            if t_ko or h_ko:
                session.execute(text(
                    "INSERT INTO Alertes (idMesure) VALUES (:id)"),
                    {"id": mesure.idMesure}
                )

        session.commit()
        session.close()
        session = None
        print("✅ Mesure insérée en BDD")

        if row and (t_ko or h_ko):
            try:
                send_alerte_email(
                    id_entrepot=data['idEntrepot'],
                    entrepot_nom=row.entrepotNom,
                    temperature=mesure.temperature,
                    humidite=mesure.humidite,
                    temp_hors_plage=t_ko,
                    hum_hors_plage=h_ko,
                    seuils={
                        'temperatureMin': row.temperatureMin,
                        'temperatureMax': row.temperatureMax,
                        'humiditeMin':    row.humiditeMin,
                        'humiditeMax':    row.humiditeMax,
                    },
                    dat_mesure=mesure.datMesure.strftime('%d/%m/%Y %H:%M:%S')
                )
            except Exception as mail_error:
                print(f"❌ Erreur envoi email : {mail_error}")

    except Exception as e:
        import traceback
        traceback.print_exc()
        if session is not None:
            try:
                session.rollback()
                session.close()
            except Exception:
                pass


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