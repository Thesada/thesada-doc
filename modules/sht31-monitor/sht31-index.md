---
title: SHT31 Monitor
parent: Modules
nav_order: 1
description: "SHT31 indoor temperature and humidity monitor -- ESPHome on Freenove ESP32-S3."
has_children: true
---

# SHT31 Monitor

A temperature and humidity monitoring node built on the Freenove ESP32-S3 WROOM and SHT31 sensor. Publishes readings to Home Assistant via the ESPHome native API and sends hourly Telegram alerts.

**Hardware:**
- Freenove ESP32-S3 WROOM
- SHT31 temperature and humidity sensor module
- Jumper wires

**What it measures:**
- Temperature (°C)
- Relative humidity (%)

**Update interval:** 30 seconds

**Alerts:** Hourly temperature and humidity report via Telegram in our test setup.