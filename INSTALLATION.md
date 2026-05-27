# Guide d'installation — FutureKawa

Ce guide explique comment installer et démarrer le projet **sur une machine vierge** (Windows, macOS ou Linux). À la fin de la procédure, la chaîne complète tourne : capteur ESP32 → broker MQTT → base MySQL.

---

## 1. Prérequis

À installer sur la machine cible :

| Outil                                                                 | Pour quoi                                           | Vérification       |
| --------------------------------------------------------------------- | --------------------------------------------------- | ------------------ |
| **Docker Desktop** (Windows/macOS) ou Docker Engine + Compose (Linux) | Lance le backend complet                            | `docker --version` |
| **Git**                                                               | Cloner le repo                                      | `git --version`    |
| **Arduino IDE 2.x**                                                   | Flasher l'ESP32 (uniquement si vous avez une carte) | —                  |

Liens d'installation :

- Docker Desktop : https://www.docker.com/products/docker-desktop/
- Git : https://git-scm.com/downloads
- Arduino IDE : https://www.arduino.cc/en/software

> 💡 Sous Windows, **lancer Docker Desktop** avant de continuer.

---

## 2. Cloner le projet

```bash
git clone https://github.com/quentinchad/futurekawa.git
cd futurekawa
```

---

## 3. Configurer les secrets

### 3.1. Créer le fichier `.env` à la racine

```bash
# Linux / macOS
cp .env.example .env

# Windows PowerShell
Copy-Item .env.example .env
```

Ouvrir `.env` avec un éditeur de texte et **remplir au minimum** :

```env
DB_PASSWORD=<choisir_un_mot_de_passe>
DB_ROOT_PASSWORD=<le_meme_mot_de_passe>
SECRET_KEY=<une_chaine_aleatoire_quelconque>
```

Pour les **emails d'alerte** (optionnel — sans ça, le système tourne mais les alertes ne partent pas par mail) :

1. Créer un compte gratuit sur https://www.mailjet.com/
2. Récupérer les clés sur https://app.mailjet.com/account/apikeys
3. Compléter dans `.env` :
   ```env
   MJ_APIKEY_PUBLIC=<clé_publique>
   MJ_APIKEY_PRIVATE=<clé_privée>
   MJ_EMAIL_SENDER=<email_vérifié_sur_mailjet>
   ```

> ⚠️ Le `.env` n'est jamais committé sur Git (il est dans le `.gitignore`).

---

## 4. Démarrer le backend

```bash
docker compose up -d --build
```

Cette commande **construit et lance 3 conteneurs** :

