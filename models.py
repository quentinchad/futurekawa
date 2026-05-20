"""
Modèles de données SQLAlchemy pour l'API FutureKawa

Définit toutes les entités de la base de données.
"""

from datetime import datetime
from enum import Enum
from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


# =============================================================================
# ÉNUMÉRATIONS
# =============================================================================

class StatutLot(Enum):
    CONFORME = "conforme"
    EN_ALERTE = "en alerte"
    PERIME = "périmé"

class TypeAlerte(Enum):
    TEMPERATURE_HORS_PLAGE = "Température hors plage"
    HUMIDITE_HORS_PLAGE = "Humidité hors plage"
    LOT_PERIME = "Lot périmé"
    LOT_PROCHE_PEREMPTION = "Lot proche péremption"

class StatutAlerte(Enum):
    EN_COURS = "en cours"
    TRAITEE = "traitée"


# =============================================================================
# MODÈLE: PAYS
# =============================================================================

class Pays(Base):
    __tablename__ = 'Pays'

    idPays = Column(Integer, primary_key=True, autoincrement=True)
    nom = Column(String(100), nullable=False)
    temperatureMin = Column(Float, nullable=False)
    temperatureMax = Column(Float, nullable=False)
    humiditeMin = Column(Float, nullable=False)
    humiditeMax = Column(Float, nullable=False)

    exploitations = relationship("Exploitation", back_populates="pays")

    def to_dict(self):
        return {
            'idPays': self.idPays,
            'nom': self.nom,
            'temperatureMin': self.temperatureMin,
            'temperatureMax': self.temperatureMax,
            'humiditeMin': self.humiditeMin,
            'humiditeMax': self.humiditeMax
        }


# =============================================================================
# MODÈLE: EXPLOITATION
# =============================================================================

class Exploitation(Base):
    __tablename__ = 'Exploitation'

    idExploitation = Column(Integer, primary_key=True, autoincrement=True)
    idPays = Column(Integer, ForeignKey('Pays.idPays'), nullable=False)
    nom = Column(String(150), nullable=False)

    pays = relationship("Pays", back_populates="exploitations")
    entrepots = relationship("Entrepot", back_populates="exploitation")
    utilisateurs = relationship("Utilisateur", back_populates="exploitation")

    def to_dict(self, include_pays=False):
        result = {
            'idExploitation': self.idExploitation,
            'idPays': self.idPays,
            'nom': self.nom
        }
        if include_pays and self.pays:
            result['pays'] = {
                'idPays': self.pays.idPays,
                'nom': self.pays.nom
            }
        return result


# =============================================================================
# MODÈLE: POSTE
# =============================================================================

class Poste(Base):
    __tablename__ = 'Poste'

    idPoste = Column(Integer, primary_key=True, autoincrement=True)
    intitule = Column(String(100), nullable=False)

    utilisateurs = relationship("Utilisateur", back_populates="poste")

    def to_dict(self):
        return {
            'idPoste': self.idPoste,
            'intitule': self.intitule
        }


# =============================================================================
# MODÈLE: UTILISATEUR
# =============================================================================

class Utilisateur(Base):
    __tablename__ = 'Utilisateur'

    idUtilisateur = Column(Integer, primary_key=True, autoincrement=True)
    idExploitation = Column(Integer, ForeignKey('Exploitation.idExploitation'), nullable=False)
    idPoste = Column(Integer, ForeignKey('Poste.idPoste'), nullable=False, default=1)
    nom = Column(String(50), nullable=False)
    prenom = Column(String(50), nullable=False)
    mail = Column(String(250), nullable=False, unique=True)
    mdp = Column(String(250), nullable=False)

    exploitation = relationship("Exploitation", back_populates="utilisateurs")
    poste = relationship("Poste", back_populates="utilisateurs")

    def to_dict(self):
        return {
            'idUtilisateur': self.idUtilisateur,
            'idExploitation': self.idExploitation,
            'idPoste': self.idPoste,
            'nom': self.nom,
            'prenom': self.prenom,
            'mail': self.mail
        }


# =============================================================================
# MODÈLE: ENTREPOT
# =============================================================================

