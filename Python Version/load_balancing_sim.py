#!/usr/bin/env python3
"""
Electricity Load Balancing Game - Digital Twin Simulation
=========================================================

A simple, intuitive real-time simulator of grid frequency for a STEM
teaching game. Generators (hydro, controlled by players via dials) must be
balanced against time-varying loads while a network operator manages circuit
breakers and clears random faults. Frequency drifts from 50 Hz whenever
generation and load are mismatched, and how fast it drifts depends on the
system inertia (which only the synchronous hydro units provide).

Run modes
---------
  --port COM3        Read a real Arduino over serial (the actual game).
  --auto             Automatic demo controller (no human, no hardware).
  --selftest         Fast headless run + summary, then exit (for testing).
  (no flag)          Solo keyboard mode: type commands to play without hardware.

  --plot             Add a live matplotlib frequency graph (needs matplotlib).
  --minutes N        Real minutes the game lasts (default 10) = one 24h day.

Serial protocol expected from the Arduino, one line ~10x/sec:
  H1:512,H2:300,B1:1,B2:0,B3:1,B4:1
  (H* = pot reading 0..1023, B* = breaker closed=1 / open=0)
"""

import argparse
import math
import os
import queue
import random
import sys
import threading
import time

# ---------------------------------------------------------------------------
# Tunable game constants (a teacher can safely edit these)
# ---------------------------------------------------------------------------
NOMINAL_HZ      = 50.0
HYDRO_MAX_MW    = 80.0     # full-scale output of each player hydro dial
HYDRO_INERTIA   = 4.0      # inertia each ONLINE hydro unit contributes
INERTIA_FLOOR   = 1.0      # stops divide-by-zero when little/no inertia online
DAMPING         = 2.0      # load self-regulation: pulls frequency back to 50
FREQ_GAIN       = 0.05     # Hz/s change per MW of imbalance per unit inertia
FAULT_DISTURB   = 60.0     # MW the grid "loses" while a fault is live + closed
TRIP_BAND       = 0.8      # |Δf| beyond this counts as an under/over-freq event
BLACKOUT_BAND   = 3.0      # |Δf| beyond this = system collapse (resets to 50)

# Scoring weights
K_FREQ   = 4.0    # weight on frequency-quality penalty
K_ENERGY = 0.5    # weight on unserved energy (per MWh)
K_EVENT  = 15.0   # penalty per trip/blackout event


# ---------------------------------------------------------------------------
# Load and renewable profiles, as a function of the simulated hour (0-24)
# ---------------------------------------------------------------------------
def residential_load(hour):
    """Double hump: morning peak ~8am, evening peak ~7pm."""
    base = 55.0
    morning = 45.0 * math.exp(-((hour - 8.0) ** 2) / 4.0)
    evening = 55.0 * math.exp(-((hour - 19.0) ** 2) / 6.0)
    return base + morning + evening


def industrial_load(hour):
    """Industrial demand is essentially constant."""
    return 50.0


def solar_output(hour):
    """Half-sine bump during daylight (~6am to ~6pm), peak at noon."""
    if 6.0 <= hour <= 18.0:
        return 60.0 * math.sin(math.pi * (hour - 6.0) / 12.0)
    return 0.0


