"""
Application Flask FutureKawa

API REST pour la gestion de la chaîne d'approvisionnement du café.
"""

import os
from flask import Flask, jsonify, request
from flask_cors import CORS
from flasgger import Swagger
from database import init_db, test_connection
from mqtt_subscriber import start_mqtt_subscriber
from services.watchdog import start_watchdog

# Import des blueprints pour l'organisation modulaire de l'API
from controllers.pays_controller import pays_bp
from controllers.exploitation_controller import exploitation_bp
from controllers.entrepot_controller import entrepot_bp
from controllers.lot_controller import lot_bp
from controllers.dashboard_controller import dashboard_bp, alerte_bp
from controllers.mesure_controller import mesure_bp


def create_app():
    """Factory function pour créer et configurer l'application Flask"""
    app = Flask(__name__)

    # Configuration de l'application
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY',
                                         'dev-secret-key-change-in-production')
    app.config['DEBUG'] = os.getenv('FLASK_DEBUG', 'True').lower() == 'true'

    # Configuration CORS
    CORS(app, resources={
        r"/api/*": {
            "origins": ["http://localhost:3000", "http://127.0.0.1:3000"],
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization"]
        }
    })

    # Configuration Swagger
    swagger_config = {
        "headers": [],
        "specs": [
            {
                "endpoint": 'apispec_1',
                "route": '/apispec_1.json',
                "rule_filter": lambda rule: True,
                "model_filter": lambda tag: True,
                "title": "API FutureKawa",
                "description": "API REST pour la gestion de la chaîne "
                               "d'approvisionnement du café",
                "version": "1.0.0"
            }
        ],
        "static_url_path": "/flasgger_static",
        "swagger_ui": True,
        "specs_route": "/docs/"
    }
    Swagger(app, config=swagger_config)

    # Enregistrement des blueprints
    app.register_blueprint(pays_bp)
    app.register_blueprint(exploitation_bp)
    app.register_blueprint(entrepot_bp)
    app.register_blueprint(lot_bp)
    app.register_blueprint(mesure_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(alerte_bp)

    # Middleware d'authentification
    @app.before_request
    def validate_token():
        public_routes = ['/docs', '/static/swagger.json', '/api/auth/validate']
        if request.path in public_routes:
            return None
        # TODO: Implémenter la validation avec l'API d'authentification externe
        return None

    @app.route('/api/auth/validate', methods=['GET'])
    def validate_auth():
        # TODO: Implémenter la validation réelle des tokens JWT
        return jsonify({'valid': True}), 200

    # Gestion des erreurs
    @app.errorhandler(404)
    def not_found(error):
        return jsonify({'error': 'Ressource non trouvée'}), 404

    @app.errorhandler(500)
    def internal_error(error):
        return jsonify({'error': 'Erreur interne du serveur'}), 500

    @app.errorhandler(400)
    def bad_request(error):
        return jsonify({'error': 'Requête invalide'}), 400

    # Route de santé
    @app.route('/health', methods=['GET'])
    def health_check():
        return jsonify({'status': 'healthy', 'service': 'FutureKawa API'})

    return app


if __name__ == '__main__':
    """Point d'entrée principal de l'application"""
    print("Initialisation de l'API FutureKawa...")

    if test_connection():
        print("Connexion à la base de données réussie")

        init_db()
        print("Base de données initialisée")

        app = create_app()

        host = os.getenv('HOST', '0.0.0.0')
        port = int(os.getenv('PORT', 5000))

        print(f"API démarrée sur http://{host}:{port}")
        print(f"Documentation disponible sur http://{host}:{port}/docs")

        # Subscriber MQTT (mesures + erreurs capteur)
        start_mqtt_subscriber()

        # Watchdog : détecte les ESP32 muets
        start_watchdog()

        app.run(host=host, port=port,
                debug=app.config['DEBUG'], use_reloader=False)
    else:
        print("Erreur de connexion à la base de données")
        exit(1)