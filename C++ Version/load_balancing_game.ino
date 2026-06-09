/*
 * Electricity Load Balancing Game  (self-contained, runs entirely on an Arduino)
 * =============================================================================
 * A STEM teaching game: a team keeps grid FREQUENCY at 50 Hz by balancing
 * generation against a changing load while clearing random faults.
 *
 *   Generator players  ->  turn the two hydro dials (potentiometers).
 *   Network operators  ->  flip the breaker switches to isolate faults and
 *                          shed load when frequency runs away.
 *
 * Frequency drifts whenever generation != load. HOW FAST it drifts depends on
 * the system INERTIA, which only the synchronous hydro units provide -- wind
 * and solar add power but no inertia. Lose the hydro units and the grid gets
 * far twitchier: the inverter-based-resources lesson, made physical.
 *
 * A servo acts as a "synchronous machine": it sweeps back and forth and the
 * SPEED of its sweep tracks the frequency, so the class can literally watch
 * the grid spin faster or slower. (To use it instead as a needle gauge, see
 * the one-line note in updateServo().)
 *
 * Everything below runs in TinkerCAD with no PC. Open the Serial Monitor at
 * 9600 baud to see the live dashboard and the final score.
 *
 * Wiring is in TINKERCAD_WIRING_GUIDE.md.
 */

#include <Servo.h>
#include <math.h>

// ----------------------- pins -----------------------
const int POT_PINS[2]     = {A0, A1};        // hydro 1, hydro 2 dials
const int BREAKER_PINS[4] = {2, 3, 4, 5};    // B1..B4 switches to GND
const int LED_PINS[4]     = {6, 7, 8, 9};    // B1..B4 status LEDs
const int SERVO_PIN       = 10;              // frequency "machine"
const int ALARM_PIN       = 13;             // on-board LED = fault alarm

// ----------------- tunable game constants -----------------
const float NOMINAL_HZ    = 50.0;
const float HYDRO_MAX_MW   = 80.0;   // full-scale output of each hydro dial
const float HYDRO_INERTIA  = 4.0;    // inertia each ONLINE hydro unit adds
const float INERTIA_FLOOR  = 1.0;    // avoids divide-by-zero with no inertia
const float DAMPING        = 2.0;    // load self-regulation toward 50 Hz
const float FREQ_GAIN      = 0.05;   // Hz/s per MW of imbalance per unit inertia
const float FAULT_DISTURB  = 60.0;   // MW the grid loses while a fault is live
const float TRIP_BAND      = 0.8;    // |df| beyond this counts as an event
const float BLACKOUT_BAND  = 3.0;    // |df| beyond this = collapse, reset to 50

const float GAME_SECONDS   = 600.0;  // real length of one game = one 24h day
const unsigned long STEP_MS = 100;   // physics tick
const unsigned long PRINT_MS = 1000; // dashboard refresh

// scoring weights
const float K_FREQ   = 4.0;
const float K_ENERGY = 0.5;
const float K_EVENT  = 15.0;

// ----------------------- state -----------------------
Servo machine;
float freq = NOMINAL_HZ;
float wind = 25.0;
float elapsed = 0.0;
float phase = 0.0;                 // servo sweep phase

int   faultFeeder = -1;            // 0..3 = faulted breaker, -1 = none
float faultClearAt = 0.0;
float nextFaultAt = 20.0;

float freqSqIntegral = 0.0;        // integral of (f-50)^2 dt
float unservedMWh = 0.0;
int   events = 0;
bool  belowBand = false;
bool  gameOver = false;

unsigned long lastStep = 0;
unsigned long lastPrint = 0;

// ----------------------- helpers -----------------------
float clampf(float x, float lo, float hi) {
  return x < lo ? lo : (x > hi ? hi : x);
}

float gameHour() {
  float h = (elapsed / GAME_SECONDS) * 24.0;
  while (h >= 24.0) h -= 24.0;
  return h;
}

// load / renewable profiles ------------------------------------------------
float residentialLoad(float h) {            // morning + evening peaks
  float morning = 45.0 * exp(-((h - 8.0) * (h - 8.0)) / 4.0);
  float evening = 55.0 * exp(-((h - 19.0) * (h - 19.0)) / 6.0);
  return 55.0 + morning + evening;
}
float industrialLoad(float)  { return 50.0; }        // constant
float solarOutput(float h) {                          // daylight half-sine
  if (h >= 6.0 && h <= 18.0) return 60.0 * sin(PI * (h - 6.0) / 12.0);
  return 0.0;
}

bool breakerClosed(int i) { return digitalRead(BREAKER_PINS[i]) == LOW; }

float hydroMW(int i) {
  return analogRead(POT_PINS[i]) / 1023.0 * HYDRO_MAX_MW;
}

// total generation, and the online synchronous inertia
float generation(float *inertia) {
  float h = gameHour();
  float p = hydroMW(0);             // hydro 1 always online
  *inertia = HYDRO_INERTIA;
  if (breakerClosed(3)) {           // B4 = hydro 2
    p += hydroMW(1);
    *inertia += HYDRO_INERTIA;
  }
  if (breakerClosed(0)) {           // B1 = wind + solar feeder (no inertia)
    p += wind + solarOutput(h);
  }
  if (*inertia < INERTIA_FLOOR) *inertia = INERTIA_FLOOR;
  return p;
}

float demand() {
  float h = gameHour();
  float p = 0.0;
  if (breakerClosed(1)) p += residentialLoad(h);   // B2 = residential
  if (breakerClosed(2)) p += industrialLoad(h);    // B3 = industrial
  return p;
}

