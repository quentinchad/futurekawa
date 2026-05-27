"""Contrôleur des mesures

POST /api/mesures              -> insertion simple d'une mesure (sans logique d'alerte)
GET  /api/mesures/entrepot/:id -> liste des mesures d'un entrepôt (pour le frontend)
GET  /api/mesures/:id          -> détail d'une mesure

NB : la logique d'alerte (détection hors-plage + envoi d'email) est gérée
uniquement par le subscriber MQTT (mqtt_subscriber.py), qui reflète le vrai
flux IoT. Le POST ici est utilisé pour les tests manuels et le backend central.
"""

from flask import Blueprint, request, jsonify
from datetime import datetime
from database import get_db, rollback_session
from models import Mesure

mesure_bp = Blueprint('mesure', __name__, url_prefix='/api/mesures')


@mesure_bp.route('', methods=['POST'])
def create_mesure():
    session = None
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
            datMesure=datetime.fromisoformat(data['datMesure'].replace('Z', '+00:00'))
                      if 'datMesure' in data else datetime.utcnow()
        )

        session.add(mesure)
        session.flush()
        result = mesure.to_dict()
        session.commit()
        session.close()

        return jsonify(result), 201

    except Exception as e:
        if session is not None:
            try:
                session.rollback()
                session.close()
            except Exception:
                pass
        print(f"Erreur création mesure : {e}")
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

        result = [m.to_dict() for m in mesures]
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