#include <WiFi.h>
#include <PubSubClient.h>
#include <DHT.h>
#include <ArduinoJson.h>
#include <time.h>
#include "config.h"   // credentials Wi-Fi + IP broker (non versionné)

#define DHTPIN  4
#define DHTTYPE DHT22
#define INTERVAL_MS (60 * 1000UL)  // 1 mesure / minute

// Buffer circulaire : stocke les mesures quand on est hors-ligne
#define BUFFER_SIZE 120  // 2h d'autonomie à 1 msg/min

struct Mesure {
  float temperature;
  float humidite;
  char  timestamp[30];
};

Mesure buffer[BUFFER_SIZE];
int bufferHead  = 0;   // prochain index où écrire
int bufferTail  = 0;   // prochain index à envoyer
int bufferCount = 0;   // nb de mesures en attente

// Espacement entre tentatives de reconnexion (non-bloquantes)
unsigned long lastWifiAttempt = 0;
unsigned long lastMqttAttempt = 0;
const unsigned long WIFI_RETRY_INTERVAL = 10000;
const unsigned long MQTT_RETRY_INTERVAL = 5000;

DHT dht(DHTPIN, DHTTYPE);
WiFiClient espClient;
PubSubClient client(espClient);


// Init : capteur, Wi-Fi (non-bloquant), MQTT, NTP
void setup() {
  Serial.begin(115200);
  dht.begin();

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.println("Tentative initiale de connexion Wi-Fi...");

  client.setServer(MQTT_BROKER, MQTT_PORT);
  client.setBufferSize(512);

  configTime(0, 0, "pool.ntp.org");
}


// Cycle principal : connectivité -> mesure -> flush -> attente
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


// Lit le DHT22 et empile la mesure dans le buffer
void preleverMesure() {
  float temperature = dht.readTemperature();
  float humidite    = dht.readHumidity();

  if (isnan(temperature) || isnan(humidite)) {
    Serial.println("Erreur lecture DHT22 - mesure ignoree");
    return;
  }

  Mesure m;
  m.temperature = temperature;
  m.humidite    = humidite;

  // Timestamp posé au moment du prélèvement (pas à l'envoi)
  struct tm timeinfo;
  if (getLocalTime(&timeinfo, 100)) {
    strftime(m.timestamp, sizeof(m.timestamp), "%Y-%m-%dT%H:%M:%SZ", &timeinfo);
  } else {
    m.timestamp[0] = '\0';  // NTP pas synchro -> Python utilisera utcnow()
  }

  buffer[bufferHead] = m;
  bufferHead = (bufferHead + 1) % BUFFER_SIZE;

  if (bufferCount < BUFFER_SIZE) {
    bufferCount++;
  } else {
    // Buffer plein : on écrase la plus ancienne
    bufferTail = (bufferTail + 1) % BUFFER_SIZE;
    Serial.println("Buffer plein, plus ancienne mesure ecrasee");
  }

  Serial.printf("Temp: %.1f C | Humidite: %.1f%% | en attente: %d\n",
                temperature, humidite, bufferCount);
}


// Publie sur MQTT toutes les mesures en attente (FIFO)
void flushBuffer() {
  while (bufferCount > 0 && client.connected()) {
    Mesure& m = buffer[bufferTail];

    StaticJsonDocument<256> doc;
    doc["idEntrepot"]  = ID_ENTREPOT;
    doc["temperature"] = m.temperature;
    doc["humidite"]    = m.humidite;
    if (m.timestamp[0] != '\0') {
      doc["datMesure"] = m.timestamp;
    }

    char jsonBuffer[256];
    size_t n = serializeJson(doc, jsonBuffer);

    if (client.publish(MQTT_TOPIC, (uint8_t*)jsonBuffer, n, false)) {
      // Succès -> on retire la mesure du buffer
      bufferTail = (bufferTail + 1) % BUFFER_SIZE;
      bufferCount--;
      Serial.printf("Mesure publiee (reste %d en attente)\n", bufferCount);
    } else {
      // Échec -> on stoppe, on retentera au prochain cycle
      Serial.println("Publication echouee - retry au prochain cycle");
      break;
    }
  }
}


// Tente une reconnexion Wi-Fi sans bloquer (max 3s par essai, 1 essai/10s)
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


// Tente une reconnexion MQTT sans bloquer (1 essai / 5s)
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