---
title: Well Pump Monitor
parent: Modules
nav_order: 3
description: "Well pump monitoring system -- current draw, pressure tank, short-cycle detection, freeze risk alerting."
has_children: true
---

# Well Pump Monitor

> **Work in progress** -- This module is in the design phase. Hardware has not been built or tested yet. Specifications and BOM may change.
{: .warning }

Monitors a submersible well pump system - pump current draw, pressure
tank pressure, short-cycle detection, and freeze risk alerting.

---

## The Problem

A submersible well pump fails silently. Common failure modes:

- **Short cycling:** The pump turns on and off too frequently - usually
  means the pressure tank has lost its air charge (waterlogged). This
  kills pump motors. By the time you notice low water pressure, the
  pump may already be damaged.
- **Pump seizure:** Motor draws excessive current or zero current.
  Either way, no water.
- **Freeze risk:** In an unheated pump house or exposed plumbing, the
  pressure tank and lines can freeze. By the time you notice, pipes
  have burst.

None of these are visible without instrumentation. The goal is to detect
all three conditions and alert via Telegram before they cause damage.

---

## What It Monitors

| Measurement | Sensor | What it tells you |
|---|---|---|
| Pump current draw | SCT-013-030 CT clamp | Is the pump running? How much current? Abnormal draw = failing motor. |
| Tank pressure | 0.5-4.5V pressure transducer | Real-time system pressure. Tracks fill/draw cycles. |
| Cycle count and timing | Derived from current + pressure | Short-cycle detection. Too many cycles per hour = waterlogged tank. |
| Ambient temperature | DS18B20 | Freeze risk at the pressure tank / pump house. |

---

## System Layout

```
Well (underground)
    |
    | Submersible pump (240V, 2-wire + ground)
    |
    v
Control box (on wall) <-- CT clamp goes here
    |
    | Supply line
    v
Pressure tank
    |-- Pressure switch (40/60 or 30/50 PSI cut-in/cut-out)
    |-- Pressure gauge (existing) <-- brass tee + transducer here
    |-- DS18B20 (ambient temp, freeze risk)
    |
    v
House plumbing
```

---

## Bill of Materials

### Sensors

| Part | Qty | Interface | Purpose | Est. Cost (CAD) |
|---|---|---|---|---|
| SCT-013-030 CT clamp (30A, voltage output) | 1 | Analog (0-1V) via ADS1115 | Pump current draw (240V circuit) | ~$9 |
| Pressure transducer, 0-100 PSI, 0.5-4.5V, 1/4" NPT | 1 | Analog via ADS1115 | Tank pressure - real-time PSI reading | ~$10 |
| DS18B20 waterproof probe (2m lead) | 1 | 1-Wire | Ambient temperature near pressure tank | ~$4 |
| ADS1115 16-bit ADC breakout | 1 | I2C (addr 0x48) | Reads CT clamp and pressure transducer | ~$6 |

### Plumbing

| Part | Qty | Purpose | Est. Cost (CAD) |
|---|---|---|---|
| 1/4" NPT brass tee | 1 | Taps into existing gauge port. Gauge stays, transducer added. | ~$8 |
| Teflon tape | 1 | Thread sealant for NPT fittings | ~$2 |

### Controller

Each node requires its own base board. Two options:

| Option | Board | Est. Cost (CAD) | Notes |
|---|---|---|---|
| With cellular | LILYGO T-SIM7080-S3 | ~$46 | WiFi + LTE-M fallback |
| WiFi only | Thesada base node (custom, no modem) | ~$15-20 | Requires reliable WiFi coverage at pump house |

The well pump monitor is typically in a separate building from the
OWB monitor, so a shared node is unlikely. Choose WiFi-only if the
pump house has reliable WiFi coverage; choose cellular if it does not.

### Total

| Category | WiFi only | With cellular |
|---|---|---|
| Sensors | ~$29 | ~$29 |
| Plumbing | ~$10 | ~$10 |
| Controller | ~$18 | ~$46 |
| **Total** | **~$57** | **~$85** |

---

## Sensor Details

### CT Clamp on 240V Circuit

The well pump runs on 240V. The CT clamp works the same way as on
120V - it measures current through a single conductor, not voltage.

**Critical:** Inside the control box, individual conductors (L1, L2,
ground) should be accessible. Clamp the CT around **one hot conductor
only** (either L1 or L2, not both). Clamping around both hot
conductors in a 240V circuit produces a null reading because the
currents are equal and opposite.

