---
title: Bill of Materials
parent: OWB Monitor
nav_order: 1
description: "Bill of materials for the outdoor wood boiler monitoring node -- DS18B20, CT clamps, ADS1115, LILYGO T-SIM7080-S3."
---

# OWB Monitor - Bill of Materials

Parts list for the outdoor wood boiler monitoring node. Monitors
supply/return temperatures on two hydronic loops and pump current draw
on each circulator pump.

---

## Sensors

| Part | Qty | Interface | Purpose | Est. Cost (CAD) |
|---|---|---|---|---|
| DS18B20 waterproof probe (2m lead) | 4 | 1-Wire | Supply and return temp on house loop and barn loop | ~$14 |
| SCT-013-030 CT clamp (30A, voltage output) | 2 | Analog (0-1V) via ADS1115 | Current draw on each circulator pump | ~$17 |
| ADS1115 16-bit ADC breakout | 1 | I2C (addr 0x48) | Converts CT clamp analog signal to digital for ESP32 | ~$6 |

### DS18B20 Notes

- Use the waterproof probe version with a stainless steel tip, not the bare TO-92 package
- Pipe-clamp mounting: thermal paste between probe and pipe, secured with a hose clamp
- All four sensors run on a single 1-Wire data bus (one GPIO pin)
- Each sensor has a unique address burned into the chip - run a 1-Wire scan to discover addresses before configuring

### SCT-013-030 Notes

- The SCT-013-030 is the **voltage output** version with a built-in burden resistor
- Output: 0-1V AC proportional to 0-30A measured current
- Clamps around a **single conductor** only - clamping around both wires in a cable produces a null reading (currents cancel)
- No external signal conditioning needed - connect directly to ADS1115 input

### ADS1115 Notes

- 16-bit ADC, 4 channels, I2C interface
- Default address 0x48 (addr pin to GND)
- Two differential channels used: A0_A1 for house pump, A2_A3 for barn pump
- Gain setting: 0.256V in config.json (tightest usable range for 0-1V CT clamp signal, best resolution)
- Calibration: multiply factor in firmware config -- fine-tune against a clamp meter reading on-site

---

## Controller

| Part | Qty | Purpose | Est. Cost (CAD) |
|---|---|---|---|
| LILYGO T-SIM7080-S3 | 1 | Main controller (ESP32-S3 + Cat-M1 cellular) | ~$46 |

### Pin Assignments

Confirmed against the LILYGO T-SIM7080-S3 board:

| Function | GPIO | Notes |
|---|---|---|
| 1-Wire (DS18B20) | GPIO12 | Single data bus for all four temp sensors |
| I2C SDA (ADS1115) | GPIO1 | |
| I2C SCL (ADS1115) | GPIO2 | |

---

## Monitored Outlet Box

A custom plug-in enclosure that the circulator pumps plug into. Each
outlet is wired through a CT clamp for current monitoring. No panel
work or hardwiring required.

| Part | Qty | Purpose | Est. Cost (CAD) |
|---|---|---|---|
| 2-outlet box (120V, standard) | 1 | Enclosure for monitored outlets | ~$10 |
| 14 AWG cable + plug | 1 | Input cable with standard plug | ~$8 |

The pumps plug into the box. The box plugs into a standard wall outlet.
Each CT clamp goes around the hot conductor inside the box for each
outlet.

---

## Mounting and Consumables

| Part | Qty | Purpose | Est. Cost (CAD) |
|---|---|---|---|
| Hose clamps, 1" range (e.g. 3/4" - 1-1/4" adjustable) | 4 | Secure DS18B20 probes to ~1" OD pipes | ~$4 |
| Thermal paste | 1 tube | Thermal contact between probe and pipe | ~$5 |
| USB-C cable + 5V/2A power supply | 1 | Power for the LILYGO board | ~$12 |
| Temporary enclosure | 1 | Protects the board during initial deployment | ~$8 |

### Enclosure Notes

The initial deployment uses a temporary enclosure. Permanent housing
will be 3D-printed in ASA (heat and UV resistant). That is a separate
future step.

---

## Total Estimated Cost

| Category | Est. Cost (CAD) |
|---|---|
| Sensors (DS18B20, CT clamps, ADC) | ~$37 |
| Controller (LILYGO T-SIM7080-S3) | ~$46 |
| Monitored outlet box | ~$18 |
| Mounting and consumables | ~$29 |
| **Total** | **~$130** |

<!-- NOTE: This total is for the OWB monitor node only. It does not include
     the base node prototyping costs (PCB fabrication, solar charging,
     battery, IP65 enclosure) which are shared across all Thesada modules.
     See the Hardware Costs sheet in the financial model for the full
     per-module and total breakdown. -->

---

## Sourcing

Almost everything comes from AliExpress. Lead times to Canada are
typically 2-4 weeks, so order early. The cost savings are significant -
most components are 30-60% cheaper than domestic alternatives.

Amazon or Digi-Key are fallbacks for when you need something fast
(2-3 day shipping) and are willing to pay the premium for it.

| Source | When to use | Parts |
|---|---|---|
| AliExpress | Default for everything | DS18B20 probes, SCT-013-030 clamps, ADS1115, LILYGO board, USB-C supply, hose clamps, enclosures |
| Amazon | Need it this week | Thermal paste, USB cables, hose clamps if sizing is wrong |
| Local hardware store | Same day | Outlet box, 14 AWG cable, wire nuts |
| Digi-Key | Specific part not on AliExpress, or need exact specs fast | ADS1115 breakout (verified datasheet), precision resistors |

The BOM prices above are based on AliExpress pricing. Sourcing the
same parts from Amazon or Digi-Key would roughly double the total cost.