# ---------------------------------------------------------------------------
# Simulation state
# ---------------------------------------------------------------------------
class Sim:
    def __init__(self, game_minutes):
        self.freq = NOMINAL_HZ
        self.game_seconds = game_minutes * 60.0
        self.elapsed = 0.0

        # Player-controlled hydro setpoints (MW). Start at half output.
        self.hydro1 = HYDRO_MAX_MW * 0.5
        self.hydro2 = HYDRO_MAX_MW * 0.5

        # Wind uses a random walk so it "varies randomly" per the brief.
        self.wind = 25.0

        # Breakers: True = closed (connected). Operators open these.
        #   B1 = wind+solar feeder, B2 = residential load,
        #   B3 = industrial load, B4 = hydro unit 2
        self.breakers = {"B1": True, "B2": True, "B3": True, "B4": True}

        # Fault state
        self.fault_feeder = None
        self.fault_clear_at = 0.0
        self.next_fault_at = random.uniform(20.0, 45.0)

        # Score accumulators
        self.freq_sq_integral = 0.0   # integral of (f-50)^2 dt
        self.unserved_mwh = 0.0
        self.events = 0
        self._below_band = False      # edge-detect for counting trip events

    # -- time mapping -------------------------------------------------------
    @property
    def hour(self):
        """Map real elapsed time onto a 24h day."""
        return (self.elapsed / self.game_seconds) * 24.0 % 24.0

    # -- one physics step ---------------------------------------------------
    def step(self, dt):
        self.elapsed += dt
        self._update_wind(dt)
        self._update_faults()

        p_gen, inertia = self._generation()
        p_load = self._demand()

        # A live, un-isolated fault behaves like a sudden hidden drain on the grid.
        disturbance = 0.0
        if self.fault_feeder and self.breakers[self.fault_feeder]:
            disturbance = FAULT_DISTURB

        imbalance = p_gen - p_load - disturbance

        # Simple swing-style update: rate of change of frequency is the
        # imbalance divided by inertia, plus damping that restores 50 Hz.
        rocof = (FREQ_GAIN * imbalance - DAMPING * (self.freq - NOMINAL_HZ)) / inertia
        self.freq += rocof * dt

        self._update_score(dt, p_load)
        return p_gen, p_load, inertia, imbalance, disturbance

    def _update_wind(self, dt):
        self.wind += random.uniform(-1.0, 1.0) * dt * 8.0
        self.wind = max(0.0, min(50.0, self.wind))

    def _update_faults(self):
        if self.fault_feeder is None and self.elapsed >= self.next_fault_at:
            self.fault_feeder = random.choice(list(self.breakers.keys()))
            self.fault_clear_at = self.elapsed + random.uniform(8.0, 15.0)
        elif self.fault_feeder and self.elapsed >= self.fault_clear_at:
            # Fault has been on the system long enough to self-extinguish;
            # operator may now safely re-close the breaker.
            self.fault_feeder = None
            self.next_fault_at = self.elapsed + random.uniform(25.0, 50.0)

    def _generation(self):
        h = self.hour
        p = self.hydro1
        inertia = HYDRO_INERTIA
        if self.breakers["B4"]:
            p += self.hydro2
            inertia += HYDRO_INERTIA
        if self.breakers["B1"]:
            p += self.wind + solar_output(h)   # wind/solar add power, no inertia
        return p, max(INERTIA_FLOOR, inertia)

    def _demand(self):
        h = self.hour
        p = 0.0
        if self.breakers["B2"]:
            p += residential_load(h)
        if self.breakers["B3"]:
            p += industrial_load(h)
        return p

    def _update_score(self, dt, p_load):
        df = self.freq - NOMINAL_HZ
        self.freq_sq_integral += df * df * dt

        # Any load feeder that is open is load we failed to deliver.
        h = self.hour
        shed = 0.0
        if not self.breakers["B2"]:
            shed += residential_load(h)
        if not self.breakers["B3"]:
            shed += industrial_load(h)
        self.unserved_mwh += shed * dt / 3600.0   # MW*s -> MWh

        # Count discrete under/over-frequency trip events on entry.
        out = abs(df) > TRIP_BAND
        if out and not self._below_band:
            self.events += 1
        self._below_band = out

        # Blackout: frequency ran away. Count it and recover to 50 Hz.
        if abs(df) > BLACKOUT_BAND:
            self.events += 2
            self.freq = NOMINAL_HZ

    def score(self):
        secs = max(self.elapsed, 1e-6)
        rms_dev = math.sqrt(self.freq_sq_integral / secs)
        raw = 1000.0
        raw -= K_FREQ * self.freq_sq_integral
        raw -= K_ENERGY * self.unserved_mwh
        raw -= K_EVENT * self.events
        return {
            "score": round(max(0.0, raw)),
            "rms_dev_hz": round(rms_dev, 3),
            "unserved_mwh": round(self.unserved_mwh, 2),
            "events": self.events,
        }