The SCT-013-030 is the voltage-output version (built-in burden
resistor, 0-1V output). A typical submersible pump draws 5-15A at
240V - well within the 30A range of the clamp.

### Pressure Transducer

A 0-100 PSI transducer with 0.5-4.5V output. This is the cheapest
type on AliExpress ($8-12 CAD) and reads directly on the ADS1115
without any signal conditioning.

Output mapping:
- 0.5V = 0 PSI
- 4.5V = 100 PSI
- Linear between these points

A standard residential well system runs at 40-60 or 30-50 PSI.
The 0-100 PSI range has plenty of headroom.

Installation: thread into one side of a 1/4" NPT brass tee. The
existing pressure gauge threads into the other side. The tee
threads into the existing gauge port on the pressure tank. No
plumbing modifications beyond adding the tee.

ADS1115 gain setting: use `"gain": 4.096` in config.json (range
0-4.096V covers the 0.5-4.5V output). Calibration via multiply
factor in firmware config to convert voltage to PSI.

### DS18B20 (Freeze Risk)

Same sensor as the OWB monitor. Mount near the pressure tank or on
exposed plumbing. Alerts if ambient temperature drops below a
threshold (e.g. 2C) when freeze risk is real.

---

## Alert Logic

| Condition | Alert | Priority |
|---|---|---|
| Pump current = 0 for > 5 min while pressure dropping | Pump not running - possible failure | Critical |
| Pump current > [rated amps + 20%] | Pump drawing excessive current | Critical |
| Cycle count > 6 per hour | Short cycling - check pressure tank air charge | Warning |
| Pump on-time < 30 seconds per cycle | Short cycling - very short run times | Warning |
| Ambient temp < 2C | Freeze risk at pump house | Warning |
| Ambient temp < 0C | Freeze warning - take action | Critical |
| Pressure below 20 PSI for > 10 min | Low system pressure | Critical |

### Short-Cycle Detection Logic

A healthy well pump cycle looks like:
1. Pressure drops to cut-in (e.g. 40 PSI) as water is used
2. Pump turns on (current spike, then steady draw)
3. Pressure rises to cut-out (e.g. 60 PSI)
4. Pump turns off
5. Cycle takes several minutes depending on usage

A short cycle looks like:
1. Pump turns on
2. Pressure rises quickly to cut-out (seconds, not minutes)
3. Pump turns off
4. Pressure drops quickly back to cut-in
5. Repeat - many times per hour

This happens when the pressure tank is waterlogged (no air cushion).
The pump has to start and stop constantly because there is no buffer.
Each start puts mechanical stress on the motor.

Detection: count pump start events (current going from ~0 to > 1A)
per hour. More than 6 starts per hour with run times under 1-2 minutes
is a strong indicator of a waterlogged tank.

---

## Pin Assignments

Same controller as OWB monitor (LILYGO T-SIM7080-S3):

| Function | GPIO | Notes |
|---|---|---|
| 1-Wire (DS18B20) | GPIO12 | Shares bus with OWB sensors if on same node |
| I2C SDA (ADS1115) | GPIO1 | |
| I2C SCL (ADS1115) | GPIO2 | |

If sharing a node with the OWB monitor, the DS18B20 is added to
the existing 1-Wire bus and the pressure transducer uses a free
ADS1115 channel (A2 or A3).

If standalone, the ADS1115 uses channels A0 (CT clamp) and A1
(pressure transducer) - same as the OWB layout.

---

## Sourcing

| Source | Parts |
|---|---|
| AliExpress | SCT-013-030, pressure transducer (search "0-100 PSI 0.5-4.5V 1/4 NPT"), DS18B20, ADS1115 |
| Local hardware store | 1/4" NPT brass tee, Teflon tape |

Order the pressure transducer early - AliExpress lead time is 2-4
weeks. Verify the thread is 1/4" NPT (not BSP) before ordering.
Most North American pressure tanks use NPT threads.

---

## Open Items

- [ ] Verify pump rated current draw at 240V (sets the alert threshold)
- [ ] Confirm 1/4" NPT thread on existing gauge port
- [ ] Decide: standalone node or shared with OWB monitor (depends on
      physical distance between boiler room and pump house)
- [ ] Determine short-cycle threshold (starts per hour) from baseline
      data after deployment
