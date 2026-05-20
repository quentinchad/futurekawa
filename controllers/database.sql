CREATE DATABASE IF NOT EXISTS futureKawa;
USE futureKawa;

CREATE TABLE Pays(
    idPays INT AUTO_INCREMENT,
    nom VARCHAR(50),
    temperatureMin DECIMAL(15,2),
    temperatureMax DECIMAL(15,2),
    humiditeMin DECIMAL(15,2),
    humiditeMax DECIMAL(15,2),
    PRIMARY KEY(idPays)
);

CREATE TABLE Exploitation(
    idExploitation INT AUTO_INCREMENT,
    nom VARCHAR(50),
    idPays INT NOT NULL,
    PRIMARY KEY(idExploitation),
    FOREIGN KEY(idPays) REFERENCES Pays(idPays)
);

CREATE TABLE Entrepot(
    idEntrepot INT AUTO_INCREMENT,
    nom VARCHAR(50),
    adresse VARCHAR(100),
    limiteQte INT,
    idExploitation INT NOT NULL,
    PRIMARY KEY(idEntrepot),
    FOREIGN KEY(idExploitation) REFERENCES Exploitation(idExploitation)
);

CREATE TABLE LotGrains(
    idLotGrains INT AUTO_INCREMENT,
    datSto DATE,
    statut VARCHAR(10),
    datSortie DATE,
    idEntrepot INT,
    PRIMARY KEY(idLotGrains),
    FOREIGN KEY(idEntrepot) REFERENCES Entrepot(idEntrepot)
);

CREATE TABLE Mesures(
    idMesure INT AUTO_INCREMENT,
    temperature DECIMAL(15,2),
    humidite DECIMAL(15,2),
    datMesure DATETIME,
    idEntrepot INT NOT NULL,
    PRIMARY KEY(idMesure),
    FOREIGN KEY(idEntrepot) REFERENCES Entrepot(idEntrepot)
);

CREATE TABLE Alertes(
    idAlerte INT AUTO_INCREMENT,
    idMesure INT NOT NULL,
    PRIMARY KEY(idAlerte),
    UNIQUE(idMesure),
    FOREIGN KEY(idMesure) REFERENCES Mesures(idMesure)
);

CREATE TABLE Poste(
    idPoste INT AUTO_INCREMENT,
    intitule VARCHAR(100),
    PRIMARY KEY(idPoste)
);

CREATE TABLE Utilisateur(
    idUtilisateur INT AUTO_INCREMENT,
    nom VARCHAR(50),
    prenom VARCHAR(50),
    mail VARCHAR(250),
    mdp VARCHAR(250),
    idExploitation INT NOT NULL,
    idPoste INT NOT NULL DEFAULT 1,
    PRIMARY KEY(idUtilisateur),
    FOREIGN KEY(idExploitation) REFERENCES Exploitation(idExploitation),
    FOREIGN KEY(idPoste) REFERENCES Poste(idPoste)
);

INSERT INTO Poste (intitule) VALUES
('Employé'),
('Responsable exploitation');

INSERT INTO Pays (nom, temperatureMin, temperatureMax, humiditeMin, humiditeMax) VALUES
('Brésil', 18.50, 32.00, 60.00, 90.00),
('Colombie', 15.00, 28.00, 55.00, 85.00),
('Équateur', 12.00, 25.00, 50.00, 80.00);

INSERT INTO Exploitation (nom, idPays) VALUES
('Fazenda Santa Maria', 1), ('Rancho Rio Doce', 1), ('Serra do Cafe', 1), ('Ouro Verde', 1), ('Bahia Coffee', 1), ('Minas Garden', 1),
('Finca La Esperanza', 2), ('El Mirador', 2), ('Cafetal Medellin', 2), ('Sierra Nevada', 2), ('Huila Heights', 2), ('Andes Aroma', 2),
('Amazonia Viva', 3), ('Volcan Pichincha', 3), ('Mitad del Mundo', 3), ('Galapagos Beans', 3), ('Quito Roast', 3), ('Sol de Ecuador', 3);