# ---------------------------------------------------------------------------
# Input sources -- each provides hydro setpoints + breaker states
# ---------------------------------------------------------------------------
class KeyboardInput:
    """Solo play with no hardware: type line commands.
       h1 +5 / h1 -5   adjust hydro 1     b2   toggle breaker 2     q  quit"""
    HELP = "  commands: h1 +/-N , h2 +/-N , b1 b2 b3 b4 (toggle) , q (quit)"

    def __init__(self):
        self.q = queue.Queue()
        self.quit = False
        t = threading.Thread(target=self._reader, daemon=True)
        t.start()

    def _reader(self):
        for line in sys.stdin:
            self.q.put(line.strip())

    def apply(self, sim):
        while not self.q.empty():
            cmd = self.q.get().lower().split()
            if not cmd:
                continue
            if cmd[0] == "q":
                self.quit = True
            elif cmd[0] in ("h1", "h2") and len(cmd) == 2:
                try:
                    delta = float(cmd[1])
                    cur = sim.hydro1 if cmd[0] == "h1" else sim.hydro2
                    val = max(0.0, min(HYDRO_MAX_MW, cur + delta))
                    if cmd[0] == "h1":
                        sim.hydro1 = val
                    else:
                        sim.hydro2 = val
                except ValueError:
                    pass
            elif cmd[0] in sim.breakers:
                key = cmd[0].upper()
                sim.breakers[key] = not sim.breakers[key]


class AutoInput:
    """Automatic controller: nudges hydro to chase load, isolates faults."""
    def apply(self, sim):
        # Clear faults by opening the faulted breaker; reclose when clear.
        for b in sim.breakers:
            if sim.fault_feeder == b:
                sim.breakers[b] = False
            elif not sim.breakers[b] and sim.fault_feeder is None:
                sim.breakers[b] = True
        # Chase the imbalance with the available hydro.
        p_gen, _ = sim._generation()
        p_load = sim._demand()
        err = p_load - p_gen
        sim.hydro1 = max(0.0, min(HYDRO_MAX_MW, sim.hydro1 + err * 0.5))
        if sim.breakers["B4"]:
            sim.hydro2 = max(0.0, min(HYDRO_MAX_MW, sim.hydro2 + err * 0.5))
    quit = False