class Entrepot(Base):
    __tablename__ = 'Entrepot'

    idEntrepot = Column(Integer, primary_key=True, autoincrement=True)
    idExploitation = Column(Integer, ForeignKey('Exploitation.idExploitation'), nullable=False)
    nom = Column(String(100), nullable=False)
    adresse = Column(String(255), nullable=False)
    limiteQte = Column(Integer, nullable=False)

    exploitation = relationship("Exploitation", back_populates="entrepots")
    lots = relationship("LotGrains", back_populates="entrepot")
    mesures = relationship("Mesure", back_populates="entrepot")

    def to_dict(self, include_details=False):
        result = {
            'idEntrepot': self.idEntrepot,
            'idExploitation': self.idExploitation,
            'nom': self.nom,
            'adresse': self.adresse,
            'limiteQte': self.limiteQte
        }
        if include_details:
            if self.exploitation:
                result['nomExploitation'] = self.exploitation.nom
            if self.exploitation and self.exploitation.pays:
                result['nomPays'] = self.exploitation.pays.nom
                result['pays'] = {
                    'idPays': self.exploitation.pays.idPays,
                    'nom': self.exploitation.pays.nom,
                    'temperatureMin': self.exploitation.pays.temperatureMin,
                    'temperatureMax': self.exploitation.pays.temperatureMax,
                    'humiditeMin': self.exploitation.pays.humiditeMin,
                    'humiditeMax': self.exploitation.pays.humiditeMax
                }
        return result


# =============================================================================
# MODÈLE: LOT DE GRAINS
# =============================================================================

class LotGrains(Base):
    __tablename__ = 'LotGrains'

    idLotGrains = Column(Integer, primary_key=True, autoincrement=True)
    idEntrepot = Column(Integer, ForeignKey('Entrepot.idEntrepot'), nullable=True)
    datSto = Column(DateTime, nullable=False, default=datetime.utcnow)
    statut = Column(String(10), nullable=False, default='conforme')
    datSortie = Column(DateTime, nullable=True)

    entrepot = relationship("Entrepot", back_populates="lots")

    def to_dict(self, include_hierarchy=False):
        result = {
            'idLotGrains': self.idLotGrains,
            'idEntrepot': self.idEntrepot,
            'datSto': self.datSto.isoformat() if self.datSto else None,
            'statut': self.statut,
            'datSortie': self.datSortie.isoformat() if self.datSortie else None
        }
        if include_hierarchy and self.entrepot:
            result['entrepot'] = {
                'idEntrepot': self.entrepot.idEntrepot,
                'nom': self.entrepot.nom
            }
            if self.entrepot.exploitation:
                result['exploitation'] = {
                    'idExploitation': self.entrepot.exploitation.idExploitation,
                    'nom': self.entrepot.exploitation.nom
                }
                if self.entrepot.exploitation.pays:
                    result['pays'] = {
                        'idPays': self.entrepot.exploitation.pays.idPays,
                        'nom': self.entrepot.exploitation.pays.nom,
                        'temperatureMin': self.entrepot.exploitation.pays.temperatureMin,
                        'temperatureMax': self.entrepot.exploitation.pays.temperatureMax,
                        'humiditeMin': self.entrepot.exploitation.pays.humiditeMin,
                        'humiditeMax': self.entrepot.exploitation.pays.humiditeMax
                    }
        return result


# =============================================================================
# MODÈLE: MESURE
# =============================================================================

class Mesure(Base):
    __tablename__ = 'Mesures'

    idMesure = Column(Integer, primary_key=True, autoincrement=True)
    idEntrepot = Column(Integer, ForeignKey('Entrepot.idEntrepot'), nullable=False)
    temperature = Column(Float, nullable=False)
    humidite = Column(Float, nullable=False)
    datMesure = Column(DateTime, nullable=False, default=datetime.utcnow)

    entrepot = relationship("Entrepot", back_populates="mesures")
    alertes = relationship("Alerte", back_populates="mesure")

    def to_dict(self):
        return {
            'idMesure': self.idMesure,
            'idEntrepot': self.idEntrepot,
            'temperature': self.temperature,
            'humidite': self.humidite,
            'datMesure': self.datMesure.isoformat() if self.datMesure else None
        }


# =============================================================================
# MODÈLE: ALERTE
# =============================================================================

class Alerte(Base):
    __tablename__ = 'Alertes'

    idAlerte = Column(Integer, primary_key=True, autoincrement=True)
    idMesure = Column(Integer, ForeignKey('Mesures.idMesure'), nullable=False)

    mesure = relationship("Mesure", back_populates="alertes")

    def to_dict(self):
        return {
            'idAlerte': self.idAlerte,
            'idMesure': self.idMesure
        }