---
title: OWB Monitor
parent: Modules
nav_order: 1
has_children: true
description: "Outdoor wood boiler monitoring -- supply/return temperatures, pump current, Telegram alerts."
---

# OWB Monitor

A hydronic woodboiler monitoring node built on the LILYGO T-SIM7080-S3 and four DS18B20 temperature sensors. Monitors supply and return temperatures on two loops, pump current draw on each loop, and sends alerts via Telegram and Home Assistant.

**Hardware:**
- LILYGO T-SIM7080-S3 (ESP32-S3 + SIM7080G cellular)
- DS18B20 waterproof temperature probes × 4
- SCT-013-030 current transformer clamps × 2
- ADS1115 16-bit ADC

**What it measures:**
- Supply and return temperature — house loop
- Supply and return temperature — barn loop
- AC current draw — house loop pump
- AC current draw — barn loop pump

**Collection interval:** 60s (temperature), 60s (current)
**Publish interval:** Every 60 readings (once per hour)

**Alerts:**
- Supply temperature below 40°C — boiler going out or not heating
- Supply/return delta below 5°C — possible flow or pump issue
- Pump current at zero during heating hours — pump failure