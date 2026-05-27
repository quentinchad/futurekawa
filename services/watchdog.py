"""Watchdog : détecte les entrepôts dont le module IoT est silencieux.

Un ESP32 totalement HS (alim coupée, plantage) ne peut pas envoyer
de message d'erreur. On compense côté serveur en vérifiant
périodiquement la fraîcheur des mesures par entrepôt.
"""

import os
import time
import threading
from datetime import datetime, timedelta
from sqlalchemy import text

# Au-delà de N minutes sans mesure pour un entrepôt actif, on alerte
SILENCE_THRESHOLD_MIN = int(os.getenv("WATCHDOG_SILENCE_MIN", "15"))
CHECK_INTERVAL_SEC    = int(os.getenv("WATCHDOG_INTERVAL_SEC", "300"))  # 5 min

# Mémoire process : entrepôts déjà signalés muets (évite spam)
_already_alerted: set[int] = set()


def _check_loop():
    from database import get_db
    from services.alert_email_service import send_sensor_error_email

    while True:
        try:
            session = get_db()
            try:
                # On regarde uniquement les entrepôts qui ont DÉJÀ eu au moins
                # une mesure. Un entrepôt sans ESP32 ne déclenche pas d'alerte.
                rows = session.execute(text("""
                    SELECT idEntrepot, MAX(datMesure) AS derniere
                    FROM Mesures
                    GROUP BY idEntrepot
                """)).fetchall()
            finally:
                session.close()

            now = datetime.utcnow()
            for r in rows:
                if r.derniere is None:
                    continue
                ago = now - r.derniere

                if ago > timedelta(minutes=SILENCE_THRESHOLD_MIN):
                    if r.idEntrepot not in _already_alerted:
                        minutes = int(ago.total_seconds() // 60)
                        print(f"🐶 Watchdog : entrepot {r.idEntrepot} "
                              f"muet depuis {minutes} min")
                        try:
                            send_sensor_error_email(
                                r.idEntrepot,
                                "SENSOR_SILENT",
                                f"Aucune mesure reçue depuis {minutes} minutes. "
                                f"Module IoT probablement hors ligne."
                            )
                            _already_alerted.add(r.idEntrepot)
                        except Exception as mail_error:
                            print(f"❌ Watchdog : envoi mail échoué : {mail_error}")
                else:
                    # L'entrepôt s'est remis à publier
                    _already_alerted.discard(r.idEntrepot)

        except Exception as e:
            print(f"⚠️  Watchdog : erreur boucle : {e}")

        time.sleep(CHECK_INTERVAL_SEC)


def start_watchdog():
    """Démarre le watchdog dans un thread séparé."""
    t = threading.Thread(target=_check_loop, daemon=True)
    t.start()
    print(f"🐶 Watchdog capteurs démarré "
          f"(seuil silence : {SILENCE_THRESHOLD_MIN} min, "
          f"intervalle : {CHECK_INTERVAL_SEC}s)")