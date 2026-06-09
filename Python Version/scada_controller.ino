/*
 * Electricity Load Balancing Game - SCADA Controller (Arduino Uno)
 * ================================================================
 * Reads the generator dials and the operator's circuit-breaker switches,
 * mirrors each breaker's state on a status LED, and streams the readings to
 * the Python digital twin over USB serial ~10 times per second.
 *
 * It can also receive a one-line command from Python telling it where the
 * current fault is, e.g.  "FAULT:B2"  (or "FAULT:NONE"), and flashes that
 * breaker's LED + the on-board pin-13 LED as an alarm so the operator knows
 * which feeder to isolate.
 *
 * Line sent to PC:   H1:512,H2:300,B1:1,B2:0,B3:1,B4:1
 *   H* = pot reading 0..1023      B* = breaker closed(1) / open(0)
 *
 * --- Wiring (see TINKERCAD_WIRING_GUIDE.md) ---
 *   A0, A1            : 10k potentiometers (hydro 1, hydro 2)
 *   D2, D3, D4, D5    : breaker switches B1..B4 to GND (uses INPUT_PULLUP)
 *   D6, D7, D8, D9    : status LEDs for B1..B4 (+220 ohm to GND)
 *   D13              : on-board LED, used as the fault alarm
 *
 * In TinkerCAD: build the circuit, paste this sketch into the code panel,
 * Start Simulation, and open the Serial Monitor to watch the data line.
 */

const int POT_PINS[2]    = {A0, A1};
const int BREAKER_PINS[4] = {2, 3, 4, 5};
const int LED_PINS[4]     = {6, 7, 8, 9};
const int ALARM_PIN       = 13;

const unsigned long SEND_INTERVAL = 100;   // ms between serial updates
unsigned long lastSend = 0;

int faultIndex = -1;        // 0..3 = which breaker is faulted, -1 = none
String inBuf = "";

void setup() {
  Serial.begin(9600);
  for (int i = 0; i < 4; i++) {
    pinMode(BREAKER_PINS[i], INPUT_PULLUP);   // switch closed = pin reads LOW
    pinMode(LED_PINS[i], OUTPUT);
  }
  pinMode(ALARM_PIN, OUTPUT);
}

void loop() {
  readCommands();

  // A breaker is "closed" when its switch connects the pin to GND (LOW).
  bool closed[4];
  for (int i = 0; i < 4; i++) {
    closed[i] = (digitalRead(BREAKER_PINS[i]) == LOW);
  }

  updateLeds(closed);

  unsigned long now = millis();
  if (now - lastSend >= SEND_INTERVAL) {
    lastSend = now;
    sendState(closed);
  }
}

// Light each LED to show its breaker state; flash the faulted feeder.
void updateLeds(bool closed[4]) {
  bool flash = (millis() / 250) % 2;          // 4 Hz blink
  for (int i = 0; i < 4; i++) {
    if (i == faultIndex) {
      digitalWrite(LED_PINS[i], flash);
    } else {
      digitalWrite(LED_PINS[i], closed[i]);
    }
  }
  digitalWrite(ALARM_PIN, (faultIndex >= 0) ? flash : LOW);
}

// Stream the current readings to the PC.
void sendState(bool closed[4]) {
  Serial.print("H1:"); Serial.print(analogRead(POT_PINS[0]));
  Serial.print(",H2:"); Serial.print(analogRead(POT_PINS[1]));
  for (int i = 0; i < 4; i++) {
    Serial.print(",B"); Serial.print(i + 1);
    Serial.print(":");  Serial.print(closed[i] ? 1 : 0);
  }
  Serial.println();
}

// Parse "FAULT:Bn" / "FAULT:NONE" from the PC.
void readCommands() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') {
      if (inBuf.startsWith("FAULT:")) {
        String f = inBuf.substring(6);
        if      (f.startsWith("B1")) faultIndex = 0;
        else if (f.startsWith("B2")) faultIndex = 1;
        else if (f.startsWith("B3")) faultIndex = 2;
        else if (f.startsWith("B4")) faultIndex = 3;
        else                          faultIndex = -1;
      }
      inBuf = "";
    } else {
      inBuf += c;
    }
  }
}
