"""Service d'envoi d'emails via Brevo (ex-Sendinblue).

Deux types d'emails :
  - send_alerte_email          : conditions hors plage (T° / humidité)
  - send_sensor_error_email    : panne capteur (NaN, valeurs aberrantes,
                                 retour à la normale)

Variables d'environnement attendues :
  BREVO_API_KEY         : clé API (xkeysib-...)
  BREVO_EMAIL_SENDER    : email expéditeur (DOIT être validé dans Brevo)
  BREVO_EMAIL_SENDER_NAME : nom affiché
"""

import os
import requests
from sqlalchemy import text
from database import get_db


# ============================================================================
# Récupération des destinataires
# ============================================================================
def get_responsable_mail(id_entrepot: int) -> list[dict]:
    """
    Récupère les emails des responsables d'exploitation liés à un entrepôt.
    Un responsable correspond à idPoste = 2 dans la table Utilisateur.
    """
    session = get_db()
    try:
        rows = session.execute(text("""
            SELECT u.nom, u.prenom, u.mail
            FROM Utilisateur u
            JOIN Exploitation ex ON u.idExploitation = ex.idExploitation
            JOIN Entrepot e ON e.idExploitation = ex.idExploitation
            WHERE e.idEntrepot = :idEntrepot
              AND u.idPoste = 2
        """), {"idEntrepot": id_entrepot}).fetchall()
    finally:
        session.close()

    return [{"nom": r.nom, "prenom": r.prenom, "mail": r.mail} for r in rows]


# ============================================================================
# Envoi générique Brevo
# ============================================================================
def _send_brevo(to_list: list[dict], subject: str, html_body: str) -> bool:
    """
    Envoie un email via l'API Brevo (https://api.brevo.com/v3/smtp/email).
    Renvoie True si l'API a accepté le message.

    Format `to_list` attendu : [{"email": "...", "name": "..."}, ...]
    """
    api_key      = os.getenv("BREVO_API_KEY")
    sender_email = os.getenv("BREVO_EMAIL_SENDER", "quentin.qojim@gmail.com")
    sender_name  = os.getenv("BREVO_EMAIL_SENDER_NAME", "FutureKawa Alertes")

    if not api_key:
        print("⚠️  Variable BREVO_API_KEY manquante - email non envoyé.")
        return False

    # On filtre les destinataires sans adresse valide
    clean_to = [
        {"email": t["email"], "name": t.get("name", "")}
        for t in to_list
        if t.get("email") and "@" in t["email"]
    ]
    if not clean_to:
        print("ℹ️  Aucun destinataire valide - email non envoyé.")
        return False

    payload = {
        "sender":      {"email": sender_email, "name": sender_name},
        "to":          clean_to,
        "subject":     subject,
        "htmlContent": html_body,
    }

    headers = {
        "accept":       "application/json",
        "content-type": "application/json",
        "api-key":      api_key,
    }

    try:
        response = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            json=payload,
            headers=headers,
            timeout=10,
        )
        print(f"🔍 Brevo HTTP status : {response.status_code}")

        # Brevo répond 201 Created en cas de succès
        if response.status_code in (200, 201):
            try:
                body = response.json()
                msg_id = body.get("messageId", "?")
            except ValueError:
                msg_id = "?"
            print(f"✅ Email envoyé à {[t['email'] for t in clean_to]} "
                  f"(messageId={msg_id})")
            return True

        # Erreur : on log le détail pour pouvoir débugger
        print(f"❌ Brevo a refusé l'envoi : {response.text}")
        return False

    except requests.exceptions.RequestException as e:
        print(f"❌ Échec envoi email Brevo : {e}")
        if hasattr(e, "response") and e.response is not None:
            print(f"   Code HTTP : {e.response.status_code}")
            print(f"   Body : {e.response.text}")
        return False


# ============================================================================
# Email d'alerte : conditions hors plage
# ============================================================================
def _build_alerte_html(
    entrepot_nom: str,
    temperature: float,
    humidite: float,
    temp_hors_plage: bool,
    hum_hors_plage: bool,
    seuils: dict,
    dat_mesure: str,
) -> str:
    problemes = []
    if temp_hors_plage:
        problemes.append(
            f"<li><strong>Température</strong> : {temperature}°C "
            f"(plage autorisée : {seuils['temperatureMin']}°C "
            f"– {seuils['temperatureMax']}°C)</li>"
        )
    if hum_hors_plage:
        problemes.append(
            f"<li><strong>Humidité</strong> : {humidite}% "
            f"(plage autorisée : {seuils['humiditeMin']}% "
            f"– {seuils['humiditeMax']}%)</li>"
        )
    problemes_html = "\n".join(problemes)

    return f"""
    <html>
    <body style="font-family: Arial, sans-serif; color: #333;
                 max-width: 600px; margin: auto;">
        <div style="background-color: #c0392b; padding: 20px;
                    border-radius: 8px 8px 0 0;">
            <h1 style="color: white; margin: 0;">Alerte Entrepôt</h1>
        </div>
        <div style="padding: 24px; border: 1px solid #ddd; border-top: none;
                    border-radius: 0 0 8px 8px;">
            <p>Une alerte a été déclenchée pour l'entrepôt
            <strong>{entrepot_nom}</strong>
            le <strong>{dat_mesure}</strong>.</p>

            <h3 style="color: #c0392b;">Valeurs hors plage :</h3>
            <ul>
                {problemes_html}
            </ul>

            <p style="margin-top: 24px; color: #777; font-size: 12px;">
                Ce message est envoyé automatiquement par le système FutureKawa.<br>
                Merci de ne pas répondre à cet email.
            </p>
        </div>
    </body>
    </html>
    """


