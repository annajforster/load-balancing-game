# Electricity Load Balancing Game

A hands-on STEM activity that teaches how a power grid stays alive: by constantly
balancing electricity **generation** against **demand**. When the two don't match,
the grid's **frequency** drifts away from its 50 Hz target — and it is up to the
players to keep it steady.

The game is built for teams of **3–6 people**, split into two roles — **generators**
and **network operators** — who must work together to hold frequency against a
day's load profile while faults strike the network at random.

![Block diagram of the mock power network](block_diagram.png)

## What the activity is about

The game centres on a mock power network and the balancing act of managing load and
generation across it. Each team keeps generation and demand in step; any mismatch
shows up immediately as a frequency deviation. Splitting the team into generators
and network operators mirrors how a real grid is run, and makes the point that no
single person controls frequency — it is a shared, second-by-second negotiation.

## How it works

The activity uses a mock **SCADA** system representing part of a power system:
generators, lines, point loads, isolators and circuit breakers. It can be run
digitally (see the demo notebook) or as a simple board with a painted one-line
diagram and LEDs showing breaker status. Everything is driven by a microprocessor
(an Arduino or similar) that reads basic digital and analogue signals.

- **Generators** are each given a dial (a potentiometer) that sets their simulated
  output power. Every hydro generator is controlled by its own dial.
- **Network operators** control the circuit breakers and isolators around the
  system. They clear faults, keep each line within its current rating, and shed or
  curtail load if frequency starts to run away.
- **Generators come in types — hydro, wind and solar — with different inertia.**
  Synchronous hydro machines spin with the grid and resist sudden frequency changes;
  inverter-based wind and solar deliver power but almost no inertia. The more the
  grid leans on wind and solar, the faster frequency swings for the same imbalance,
  so generators and operators must cooperate to keep enough inertia online.

Faults occur at random times and locations. Teams are scored on how consistently
they hold frequency and how little load (energy) they fail to deliver. A synchronous
motor, a frequency meter, or a live graph can show the frequency changing in real time.

## Reading the diagram

The one-line diagram above shows the mock network the teams operate:

- **Generators** — hydro units are circles marked `~`; wind and solar units are
  circles with a down-arrow.
- **Loads** — residential demand (house symbol) peaks in the morning and again in
  the evening; industrial demand (factory symbol) stays roughly constant.
- **Wind** output varies randomly minute to minute; **solar** output rises and falls
  with the sun, peaking around midday.
- **Hydro** output is set by each generator's own potentiometer (dial).
- **Switches / circuit breakers** sit on every line, generator and load so circuits
  can be broken. Operators use them to isolate faults and to disconnect parts of the
  network.
- **Line meters** show the current flowing through each line so operators can avoid
  overloading them.
- **Faults** are simulated at random locations and times — the operators' main job is
  to find and isolate them quickly.
- **The frequency meter** is what the whole game turns on: teams are scored on keeping
  a consistent 50 Hz without dropping load.

| Symbol | Meaning |
|--------|---------|
| Circle with `~` | Hydro generator (player-controlled dial, high inertia) |
| Circle with down-arrow | Wind or solar generator (variable, low/no inertia) |
| House | Residential load (morning + evening peaks) |
| Factory | Industrial load (constant) |

## Why we teach it

The activity shows that electrical frequency is, at heart, about the balance between
generation and load. It makes each stakeholder's role concrete — generators, network
operators and the loads themselves — and demonstrates what each contributes to keeping
frequency stable, all through a fun and interactive medium rather than a lecture.

## Learning outcomes

1. **Balancing load and generation** — understanding why this is what keeps a power
   system's frequency stable.
2. **Roles within the system** — what generators and network operators each do, and
   why they have to coordinate.
3. **Inertia and synchronous generation** — what they mean for a grid, and why a high
   share of inverter-based resources (wind and solar) leaves the system more exposed
   to frequency deviations.

## Playing it: the build

This project includes two ready-to-run versions of the game:

- **`load_balancing_game.ino`** — the complete game on a single Arduino: two hydro
  dials, four breaker switches with status LEDs, a fault alarm, and a servo that
  physically tracks the frequency. It runs end-to-end in TinkerCAD with no PC. The
  step-by-step circuit build is in **`TINKERCAD_WIRING_GUIDE.md`**.
- **`load_balancing_demo.ipynb`** — a Jupyter notebook "digital twin" for demonstrating
  the ideas on screen, with plots of a full day, a skilled-vs-hands-off comparison, an
  inertia demonstration, and live sliders to play with.

### How scoring works

A team starts from a high score and loses points for three things: frequency that
strays from 50 Hz (the bigger and longer the deviation, the larger the penalty),
energy that was never delivered because load was shed or disconnected, and each time
frequency crosses a safe band (with a heavier penalty for a full collapse). The best
teams hold frequency tight while keeping every customer supplied.
