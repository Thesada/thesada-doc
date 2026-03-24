---
title: OWB Monitor
parent: Modules
nav_order: 2
has_children: true
description: "Outdoor wood boiler monitoring -- supply/return temperatures, pump current, Telegram alerts."
---

# OWB Monitor

A hydronic woodboiler monitoring node built on the LILYGO T-SIM7080-S3 and four DS18B20 temperature sensors. Monitors supply and return temperatures on two loops, pump current draw on each loop, and sends alerts via Telegram and Home Assistant.

![OWB monitor node overview]({{ site.baseurl }}/assets/img/modules/owb-monitor/module-overview.png)

---

## Hardware

- LILYGO T-SIM7080-S3 (ESP32-S3 + SIM7080G cellular)
- DS18B20 waterproof temperature probes x 4
- SCT-013-030 current transformer clamps x 2
- ADS1115 16-bit ADC

The board, ADS1115, and wiring all fit inside a standard IP65 enclosure. Sensor cables enter through PG7 and PG9 cable glands.

![OWB monitor node closeup]({{ site.baseurl }}/assets/img/modules/owb-monitor/module-closeup.png)

---

## What it measures

- Supply and return temperature - house loop
- Supply and return temperature - barn loop
- AC current draw - house loop pump
- AC current draw - barn loop pump

**Collection interval:** 60s (temperature), 60s (current)

**Publish interval:** Every 60 readings (once per hour)

---

## Enclosure

The node sits in an IP65 junction box mounted near the boiler. The LTE antenna is stuck to the inside of the enclosure wall for cellular fallback when WiFi is unavailable.

![OWB monitor in enclosure with LTE antenna]({{ site.baseurl }}/assets/img/modules/owb-monitor/module-in-enclosure.png)

Cable glands (PG7 for sensor wires, PG9 for USB power) keep the enclosure sealed while allowing cable entry.

![PG7/PG9 cable glands detail]({{ site.baseurl }}/assets/img/modules/owb-monitor/cable-glands-detail.png)

---

## Alerts

- Supply temperature below 40C - boiler going out or not heating
- Supply/return delta below 5C - possible flow or pump issue
- Pump current at zero during heating hours - pump failure
