"""
Module de configuration et gestion de la base de données

Gère la connexion à MySQL/SQLite et les opérations de transaction.
"""

import os
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session
from dotenv import load_dotenv

# Chargement des variables d'environnement
load_dotenv()

# Base pour les modèles SQLAlchemy
Base = declarative_base()

# Variables globales pour la connexion
engine = None
SessionLocal = None

# Configuration pour MySQL (base de données principale pour la production)
# Les paramètres peuvent être configurés via des variables d'environnement
MYSQL_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),      # Hôte du serveur MySQL
    'port': os.getenv('DB_PORT', '3306'),          # Port MySQL par défaut
    'database': os.getenv('DB_NAME', 'futurekawa'), # Nom de la base de données
    'user': os.getenv('DB_USER', 'root'),          # Utilisateur MySQL
    'password': os.getenv('DB_PASSWORD', '')       # Mot de passe MySQL
}

def get_database_url():
    """Construit l'URL de connexion à la base de données"""
    db_type = os.getenv('DB_TYPE', 'mysql')
    
    if db_type == 'mysql':
        host = os.getenv('DB_HOST', 'localhost')
        port = os.getenv('DB_PORT', '3306')
        name = os.getenv('DB_NAME', 'futurekawa')
        user = os.getenv('DB_USER', 'root')
        password = os.getenv('DB_PASSWORD', '')
        
        return f"mysql+pymysql://{user}:{password}@{host}:{port}/{name}"
    else:
        return 'sqlite:///futurekawa.db'

def init_database():
    """Initialise la connexion à la base de données"""
    global engine, SessionLocal
    
    database_url = get_database_url()
    engine = create_engine(database_url, echo=os.getenv('DB_ECHO', 'False').lower() == 'true')
    SessionLocal = scoped_session(sessionmaker(bind=engine))
    
    print(f"Base de données initialisée: {database_url}")

def get_db():
    """Crée une nouvelle session de base de données"""
    if SessionLocal is None:
        init_database()
    return SessionLocal()

def init_db():
    """Initialise la base de données"""
    from models import Pays, Exploitation, Utilisateur, Entrepot, LotGrains, Mesure, Alerte
    
    Base.metadata.create_all(bind=engine)
    print("Tables créées avec succès")

def drop_db():
    """Supprime toutes les tables de la base de données"""
    from models import Pays, Exploitation, Utilisateur, Entrepot, LotGrains, Mesure, Alerte
    
    Base.metadata.drop_all(bind=engine)
    print("Tables supprimées avec succès")

def commit_session(session=None):
    """Valide la transaction en cours"""
    try:
        if session:
            session.commit()
        else:
            SessionLocal.commit()
    except Exception as e:
        print(f"Erreur lors du commit: {e}")
        raise e

def rollback_session(session=None):
    """Annule la transaction en cours"""
    try:
        if session:
            session.rollback()
        else:
            SessionLocal.rollback()
    except Exception as e:
        print(f"Erreur lors du rollback: {e}")
        raise e

def close_session():
    """Ferme la session de base de données"""
    SessionLocal.remove()

def test_connection():
    """Teste la connexion à la base de données"""
    try:
        with get_db() as session:
            session.execute(text("SELECT 1"))
        print("Connexion à la base de données réussie")
        return True
    except Exception as e:
        print(f"Erreur de connexion à la base de données: {e}")
        return False

if __name__ == "__main__":
    """
    Point d'entrée principal pour le module database.py
    
    Lorsqu'exécuté directement, ce script teste la connexion à la base de données
    et l'initialise si la connexion réussit.
    """
    # Test de connexion et initialisation
    if test_connection():
        init_db()
    else:
        print("Impossible de se connecter à la base de données")