| Conteneur   | Rôle                       | Port exposé         |
| ----------- | -------------------------- | ------------------- |
| `mosquitto` | Broker MQTT                | `1883`              |
| `db`        | Base MySQL 8               | `3307` (sur l'hôte) |
| `flask`     | API REST + subscriber MQTT | `5000`              |

Premier démarrage : compter ~2 minutes (téléchargement des images Docker + build).

### Vérifier que tout est OK

```bash
docker compose ps
```

Les 3 services doivent être en `running`.

```bash
docker compose logs -f flask
```

Tu dois voir :

```
✅ Base prête (20 entrepôts détectés)
✅ Connecté au broker MQTT
🚀 Subscriber MQTT démarré
```

Appuyer sur `Ctrl+C` pour quitter les logs (le conteneur continue de tourner).

### Tester l'API

Ouvrir dans un navigateur : http://localhost:5000/docs

Tu verras la documentation Swagger interactive de l'API.

---

## 5. Configurer et flasher l'ESP32

Cette étape n'est nécessaire que si tu as une **carte ESP32 physique** avec un capteur DHT22 branché sur la broche GPIO 4.

### 5.1. Trouver l'IP de la machine hôte

L'ESP32 a besoin de l'IP **locale** de la machine qui fait tourner Docker, pour pouvoir y envoyer les mesures.

- **Windows** : ouvrir PowerShell, taper `ipconfig`, repérer la ligne "Adresse IPv4" de la carte Wi-Fi ou Ethernet active.
- **Linux/macOS** : taper `ip -4 addr show` ou `ifconfig`.

Exemple : `192.168.1.42`

> ⚠️ Cette IP doit être sur le **même réseau Wi-Fi** que celui auquel se connectera l'ESP32.

### 5.2. Créer le fichier `config.h`

```bash
# Linux / macOS
cp esp32/config.h.example esp32/main/config.h

# Windows PowerShell
Copy-Item esp32\config.h.example esp32\main\config.h
```

⚠️ **Attention au chemin** : `config.h` doit être dans `esp32/main/` (à côté de `main.ino`), pas à la racine de `esp32/`.

Ouvrir `esp32/main/config.h` et renseigner :

```cpp
const char* WIFI_SSID     = "Nom_de_ton_Wifi";
const char* WIFI_PASSWORD = "Mot_de_passe_Wifi";
const char* MQTT_BROKER   = "192.168.1.42";   // ← IP relevée en 5.1
const int   MQTT_PORT     = 1883;
const int   ID_ENTREPOT   = 1;                // entrepôt en BDD (1 à 20)
const char* MQTT_TOPIC    = "entrepot/1/mesures";  // doit matcher ID_ENTREPOT
```

### 5.3. Configurer Arduino IDE pour l'ESP32

**Première installation seulement :**

1. Ouvrir Arduino IDE
2. **Fichier → Préférences** → dans "URLs additionnelles", coller :
   ```
   https://espressif.github.io/arduino-esp32/package_esp32_index.json
   ```
3. **Outils → Type de carte → Gestionnaire de cartes**, chercher "esp32", installer "esp32 by Espressif Systems"
4. **Outils → Type de carte → ESP32 Arduino → ESP32 Dev Module**

### 5.4. Installer les bibliothèques

**Outils → Gérer les bibliothèques**, installer :

- `PubSubClient` (par Nick O'Leary)
- `DHT sensor library` (par Adafruit)
- `Adafruit Unified Sensor` (par Adafruit)
- `ArduinoJson` (par Benoît Blanchon) — version 6.x

### 5.5. Téléverser le code

1. Brancher l'ESP32 en USB
2. **Outils → Port** → sélectionner le port COM correspondant
3. Ouvrir `esp32/main/main.ino` dans Arduino IDE
4. Cliquer sur le bouton **Téléverser** (flèche vers la droite)

Une fois le téléversement terminé, ouvrir le **Moniteur série** (115200 bauds). Tu dois voir :

```
Tentative initiale de connexion Wi-Fi...
Reconnexion Wi-Fi... OK (192.168.1.55)
Reconnexion MQTT... OK
Temp: 24.3 C | Humidite: 62.0% | en attente: 1
Mesure publiee (reste 0 en attente)
```

---

## 6. Vérifier la chaîne complète

Sur la machine Docker, dans les logs Flask :

```bash
docker compose logs -f flask
```

Environ 1 minute après le boot de l'ESP32, tu dois voir :

```
📨 Message reçu : {'idEntrepot': 1, 'temperature': 24.3, ...}
✅ Mesure insérée en BDD
```

### Vérification SQL directe

```bash
docker compose exec db mysql -uroot -p<DB_ROOT_PASSWORD> futureKawa -e "SELECT * FROM Mesures ORDER BY idMesure DESC LIMIT 5;"
```

Remplacer `<DB_ROOT_PASSWORD>` par la valeur du `.env`.

---

## 7. Tester sans ESP32 physique

Si tu n'as pas de carte ESP32 à disposition, tu peux simuler l'envoi d'une mesure depuis la machine hôte :

```bash
docker compose exec mosquitto mosquitto_pub -h localhost -t "entrepot/1/mesures" -m '{"idEntrepot":1,"temperature":24.5,"humidite":65}'
```

Si la mesure apparaît dans les logs Flask et en BDD, la chaîne backend est fonctionnelle.

Pour tester une **alerte** (mesure hors-plage), envoyer une valeur extrême :

```bash
docker compose exec mosquitto mosquitto_pub -h localhost -t "entrepot/1/mesures" -m '{"idEntrepot":1,"temperature":50,"humidite":99}'
```

Tu dois voir dans les logs un envoi d'email Mailjet (ou un warning "Variables Mailjet manquantes" si tu n'as pas configuré les clés).

---

## 8. Arrêter le projet

```bash
# Arrêt simple (préserve les données MySQL)
docker compose down

# Reset complet (efface la base, rejoue le seed au prochain démarrage)
docker compose down -v
```

> 💡 Le seed `controllers/database.sql` ne s'exécute qu'au **premier démarrage** (quand le volume MySQL est vide). Pour le rejouer, il faut `down -v`.

---

## 9. Dépannage

| Symptôme                                      | Cause probable                                          | Solution                                                                                                                       |
| --------------------------------------------- | ------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| `docker: command not found`                   | Docker pas installé ou pas démarré                      | Lancer Docker Desktop                                                                                                          |
| `docker compose ps` → `flask` en `restarting` | Mot de passe MySQL incohérent                           | Vérifier que `DB_PASSWORD` et `DB_ROOT_PASSWORD` ont la **même valeur**, puis `docker compose down -v && docker compose up -d` |
| ESP32 : `WiFi indisponible`                   | SSID ou mot de passe Wi-Fi faux                         | Corriger `esp32/main/config.h` et re-téléverser                                                                                |
| ESP32 : `Reconnexion MQTT... KO`              | Mauvaise IP du broker                                   | Vérifier l'IP de la machine hôte (`ipconfig`) et la mettre dans `config.h`                                                     |
| Logs Flask : `⚠️ idEntrepot=X inconnu`        | Le `ID_ENTREPOT` du capteur ne correspond à rien en BDD | Vérifier : `docker compose exec db mysql -uroot -p<pwd> futureKawa -e "SELECT idEntrepot, nom FROM Entrepot;"`                 |
| Logs Flask : `Variables Mailjet manquantes`   | Pas grave, les mesures sont quand même insérées en BDD  | Compléter `MJ_APIKEY_*` dans `.env` si on veut les emails                                                                      |
| Port `5000` déjà utilisé                      | Une autre app tourne dessus                             | Changer `5000:5000` → `5001:5000` dans `docker-compose.yml`                                                                    |
| Pare-feu Windows bloque l'ESP32               | Le port 1883 n'est pas ouvert                           | Pare-feu Windows → autoriser le port 1883 entrant TCP                                                                          |

---

## 10. Récap rapide pour quelqu'un de pressé

```bash
# Backend (1 minute)
git clone https://github.com/quentinchad/futurekawa.git
cd futurekawa
cp .env.example .env                              # éditer DB_PASSWORD, MJ_*
docker compose up -d --build

# ESP32 (5 minutes, optionnel)
cp esp32/config.h.example esp32/main/config.h     # éditer SSID + IP broker
# Ouvrir esp32/main/main.ino dans Arduino IDE, installer libs, téléverser
```

C'est tout. Le subscriber MQTT démarre automatiquement avec Flask et écoute les capteurs sur le topic `entrepot/+/mesures`.
