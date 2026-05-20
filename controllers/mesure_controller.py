"""Contrôleur des mesures"""

from flask import Blueprint, request, jsonify
from datetime import datetime
from database import get_db, commit_session, rollback_session
from models import Mesure
from sqlalchemy import text
from services.alert_email_service import send_alerte_email

mesure_bp = Blueprint('mesure', __name__, url_prefix='/api/mesures')

@mesure_bp.route('', methods=['POST'])
def create_mesure():
    try:
        data = request.get_json()
        
        required_fields = ['idEntrepot', 'temperature', 'humidite']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Champ requis: {field}'}), 400
        
        session = get_db()
        
        mesure = Mesure(
            idEntrepot=data['idEntrepot'],
            temperature=float(data['temperature']),
            humidite=float(data['humidite']),
            datMesure=datetime.fromisoformat(data['datMesure'].replace('Z', '+00:00')) if 'datMesure' in data else datetime.utcnow()
        )
        
        session.add(mesure)

        # ---- LOGIQUE ALERTES ----

        row = session.execute(text("""
            SELECT 
                p.temperatureMin,
                p.temperatureMax,
                p.humiditeMin,
                p.humiditeMax,
                e.nom AS entrepotNom
            FROM Entrepot e
            JOIN Exploitation ex ON e.idExploitation = ex.idExploitation
            JOIN Pays p ON ex.idPays = p.idPays
            WHERE e.idEntrepot = :idEntrepot
        """), {"idEntrepot": data['idEntrepot']}).fetchone()

        if row:
            session.flush()

            temp_hors_plage = mesure.temperature < row.temperatureMin or mesure.temperature > row.temperatureMax
            hum_hors_plage  = mesure.humidite   < row.humiditeMin    or mesure.humidite   > row.humiditeMax

            if temp_hors_plage or hum_hors_plage:
                session.execute(text("""
                    INSERT INTO Alertes (idMesure) 
                    VALUES (:idMesure)
                """), {'idMesure': mesure.idMesure})

                # Envoi de l'email d'alerte
                send_alerte_email(
                    id_entrepot=data['idEntrepot'],
                    entrepot_nom=row.entrepotNom,
                    temperature=mesure.temperature,
                    humidite=mesure.humidite,
                    temp_hors_plage=temp_hors_plage,
                    hum_hors_plage=hum_hors_plage,
                    seuils={
                        'temperatureMin': row.temperatureMin,
                        'temperatureMax': row.temperatureMax,
                        'humiditeMin':    row.humiditeMin,
                        'humiditeMax':    row.humiditeMax,
                    },
                    dat_mesure=mesure.datMesure.strftime('%d/%m/%Y %H:%M:%S')
                )

        # ---- FIN ----

        result = mesure.to_dict()
        session.commit()
        session.close()
        
        return jsonify(result), 201
        
    except Exception as e:
        session.rollback()
        session.close()
        print(f"Erreur: {e}")
        return jsonify({'error': str(e)}), 500

@mesure_bp.route('/entrepot/<string:entrepot_id>', methods=['GET'])
def get_mesures_by_entrepot(entrepot_id):
    try:
        session = get_db()
        
        query = session.query(Mesure).filter(Mesure.idEntrepot == entrepot_id)
        
        from_date = request.args.get('from_date')
        if from_date:
            from_date_dt = datetime.fromisoformat(from_date.replace('Z', '+00:00'))
            query = query.filter(Mesure.datMesure >= from_date_dt)
        
        limit = request.args.get('limit', 100, type=int)
        mesures = query.order_by(Mesure.datMesure.desc()).limit(limit).all()
        
        result = [mesure.to_dict() for mesure in mesures]
        session.close()
        
        return jsonify(result), 200
        
    except Exception as e:
        rollback_session()
        return jsonify({'error': str(e)}), 500

@mesure_bp.route('/<string:mesure_id>', methods=['GET'])
def get_mesure(mesure_id):
    try:
        session = get_db()
        mesure = session.query(Mesure).filter(Mesure.idMesure == mesure_id).first()
        
        if not mesure:
            session.close()
            return jsonify({'error': 'Mesure non trouvée'}), 404
        
        result = mesure.to_dict()
        session.close()
        
        return jsonify(result), 200
        
    except Exception as e:
        rollback_session()
        return jsonify({'error': str(e)}), 500