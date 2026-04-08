---
title: Wiring
parent: OWB Monitor
nav_order: 1
description: "Wiring diagram for the OWB monitor -- DS18B20 1-Wire bus, ADS1115 I2C, CT clamp connections."
---

# OWB Monitor - Wiring

## Wiring Diagram

```
                    LILYGO T-SIM7080-S3
                   ┌─────────────────────┐
       DC1 (3V3) ──┤ 3V3                 │
             GND ──┤ GND                 │
                   │                     │
          GPIO12 ──┤ 1-Wire ─────────────┼──[4.7kΩ]── DC1 (3V3)
                   │          │          │
                   │          ├── DS18B20 (House loop supply)
                   │          ├── DS18B20 (House loop return)
                   │          ├── DS18B20 (Barn loop supply)
                   │          └── DS18B20 (Barn loop return)
                   │                     │
            GPIO1 ──┤ SDA ───────────────── ADS1115 SDA
            GPIO2 ──┤ SCL ───────────────── ADS1115 SCL
                   └─────────────────────┘

    ADS1115 (addr 0x48)
   ┌──────────────────────────────────────┐
   │ VCC  ── DC1 (3V3)                    │
   │ GND  ── GND                          │
   │ ADDR ── GND                          │
   │ A0 ──┐  SCT-013-030 (house pump)     │
   │ A1 ──┘                               │
   │ A2 ──┐  SCT-013-030 (barn pump)      │
   │ A3 ──┘                               │
   └──────────────────────────────────────┘
```

---

## Temperature Sensors - DS18B20

Four DS18B20 waterproof probes mounted on pipes using hose clamps with thermal paste. All four sensors share a single 1-Wire data line.

| Sensor | Location | GPIO |
|---|---|---|
| House loop supply | Supply pipe - house loop | GPIO12 (1-Wire bus) |
| House loop return | Return pipe - house loop | GPIO12 (1-Wire bus) |
| Barn loop supply | Supply pipe - barn loop | GPIO12 (1-Wire bus) |
| Barn loop return | Return pipe - barn loop | GPIO12 (1-Wire bus) |

### Mounting

- Apply thermal paste to the pipe at each sensor location
- Place the DS18B20 probe flat against the paste
- Secure with a hose clamp sized to the pipe OD

### 1-Wire Pull-up Resistor

The 1-Wire bus requires a 4.7kΩ pull-up resistor between the data line and 3.3V. Place it at the node end of the wire run, not at the sensor.

---

## Current Sensors - SCT-013-030

Two CT clamps, one per pump. Each clamp goes around the **hot conductor only** - not both conductors in the cable. Clamping both conductors cancels the magnetic field and produces a null reading.

The pumps are plug-in. A custom monitored outlet box (planned) routes each pump's hot conductor through a CT clamp before the outlet. The box plugs into a standard 120V outlet - no panel work required.

| Sensor | Pump | ADS1115 Channel |
|---|---|---|
| House pump current | House loop pump | A0_A1 (differential) |
| Barn pump current | Barn loop pump | A2_A3 (differential) |

### SCT-013-030 Notes

The SCT-013-030 is the **voltage output** version with a built-in burden resistor. Output is 0-1V AC proportional to 0-30A. Connects directly to ADS1115 - no external resistor needed.

---

## ADS1115 - I2C

| ADS1115 Pin | LILYGO T-SIM7080-S3 Pin |
|---|---|
| VCC | DC1 (3V3) |
| GND | GND |
| SDA | GPIO1 |
| SCL | GPIO2 |
| ADDR | GND (address 0x48) |

---

## Power

5V Power supply and LiPo planned for the permanent install.
