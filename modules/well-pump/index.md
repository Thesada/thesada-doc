---
title: Well Pump Monitoring System
parent: Modules
nav_order: 3
description: "DIY open-source well pump monitor: watch a water well pump for dry running, short cycling, a stopped pump and freezing, with alerts to your phone."
---

# Well Pump Monitoring System

> **On the bench, not in the field yet.** This monitor is still being designed. If you look after wells or pumps and want to know more, or would like to try it in a test setup, get in touch: [info@hit-con.ca](mailto:info@hit-con.ca)

Monitors a water well pump and its pressure tank: is the pump running, is it running dry, is it short cycling, and is the pump house about to freeze. It sends an alert to your phone before a small problem becomes a burnt-out pump or a burst pipe. Open source, about $57 CAD in parts, no cloud subscription.

---

## The Problem

A submersible well pump fails silently. Common failure modes:

- **Short cycling:** The pump turns on and off too frequently - usually means the pressure tank has lost its air charge (waterlogged) or you have a leak somewhere. This kills pump motors. By the time you notice low water pressure, the pump may already be damaged.
- **Pump seizure:** Motor draws excessive current or zero current. Either way, no water.
- **Running dry:** The water level drops below the pump intake (drought, a heavy draw, a failing well). The pump keeps spinning with no water to move and no water to cool it. A few minutes of this can destroy the motor.
- **Freeze risk:** In an unheated pump house or exposed plumbing, the pressure tank and lines can freeze. By the time you notice, pipes have burst.

None of these are visible without instrumentation. The goal is to detect all three conditions and alert via Telegram before they cause damage.

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

The well pump monitor is typically in a separate building from the OWB monitor, so a shared node is unlikely. Choose WiFi-only if the pump house has reliable WiFi coverage or cellular if it does not.

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

The well pump runs on 240V. The CT clamp works the same way as on 120V - it measures current through a single conductor, not voltage.

**Critical:** Inside the control box, individual conductors (L1, L2, ground) should be accessible. Clamp the CT around **one hot conductor only** (either L1 or L2, not both). Clamping around both hot conductors in a 240V circuit produces a null reading because the currents are equal and opposite.

The SCT-013-030 is the voltage-output version (built-in burden resistor, 0-1V output). A typical submersible pump draws 5-15A at 240V - well within the 30A range of the clamp.

### Pressure Transducer

A 0-100 PSI transducer with 0.5-4.5V output. This is the cheapest type on AliExpress ($8-12 CAD) and reads directly on the ADS1115 without any signal conditioning.

Output mapping:
- 0.5V = 0 PSI
- 4.5V = 100 PSI
- Linear between these points

A standard residential well system runs at 40-60 or 30-50 PSI. The 0-100 PSI range has plenty of headroom.

Installation: thread into one side of a 1/4" NPT brass tee. The existing pressure gauge threads into the other side. The tee threads into the existing gauge port on the pressure tank. No plumbing modifications beyond adding the tee.

ADS1115 gain setting: use `"gain": 4.096` in config.json (range 0-4.096V covers the 0.5-4.5V output). Calibration via multiply factor in firmware config to convert voltage to PSI.

### DS18B20 (Freeze Risk)

Same sensor as the OWB monitor. Mount near the pressure tank or on exposed plumbing. Alerts if ambient temperature drops below a threshold (e.g. 2C) when freeze risk is real.

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

### Dry-Run Detection

A submersible pump moving water draws a steady current. With no water at the intake it has almost no load, so the current drops well below its normal running value while the pump stays switched on. Pressure stops rising at the same time.

Detection: while the pump is on, current more than about 30 % below its learned normal running current, together with flat or falling pressure for more than 30 seconds, raises a critical "pump running dry" alert. The normal running current is learned from the first days of data, since every pump and well depth differs.

This is a monitor, not a protection relay. It tells you fast, it does not switch the pump off. For automatic cut-off, a dry-run protection relay in the control box is the right part, and this monitor shows you when it trips.

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

This happens when the pressure tank is waterlogged (no air cushion) or you have a leak in the system. The pump has to start and stop constantly because there is no buffer. Each start puts mechanical stress on the motor.

Detection: count pump start events (current going from ~0 to > 1A) per hour. More than 6 starts per hour with run times under 1-2 minutes is a strong indicator of a waterlogged tank or a leak.

---

## Pin Assignments

Same controller as OWB monitor (LILYGO T-SIM7080-S3):

| Function | GPIO |
|---|---|
| 1-Wire (DS18B20) | GPIO12 |
| I2C SDA (ADS1115) | GPIO1 |
| I2C SCL (ADS1115) | GPIO2 |



---

## Sourcing

| Source | Parts |
|---|---|
| AliExpress | SCT-013-030, pressure transducer (search "0-100 PSI 0.5-4.5V 1/4 NPT"), DS18B20, ADS1115 |
| Local hardware store | 1/4" NPT brass tee, Teflon tape |

Order the pressure transducer early - AliExpress lead time is 2-4 weeks. Verify the thread is 1/4" NPT (not BSP) before ordering. Most North American pressure tanks use NPT threads.

---

## FAQ

**How do I know if my well pump is running?** Clamp a current sensor around one hot wire at the control box. Current above about 1 A means the pump runs. This monitor logs every start and stop, so you also see how long and how often it runs.

**Can I detect a dry well before the pump burns out?** Yes, by its current. A pump with no water draws noticeably less than its normal running current. See dry-run detection above.

**What is short cycling and why does it matter?** The pump starts and stops many times an hour, usually because the pressure tank lost its air charge. Every start wears the motor. Counting starts per hour catches it early.

**Does it need internet or a cloud account?** It needs a network to send alerts: Wi-Fi, or LTE-M on the cellular board when the pump house has no Wi-Fi. There is no cloud subscription. Data goes to your own app or Home Assistant.

---

## Open Items

- [ ] Verify pump rated current draw at 240V (sets the alert threshold)
- [ ] Confirm 1/4" NPT thread on existing gauge port
- [ ] Decide: standalone node or shared with another module's node (depends on
      physical distance between the deployment sites)
- [ ] Determine short-cycle threshold (starts per hour) from baseline
      data after deployment

---

> **On the bench, not in the field yet.** This monitor is still being designed. If you look after wells or pumps and want to know more, or would like to try it in a test setup, get in touch: [info@hit-con.ca](mailto:info@hit-con.ca)
