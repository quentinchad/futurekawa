#include <WiFi.h>
#include <PubSubClient.h>
#include <DHT.h>
#include <ArduinoJson.h>
#include <time.h>
#include "config.h"   // credentials Wi-Fi + IP broker + coefficients de calibration

#define DHTPIN  4
#define DHTTYPE DHT22
#define INTERVAL_MS (60 * 1000UL)  // 1 mesure / minute

// Buffer circulaire : stocke les mesures quand on est hors-ligne
#define BUFFER_SIZE 120  // 2h d'autonomie à 1 msg/min

// Détection panne capteur
#define DHT_FAIL_THRESHOLD 5         // nb d'échecs consécutifs avant alerte
#define DHT_TEMP_MIN_PHYS -40.0f     // borne physique basse capteur
#define DHT_TEMP_MAX_PHYS  80.0f     // borne physique haute capteur
#define DHT_HUM_MIN_PHYS    0.0f
#define DHT_HUM_MAX_PHYS  100.0f

struct Mesure {
  float temperature;
  float humidite;
  char  timestamp[30];
};

Mesure buffer[BUFFER_SIZE];
int bufferHead  = 0;
int bufferTail  = 0;
int bufferCount = 0;

// Compteurs / état pour la détection d'erreurs capteur
int  dhtFailStreak       = 0;
bool sensorErrorReported = false;

// Espacement entre tentatives de reconnexion (non-bloquantes)
unsigned long lastWifiAttempt = 0;
unsigned long lastMqttAttempt = 0;
const unsigned long WIFI_RETRY_INTERVAL = 10000;
const unsigned long MQTT_RETRY_INTERVAL = 5000;

// Construction dynamique du topic d'erreurs : entrepot/<id>/erreurs
char MQTT_TOPIC_ERREURS[64];

DHT dht(DHTPIN, DHTTYPE);
WiFiClient espClient;
PubSubClient client(espClient);


// ============================================================================
// Init : capteur, Wi-Fi (non-bloquant), MQTT, NTP
// ============================================================================
void setup() {
  Serial.begin(115200);
  dht.begin();

  snprintf(MQTT_TOPIC_ERREURS, sizeof(MQTT_TOPIC_ERREURS),
           "entrepot/%d/erreurs", ID_ENTREPOT);

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.println("Tentative initiale de connexion Wi-Fi...");

  client.setServer(MQTT_BROKER, MQTT_PORT);
  client.setBufferSize(512);

  // NTP en UTC (offset = 0). Les conversions locales se font côté app.
  configTime(0, 0, "pool.ntp.org", "time.google.com");
}


// ============================================================================
// Cycle principal : connectivité -> mesure -> flush -> attente
// ============================================================================
void loop() {
  ensureWifi();
  if (WiFi.status() == WL_CONNECTED) {
    ensureMqtt();
    client.loop();
  }

  preleverMesure();

  if (client.connected()) {
    flushBuffer();
  }

  // Attente non-bloquante avant la prochaine mesure
  unsigned long start = millis();
  while (millis() - start < INTERVAL_MS) {
    if (WiFi.status() == WL_CONNECTED && client.connected()) {
      client.loop();
    }
    delay(200);
  }
}


// ============================================================================
// Lecture DHT22 : calibration + sanity-checks + détection d'erreur
// ============================================================================
void preleverMesure() {
  float tempBrute = dht.readTemperature();
  float humBrute  = dht.readHumidity();

  // ---- Cas 1 : NaN -> capteur déconnecté ou broche en l'air -----------------
  if (isnan(tempBrute) || isnan(humBrute)) {
    dhtFailStreak++;
    Serial.printf("Erreur lecture DHT22 (NaN) %d/%d\n",
                  dhtFailStreak, DHT_FAIL_THRESHOLD);
    if (dhtFailStreak >= DHT_FAIL_THRESHOLD && !sensorErrorReported) {
      signalSensorError("DHT_NAN",
        "Lectures NaN consecutives - capteur deconnecte ou cable HS");
      sensorErrorReported = true;
    }
    return;
  }

  // ---- Cas 2 : valeurs aberrantes (hors plage physique DHT22) ---------------
  if (tempBrute < DHT_TEMP_MIN_PHYS || tempBrute > DHT_TEMP_MAX_PHYS ||
      humBrute  < DHT_HUM_MIN_PHYS  || humBrute  > DHT_HUM_MAX_PHYS) {
    dhtFailStreak++;
    Serial.printf("Valeur aberrante (T=%.1f H=%.1f) %d/%d\n",
                  tempBrute, humBrute, dhtFailStreak, DHT_FAIL_THRESHOLD);
    if (dhtFailStreak >= DHT_FAIL_THRESHOLD && !sensorErrorReported) {
      signalSensorError("DHT_OUT_OF_RANGE",
        "Valeurs hors limites physiques en continu - capteur defectueux");
      sensorErrorReported = true;
    }
    return;
  }

  // ---- Lecture OK -----------------------------------------------------------
  // Si le capteur était signalé en panne et revient à la normale -> on prévient
  if (sensorErrorReported) {
    signalSensorError("DHT_OK", "Capteur a nouveau operationnel");
    sensorErrorReported = false;
  }
  dhtFailStreak = 0;

  // ---- Calibration : valeur_corrigee = brute * GAIN + OFFSET ---------------
  float temperature = tempBrute * TEMP_GAIN + TEMP_OFFSET;
  float humidite    = humBrute  * HUM_GAIN  + HUM_OFFSET;
  if (humidite < 0)   humidite = 0;
  if (humidite > 100) humidite = 100;

  // ---- Timestamp posé AU MOMENT DU PRÉLÈVEMENT ------------------------------
  // Si NTP pas encore synchro, on REJETTE la mesure plutôt que d'envoyer
  // une valeur sans timestamp fiable (le serveur la refuserait de toute façon).
  struct tm timeinfo;
  if (!getLocalTime(&timeinfo, 100)) {
    Serial.println("NTP pas encore synchro - mesure ignoree");
    return;
  }

  Mesure m;
  m.temperature = temperature;
  m.humidite    = humidite;
  strftime(m.timestamp, sizeof(m.timestamp), "%Y-%m-%dT%H:%M:%SZ", &timeinfo);

  buffer[bufferHead] = m;
  bufferHead = (bufferHead + 1) % BUFFER_SIZE;

  if (bufferCount < BUFFER_SIZE) {
    bufferCount++;
  } else {
    // Buffer plein : on écrase la plus ancienne (FIFO glissant)
    bufferTail = (bufferTail + 1) % BUFFER_SIZE;
    Serial.println("Buffer plein, plus ancienne mesure ecrasee");
  }

  Serial.printf("Temp: %.2f C (brut %.2f) | Hum: %.2f%% (brut %.2f) | buf: %d\n",
                temperature, tempBrute, humidite, humBrute, bufferCount);
}