def send_alerte_email(
    id_entrepot: int,
    entrepot_nom: str,
    temperature: float,
    humidite: float,
    temp_hors_plage: bool,
    hum_hors_plage: bool,
    seuils: dict,
    dat_mesure: str,
) -> None:
    """Envoie un email d'alerte aux responsables d'exploitation."""
    destinataires = get_responsable_mail(id_entrepot)
    if not destinataires:
        print(f"ℹ️  Aucun responsable d'exploitation pour l'entrepôt {id_entrepot}.")
        return

    problemes = []
    if temp_hors_plage:
        problemes.append("température")
    if hum_hors_plage:
        problemes.append("humidité")
    sujet = f"[FutureKawa] Alerte {' & '.join(problemes)} – Entrepôt {entrepot_nom}"

    html_body = _build_alerte_html(
        entrepot_nom=entrepot_nom,
        temperature=temperature,
        humidite=humidite,
        temp_hors_plage=temp_hors_plage,
        hum_hors_plage=hum_hors_plage,
        seuils=seuils,
        dat_mesure=dat_mesure,
    )

    to_list = [
        {"email": d["mail"], "name": f"{d['prenom']} {d['nom']}"}
        for d in destinataires
    ]
    print(f"🔍 Destinataires construits : {to_list}")

    _send_brevo(to_list, sujet, html_body)


# ============================================================================
# Email d'erreur capteur
# ============================================================================
# Description lisible des codes envoyés par l'ESP32
_ERROR_LABELS = {
    "DHT_NAN":          "Lectures invalides (NaN)",
    "DHT_OUT_OF_RANGE": "Valeurs hors limites physiques",
    "DHT_OK":           "Capteur à nouveau opérationnel",
    "SENSOR_SILENT":    "Capteur muet (aucune mesure reçue)",
    "UNKNOWN":          "Anomalie capteur",
}


def _build_sensor_error_html(id_entrepot: int, code: str, details: str) -> str:
    label = _ERROR_LABELS.get(code, code)

    # Email de "rétablissement" = ton vert ; sinon orange
    if code == "DHT_OK":
        color = "#27ae60"
        title = "✅ Capteur rétabli"
        intro = (f"Le capteur de l'entrepôt <strong>{id_entrepot}</strong> "
                 f"fonctionne à nouveau normalement.")
    else:
        color = "#e67e22"
        title = "⚠️ Panne capteur"
        intro = (f"Le module IoT de l'entrepôt <strong>{id_entrepot}</strong> "
                 f"remonte une anomalie. Une vérification physique est nécessaire.")

    return f"""
    <html>
    <body style="font-family: Arial, sans-serif; color: #333;
                 max-width: 600px; margin: auto;">
        <div style="background-color: {color}; padding: 20px;
                    border-radius: 8px 8px 0 0;">
            <h1 style="color: white; margin: 0;">{title}</h1>
        </div>
        <div style="padding: 24px; border: 1px solid #ddd; border-top: none;
                    border-radius: 0 0 8px 8px;">
            <p>{intro}</p>

            <h3 style="color: {color};">Détails techniques :</h3>
            <ul>
                <li><strong>Entrepôt :</strong> {id_entrepot}</li>
                <li><strong>Code :</strong> <code>{code}</code> ({label})</li>
                <li><strong>Information :</strong> {details}</li>
            </ul>

            <p>Points à vérifier sur place :</p>
            <ul>
                <li>Alimentation du microcontrôleur</li>
                <li>Câblage du capteur (broche data, masse, VCC)</li>
                <li>Connectivité Wi-Fi de la zone</li>
            </ul>

            <p style="margin-top: 24px; color: #777; font-size: 12px;">
                Ce message est envoyé automatiquement par le système FutureKawa.<br>
                Merci de ne pas répondre à cet email.
            </p>
        </div>
    </body>
    </html>
    """


def send_sensor_error_email(id_entrepot: int, code: str, details: str) -> None:
    """Email envoyé quand le module IoT d'un entrepôt remonte un défaut."""
    destinataires = get_responsable_mail(id_entrepot)
    if not destinataires:
        print(f"ℹ️  Aucun responsable d'exploitation pour l'entrepôt {id_entrepot}.")
        return

    label = _ERROR_LABELS.get(code, code)
    if code == "DHT_OK":
        sujet = f"[FutureKawa] Capteur rétabli – Entrepôt {id_entrepot}"
    else:
        sujet = f"[FutureKawa] Panne capteur ({label}) – Entrepôt {id_entrepot}"

    html_body = _build_sensor_error_html(id_entrepot, code, details)

    to_list = [
        {"email": d["mail"], "name": f"{d['prenom']} {d['nom']}"}
        for d in destinataires
    ]

    _send_brevo(to_list, sujet, html_body)