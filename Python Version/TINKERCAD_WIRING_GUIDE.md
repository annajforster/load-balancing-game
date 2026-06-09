# TinkerCAD Wiring Guide

This version runs **entirely on the Arduino** — no PC, no Python. You build the
circuit in TinkerCAD's canvas, paste in `load_balancing_game.ino`, and play it
right there in the browser. (TinkerCAD runs Arduino C++ and can't import a
circuit file, so this is the build sheet.)

## What to drag onto the canvas

- 1x Arduino Uno R3
- 1x (or 2x) breadboard
- 2x Potentiometer — the hydro generator dials
- 4x Slide switch *or* pushbutton — the circuit breakers B1–B4
- 4x LED + 4x 220 ohm resistor — breaker status lights
- 1x Positional Micro Servo — the "synchronous machine" / frequency indicator

## Connections

Potentiometers (3 legs: outer-1, wiper-middle, outer-2):
| Pot | outer-1 | wiper (middle) | outer-2 |
|-----|---------|----------------|---------|
| Hydro 1 | 5V | A0 | GND |
| Hydro 2 | 5V | A1 | GND |

Breaker switches (one side to the pin, the other to GND). The sketch uses
`INPUT_PULLUP`, so **closed = connected to GND**; no extra resistors needed.
| Switch | Pin | Controls |
|--------|-----|----------|
| B1 | D2 | wind + solar feeder |
| B2 | D3 | residential load |
| B3 | D4 | industrial load |
| B4 | D5 | hydro unit 2 |

Status LEDs (long leg / anode to the pin via a 220 ohm resistor, short leg to GND):
| LED | Pin |
|-----|-----|
| B1 status | D6 |
| B2 status | D7 |
| B3 status | D8 |
| B4 status | D9 |

Servo (3-wire):
| Servo wire | Connect to |
|------------|-----------|
| Signal (orange/yellow) | D10 |
| Power (red) | 5V |
| Ground (brown/black) | GND |

The on-board pin-13 LED is the fault alarm (no wiring needed). Leave **A4**
unconnected — the sketch reads its floating noise to seed the random faults.

## Running it in TinkerCAD

1. Build the circuit above.
2. Open the **Code** panel, switch it to **Text**, and paste all of
   `load_balancing_game.ino`.
3. Click **Start Simulation**.
4. Open **Code > Serial Monitor** (9600 baud) to see the live dashboard, e.g.
   `09:14  f=49.87Hz  gen=130  load=132  H=8  B=1101  FAULT:B2  score=812`.

## How to play

- **Generators:** watch the frequency and turn the hydro dials so generation
  matches demand. If you have spare dial range, hold a little in reserve.
- **Operators:** when a status LED (and the pin-13 alarm) starts blinking, that
  feeder is faulted — flip its switch to isolate it, then flip it back once the
  fault clears. Open a load breaker to shed load if frequency climbs too high.
- The **servo** sweeps faster when frequency is high and stalls as it collapses —
  your physical "is the grid spinning at the right speed?" gauge.
- After `GAME_SECONDS` (default 600 s = one simulated day) the Serial Monitor
  prints the final score.

To change difficulty, edit the constants near the top of the sketch
(`GAME_SECONDS`, `FAULT_DISTURB`, `HYDRO_MAX_MW`, the scoring weights, etc.).