// ============================================================================
// Publie sur MQTT toutes les mesures en attente (FIFO)
// ============================================================================
void flushBuffer() {
  while (bufferCount > 0 && client.connected()) {
    Mesure& m = buffer[bufferTail];

    StaticJsonDocument<256> doc;
    doc["idEntrepot"]  = ID_ENTREPOT;
    doc["temperature"] = m.temperature;
    doc["humidite"]    = m.humidite;
    doc["datMesure"]   = m.timestamp;   // toujours présent (cf. preleverMesure)

    char jsonBuffer[256];
    size_t n = serializeJson(doc, jsonBuffer);

    if (client.publish(MQTT_TOPIC, (uint8_t*)jsonBuffer, n, false)) {
      bufferTail = (bufferTail + 1) % BUFFER_SIZE;
      bufferCount--;
      Serial.printf("Mesure publiee (reste %d en attente)\n", bufferCount);
    } else {
      Serial.println("Publication echouee - retry au prochain cycle");
      break;
    }
  }
}


// ============================================================================
// Publie une erreur capteur sur le topic entrepot/<id>/erreurs
// (retain=true pour que le serveur la voit dès qu'il se reconnecte)
// ============================================================================
void signalSensorError(const char* code, const char* details) {
  if (!client.connected()) {
    Serial.println("Pas de connexion MQTT - erreur non publiee");
    return;
  }
  StaticJsonDocument<256> doc;
  doc["idEntrepot"] = ID_ENTREPOT;
  doc["code"]       = code;
  doc["details"]    = details;

  struct tm timeinfo;
  char ts[30];
  if (getLocalTime(&timeinfo, 100)) {
    strftime(ts, sizeof(ts), "%Y-%m-%dT%H:%M:%SZ", &timeinfo);
    doc["datSignal"] = ts;
  }

  char jsonBuf[256];
  size_t n = serializeJson(doc, jsonBuf);

  if (client.publish(MQTT_TOPIC_ERREURS, (uint8_t*)jsonBuf, n, true)) {
    Serial.printf("🚨 Erreur capteur publiee : %s\n", code);
  } else {
    Serial.printf("Publication erreur capteur echouee (%s)\n", code);
  }
}


// ============================================================================
// Reconnexions non-bloquantes Wi-Fi / MQTT
// ============================================================================
void ensureWifi() {
  if (WiFi.status() == WL_CONNECTED) return;

  unsigned long now = millis();
  if (now - lastWifiAttempt < WIFI_RETRY_INTERVAL) return;

  lastWifiAttempt = now;
  Serial.print("Reconnexion Wi-Fi... ");
  WiFi.disconnect();
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 3000) {
    delay(100);
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("OK (" + WiFi.localIP().toString() + ")");
  } else {
    Serial.println("KO (on continue en mode offline)");
  }
}


void ensureMqtt() {
  if (client.connected()) return;

  unsigned long now = millis();
  if (now - lastMqttAttempt < MQTT_RETRY_INTERVAL) return;

  lastMqttAttempt = now;
  Serial.print("Reconnexion MQTT... ");
  if (client.connect("ESP32Client")) {
    Serial.println("OK");
  } else {
    Serial.printf("KO (rc=%d)\n", client.state());
  }
}