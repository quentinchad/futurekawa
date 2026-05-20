"""Service d'envoi d'emails d'alertes via Mailjet"""

import os
import requests
from requests.auth import HTTPBasicAuth
from sqlalchemy import text
from database import get_db


def get_responsable_mail(id_entrepot: int) -> list[dict]:
    """
    Récupère les emails des responsables d'exploitation liés à un entrepôt.
    Un responsable correspond à idPoste = 2 dans la table Utilisateur.
    
    Returns:
        Liste de dicts {"nom": ..., "prenom": ..., "mail": ...}
    """
    session = get_db()
    rows = session.execute(text("""
        SELECT u.nom, u.prenom, u.mail
        FROM Utilisateur u
        JOIN Exploitation ex ON u.idExploitation = ex.idExploitation
        JOIN Entrepot e ON e.idExploitation = ex.idExploitation
        WHERE e.idEntrepot = :idEntrepot
        AND u.idPoste = 2
    """), {"idEntrepot": id_entrepot}).fetchall()

    return [{"nom": r.nom, "prenom": r.prenom, "mail": r.mail} for r in rows]


def _build_html_body(
    entrepot_nom: str,
    temperature: float,
    humidite: float,
    temp_hors_plage: bool,
    hum_hors_plage: bool,
    seuils: dict,
    dat_mesure: str,
) -> str:
    """Construit le corps HTML de l'email d'alerte."""

    problemes = []
    if temp_hors_plage:
        problemes.append(
            f"<li><strong>Température</strong> : {temperature}°C "
            f"(plage autorisée : {seuils['temperatureMin']}°C – {seuils['temperatureMax']}°C)</li>"
        )
    if hum_hors_plage:
        problemes.append(
            f"<li><strong>Humidité</strong> : {humidite}% "
            f"(plage autorisée : {seuils['humiditeMin']}% – {seuils['humiditeMax']}%)</li>"
        )

    problemes_html = "\n".join(problemes)

    return f"""
    <html>
    <body style="font-family: Arial, sans-serif; color: #333; max-width: 600px; margin: auto;">
        <div style="background-color: #c0392b; padding: 20px; border-radius: 8px 8px 0 0;">
            <h1 style="color: white; margin: 0;">Alerte Entrepôt</h1>
        </div>
        <div style="padding: 24px; border: 1px solid #ddd; border-top: none; border-radius: 0 0 8px 8px;">
            <p>Une alerte a été déclenchée pour l'entrepôt <strong>{entrepot_nom}</strong>
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
    """
    Envoie un email d'alerte aux responsables d'exploitation de l'entrepôt.

    Args:
        id_entrepot      : identifiant de l'entrepôt concerné
        entrepot_nom     : nom de l'entrepôt (pour affichage)
        temperature      : valeur mesurée
        humidite         : valeur mesurée
        temp_hors_plage  : True si la température est hors seuil
        hum_hors_plage   : True si l'humidité est hors seuil
        seuils           : dict avec les clés temperatureMin/Max, humiditeMin/Max
        dat_mesure       : horodatage de la mesure (chaîne lisible)
    """
    api_key_public  = os.getenv("MJ_APIKEY_PUBLIC")
    api_key_private = os.getenv("MJ_APIKEY_PRIVATE")
    sender_email    = os.getenv("MJ_EMAIL_SENDER", "noreply@futurekawa.com")
    sender_name     = os.getenv("MJ_EMAIL_SENDER_NAME", "FutureKawa Alertes")

    if not api_key_public or not api_key_private:
        print("⚠️  Variables Mailjet manquantes (MJ_APIKEY_PUBLIC / MJ_APIKEY_PRIVATE).")
        return

    destinataires = get_responsable_mail(id_entrepot)
    if not destinataires:
        print(f"ℹ️  Aucun responsable d'exploitation trouvé pour l'entrepôt {id_entrepot}.")
        return

    problemes = []
    if temp_hors_plage:
        problemes.append("température")
    if hum_hors_plage:
        problemes.append("humidité")
    sujet = f"[FutureKawa] Alerte {' & '.join(problemes)} – Entrepôt {entrepot_nom}"

    html_body = _build_html_body(
        entrepot_nom=entrepot_nom,
        temperature=temperature,
        humidite=humidite,
        temp_hors_plage=temp_hors_plage,
        hum_hors_plage=hum_hors_plage,
        seuils=seuils,
        dat_mesure=dat_mesure,
    )

    to_list = [
        {"Email": d["mail"], "Name": f"{d['prenom']} {d['nom']}"}
        for d in destinataires
    ]

    payload = {
        "Messages": [
            {
                "From": {"Email": sender_email, "Name": sender_name},
                "To": to_list,
                "Subject": sujet,
                "HTMLPart": html_body,
            }
        ]
    }

    try:
        response = requests.post(
            "https://api.mailjet.com/v3.1/send",
            json=payload,
            auth=HTTPBasicAuth(api_key_public, api_key_private),
            timeout=10,
        )
        response.raise_for_status()
        print(f"✅ Email d'alerte envoyé à {[d['mail'] for d in destinataires]}")
    except requests.exceptions.RequestException as e:
        # On loggue sans faire planter l'appel principal
        print(f"❌ Échec envoi email Mailjet : {e}")