INSERT INTO Entrepot (nom, adresse, limiteQte, idExploitation) VALUES
('Hangar A1', 'Rua 10, Santos', 5000, 1), ('Silo Central', 'Rua 15, Santos', 10000, 1),
('Stock Sud', 'Av. Brasil, Vitoria', 3000, 2), ('Nord Storage', 'Av. Brasil, Vitoria', 3000, 2),
('Warehouse Alpha', 'Calle 5, Bogota', 4500, 7), ('Silo Principal', 'Calle 8, Bogota', 8000, 7),
('Deposito Norte', 'Carrera 12, Cali', 6000, 8), ('Ecuador Main', 'Av. de los Shyris, Quito', 7000, 13),
('Petit Entrepot', 'Rue de la Paix, Quito', 1500, 14), ('Magasin 5', 'Quito Sector 4', 2000, 15),
('Stock 11', 'Lieu-dit 1', 2500, 3), ('Stock 12', 'Lieu-dit 2', 2500, 4), ('Stock 13', 'Lieu-dit 3', 2500, 5),
('Stock 14', 'Lieu-dit 4', 2500, 6), ('Stock 15', 'Lieu-dit 5', 2500, 9), ('Stock 16', 'Lieu-dit 6', 2500, 10),
('Stock 17', 'Lieu-dit 7', 2500, 11), ('Stock 18', 'Lieu-dit 8', 2500, 12), ('Stock 19', 'Lieu-dit 9', 2500, 16),
('Stock 20', 'Lieu-dit 10', 2500, 17);

INSERT INTO Utilisateur (nom, prenom, mail, mdp, idExploitation, idPoste) VALUES
('Dupont', 'Jean', 'chirat.quentin@gmail.com', 'hash123', 1, 2),
('Silva', 'Maria', 'maria@kawa.com', 'hash123', 1, 1),
('Garcia', 'Carlos', 'carlos@kawa.com', 'hash123', 7, 2),
('Mendoza', 'Elena', 'elena@kawa.com', 'hash123', 13, 2),
('López', 'Juan', 'juan@kawa.com', 'hash123', 2, 1),
('Santos', 'Lucas', 'lucas@kawa.com', 'hash123', 3, 1),
('Ferreira', 'Ana', 'ana@kawa.com', 'hash123', 4, 1),
('Gomez', 'Luis', 'luis@kawa.com', 'hash123', 5, 1),
('Diaz', 'Sofia', 'sofia@kawa.com', 'hash123', 6, 1),
('Torres', 'Diego', 'diego@kawa.com', 'hash123', 8, 1),
('Ruiz', 'Carmen', 'carmen@kawa.com', 'hash123', 9, 1),
('Morales', 'Pablo', 'pablo@kawa.com', 'hash123', 10, 1),
('Castro', 'Isabel', 'isabel@kawa.com', 'hash123', 11, 1),
('Ortiz', 'Javier', 'javier@kawa.com', 'hash123', 12, 1),
('Silva', 'Ricardo', 'ricardo@kawa.com', 'hash123', 14, 1),
('Reyes', 'Marta', 'marta@kawa.com', 'hash123', 15, 1),
('Jimenez', 'Hugo', 'hugo@kawa.com', 'hash123', 16, 1),
('Vargas', 'Laura', 'laura@kawa.com', 'hash123', 17, 1),
('Ramos', 'Oscar', 'oscar@kawa.com', 'hash123', 18, 1),
('Pereira', 'Teresa', 'teresa@kawa.com', 'hash123', 1, 1);

INSERT INTO LotGrains (datSto, statut, datSortie, idEntrepot) VALUES
('2024-01-10', 'Stocké', NULL, 1), ('2024-01-12', 'Vendu', '2024-02-15', 1),
('2024-02-01', 'Stocké', NULL, 2), ('2024-02-05', 'Transit', NULL, 5),
('2024-01-20', 'Stocké', NULL, 8), ('2024-01-25', 'Vendu', '2024-03-01', 8),
('2024-03-01', 'Stocké', NULL, 1), ('2024-03-02', 'Stocké', NULL, 3),
('2024-03-03', 'Stocké', NULL, 4), ('2024-03-04', 'Stocké', NULL, 6),
('2024-03-05', 'Stocké', NULL, 7), ('2024-03-06', 'Stocké', NULL, 9),
('2024-03-07', 'Stocké', NULL, 10), ('2024-03-08', 'Stocké', NULL, 11),
('2024-03-09', 'Stocké', NULL, 12), ('2024-03-10', 'Stocké', NULL, 13),
('2024-03-11', 'Stocké', NULL, 14), ('2024-03-12', 'Stocké', NULL, 15),
('2024-03-13', 'Stocké', NULL, 16), ('2024-03-14', 'Stocké', NULL, 17);