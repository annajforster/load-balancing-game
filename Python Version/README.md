# Electricity Load Balancing Game — Arduino Edition

A STEM teaching game where a team keeps grid **frequency at 50 Hz** by
balancing generation against a changing load while clearing random faults.
It maps the roles in the block diagram onto real controls: **generator players**
turn hydro dials, **network operators** work the circuit breakers. The whole
game runs on a single Arduino and is fully playable inside **TinkerCAD** — no PC.

## The files

| File | What it is |
|------|-----------|
| `load_balancing_game.ino` | The complete game. Physics, load profiles, faults, scoring, LEDs, servo and the serial dashboard all run on the Arduino. |
| `TINKERCAD_WIRING_GUIDE.md` | How to build the circuit and run it in TinkerCAD. |

## Why all-C++ (vs the earlier Python split)

Running everything on the Arduino means it simulates end-to-end in TinkerCAD
with no serial bridge or extra software — the right trade for a classroom. The
only thing lost is an on-screen graph, which the **servo** now stands in for by
physically tracking the frequency. The Uno handles the small floating-point
maths comfortably.

## The model (kept simple on purpose)

Frequency changes in proportion to the generation/load imbalance, divided by the
system **inertia**, plus damping that pulls it back to 50 Hz:

```
df/dt = (gain * imbalance − damping * (f − 50)) / inertia
```

Only the synchronous **hydro** units add inertia. Wind and solar add power but
**no inertia**, so the more the grid leans on them, the faster frequency swings
for the same mistake — losing both hydro units makes the grid about 8× twitchier.
That is the inverter-based-resources lesson, made physical (verified: 2 hydro
online → 0.125 Hz/s for a 20 MW surplus; 1 hydro → 0.25 Hz/s).

- Hydro 1 & 2: player dials, 0–80 MW each, high inertia.
- Wind: random walk (varies randomly). Solar: half-sine, peaks at midday.
- Residential load: morning + evening peaks. Industrial load: constant.
- Faults hit a random feeder; its status LED and the pin-13 alarm blink. The
  operator opens that breaker to isolate it, then re-closes once it clears.

## The servo

The servo sweeps back and forth and the **speed of its sweep tracks frequency**,
so the class can watch the "machine" spin faster when frequency is high and
stall as it collapses — a tangible synchronous-machine analogue. If you'd rather
it act as a fixed **needle gauge** (angle = current frequency), there's a
commented one-line swap inside `updateServo()`.

## Scoring

Higher is better, out of ~1000. Penalties for:
- **Frequency quality** — accumulated squared deviation from 50 Hz.
- **Unserved energy** — load disconnected (e.g. shed to save frequency), in MWh.
- **Events** — each excursion past ±0.8 Hz, with extra penalty for a blackout.

Tested behaviour: a skilful team holds ~50.00 Hz / score ~999; a passive team
sags to ~49.4 Hz / score ~720 with several events.

## Maps to the learning outcomes

- *Balancing load and generation* — the entire frequency mechanic.
- *Roles of generators vs operators* — dials vs breakers, who fixes what.
- *Inertia & inverter-based resources* — synchronous hydro vs wind/solar, shown
  on the servo.

## Easy extensions

- Swap the Uno for a **Mega** to add more dials/breakers and cover the full
  one-line diagram (more generators, more feeders).
- Add an LCD or 7-segment display to show the Hz reading numerically.
- Tune any constant at the top of the sketch to change difficulty.
