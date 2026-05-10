/*
 * ============================================================
 *  ESP32 GPS Vehicle Tracker + Violation Alert System
 * ============================================================
 *
 *  Hardware Required:
 *    - ESP32 Dev Board (e.g., ESP32-WROOM-32)
 *    - NEO-6M GPS Module
 *    - Active Buzzer (for violation alerts)
 *    - Red LED + 220Ω resistor (violation indicator)
 *    - Green LED + 220Ω resistor (status indicator)
 *
 *  Wiring:
 *    GPS Module (NEO-6M):
 *      VCC  -> 3.3V
 *      GND  -> GND
 *      TX   -> GPIO 16 (ESP32 RX2)
 *      RX   -> GPIO 17 (ESP32 TX2)
 *
 *    Buzzer:
 *      (+)  -> GPIO 25
 *      (-)  -> GND
 *
 *    Red LED (Violation):
 *      Anode  -> GPIO 26 (through 220Ω resistor)
 *      Cathode -> GND
 *
 *    Green LED (Status):
 *      Anode  -> GPIO 27 (through 220Ω resistor)
 *      Cathode -> GND
 *
 *  Libraries Required (install via Arduino Library Manager):
 *    - TinyGPSPlus by Mikal Hart
 *    - ArduinoJson by Benoit Blanchon (v6 or v7)
 *
 *  Setup:
 *    1. Install Arduino IDE + ESP32 board support
 *    2. Install the two libraries above
 *    3. Update WIFI_SSID, WIFI_PASSWORD, and SERVER_URL below
 *    4. Select board: "ESP32 Dev Module"
 *    5. Upload!
 *
 * ============================================================
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <TinyGPSPlus.h>
#include <ArduinoJson.h>

// ========================
//  CONFIGURATION - EDIT THESE
// ========================
const char* WIFI_SSID     = "STJC_GENTS";       // Your WiFi network name
const char* WIFI_PASSWORD = "admin@123";    // Your WiFi password
const char* SERVER_URL    = "http://172.16.13.221:5000/send_gps";  // Your Flask server IP + endpoint
const char* VEHICLE_ID    = "TN09AB1234";            // Must match registered vehicle in backend

// ========================
//  PIN DEFINITIONS
// ========================
#define GPS_RX_PIN    16    // ESP32 RX2 <- GPS TX
#define GPS_TX_PIN    17    // ESP32 TX2 -> GPS RX
#define BUZZER_PIN    25    // Active buzzer
#define RED_LED_PIN   26    // Violation alert LED
#define GREEN_LED_PIN 27    // Normal status LED

// ========================
//  TIMING (milliseconds)
// ========================
#define GPS_SEND_INTERVAL   3000    // Send GPS data every 3 seconds
#define WIFI_RETRY_INTERVAL 5000    // Retry WiFi connection every 5 seconds
#define BUZZER_DURATION     2000    // Buzzer on-time per alert cycle (ms)
#define BUZZER_PATTERN_ON   200     // Buzzer beep ON duration (ms)
#define BUZZER_PATTERN_OFF  100     // Buzzer beep OFF duration (ms)

// ========================
//  OBJECTS
// ========================
TinyGPSPlus gps;
HardwareSerial gpsSerial(2);  // UART2 for GPS

// ========================
//  STATE VARIABLES
// ========================
unsigned long lastGPSSend      = 0;
unsigned long lastWiFiRetry    = 0;
unsigned long violationStart   = 0;
bool violationActive           = false;
bool buzzerActive              = false;
int  tripCount                 = 0;
String lastStatus              = "IDLE";

// ========================
//  SETUP
// ========================
void setup() {
  // Initialize Serial for debugging
  Serial.begin(115200);
  delay(1000);

  Serial.println();
  Serial.println("╔══════════════════════════════════════════╗");
  Serial.println("║  ESP32 GPS Vehicle Tracker v1.0          ║");
  Serial.println("║  Violation Alert System                  ║");
  Serial.println("╚══════════════════════════════════════════╝");
  Serial.println();

  // Initialize GPS Serial
  gpsSerial.begin(9600, SERIAL_8N1, GPS_RX_PIN, GPS_TX_PIN);
  Serial.println("[GPS] UART2 initialized (9600 baud)");

  // Initialize output pins
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(RED_LED_PIN, OUTPUT);
  pinMode(GREEN_LED_PIN, OUTPUT);

  // Initial LED state
  digitalWrite(BUZZER_PIN, LOW);
  digitalWrite(RED_LED_PIN, LOW);
  digitalWrite(GREEN_LED_PIN, LOW);

  // Startup LED test (flash all LEDs)
  startupAnimation();

  // Connect to WiFi
  connectToWiFi();
}

// ========================
//  MAIN LOOP
// ========================
void loop() {
  // ---- 1. Read GPS data continuously ----
  while (gpsSerial.available() > 0) {
    gps.encode(gpsSerial.read());
  }

  // ---- 2. Check WiFi connection ----
  if (WiFi.status() != WL_CONNECTED) {
    digitalWrite(GREEN_LED_PIN, LOW);

    // Blink red LED slowly to indicate no WiFi
    digitalWrite(RED_LED_PIN, (millis() / 500) % 2);

    if (millis() - lastWiFiRetry >= WIFI_RETRY_INTERVAL) {
      lastWiFiRetry = millis();
      Serial.println("[WIFI] Connection lost. Reconnecting...");
      connectToWiFi();
    }
    return;  // Don't send data without WiFi
  }

  // WiFi connected -> green LED on
  if (!violationActive) {
    digitalWrite(GREEN_LED_PIN, HIGH);
    digitalWrite(RED_LED_PIN, LOW);
  }

  // ---- 3. Send GPS data at intervals ----
  if (millis() - lastGPSSend >= GPS_SEND_INTERVAL) {
    lastGPSSend = millis();

    if (gps.location.isValid() && gps.location.isUpdated()) {
      double latitude  = gps.location.lat();
      double longitude = gps.location.lng();

      Serial.printf("[GPS] Fix: %.6f, %.6f | Sats: %d | HDOP: %.1f\n",
                    latitude, longitude,
                    gps.satellites.value(),
                    gps.hdop.hdop());

      sendGPSToServer(latitude, longitude);
    } else {
      Serial.printf("[GPS] Waiting for fix... Chars: %lu | Sentences: %lu | Checksum Fails: %lu\n",
                    gps.charsProcessed(),
                    gps.sentencesWithFix(),
                    gps.failedChecksum());

      // Blink green LED to show GPS searching
      digitalWrite(GREEN_LED_PIN, (millis() / 300) % 2);
    }
  }

  // ---- 4. Handle violation buzzer pattern ----
  handleViolationAlert();
}

// ========================
//  WiFi CONNECTION
// ========================
void connectToWiFi() {
  Serial.printf("[WIFI] Connecting to '%s'", WIFI_SSID);

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500);
    Serial.print(".");
    attempts++;

    // Alternate LEDs while connecting
    digitalWrite(GREEN_LED_PIN, attempts % 2);
    digitalWrite(RED_LED_PIN, (attempts + 1) % 2);
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println();
    Serial.printf("[WIFI] Connected! IP: %s\n", WiFi.localIP().toString().c_str());
    Serial.printf("[WIFI] Signal: %d dBm\n", WiFi.RSSI());

    digitalWrite(GREEN_LED_PIN, HIGH);
    digitalWrite(RED_LED_PIN, LOW);

    // Success beep
    tone(BUZZER_PIN, 1000, 100);
    delay(150);
    tone(BUZZER_PIN, 1500, 100);
  } else {
    Serial.println();
    Serial.println("[WIFI] ❌ Connection FAILED! Will retry...");

    digitalWrite(GREEN_LED_PIN, LOW);
    digitalWrite(RED_LED_PIN, HIGH);

    // Failure beep
    tone(BUZZER_PIN, 400, 300);
  }
}

// ========================
//  SEND GPS DATA TO SERVER
// ========================
void sendGPSToServer(double latitude, double longitude) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[HTTP] No WiFi - skipping send");
    return;
  }

  HTTPClient http;
  http.begin(SERVER_URL);
  http.addHeader("Content-Type", "application/json");
  http.setTimeout(5000);  // 5 second timeout

  // Build JSON payload matching your Flask backend's expected format
  StaticJsonDocument<256> doc;
  doc["vehicle_id"] = VEHICLE_ID;
  doc["latitude"]   = latitude;
  doc["longitude"]  = longitude;

  // Build timestamp: YYYY-MM-DDTHH:MM:SS from GPS time
  char timestamp[30];
  if (gps.date.isValid() && gps.time.isValid()) {
    snprintf(timestamp, sizeof(timestamp), "%04d-%02d-%02dT%02d:%02d:%02d",
             gps.date.year(), gps.date.month(), gps.date.day(),
             gps.time.hour(), gps.time.minute(), gps.time.second());
  } else {
    // Fallback: use millis-based counter
    snprintf(timestamp, sizeof(timestamp), "1970-01-01T00:00:%02lu", (millis() / 1000) % 60);
  }
  doc["timestamp"] = timestamp;

  String jsonPayload;
  serializeJson(doc, jsonPayload);

  Serial.printf("[HTTP] POST -> %s\n", SERVER_URL);
  Serial.printf("[HTTP] Body: %s\n", jsonPayload.c_str());

  int httpCode = http.POST(jsonPayload);

  if (httpCode > 0) {
    String response = http.getString();
    Serial.printf("[HTTP] Response (%d): %s\n", httpCode, response.c_str());

    // Parse server response to check for violations
    parseServerResponse(response);
  } else {
    Serial.printf("[HTTP] ❌ POST failed: %s\n", http.errorToString(httpCode).c_str());
  }

  http.end();
}

// ========================
//  PARSE SERVER RESPONSE
// ========================
void parseServerResponse(String response) {
  StaticJsonDocument<256> doc;
  DeserializationError error = deserializeJson(doc, response);

  if (error) {
    Serial.printf("[PARSE] JSON error: %s\n", error.c_str());
    return;
  }

  const char* status = doc["status"] | "unknown";
  int serverTripCount = doc["trip_count"] | 0;
  const char* vehicleId = doc["vehicle_id"] | "unknown";

  lastStatus = String(status);
  tripCount  = serverTripCount;

  Serial.printf("[STATUS] Vehicle: %s | Status: %s | Trips: %d\n",
                vehicleId, status, serverTripCount);

  // ---- CHECK FOR VIOLATION ----
  if (String(status) == "VIOLATION DETECTED") {
    if (!violationActive) {
      Serial.println();
      Serial.println("╔══════════════════════════════════════════╗");
      Serial.println("║  🚨 VIOLATION DETECTED! ALERT ACTIVE!   ║");
      Serial.println("╚══════════════════════════════════════════╝");
      Serial.printf("  Vehicle  : %s\n", vehicleId);
      Serial.printf("  Trips    : %d\n", serverTripCount);
      Serial.printf("  Status   : %s\n", status);
      Serial.println();

      violationActive = true;
      violationStart  = millis();
    }
  } else {
    // No violation - clear alert
    if (violationActive) {
      Serial.println("[ALERT] Violation cleared. Returning to normal.");
    }
    violationActive = false;
    buzzerActive    = false;
    digitalWrite(RED_LED_PIN, LOW);
    digitalWrite(GREEN_LED_PIN, HIGH);
    noTone(BUZZER_PIN);
  }
}

// ========================
//  VIOLATION ALERT HANDLER
// ========================
void handleViolationAlert() {
  if (!violationActive) return;

  // Red LED stays ON during violation
  digitalWrite(RED_LED_PIN, HIGH);
  // Green LED OFF during violation
  digitalWrite(GREEN_LED_PIN, LOW);

  // Buzzer alarm pattern: rapid beeping
  unsigned long elapsed = millis() - violationStart;
  unsigned long patternCycle = BUZZER_PATTERN_ON + BUZZER_PATTERN_OFF;

  if ((elapsed % patternCycle) < BUZZER_PATTERN_ON) {
    // Alternate between two tones for urgency
    if ((elapsed / 1000) % 2 == 0) {
      tone(BUZZER_PIN, 2000);  // High pitch
    } else {
      tone(BUZZER_PIN, 1500);  // Lower pitch
    }
  } else {
    noTone(BUZZER_PIN);
  }

  // Also flash the red LED rapidly
  if ((elapsed / 150) % 2 == 0) {
    digitalWrite(RED_LED_PIN, HIGH);
  } else {
    digitalWrite(RED_LED_PIN, LOW);
  }
}

// ========================
//  STARTUP ANIMATION
// ========================
void startupAnimation() {
  Serial.println("[BOOT] Running startup LED test...");

  for (int i = 0; i < 3; i++) {
    digitalWrite(GREEN_LED_PIN, HIGH);
    delay(100);
    digitalWrite(GREEN_LED_PIN, LOW);

    digitalWrite(RED_LED_PIN, HIGH);
    delay(100);
    digitalWrite(RED_LED_PIN, LOW);
  }

  // Short beep to confirm buzzer works
  tone(BUZZER_PIN, 800, 150);
  delay(200);

  Serial.println("[BOOT] Hardware test complete.");
}