class SerialInput:
    """Read a real Arduino over serial in a background thread."""
    def __init__(self, port, baud=9600):
        import serial  # pyserial; only imported if this mode is used
        self.ser = serial.Serial(port, baud, timeout=0.1)
        self.latest = {}
        self.quit = False
        self._last_fault = "init"
        t = threading.Thread(target=self._reader, daemon=True)
        t.start()

    def _reader(self):
        while True:
            try:
                line = self.ser.readline().decode(errors="ignore").strip()
            except Exception:
                continue
            if not line:
                continue
            d = {}
            for part in line.split(","):
                if ":" in part:
                    k, v = part.split(":", 1)
                    try:
                        d[k.strip()] = int(v)
                    except ValueError:
                        pass
            if d:
                self.latest = d

    def apply(self, sim):
        d = self.latest
        if "H1" in d:
            sim.hydro1 = d["H1"] / 1023.0 * HYDRO_MAX_MW
        if "H2" in d:
            sim.hydro2 = d["H2"] / 1023.0 * HYDRO_MAX_MW
        for b in sim.breakers:
            if b in d:
                sim.breakers[b] = bool(d[b])
        # Tell the Arduino where the fault is so it can flash the alarm LED.
        fault = sim.fault_feeder or "NONE"
        if fault != self._last_fault:
            self._last_fault = fault
            try:
                self.ser.write((f"FAULT:{fault}\n").encode())
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Console dashboard
# ---------------------------------------------------------------------------
def render(sim, p_gen, p_load, inertia, imbalance, disturbance, controller):
    os.system("cls" if os.name == "nt" else "clear")
    df = sim.freq - NOMINAL_HZ
    bar_pos = int(max(-10, min(10, df / 0.3)))   # one char ~ 0.3 Hz
    bar = list("----------|----------")
    bar[10 + bar_pos] = "#"
    fault = f"!! FAULT on {sim.fault_feeder} -- ISOLATE IT !!" if sim.fault_feeder else "system normal"

    print("=" * 56)
    print("   ELECTRICITY LOAD BALANCING  -  DIGITAL TWIN")
    print("=" * 56)
    print(f"  Day time : {int(sim.hour):02d}:{int((sim.hour%1)*60):02d}"
          f"      Game: {sim.elapsed:5.0f}/{sim.game_seconds:.0f}s")
    print()
    print(f"  FREQUENCY : {sim.freq:6.2f} Hz   ({df:+.2f})")
    print(f"   47 [{''.join(bar)}] 53")
    print()
    print(f"  Generation: {p_gen:6.1f} MW   (hydro1 {sim.hydro1:4.0f}"
          f"  hydro2 {sim.hydro2:4.0f}  wind {sim.wind:4.0f}"
          f"  solar {solar_output(sim.hour):4.0f})")
    print(f"  Demand    : {p_load:6.1f} MW")
    print(f"  Imbalance : {imbalance:+6.1f} MW"
          + (f"   (fault drain -{disturbance:.0f})" if disturbance else ""))
    print(f"  Inertia   : {inertia:5.1f}   <- lower = faster swings")
    print()
    bk = "  ".join(f"{b}:{'ON ' if v else 'off'}" for b, v in sim.breakers.items())
    print(f"  Breakers  : {bk}")
    print(f"  Status    : {fault}")
    print()
    s = sim.score()
    print(f"  SCORE {s['score']:5d}   rms Δf {s['rms_dev_hz']}Hz"
          f"   unserved {s['unserved_mwh']}MWh   events {s['events']}")
    if isinstance(controller, KeyboardInput):
        print("\n" + KeyboardInput.HELP)


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def run(controller, game_minutes, realtime=True, use_plot=False):
    sim = Sim(game_minutes)
    dt = 0.1
    plot = LivePlot() if use_plot else None
    last = time.time()

    while sim.elapsed < sim.game_seconds and not controller.quit:
        controller.apply(sim)
        out = sim.step(dt)
        if realtime:
            render(sim, *out, controller)
            if plot:
                plot.update(sim.elapsed, sim.freq)
            sleep = dt - (time.time() - last)
            if sleep > 0:
                time.sleep(sleep)
            last = time.time()

    return sim.score()


class LivePlot:
    def __init__(self):
        import matplotlib.pyplot as plt
        self.plt = plt
        plt.ion()
        self.fig, self.ax = plt.subplots()
        self.xs, self.ys = [], []
        self.line, = self.ax.plot([], [])
        self.ax.set_ylim(46, 54)
        self.ax.axhline(50, linestyle="--")
        self.ax.set_xlabel("time (s)")
        self.ax.set_ylabel("frequency (Hz)")

    def update(self, t, f):
        self.xs.append(t)
        self.ys.append(f)
        self.line.set_data(self.xs, self.ys)
        self.ax.set_xlim(0, max(10, t))
        self.fig.canvas.draw_idle()
        self.plt.pause(0.001)


def main():
    ap = argparse.ArgumentParser(description="Load balancing game digital twin")
    ap.add_argument("--port", help="serial port of the Arduino (real game)")
    ap.add_argument("--auto", action="store_true", help="automatic demo controller")
    ap.add_argument("--selftest", action="store_true", help="fast headless test")
    ap.add_argument("--plot", action="store_true", help="live frequency graph")
    ap.add_argument("--minutes", type=float, default=10.0, help="game length in minutes")
    args = ap.parse_args()

    if args.selftest:
        random.seed(1)
        sim = Sim(game_minutes=2.0)
        ctrl = AutoInput()
        for _ in range(1200):          # 120 sim-seconds at dt=0.1
            ctrl.apply(sim)
            sim.step(0.1)
        print("Self-test complete.")
        print("Final frequency:", round(sim.freq, 3), "Hz")
        print("Score:", sim.score())
        return

    if args.port:
        controller = SerialInput(args.port)
    elif args.auto:
        controller = AutoInput()
    else:
        controller = KeyboardInput()

    result = run(controller, args.minutes, realtime=True, use_plot=args.plot)
    print("\nGAME OVER")
    print("Final score:", result)


if __name__ == "__main__":
    main()