void updateFaults() {
  if (faultFeeder < 0 && elapsed >= nextFaultAt) {
    faultFeeder = random(0, 4);
    faultClearAt = elapsed + random(8, 16);
  } else if (faultFeeder >= 0 && elapsed >= faultClearAt) {
    faultFeeder = -1;                               // self-extinguished
    nextFaultAt = elapsed + random(25, 51);
  }
}

void updateScore(float dt) {
  float df = freq - NOMINAL_HZ;
  freqSqIntegral += df * df * dt;

  float h = gameHour();
  float shed = 0.0;                                 // open load feeders = unserved
  if (!breakerClosed(1)) shed += residentialLoad(h);
  if (!breakerClosed(2)) shed += industrialLoad(h);
  unservedMWh += shed * dt / 3600.0;

  bool out = fabs(df) > TRIP_BAND;
  if (out && !belowBand) events++;
  belowBand = out;

  if (fabs(df) > BLACKOUT_BAND) { events += 2; freq = NOMINAL_HZ; }
}

long currentScore() {
  float raw = 1000.0 - K_FREQ * freqSqIntegral
                     - K_ENERGY * unservedMWh
                     - K_EVENT * events;
  return raw < 0 ? 0 : (long)raw;
}

// ----------------------- one physics step -----------------------
void stepPhysics(float dt) {
  elapsed += dt;

  wind += (random(-100, 101) / 100.0) * dt * 8.0;   // random walk
  wind = clampf(wind, 0.0, 50.0);

  updateFaults();

  float inertia;
  float pGen = generation(&inertia);
  float pLoad = demand();
  float disturb = (faultFeeder >= 0 && breakerClosed(faultFeeder)) ? FAULT_DISTURB : 0.0;
  float imbalance = pGen - pLoad - disturb;

  // simple swing-style update: rate of change of frequency = imbalance /
  // inertia, plus damping that restores 50 Hz.
  float rocof = (FREQ_GAIN * imbalance - DAMPING * (freq - NOMINAL_HZ)) / inertia;
  freq += rocof * dt;

  updateScore(dt);
}

// ----------------------- outputs -----------------------
void updateLeds() {
  bool flash = (millis() / 250) % 2;                // 4 Hz alarm blink
  for (int i = 0; i < 4; i++) {
    if (i == faultFeeder) digitalWrite(LED_PINS[i], flash);   // blink the faulted feeder
    else                  digitalWrite(LED_PINS[i], breakerClosed(i));
  }
  digitalWrite(ALARM_PIN, (faultFeeder >= 0) ? flash : LOW);
}

void updateServo(float dt) {
  // Sweep speed tracks frequency, so the machine visibly spins faster when
  // frequency is high and stalls when it collapses. The (freq-44) offset and
  // gain are exaggerated so small Hz changes are easy to see.
  float sweepRate = (freq - 44.0) * 1.2;            // rad/s, always > 0 in normal range
  if (sweepRate < 0) sweepRate = 0;
  phase += sweepRate * dt;
  int angle = (int)(90.0 + 80.0 * sin(phase));
  machine.write(angle);
  // -- Needle-gauge alternative: comment the 4 lines above and use instead:
  // machine.write((int)clampf((freq - 47.0) / 6.0 * 180.0, 0, 180));
}

void printDashboard() {
  float inertia;
  float pGen = generation(&inertia);
  int h = (int)gameHour();
  int m = (int)((gameHour() - h) * 60);

  Serial.print(h); Serial.print(':');
  if (m < 10) Serial.print('0');
  Serial.print(m);
  Serial.print("  f="); Serial.print(freq, 2); Serial.print("Hz");
  Serial.print("  gen="); Serial.print(pGen, 0);
  Serial.print("  load="); Serial.print(demand(), 0);
  Serial.print("  H="); Serial.print(inertia, 0);
  Serial.print("  B=");
  for (int i = 0; i < 4; i++) Serial.print(breakerClosed(i) ? '1' : '0');
  if (faultFeeder >= 0) { Serial.print("  FAULT:B"); Serial.print(faultFeeder + 1); }
  Serial.print("  score="); Serial.print(currentScore());
  Serial.println();
}

// ----------------------- setup / loop -----------------------
void setup() {
  Serial.begin(9600);
  for (int i = 0; i < 4; i++) {
    pinMode(BREAKER_PINS[i], INPUT_PULLUP);   // closed switch = pin LOW
    pinMode(LED_PINS[i], OUTPUT);
  }
  pinMode(ALARM_PIN, OUTPUT);
  machine.attach(SERVO_PIN);
  randomSeed(analogRead(A4));                 // A4 left floating for entropy
  Serial.println("== Load Balancing Game: hold 50 Hz! ==");
}

void loop() {
  unsigned long now = millis();

  if (gameOver) { machine.write(90); return; }

  if (now - lastStep >= STEP_MS) {
    float dt = (now - lastStep) / 1000.0;
    lastStep = now;
    stepPhysics(dt);
    updateLeds();
    updateServo(dt);

    if (elapsed >= GAME_SECONDS) {
      gameOver = true;
      Serial.println("== GAME OVER ==");
      Serial.print("Final score: "); Serial.println(currentScore());
      Serial.print("Unserved energy (MWh): "); Serial.println(unservedMWh, 2);
      Serial.print("Frequency events: "); Serial.println(events);
    }
  }

  if (now - lastPrint >= PRINT_MS && !gameOver) {
    lastPrint = now;
    printDashboard();
  }
}
